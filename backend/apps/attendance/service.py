from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.academics.access import Conflict, school
from apps.academics.models import ClassSubject
from apps.accounts.access import permission_codes, require
from apps.accounts.authentication import audit
from apps.admissions.models import StudentEnrollment

from .access import BROAD, group_allowed
from .models import (
    AttendanceCorrection,
    AttendanceHoliday,
    AttendanceRecord,
    AttendanceSession,
    AttendanceSettings,
)


def policy():
    institution = school()
    return AttendanceSettings.objects.filter(institution=institution).first() or AttendanceSettings(
        institution=institution
    )


def today():
    try:
        zone = ZoneInfo(school().timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise serializers.ValidationError(
            "The institution timezone must be configured correctly."
        ) from exc
    return timezone.localdate(timezone=zone)


def eligible(session, day):
    selected = StudentEnrollment.objects.filter(
        session=session,
        student__admission_date__lte=day,
        enrollment_date__lte=day,
    ).filter(Q(ended_on__isnull=True) | Q(ended_on__gt=day))
    latest = (
        selected.filter(student=OuterRef("student_id"))
        .order_by("-enrollment_date", "-created_at", "-pk")
        .values("pk")[:1]
    )
    return selected.filter(pk=Subquery(latest))


def section_roster(values):
    return (
        eligible(values["session"], values["date"])
        .filter(
            academic_class=values["academic_class"],
            section=values.get("section"),
        )
        .select_related("student")
        .order_by("roll_number", "student__admission_number", "pk")
    )


def working_day(day, settings):
    entry = AttendanceHoliday.objects.filter(institution=settings.institution, date=day).first()
    return entry.kind == "working" if entry else day.weekday() not in settings.non_teaching_weekdays


def assignment_for(session, academic_class, subject):
    rows = ClassSubject.objects.filter(academic_class=academic_class, subject=subject)
    return rows.filter(session=session).first() or rows.filter(session__isnull=True).first()


def validate_group(values):
    institution = school()
    session, academic_class = values["session"], values["academic_class"]
    section, subject = values.get("section"), values.get("subject")
    if (
        session.institution_id != institution.pk
        or academic_class.institution_id != institution.pk
        or (section and section.academic_class_id != academic_class.pk)
        or (subject and subject.institution_id != institution.pk)
    ):
        raise serializers.ValidationError(
            "Choose a valid session, class and section from this institution."
        )
    if subject:
        assignment = assignment_for(session, academic_class, subject)
        if not assignment or not assignment.active:
            raise serializers.ValidationError(
                {"subject": "This subject is not assigned to the selected class and session."}
            )


def validate_day(values):
    day, session = values["date"], values["session"]
    if not session.start_date <= day <= session.end_date or day > today():
        raise serializers.ValidationError(
            {"date": "Choose a date within the session and on or before today."}
        )


def register_key(values):
    return {
        key: values.get(key, "" if key == "period" else None)
        for key in ("session", "academic_class", "section", "date", "mode", "subject", "period")
    }


def available_roster(values):
    from apps.timetables.service import matching_occurrence

    rows = section_roster(values)
    lesson = matching_occurrence(school(), values)
    if lesson and lesson[0].group_id:
        rows = rows.filter(pk__in=lesson[0].group.enrollments.values("pk"))
    if values["mode"] == "daily":
        rows = rows.exclude(
            student_id__in=AttendanceRecord.objects.filter(
                session=values["session"],
                date=values["date"],
                mode="daily",
            ).values("student_id")
        )
    return rows


def create_register(values, request):
    if not group_allowed(request.user, values):
        raise PermissionDenied("This attendance group is outside your teaching assignments.")
    key = register_key(values)
    existing = AttendanceSession.objects.filter(**key).first()
    if existing:
        return existing, False
    validate_group(values)
    validate_day(values)
    config = policy()
    override = values.get("calendar_override", "")
    if not working_day(values["date"], config):
        require(request.user, "accounts.override_attendance_calendar")
        if not override:
            raise serializers.ValidationError(
                {"calendar_override": "Give a reason to open a non-teaching day."}
            )
    if override:
        require(request.user, "accounts.override_attendance_calendar")
    roster = list(available_roster(values))
    if not roster:
        raise serializers.ValidationError(
            "No eligible unreserved students match the selected attendance group."
        )
    from apps.timetables.service import attendance_snapshot

    register = AttendanceSession.objects.create(
        **values,
        schedule_snapshot=attendance_snapshot(
            school(), values, request.user, BROAD in permission_codes(request.user)
        ),
        late_attended=config.late_attended,
        excused_policy=config.excused_policy,
        recorded_by=request.user,
    )
    AttendanceRecord.objects.bulk_create(
        [
            AttendanceRecord(
                register=register,
                student=row.student,
                enrollment=row,
                session=register.session,
                date=register.date,
                mode=register.mode,
                roll_number=row.roll_number,
            )
            for row in roster
        ]
    )
    audit(
        request,
        "ATTENDANCE_CREATED",
        "attendance",
        register,
        eligible=len(roster),
        mode=register.mode,
        calendar_override=bool(override),
    )
    return register, True


def check_version(register, version):
    if register.version != version:
        raise Conflict("This register changed. Reload it before saving.")


def mark(record, status, remarks, user, now):
    if (record.status, record.remarks) == (status, remarks):
        return False
    if record.recorded_at is None and status != "unmarked":
        record.recorded_at, record.recorded_by = now, user
    record.status, record.remarks, record.updated_by = status, remarks, user
    record.save(
        update_fields=[
            "status",
            "remarks",
            "recorded_at",
            "recorded_by",
            "updated_by",
            "updated_at",
        ]
    )
    return True


def bump(register):
    register.version += 1
    register.save(update_fields=["version", "updated_at"])


def save_marks(register, data, request):
    if register.status != "draft":
        raise Conflict("A finalized register requires an audited correction.")
    check_version(register, data["version"])
    items = data["marks"]
    records = {
        row.pk: row for row in register.records.filter(pk__in=[item["record"] for item in items])
    }
    if len(records) != len(items):
        raise serializers.ValidationError(
            "Each mark must reference one distinct record in this register."
        )
    now = timezone.now()
    changed = sum(
        mark(records[item["record"]], item["status"], item.get("remarks", ""), request.user, now)
        for item in items
    )
    if changed:
        bump(register)
        audit(request, "ATTENDANCE_DRAFT_UPDATED", "attendance", register, changed=changed)


def finalize(register, data, request):
    if register.status == "finalized":
        return
    check_version(register, data["version"])
    missing = register.records.filter(status="unmarked").count()
    if missing and not data.get("acknowledge_unmarked"):
        raise serializers.ValidationError("Acknowledge the unmarked students before finalizing.")
    register.status, register.finalized_at, register.finalized_by = (
        "finalized",
        timezone.now(),
        request.user,
    )
    register.version += 1
    register.save(update_fields=["status", "finalized_at", "finalized_by", "version", "updated_at"])
    audit(request, "ATTENDANCE_FINALIZED", "attendance", register, unmarked=missing)


def correct(register, data, request):
    if register.status != "finalized":
        raise Conflict("Finalize the register before making a correction.")
    check_version(register, data["version"])
    record = register.records.filter(pk=data["record"]).first()
    if not record:
        raise serializers.ValidationError("Choose a student in this register.")
    leave = (
        approved_for(register).filter(student_id=record.student_id).first()
        if data.get("use_leave")
        else None
    )
    if data.get("use_leave") and not leave:
        raise serializers.ValidationError("No approved leave covers this student on that date.")
    status = "excused" if leave else data["status"]
    remarks = data.get("remarks", record.remarks)
    previous = (record.status, record.remarks)
    if not mark(record, status, remarks, request.user, timezone.now()):
        return
    correction = AttendanceCorrection.objects.create(
        record=record,
        previous_status=previous[0],
        previous_remarks=previous[1],
        status=status,
        remarks=remarks,
        actor=request.user,
        reason=data["reason"],
        leave=leave,
    )
    bump(register)
    audit(
        request,
        "ATTENDANCE_CORRECTED",
        "attendance",
        register,
        correction_id=str(correction.pk),
        previous_status=previous[0],
        status=status,
        leave_reconciliation=bool(leave),
    )


def approved_for(register):
    from .models import StudentLeaveRequest

    return StudentLeaveRequest.objects.filter(
        session=register.session,
        status="approved",
        start_date__lte=register.date,
        end_date__gte=register.date,
    )

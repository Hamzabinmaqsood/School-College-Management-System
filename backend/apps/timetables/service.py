from copy import copy
from datetime import timedelta

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.academics.models import ClassSubject
from apps.admissions.models import StudentEnrollment
from apps.attendance.models import AttendanceHoliday, TeachingAssignment
from apps.hr.models import EmployeeAttendance, EmployeeLeave, EmploymentContract

from . import models


def overlaps(a, b, c, d):
    return a < d and c < b


def first_on(day, weekday):
    return day + timedelta(days=(weekday - day.weekday()) % 7)


def last_on(day, weekday):
    return day - timedelta(days=(day.weekday() - weekday) % 7)


def end_of(version):
    if version.superseded_on:
        return min(version.effective_end, version.superseded_on - timedelta(days=1))
    return version.effective_end


def published(institution, start, end):
    return models.Version.objects.filter(
        plan__institution=institution,
        status="published",
        effective_start__lte=end,
        effective_end__gte=start,
    ).filter(Q(superseded_on__isnull=True) | Q(superseded_on__gt=start))


def validate_version_bounds(plan, start, end):
    if not plan.session.start_date <= start <= end <= plan.session.end_date:
        raise ValidationError("Timetable dates must be ordered and inside the academic session.")


def eligible_assignments(plan, subject, start, end):
    return TeachingAssignment.objects.filter(
        session=plan.session,
        academic_class=plan.section.academic_class,
        user__is_active=True,
        active=True,
    ).filter(
        Q(section=plan.section) | Q(section__isnull=True),
        Q(subject=subject) | Q(subject__isnull=True),
        Q(effective_start__isnull=True) | Q(effective_start__lte=start),
        Q(effective_end__isnull=True) | Q(effective_end__gte=end),
    )


def eligible(plan, subject, teacher, start, end):
    return eligible_assignments(plan, subject, start, end).filter(user=teacher).exists()


def unavailable(plan, teacher, weekday, period, start, end):
    blocked = models.Availability.objects.filter(
        institution=plan.institution,
        teacher=teacher,
        preference="hard",
        weekday=weekday,
        starts_at__lt=period.ends_at,
        ends_at__gt=period.starts_at,
        effective_start__lte=end,
        effective_end__gte=start,
    )
    return any(
        first_on(max(start, row.effective_start), weekday) <= min(end, row.effective_end)
        for row in blocked
    )


def preference_score(slot):
    start = slot.version.effective_start
    end = slot.version.effective_end
    preferences = models.Availability.objects.filter(
        institution=slot.version.plan.institution,
        teacher=slot.teacher,
        weekday=slot.weekday,
        starts_at__lt=slot.period.ends_at,
        ends_at__gt=slot.period.starts_at,
        effective_start__lte=end,
        effective_end__gte=start,
    ).exclude(preference="hard")
    return sum(
        (rule.priority if rule.preference == "prefer" else -rule.priority)
        for rule in preferences
        if first_on(max(start, rule.effective_start), slot.weekday) <= min(end, rule.effective_end)
    )


def curriculum_for(session, academic_class, subject):
    assignments = ClassSubject.objects.filter(academic_class=academic_class, subject=subject)
    return (
        assignments.filter(session=session).first()
        or assignments.filter(session__isnull=True).first()
    )


def eligible_group_members(group, start, end):
    return StudentEnrollment.objects.filter(session=group.session, section=group.section).filter(
        Q(enrollment_date__lte=start),
        Q(ended_on__gt=end) | Q(ended_on__isnull=True, status="active"),
    )


def validate_roster(group, version, start, end):
    anchor = group.effective_version
    if anchor and (
        anchor.plan_id != version.plan_id
        or start < anchor.effective_start
        or (anchor.pk != version.pk and anchor.status != "published")
    ):
        raise ValidationError("Select a roster effective for this timetable revision.")
    if (
        models.TeachingGroup.objects.filter(
            predecessor=group,
            effective_version__effective_start__lte=start,
        )
        .filter(Q(effective_version=version) | Q(effective_version__status="published"))
        .exists()
    ):
        raise ValidationError("Select the successor roster for this timetable revision.")
    if (
        anchor
        and group.enrollments.exclude(pk__in=eligible_group_members(group, start, end)).exists()
    ):
        raise ValidationError("Successor roster members must be enrolled for all lesson dates.")


def recurring_employment_issue(plan, teacher, period, start, end):
    from apps.hr.models import Employee

    if not Employee.objects.filter(user=teacher).exists():
        return False
    while start <= end:
        if working_date(plan, start) and staff_issue(teacher, start, period, recurring=True):
            return True
        start += timedelta(days=7)
    return False


def validate_slot(slot, start=None, end=None):
    plan = slot.version.plan
    period = slot.period
    start = start or first_on(slot.version.effective_start, slot.weekday)
    end = end or last_on(slot.version.effective_end, slot.weekday)
    if start > end or slot.weekday not in plan.shift.weekdays:
        raise ValidationError("Choose a working weekday in the version's effective dates.")
    if period.shift_id != plan.shift_id or not period.teaching:
        raise ValidationError("Choose a teaching period from the plan's shift.")
    curriculum = curriculum_for(plan.session, plan.section.academic_class, slot.subject)
    if not curriculum or not curriculum.active or not slot.subject.active:
        raise ValidationError("Choose an active subject from the class curriculum.")
    if slot.group_id:
        group = slot.group
        if curriculum.mandatory or (group.session_id, group.section_id, group.subject_id) != (
            plan.session_id,
            plan.section_id,
            slot.subject_id,
        ):
            raise ValidationError(
                "Choose the optional group for this session, section and subject."
            )
        validate_roster(group, slot.version, start, end)
        if not group.enrollments.exists():
            raise ValidationError("Add explicit memberships before scheduling the group.")
    elif not curriculum.mandatory:
        raise ValidationError("Choose an explicit teaching group for an optional subject.")
    if not eligible(plan, slot.subject, slot.teacher, start, end):
        raise ValidationError("The teacher needs an active assignment for all lesson dates.")
    if unavailable(plan, slot.teacher, slot.weekday, period, start, end):
        raise ValidationError("The teacher has hard unavailability during this lesson.")
    if recurring_employment_issue(plan, slot.teacher, period, start, end):
        raise ValidationError(
            "The teacher's employment or contract does not cover these lesson dates."
        )
    if slot.room_id:
        room = slot.room
        if room.institution_id != plan.institution_id or not room.active:
            raise ValidationError("Choose an active room from this institution.")
        settings = models.Settings.objects.filter(institution=plan.institution).first()
        if room.capacity is not None and (settings is None or settings.enforce_capacity):
            roster = StudentEnrollment.objects.filter(
                session=plan.session,
                section=plan.section,
                status="active",
            )
            if slot.group_id:
                roster = roster.filter(pk__in=slot.group.enrollments.values("pk"))
            if roster.count() > room.capacity:
                raise ValidationError(
                    "The room capacity is smaller than the active section roster."
                )


def conflict_kind(slot, other):
    if not overlaps(
        slot.period.starts_at, slot.period.ends_at, other.period.starts_at, other.period.ends_at
    ):
        return None
    if slot.version.plan.section_id == other.version.plan.section_id:
        if not slot.group_id or not other.group_id or slot.group_id == other.group_id:
            return "section"
        students = slot.group.enrollments.values("student_id")
        if other.group.enrollments.filter(student_id__in=students).exists():
            return "student group"
    if slot.teacher_id == other.teacher_id:
        return "teacher"
    if slot.room_id and slot.room_id == other.room_id:
        return "room"
    return None


def check_conflicts(slot):
    version = slot.version
    visible = published(version.plan.institution, version.effective_start, version.effective_end)
    peers = models.Entry.objects.filter(
        weekday=slot.weekday,
        version__in=visible.exclude(plan=version.plan),
    ) | models.Entry.objects.filter(version=version, weekday=slot.weekday)
    for other in peers.exclude(pk=slot.pk).select_related("period", "version__plan"):
        start = max(version.effective_start, other.version.effective_start)
        end = min(version.effective_end, end_of(other.version))
        if first_on(start, slot.weekday) <= end and (kind := conflict_kind(slot, other)):
            return kind
    changes = (
        models.Exception.objects.filter(
            Q(destination_version__in=visible.exclude(plan=version.plan))
            | Q(
                destination_version__isnull=True,
                entry__version__in=visible.exclude(plan=version.plan),
            )
        )
        .exclude(kind="cancelled")
        .filter(
            Q(destination_date__range=(version.effective_start, version.effective_end))
            | Q(
                destination_date__isnull=True,
                date__range=(version.effective_start, version.effective_end),
            )
        )
        .select_related(
            "entry__version__plan",
            "destination_version__plan",
            "destination_group",
            "entry__period",
            "entry__group",
            "entry__teacher",
            "entry__room",
            "period",
            "teacher",
            "room",
        )
    )
    for change in changes:
        date = change.destination_date or change.date
        actual_entry, period, teacher, room, _ = replacement(change, change.entry)
        if (
            date.weekday() != slot.weekday
            or date > end_of(actual_entry.version)
            or closure(version.plan.institution, date)
        ):
            continue
        actual = models.Entry(
            version=actual_entry.version,
            group=actual_entry.group,
            period=period,
            teacher=teacher,
            room=room,
        )
        if conflict := conflict_kind(slot, actual):
            return conflict
    return None


def staff_issue(teacher, date, period, *, recurring=False):
    from apps.hr.models import Employee

    staff = Employee.objects.filter(user=teacher).first()
    if staff and (
        staff.status not in {"active", "on_leave"}
        or date < staff.joined_on
        or bool(staff.ended_on and date > staff.ended_on)
    ):
        return "outside_employment_dates"
    if (
        not recurring
        and EmployeeLeave.objects.filter(
            employee__user=teacher,
            status="approved",
            start_date__lte=date,
            end_date__gte=date,
        ).exists()
    ):
        return "approved_leave"
    if (
        not recurring
        and EmployeeAttendance.objects.filter(
            employee__user=teacher, date=date, status="absent"
        ).exists()
    ):
        return "staff_absence"
    contract = (
        EmploymentContract.objects.filter(
            employee__user=teacher, active=True, start_date__lte=date, end_date__gte=date
        )
        .order_by("-start_date", "-pk")
        .first()
    )
    if staff and not contract and EmploymentContract.objects.filter(employee=staff).exists():
        return "outside_contract_dates"
    if contract:
        if contract.weekdays and date.weekday() not in contract.weekdays:
            return "outside_contract_hours"
        if (
            contract.shift_start
            and contract.shift_end
            and (
                contract.shift_start >= contract.shift_end
                or period.starts_at < contract.shift_start
                or period.ends_at > contract.shift_end
            )
        ):
            return "outside_contract_hours"
    return None


def closure(institution, date):
    return (
        AttendanceHoliday.objects.filter(institution=institution, date=date)
        .exclude(kind="working")
        .exists()
    )


def working_date(plan, date):
    return date.weekday() in plan.shift.weekdays and not closure(plan.institution, date)


def inactive(change, date):
    return bool(
        change
        and (
            change.kind == "cancelled"
            or (change.destination_date and change.destination_date != date)
        )
    )


def daily(institution, date):
    if closure(institution, date):
        return []
    versions = published(institution, date, date)
    entries = models.Entry.objects.filter(
        version__in=versions, weekday=date.weekday()
    ).select_related(
        "version__plan__section__academic_class",
        "version__plan__session",
        "period",
        "subject",
        "teacher",
        "room",
    )
    changes = models.Exception.objects.filter(
        Q(date=date, entry__in=entries)
        | Q(destination_date=date, destination_version__in=versions)
        | Q(destination_date=date, destination_version__isnull=True, entry__version__in=versions)
    ).select_related(
        "entry__version__plan__section__academic_class",
        "entry__version__plan__session",
        "destination_version__plan__section__academic_class",
        "destination_version__plan__session",
        "destination_group",
        "entry__period",
        "entry__subject",
        "entry__teacher",
        "entry__room",
        "period",
        "teacher",
        "room",
    )
    originals = {item.entry_id: item for item in changes if item.date == date}
    result = []
    for entry in entries:
        change = originals.get(entry.pk)
        if not change or inactive(change, date):
            result.append((entry, entry.period, entry.teacher, entry.room, change))
        else:
            result.append(replacement(change, entry))
    result.extend(
        replacement(item, item.entry)
        for item in changes
        if item.destination_date == date and item.date != date
    )
    return result


def replacement(change, entry):
    if change.destination_version_id:
        entry = copy(entry)
        entry.version = change.destination_version
        entry.group = change.destination_group
    return (
        entry,
        change.period or entry.period,
        change.teacher or entry.teacher,
        change.room or entry.room,
        change,
    )


def matching_occurrence(institution, values):
    if values["mode"] != "period" or not values.get("section"):
        return None
    for row in daily(institution, values["date"]):
        entry, period, _, _, change = row
        plan = entry.version.plan
        if (
            plan.session_id == values["session"].pk
            and plan.section_id == values["section"].pk
            and entry.subject_id == values["subject"].pk
            and period.code.casefold() == values["period"].casefold()
            and not inactive(change, values["date"])
        ):
            return row
    return None


def attendance_snapshot(institution, values, user, broad):
    row = matching_occurrence(institution, values)
    if not row:
        return {}
    entry, period, teacher, room, change = row
    if not broad and teacher.pk != user.pk:
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("The published timetable assigns this lesson to another teacher.")
    return {
        "entry": str(entry.pk),
        "version": str(entry.version_id),
        **(
            {"source_version": str(change.entry.version_id)}
            if change and change.destination_version_id
            else {}
        ),
        "group": str(entry.group_id) if entry.group_id else None,
        "exception": str(change.pk) if change else None,
        "teacher": str(teacher.pk),
        "room": str(room.pk) if room else None,
        "period": period.code,
        "original_date": change.date.isoformat() if change else values["date"].isoformat(),
        "starts_at": period.starts_at.isoformat(),
        "ends_at": period.ends_at.isoformat(),
    }


def subject_requirements(version):
    plan = version.plan
    counts = {}
    for subject in version.entries.values_list("subject_id", flat=True):
        counts[subject] = counts.get(subject, 0) + 1
    return [
        {
            "subject": row.subject_id,
            "subject_name": row.subject.name,
            "minimum": row.minimum,
            "maximum": row.maximum,
            "allocated": counts.get(row.subject_id, 0),
        }
        for row in models.SubjectRequirement.objects.filter(
            institution=plan.institution,
            session=plan.session,
            section=plan.section,
        ).select_related("subject")
    ]


def exam_conflict(slot, date):
    from apps.examinations.models import ExamSchedule

    plan = slot.version.plan
    scope = Q(subject__group__academic_class_id=plan.section.academic_class_id)
    if slot.room:
        scope |= Q(room__iexact=slot.room.name) | Q(room__iexact=slot.room.code)
    return (
        ExamSchedule.objects.filter(
            scope,
            subject__group__exam__institution=plan.institution,
            date=date,
            start_time__lt=slot.period.ends_at,
            end_time__gt=slot.period.starts_at,
        )
        .exclude(subject__group__exam__status="draft")
        .exists()
    )

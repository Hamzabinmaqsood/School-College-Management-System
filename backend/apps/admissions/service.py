from rest_framework import serializers

from apps.academics.access import school
from apps.accounts.authentication import audit
from apps.students.models import Student
from apps.students.service import policy

from .models import ProgressionEvent, StudentEnrollment

ARRIVALS = {
    "promote": "promoted",
    "repeat": "repeated",
    "transfer": "transferred",
    "re-enroll": None,
}
DEPARTURES = {
    "transfer-out": ("transferred_out", Student.Status.TRANSFERRED),
    "withdraw": ("withdrawn", Student.Status.WITHDRAWN),
    "graduate": ("graduated", Student.Status.GRADUATED),
}


def enroll(student, values):
    session, academic_class = values["session"], values["academic_class"]
    section = values.get("section")
    day = values["enrollment_date"]
    if (
        session.institution_id != school().pk
        or academic_class.institution_id != session.institution_id
    ):
        raise serializers.ValidationError("Select a session and class in this institution.")
    if session.status != "active" or not academic_class.active:
        raise serializers.ValidationError("New enrollment requires an active session and class.")
    if not session.start_date <= day <= session.end_date or day < student.admission_date:
        raise serializers.ValidationError(
            {"enrollment_date": "Select a date inside the session and after admission."}
        )
    active = StudentEnrollment.objects.filter(session=session, status="active")
    if active.filter(student=student).exists():
        raise serializers.ValidationError(
            "The student already has an active enrollment in this session."
        )
    if section:
        if section.academic_class_id != academic_class.pk or not section.active:
            raise serializers.ValidationError(
                {"section": "Choose an active section for this class."}
            )
        if section.capacity and active.filter(section=section).count() >= section.capacity:
            raise serializers.ValidationError(
                {"section": "This section is full for the selected session."}
            )
    elif not policy(create=False).allow_unsectioned:
        raise serializers.ValidationError({"section": "This institution requires a section."})
    roll = values.get("roll_number", "")
    if (
        roll
        and active.filter(academic_class=academic_class, section=section, roll_number=roll).exists()
    ):
        raise serializers.ValidationError(
            {"roll_number": "That roll number is already assigned in this group."}
        )
    return StudentEnrollment.objects.create(student=student, **values)


def progress(source, operation, day, target, request):
    student = source.student
    latest = student.enrollments.order_by("-enrollment_date", "-created_at", "-pk").first()
    if source.pk != latest.pk or day < (source.ended_on or source.enrollment_date):
        raise serializers.ValidationError(
            "Use the latest enrollment and a date on or after its last change."
        )
    if operation == "re-enroll":
        if (
            source.status not in {"withdrawn", "transferred_out", "graduated"}
            or student.status == "active"
        ):
            raise serializers.ValidationError("Only a departed student can be re-enrolled.")
    elif source.status != "active" or student.status != "active":
        raise serializers.ValidationError("This progression action requires an active enrollment.")
    successor = None
    if operation in ARRIVALS:
        if not target:
            raise serializers.ValidationError("Choose a target academic group.")
        session, academic_class = target["session"], target["academic_class"]
        if operation == "transfer" and (
            session.pk != source.session_id
            or academic_class.pk != source.academic_class_id
            or getattr(target.get("section"), "pk", None) == source.section_id
        ):
            raise serializers.ValidationError(
                "Select a different section in the same session and class."
            )
        if operation in {"promote", "repeat"}:
            if session.start_date <= source.session.start_date:
                raise serializers.ValidationError("Choose a later academic session.")
            if (academic_class.pk == source.academic_class_id) != (operation == "repeat"):
                raise serializers.ValidationError(
                    "Repeat retains the class. Promotion requires a different class."
                )
        ending, student_status = ARRIVALS[operation], Student.Status.ACTIVE
    else:
        if target:
            raise serializers.ValidationError("A departure does not accept a destination group.")
        ending, student_status = DEPARTURES[operation]
    if ending:
        source.status, source.ended_on = ending, day
        source.save(update_fields=["status", "ended_on", "updated_at"])
    if target:
        successor = enroll(student, target | {"enrollment_date": day})
    student.status = student_status
    student.save(update_fields=["status", "updated_at"])
    event = ProgressionEvent.objects.create(
        enrollment=source,
        successor=successor,
        action=operation,
        effective_date=day,
        actor=request.user,
    )
    audit(
        request,
        "ENROLLMENT_PROGRESSION",
        "studentenrollment",
        source,
        action_code=operation,
        progression_id=str(event.pk),
        successor_id=str(successor.pk) if successor else None,
    )
    return successor or source

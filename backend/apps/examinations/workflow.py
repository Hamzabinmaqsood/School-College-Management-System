from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.access import Conflict
from apps.accounts.access import permission_codes
from apps.accounts.authentication import audit
from apps.attendance.access import assignments_for, covered
from apps.attendance.service import eligible

from . import models
from .catalog import BROAD


def require_scope(user, component, section):
    group = component.subject.group
    if BROAD in permission_codes(user):
        return
    assignments = assignments_for(user, operational=True).filter(
        session=group.exam.session,
        academic_class=group.academic_class,
        section_id=section,
        subject=component.subject.subject,
    )
    if not covered(assignments, group.exam.start_date).exists():
        raise PermissionDenied("This assessment is outside your teaching assignments.")


def registration_defaults(enrollment):
    student = enrollment.student
    return {
        "student": student,
        "section": enrollment.section,
        "enrollment": enrollment,
        "details": {
            "student": f"{student.first_name} {student.last_name}".strip(),
            "admission": student.admission_number,
            "roll": enrollment.roll_number,
            "class": enrollment.academic_class.name,
            "section": enrollment.section.name if enrollment.section else "",
        },
    }


def snapshot(exam, request):
    for group in exam.groups.prefetch_related("subjects__components"):
        subjects = list(group.subjects.all())
        if not subjects:
            raise ValidationError("Every participating class needs configured subjects.")
        roster = (
            eligible(exam.session, exam.start_date)
            .filter(academic_class=group.academic_class)
            .select_related("student", "section", "academic_class")
        )
        for enrollment in roster:
            models.StudentExamRegistration.objects.get_or_create(
                group=group, student=enrollment.student, defaults=registration_defaults(enrollment)
            )
        registrations = list(
            group.registrations.filter(excluded=False).prefetch_related("optional_subjects")
        )
        if not registrations:
            raise ValidationError("Every participating class needs an eligible roster.")
        for subject in subjects:
            groups = {}
            for item in registrations:
                if not subject.optional or subject in item.optional_subjects.all():
                    groups.setdefault(item.section_id, []).append(item)
            for component in subject.components.all():
                for section, rows in groups.items():
                    submission = models.MarksSubmission.objects.create(
                        component=component, section_id=section
                    )
                    models.StudentAssessmentMark.objects.bulk_create(
                        [
                            models.StudentAssessmentMark(submission=submission, registration=row)
                            for row in rows
                        ]
                    )
    audit(request, "EXAM_ROSTER_FROZEN", "examination", exam)


def save(register, values, request):
    if register.status != "draft":
        raise Conflict("Only draft submissions may be edited.")
    check_version(register, values["version"])
    updates = {}
    for row in values["marks"]:
        identity = row["registration"]
        if identity in updates:
            raise ValidationError("Use each student once per save.")
        if row["obtained"] is not None and row["obtained"] > register.component.maximum:
            raise ValidationError("A score exceeds the component maximum.")
        updates[identity] = row
    marks = list(register.marks.filter(registration_id__in=updates))
    if len(marks) != len(updates):
        raise ValidationError("A student is outside the frozen roster.")
    for mark in marks:
        row = updates[mark.registration_id]
        mark.status, mark.obtained, mark.remarks = row["status"], row["obtained"], row["remarks"]
        mark.entered_by = mark.entered_by or request.user
        mark.updated_by = request.user
        mark.save(
            update_fields=[
                "status",
                "obtained",
                "remarks",
                "entered_by",
                "updated_by",
                "updated_at",
            ]
        )
    register.version += 1
    register.save(update_fields=["version", "updated_at"])
    audit(request, "EXAM_MARKS_SAVED", "markssubmission", register, count=len(marks))


def check_version(register, version):
    if register.version != version:
        raise Conflict("Marks changed since you loaded the roster. Refresh before editing.")

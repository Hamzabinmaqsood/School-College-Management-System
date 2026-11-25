from django.shortcuts import get_object_or_404

from apps.academics.access import school
from apps.accounts.access import require
from apps.accounts.authentication import audit

from .models import AdmissionNumberPolicy, Guardian, Student, StudentDocument, StudentGuardian


def policy(*, create=True):
    institution = school()
    if not create:
        return AdmissionNumberPolicy.objects.filter(
            institution=institution
        ).first() or AdmissionNumberPolicy(institution=institution)
    return AdmissionNumberPolicy.objects.get_or_create(institution=institution)[0]


def create_student(values):
    institution = school()
    if "admission_number" not in values:
        sequence = policy()
        while True:
            number = f"{sequence.prefix}-{sequence.next_number:0{sequence.padding}d}"
            sequence.next_number += 1
            if not Student.objects.filter(
                institution=institution, admission_number=number
            ).exists():
                break
        sequence.save(update_fields=["next_number", "updated_at"])
        values = values | {"admission_number": number}
    return Student.objects.create(institution=institution, **values)


def link_guardian(student, values, request):
    values = dict(values)
    if new := values.pop("new_guardian", None):
        require(request.user, "students.add_guardian")
        guardian = Guardian.objects.create(institution=student.institution, **new)
        values["guardian"] = guardian
        audit(request, "GUARDIAN_CREATED", "guardian", guardian)
    else:
        require(request.user, "students.view_guardian")
    if values.get("primary"):
        student.guardian_links.filter(primary=True).update(primary=False)
    link = StudentGuardian.objects.create(student=student, **values)
    audit(request, "GUARDIAN_LINKED", "student", student, link_id=str(link.pk))
    return link


def store_document(student, values, request):
    content = values["file"]
    document = StudentDocument.objects.create(
        student=student,
        kind=values["kind"],
        label=values["label"],
        content=content,
        size=len(content),
    )
    audit(request, "STUDENT_DOCUMENT_ADDED", "studentdocument", document, kind=document.kind)
    return document


def student_for(pk):
    return get_object_or_404(Student, pk=pk, institution=school())

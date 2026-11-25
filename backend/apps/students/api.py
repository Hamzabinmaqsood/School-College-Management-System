from typing import ClassVar

from django.db.models import Count, Exists, OuterRef, Prefetch
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.academics.access import RecordsView, school
from apps.academics.models import AcademicSession
from apps.accounts.access import permission_codes
from apps.accounts.authentication import audit
from apps.admissions.api import EnrollmentFields
from apps.admissions.models import StudentEnrollment

from .models import Guardian, Student, StudentDocument, StudentGuardian
from .reports import csv_download
from .serializers import GuardianFields, StudentFields
from .service import create_student


def cohort_params(request):
    return {
        key: serializers.UUIDField().run_validation(request.query_params[key])
        for key in ("session", "academic_class", "section")
        if request.query_params.get(key)
    }


def cohort(params):
    return (
        StudentEnrollment.objects.filter(**params)
        .select_related("academic_class", "session", "section")
        .order_by("-enrollment_date", "-created_at", "-pk")
    )


def name(student):
    return student.preferred_name or f"{student.first_name} {student.last_name}".strip()


def projected(student):
    enrollment = next(iter(getattr(student, "roster", [])), None)
    return {
        "id": str(student.pk),
        "admission_number": student.admission_number,
        "name": name(student),
        "admission_date": student.admission_date,
        "status": student.status,
        "class_name": enrollment.academic_class.name if enrollment else None,
        "section_name": enrollment.section.name if enrollment and enrollment.section else None,
        "roll_number": enrollment.roll_number if enrollment else None,
        "guardian": next(
            (link.guardian.full_name for link in getattr(student, "primary_links", [])), None
        ),
        "photo_url": next(
            (
                f"/api/v1/students/{student.pk}/documents/{item.pk}/preview/"
                for item in getattr(student, "portraits", [])
            ),
            None,
        ),
    }


class Students(RecordsView):
    queryset = Student.objects.all()
    serializer_class = StudentFields
    license_feature = "students"
    permission_map: ClassVar = {
        "list": "accounts.view_students",
        "create": "students.add_student",
        "retrieve": "accounts.view_student_details",
        "partial_update": ["students.change_student", "accounts.view_student_details"],
        "summary": "accounts.view_students",
        "history": ["accounts.view_student_details", "accounts.view_admissions"],
        "export": ["accounts.view_students", "accounts.export_students"],
        "enrollment_report": [
            "accounts.view_student_details",
            "accounts.view_admissions",
            "accounts.export_admissions",
        ],
        "print_profile": ["accounts.view_student_details", "accounts.print_students"],
    }
    search_fields = (
        "first_name",
        "last_name",
        "preferred_name",
        "admission_number",
        "registration_number",
    )
    filterset_fields = ("status",)
    ordering_fields = ("admission_number", "first_name", "admission_date")
    ordering = ("admission_number", "id")

    def get_queryset(self):
        query = super().get_queryset()
        if self.action not in {"list", "export"}:
            return query
        filters = cohort_params(self.request)
        roster = cohort(filters or {"session__is_current": True})
        if filters:
            query = query.filter(Exists(roster.filter(student=OuterRef("pk"))))
        query = query.prefetch_related(Prefetch("enrollments", queryset=roster, to_attr="roster"))
        if self.action == "list":
            permissions = permission_codes(self.request.user)
            if "students.view_guardian" in permissions:
                links = StudentGuardian.objects.filter(primary=True).select_related("guardian")
                query = query.prefetch_related(
                    Prefetch("guardian_links", queryset=links, to_attr="primary_links")
                )
            if "students.view_studentdocument" in permissions:
                photos = (
                    StudentDocument.objects.filter(kind="photo", archived_at__isnull=True)
                    .only("student_id", "id")
                    .order_by("-created_at")
                )
                query = query.prefetch_related(
                    Prefetch("documents", queryset=photos, to_attr="portraits")
                )
        return query

    def list(self, request, *args, **kwargs):
        records = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(records)
        return self.get_paginated_response([projected(record) for record in page])

    def create(self, request, *args, **kwargs):
        def save():
            form = self.get_serializer(data=request.data)
            form.is_valid(raise_exception=True)
            student = create_student(form.validated_data)
            audit(request, "STUDENT_CREATED", "student", student)
            return Response(self.get_serializer(student).data, status=201)

        return self.write(save)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        students = self.get_queryset()
        institution = school()
        current = AcademicSession.objects.filter(institution=institution, is_current=True).first()
        active = StudentEnrollment.objects.filter(
            session=current, student__institution=institution, status="active"
        )
        new_students = (
            students.filter(
                Exists(StudentEnrollment.objects.filter(session=current, student=OuterRef("pk"))),
                admission_date__range=(current.start_date, current.end_date),
            ).count()
            if current
            else 0
        )
        distribution = (
            active.values("academic_class_id", "academic_class__name")
            .annotate(count=Count("id"))
            .order_by("academic_class__name")
        )
        return Response(
            {
                "total_students": students.count(),
                "active_students": students.filter(status="active").count(),
                "session_name": current.name if current else None,
                "current_enrollments": active.count(),
                "new_admissions": new_students,
                "class_distribution": list(distribution),
            }
        )

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        rows = cohort({"student": self.get_object()})
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(EnrollmentFields(page, many=True).data)

    @action(detail=True, methods=["get"], url_path="print")
    def print_profile(self, request, pk=None):
        student = self.get_object()
        return Response(self.get_serializer(student).data, headers={"Cache-Control": "no-store"})

    @action(detail=False, methods=["get"])
    def export(self, request):
        rows = (
            projected(record)
            for record in self.filter_queryset(self.get_queryset()).iterator(chunk_size=200)
        )
        keys = (
            "admission_number",
            "name",
            "class_name",
            "section_name",
            "roll_number",
            "admission_date",
            "status",
        )
        return csv_download(
            "students",
            ("Admission number", "Student", "Class", "Section", "Roll", "Admission date", "Status"),
            ((item[key] for key in keys) for item in rows),
        )

    @action(detail=True, methods=["get"], url_path="enrollment-report")
    def enrollment_report(self, request, pk=None):
        rows = cohort({"student": self.get_object()})
        return csv_download(
            "enrollment-history",
            ("Session", "Class", "Section", "Roll", "Date", "Ended", "Status"),
            (
                (
                    row.session.name,
                    row.academic_class.name,
                    row.section.name if row.section else "",
                    row.roll_number,
                    row.enrollment_date,
                    row.ended_on,
                    row.status,
                )
                for row in rows.iterator()
            ),
        )


class Guardians(RecordsView):
    queryset = Guardian.objects.all()
    serializer_class = GuardianFields
    license_feature = "students"
    permission_map: ClassVar = {
        "list": "students.view_guardian",
        "retrieve": "students.view_guardian",
        "create": "students.add_guardian",
        "partial_update": "students.change_guardian",
    }
    search_fields = ("full_name", "phone", "email")
    ordering = ("full_name", "id")

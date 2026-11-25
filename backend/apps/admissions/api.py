import json
from typing import ClassVar

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.academics.access import RecordsView
from apps.academics.models import AcademicClass, AcademicSession, Section
from apps.accounts.access import require
from apps.accounts.authentication import audit
from apps.students.serializers import DocumentInput, GuardianChoice, StudentFields
from apps.students.service import create_student, link_guardian, store_document

from .models import StudentEnrollment
from .service import enroll, progress


class GroupInput(serializers.Serializer):
    session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.all())
    academic_class = serializers.PrimaryKeyRelatedField(queryset=AcademicClass.objects.all())
    section = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(), allow_null=True, required=False
    )
    roll_number = serializers.RegexField(
        r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$", required=False, allow_blank=True
    )

    def validate_roll_number(self, value):
        return value.upper()


class AdmissionInput(serializers.Serializer):
    student = StudentFields()
    enrollment = GroupInput()
    guardians = GuardianChoice(many=True, required=False, max_length=10)
    documents = serializers.ListField(child=serializers.DictField(), max_length=6, required=False)

    def validate_guardians(self, values):
        if sum(link["primary"] for link in values) > 1:
            raise serializers.ValidationError("Choose at most one primary guardian.")
        ids = [link["guardian"].pk for link in values if link.get("guardian")]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("A guardian may be linked only once.")
        return values


class ProgressInput(serializers.Serializer):
    effective_date = serializers.DateField()
    target = GroupInput(required=False, allow_null=True)


class EnrollmentFields(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.first_name", read_only=True)
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    session_name = serializers.CharField(source="session.name", read_only=True)
    class_name = serializers.CharField(source="academic_class.name", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True, default=None)
    transitions = serializers.SerializerMethodField()

    class Meta:
        model = StudentEnrollment
        fields = (
            "id",
            "student",
            "student_name",
            "admission_number",
            "session",
            "session_name",
            "academic_class",
            "class_name",
            "section",
            "section_name",
            "roll_number",
            "enrollment_date",
            "status",
            "ended_on",
            "transitions",
            "created_at",
            "updated_at",
        )

    def get_transitions(self, enrollment):
        return list(enrollment.progression.values("action", "effective_date", "successor_id"))


def read_documents(request, attachments):
    documents, used = [], set()
    if attachments:
        require(request.user, "students.add_studentdocument")
    for item in attachments:
        field = item.get("field")
        if not isinstance(field, str) or field in used or field not in request.FILES:
            raise serializers.ValidationError(
                "Each selected document must have exactly one upload."
            )
        used.add(field)
        upload = DocumentInput(
            data={
                "kind": item.get("kind"),
                "label": item.get("label"),
                "file": request.FILES[field],
            }
        )
        upload.is_valid(raise_exception=True)
        documents.append(upload.validated_data)
    if used != set(request.FILES) or any(len(request.FILES.getlist(key)) != 1 for key in used):
        raise serializers.ValidationError("File uploads and document references must match.")
    return documents


class Admissions(RecordsView):
    queryset = StudentEnrollment.objects.select_related(
        "student", "academic_class", "session", "section"
    )
    serializer_class = EnrollmentFields
    institution_lookup = "student__institution"
    http_method_names = ("get", "post", "head", "options")
    license_feature = "admissions"
    permission_map: ClassVar = {
        "list": "accounts.view_admissions",
        "retrieve": "accounts.view_admissions",
        "create": ["admissions.add_studentenrollment", "students.add_student"],
        "progression": ["accounts.progress_students", "accounts.view_admissions"],
        "export": ["accounts.view_admissions", "accounts.export_admissions"],
    }
    filterset_fields = ("session", "academic_class", "section", "student", "status")
    search_fields = (
        "student__first_name",
        "student__last_name",
        "student__admission_number",
        "roll_number",
    )
    ordering_fields = ("enrollment_date", "student__admission_number", "roll_number")
    ordering = ("-enrollment_date", "-created_at", "id")

    def get_license_features(self):
        return ("admissions", "students") if self.action == "create" else ("admissions",)

    def create(self, request, *args, **kwargs):
        return self.write(self.admit, request)

    def admit(self, request):
        data = request.data
        if "payload" in data:
            try:
                data = json.loads(data["payload"])
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError("Invalid admission form.") from exc
        form = AdmissionInput(data=data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        guardians = values.get("guardians", [])
        if guardians:
            require(request.user, "accounts.manage_guardian_links")
        documents = read_documents(request, values.get("documents", []))
        student = create_student(values["student"])
        audit(request, "STUDENT_CREATED", "student", student)
        enrollment = enroll(
            student, values["enrollment"] | {"enrollment_date": student.admission_date}
        )
        for guardian in guardians:
            link_guardian(student, guardian, request)
        for document in documents:
            store_document(student, document, request)
        audit(request, "STUDENT_ADMITTED", "studentenrollment", enrollment)
        return Response(self.get_serializer(enrollment).data, status=201)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"(?P<operation>promote|repeat|transfer|transfer-out|withdraw|graduate|re-enroll)",
    )
    def progression(self, request, pk=None, operation=None):
        def change():
            form = ProgressInput(data=request.data)
            form.is_valid(raise_exception=True)
            result = progress(
                self.get_object(),
                operation,
                form.validated_data["effective_date"],
                form.validated_data.get("target"),
                request,
            )
            return Response(self.get_serializer(result).data)

        return self.write(change)

    @action(detail=False, methods=["get"])
    def export(self, request):
        from apps.students.reports import csv_download

        rows = self.filter_queryset(self.get_queryset())
        return csv_download(
            "admission-register",
            (
                "Admission number",
                "Student",
                "Session",
                "Class",
                "Section",
                "Roll",
                "Date",
                "Status",
            ),
            (
                (
                    row.student.admission_number,
                    f"{row.student.first_name} {row.student.last_name}",
                    row.session.name,
                    row.academic_class.name,
                    row.section.name if row.section else "",
                    row.roll_number,
                    row.enrollment_date,
                    row.status,
                )
                for row in rows.iterator()
            ),
        )

from typing import ClassVar

from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.authentication import audit

from .access import RecordsView, school
from .models import AcademicClass, AcademicSession, ClassSubject, Section, Subject

BASE_FIELDS = ("id", "name", "code", "created_at", "updated_at")


class NamedFields(serializers.ModelSerializer):
    def validate_code(self, code):
        return code.upper()


class SessionFields(NamedFields):
    class Meta:
        model = AcademicSession
        fields = (*BASE_FIELDS, "start_date", "end_date", "status", "is_current")
        read_only_fields = ("is_current",)

    def validate(self, attrs):
        instance = self.instance
        if (
            instance
            and instance.status == "closed"
            and any(
                key in attrs and attrs[key] != getattr(instance, key)
                for key in ("status", "start_date", "end_date")
            )
        ):
            raise serializers.ValidationError(
                "Closed session dates and status are retained for history."
            )
        if instance and instance.status == "active" and attrs.get("status") == "planned":
            raise serializers.ValidationError(
                {"status": "An active session may remain active or be closed."}
            )
        start = attrs.get("start_date", getattr(instance, "start_date", None))
        end = attrs.get("end_date", getattr(instance, "end_date", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_date": "End date must follow the start date."})
        if (
            instance
            and instance.studentenrollment_set.exclude(enrollment_date__range=(start, end)).exists()
        ):
            raise serializers.ValidationError(
                "Session dates must contain the existing enrollments."
            )
        return attrs


class ClassFields(NamedFields):
    class Meta:
        model = AcademicClass
        fields = (*BASE_FIELDS, "category", "display_order", "active")


class SectionFields(NamedFields):
    class_name = serializers.CharField(source="academic_class.name", read_only=True)
    capacity = serializers.IntegerField(
        min_value=1, max_value=10000, allow_null=True, required=False
    )

    class Meta:
        model = Section
        fields = (*BASE_FIELDS, "academic_class", "class_name", "capacity", "active")

    def validate_academic_class(self, value):
        if value.institution_id != school().pk or (
            self.instance and value.pk != self.instance.academic_class_id
        ):
            raise serializers.ValidationError("Choose the original class in this institution.")
        return value

    def validate_capacity(self, capacity):
        if (
            self.instance
            and capacity
            and self.instance.studentenrollment_set.filter(
                status="active", session__status="active"
            ).exists()
        ):
            from django.db.models import Count

            counts = (
                self.instance.studentenrollment_set.filter(
                    status="active", session__status="active"
                )
                .values("session")
                .annotate(total=Count("id"))
            )
            if counts.filter(total__gt=capacity).exists():
                raise serializers.ValidationError("Capacity is below an existing session roster.")
        return capacity


class SubjectFields(NamedFields):
    class Meta:
        model = Subject
        fields = (*BASE_FIELDS, "description", "active")


class AssignmentFields(serializers.ModelSerializer):
    class_name = serializers.CharField(source="academic_class.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    session_name = serializers.CharField(source="session.name", read_only=True, default=None)

    class Meta:
        model = ClassSubject
        fields = (
            "id",
            "academic_class",
            "class_name",
            "subject",
            "subject_name",
            "session",
            "session_name",
            "mandatory",
            "active",
            "created_at",
            "updated_at",
        )

    def validate(self, values):
        institution = school().pk
        for key in ("academic_class", "subject", "session"):
            value = values.get(key, getattr(self.instance, key, None))
            if value and value.institution_id != institution:
                raise serializers.ValidationError({key: "Choose a record from this institution."})
            if self.instance and key in values and value != getattr(self.instance, key):
                raise serializers.ValidationError(
                    {key: "Create a new assignment to change its subject, class or session."}
                )
        return values


class Sessions(RecordsView):
    queryset = AcademicSession.objects.all()
    serializer_class = SessionFields
    permission_map: ClassVar = {
        "list": "accounts.view_sessions",
        "retrieve": "accounts.view_sessions",
        "create": "academics.add_academicsession",
        "partial_update": "academics.change_academicsession",
        "set_current": "academics.change_academicsession",
    }
    filterset_fields = ("status", "is_current")
    search_fields = ("name", "code")
    ordering_fields = ("name", "start_date", "end_date")
    ordering = ("-start_date", "id")

    def perform_update(self, serializer):
        instance = serializer.instance
        if (
            instance.is_current
            and serializer.validated_data.get("status", instance.status) != "active"
        ):
            instance.is_current = False
        super().perform_update(serializer)

    @action(detail=True, methods=["post"], url_path="set-current")
    @transaction.atomic
    def set_current(self, request, pk=None):
        school(lock=True)
        instance = self.get_object()
        if instance.status != "active":
            raise serializers.ValidationError("Only an active session can be current.")
        self.get_queryset().filter(is_current=True).exclude(pk=instance.pk).update(is_current=False)
        instance.is_current = True
        instance.save(update_fields=["is_current", "updated_at"])
        audit(request, "SESSION_CURRENT_CHANGED", "academicsession", instance)
        return Response(self.get_serializer(instance).data)


class Classes(RecordsView):
    queryset = AcademicClass.objects.all()
    serializer_class = ClassFields
    permission_map: ClassVar = {
        "list": "accounts.view_classes",
        "retrieve": "accounts.view_classes",
        "create": "academics.add_academicclass",
        "partial_update": "academics.change_academicclass",
    }
    filterset_fields = ("active", "category")
    search_fields = ("name", "code", "category")
    ordering_fields = ("name", "display_order", "code")
    ordering = ("display_order", "name", "id")


class Sections(RecordsView):
    queryset = Section.objects.select_related("academic_class")
    serializer_class = SectionFields
    institution_lookup = "academic_class__institution"
    permission_map: ClassVar = {
        "list": "accounts.view_sections",
        "retrieve": "accounts.view_sections",
        "create": "academics.add_section",
        "partial_update": "academics.change_section",
    }
    filterset_fields = ("academic_class", "active")
    search_fields = ("name", "code", "academic_class__name")
    ordering_fields = ("name", "code")
    ordering = ("academic_class__display_order", "name", "id")


class Subjects(RecordsView):
    queryset = Subject.objects.all()
    serializer_class = SubjectFields
    permission_map: ClassVar = {
        "list": "accounts.view_subjects",
        "retrieve": "accounts.view_subjects",
        "create": "academics.add_subject",
        "partial_update": "academics.change_subject",
    }
    filterset_fields = ("active",)
    search_fields = ("name", "code")
    ordering_fields = ("name", "code")
    ordering = ("name", "id")


class Assignments(RecordsView):
    queryset = ClassSubject.objects.select_related("academic_class", "subject", "session")
    serializer_class = AssignmentFields
    institution_lookup = "academic_class__institution"
    permission_map: ClassVar = {
        "list": "academics.view_classsubject",
        "retrieve": "academics.view_classsubject",
        "create": "academics.add_classsubject",
        "partial_update": "academics.change_classsubject",
    }
    filterset_fields = ("academic_class", "subject", "session", "mandatory", "active")
    search_fields = ("academic_class__name", "subject__name", "session__name")
    ordering = ("academic_class__display_order", "subject__name", "id")

from datetime import timedelta
from typing import ClassVar

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.accounts.authentication import audit
from apps.attendance.models import TeachingAssignment
from apps.attendance.serializers import AssignmentFields
from apps.audit.models import AuditEvent
from apps.students.serializers import DocumentInput

from . import models
from .api import Employees, HRView, input_data, schema, today


class EmployeeAssignments(Employees):
    permission_map: ClassVar = Employees.permission_map | {
        "assignments": "accounts.view_teachers",
        "assignment_history": ("accounts.view_teachers", "accounts.manage_teaching_assignments"),
        "assign": ("accounts.view_teachers", "accounts.manage_teaching_assignments"),
        "assignment_dates": ("accounts.view_teachers", "accounts.manage_teaching_assignments"),
        "deactivate_assignment": ("accounts.view_teachers", "accounts.manage_teaching_assignments"),
    }

    @action(detail=True, methods=["get"])
    def assignments(self, request, pk=None):
        row = self.get_object()
        assignments = TeachingAssignment.objects.filter(user_id=row.user_id) if row.user_id else []
        return Response(AssignmentFields(assignments, many=True).data)

    @action(detail=True, methods=["get"], url_path="assignment-history")
    def assignment_history(self, request, pk=None):
        employee = self.get_object()
        identifier = serializers.UUIDField().run_validation(request.query_params.get("assignment"))
        if not employee.user_id:
            raise ValidationError("This employee has no linked account.")
        assignment = get_object_or_404(
            TeachingAssignment,
            pk=identifier,
            user_id=employee.user_id,
            session__institution=employee.institution,
        )
        events = (
            AuditEvent.objects.filter(
                resource_type="teachingassignment", resource_id=str(assignment.pk)
            )
            .order_by("-timestamp", "-pk")
            .values(
                "id",
                "timestamp",
                "action",
                "acting_user__username",
                "sanitized_metadata",
            )
        )
        return self.get_paginated_response(self.paginate_queryset(events))

    @assignments.mapping.post
    def assign(self, request, pk=None):
        def operation():
            row = self.get_object()
            if (
                not row.user_id
                or not row.designation.teaching
                or row.status not in ("active", "on_leave")
            ):
                raise ValidationError(
                    "Link an active teaching employee to an existing account first."
                )
            form = AssignmentFields(data={**request.data, "user": row.user_id})
            form.is_valid(raise_exception=True)
            assignment = form.save()
            audit(request, "HR_TEACHING_ASSIGNMENT_CREATED", "teachingassignment", assignment)
            return Response(form.data, status=201)

        return self.write(operation)

    @action(detail=True, methods=["patch"], url_path="assignment-dates")
    def assignment_dates(self, request, pk=None):
        def operation():
            row = self.get_object()
            key = serializers.UUIDField().run_validation(request.data.get("assignment"))
            assignment = get_object_or_404(TeachingAssignment, pk=key, user_id=row.user_id)
            dates = ("effective_start", "effective_end")
            before = AssignmentFields(assignment).data
            changes = {key: request.data[key] for key in dates if key in request.data}
            form = AssignmentFields(assignment, data=changes, partial=True)
            form.is_valid(raise_exception=True)
            form.save()
            audit(
                request,
                "HR_TEACHING_ASSIGNMENT_DATES_UPDATED",
                "teachingassignment",
                assignment,
                before={key: before[key] for key in dates},
                after={key: form.data[key] for key in dates},
            )
            return Response(form.data)

        return self.write(operation)

    @action(detail=True, methods=["post"], url_path="deactivate-assignment")
    def deactivate_assignment(self, request, pk=None):
        def operation():
            row = self.get_object()
            if not row.user_id:
                raise ValidationError("This employee has no linked account.")
            key = serializers.UUIDField().run_validation(request.data.get("assignment"))
            assignment = get_object_or_404(TeachingAssignment, pk=key, user_id=row.user_id)
            assignment.active = False
            assignment.save(update_fields=["active", "updated_at"])
            audit(request, "HR_TEACHING_ASSIGNMENT_DEACTIVATED", "teachingassignment", assignment)
            return Response(AssignmentFields(assignment).data)

        return self.write(operation)


class Upload(serializers.Serializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=models.Employee.objects.all())
    label = serializers.CharField(max_length=120)
    kind = serializers.SlugField(max_length=40)
    file = serializers.FileField(write_only=True)

    validate_file = DocumentInput.validate_file


class Documents(HRView):
    queryset = models.EmployeeDocument.objects.defer("content")
    institution_lookup = "employee__institution"
    serializer_class = schema(models.EmployeeDocument, ("content", "uploaded_by"))
    filterset_fields = ("employee", "kind")
    permission_map: ClassVar = {
        "list": "accounts.view_employee_documents",
        "retrieve": "accounts.view_employee_documents",
        "download": "accounts.view_employee_documents",
        "create": "accounts.manage_employee_documents",
        "archive": "accounts.manage_employee_documents",
        "retention": "accounts.manage_employee_documents",
        "due": "accounts.manage_employee_documents",
        "reviews": "accounts.view_employee_documents",
    }

    def create(self, request, *args, **kwargs):
        def operation():
            data = input_data(Upload, request)
            content = data.pop("file")
            settings = models.HRSettings.objects.filter(
                institution=data["employee"].institution
            ).first()
            days = (
                settings.document_retention_by_kind.get(
                    data["kind"], settings.document_retention_days
                )
                if settings
                else None
            )
            row = models.EmployeeDocument.objects.create(
                review_on=today() + timedelta(days=days) if days else None,
                **data,
                content=content,
                size=len(content),
                uploaded_by=request.user,
            )
            audit(request, "HR_DOCUMENT_UPLOADED", "employeedocument", row)
            return Response(self.get_serializer(row).data, status=201)

        return self.write(operation)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        row = self.get_object()
        audit(request, "HR_DOCUMENT_DOWNLOADED", "employeedocument", row)
        return HttpResponse(
            bytes(row.content),
            content_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="employee-document-{row.pk}.png"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        def operation():
            row = self.get_object()
            if row.retention_hold:
                raise ValidationError("Release the retention hold before archiving.")
            if not row.archived_at:
                row.archived_at = timezone.now()
                row.save(update_fields=["archived_at", "updated_at"])
                audit(request, "HR_DOCUMENT_ARCHIVED", "employeedocument", row)
            return Response(self.get_serializer(row).data)

        return self.write(operation)

    @action(detail=False, methods=["get"])
    def due(self, request):
        rows = (
            self.filter_queryset(self.get_queryset())
            .filter(archived_at__isnull=True, review_on__lte=today())
            .order_by("review_on", "pk")
        )
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def reviews(self, request, pk=None):
        rows = self.get_object().reviews.order_by("-created_at")
        page = self.paginate_queryset(rows)
        output = schema(models.DocumentRetentionReview, ("document",))
        return self.get_paginated_response(output(page, many=True).data)

    @action(detail=True, methods=["post"])
    def retention(self, request, pk=None):
        def operation():
            row = self.get_object()
            action_name = serializers.ChoiceField(("extend", "hold", "release")).run_validation(
                request.data.get("operation")
            )
            reason = serializers.CharField(max_length=400).run_validation(
                request.data.get("reason")
            )
            if action_name == "extend":
                target = serializers.DateField().run_validation(request.data.get("review_on"))
                if target <= max(today(), row.review_on or today()):
                    raise ValidationError({"review_on": "Choose a later review date."})
                row.review_on = target
            else:
                row.retention_hold = action_name == "hold"
            row.save(update_fields=["retention_hold", "review_on", "updated_at"])
            models.DocumentRetentionReview.objects.create(
                document=row,
                reviewed_by=request.user,
                operation=action_name,
                reason=reason,
                review_on=row.review_on,
                retention_hold=row.retention_hold,
            )
            audit(
                request,
                "HR_DOCUMENT_RETENTION_REVIEWED",
                "employeedocument",
                row,
                operation=action_name,
            )
            return Response(self.get_serializer(row).data)

        return self.write(operation)

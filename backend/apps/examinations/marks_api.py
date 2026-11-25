from typing import ClassVar

from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.academics.access import Conflict
from apps.accounts.access import permission_codes
from apps.accounts.authentication import audit
from apps.attendance.access import assignments_for, dated_scope

from . import models, serializers
from .catalog import BROAD
from .config_api import ExamView, payload
from .workflow import check_version, save


def mark_values(row):
    return {
        "status": row.status,
        "obtained": str(row.obtained) if row.obtained is not None else None,
        "remarks": row.remarks,
    }


def scoped(query, user, *, operational=False):
    if BROAD in permission_codes(user):
        return query
    scope = Q(pk__in=[])
    for row in assignments_for(user, operational=operational).filter(subject__isnull=False):
        scope |= Q(
            component__subject__group__exam__session_id=row.session_id,
            component__subject__group__academic_class_id=row.academic_class_id,
            component__subject__subject_id=row.subject_id,
            section_id=row.section_id,
        ) & dated_scope(row, "component__subject__group__exam__start_date")
    return query.filter(scope)


def header(row):
    subject = row.component.subject
    return {
        "id": row.pk,
        "exam": subject.group.exam.name,
        "group": subject.group_id,
        "subject": subject.subject_name,
        "component": row.component.name,
        "class": subject.group.academic_class.name,
        "section": row.section.name if row.section else "",
        "maximum": str(row.component.maximum),
        "version": row.version,
        "status": row.status,
    }


class Marks(ExamView):
    queryset = models.MarksSubmission.objects.select_related(
        "component__subject__group__academic_class", "component__subject__group__exam", "section"
    )
    institution_lookup = "component__subject__group__exam__institution"
    permission_map: ClassVar = {
        "lookups": "accounts.view_exam_marks",
        "list": "accounts.view_exam_marks",
        "retrieve": "accounts.view_exam_marks",
        "save": ("accounts.enter_exam_marks", "accounts.update_exam_marks"),
        "submit": "accounts.submit_exam_marks",
        "verify": "accounts.verify_exam_marks",
        "return_marks": "accounts.verify_exam_marks",
    }
    filterset_fields = (
        "status",
        "section",
        "component",
        "component__subject__group__exam",
        "component__subject__group__exam__session",
        "component__subject__group__academic_class",
        "component__subject__subject",
    )
    search_fields = (
        "component__name",
        "component__subject__subject_name",
        "component__subject__group__exam__name",
        "component__subject__group__academic_class__name",
    )

    def get_queryset(self):
        return scoped(
            super().get_queryset(),
            self.request.user,
            operational=self.request.method not in {"GET", "HEAD", "OPTIONS"},
        )

    def list(self, request, *args, **kwargs):
        return self.get_paginated_response(
            [
                header(row)
                for row in self.paginate_queryset(self.filter_queryset(self.get_queryset()))
            ]
        )

    @action(detail=False, methods=["get"])
    def lookups(self, request):
        options = {}
        for prefix in (
            "component__subject__group__exam__session",
            "component__subject__group__exam",
            "component__subject__group__academic_class",
            "section",
            "component__subject__subject",
            "component",
        ):
            values = (
                self.get_queryset()
                .order_by()
                .values_list(
                    f"{prefix}__id",
                    f"{prefix}__name",
                )
                .distinct()
                .order_by(f"{prefix}__name")
            )
            options[prefix] = [{"id": key, "name": name} for key, name in values if key]
        return Response(options)

    def present(self, row):
        marks = sorted(
            row.marks.select_related("registration"),
            key=lambda mark: mark.registration.details["roll"],
        )
        return header(row) | {
            "marks": [
                {
                    "registration": mark.registration_id,
                    **mark.registration.details,
                    **mark_values(mark),
                }
                for mark in marks
            ]
        }

    def retrieve(self, request, *args, **kwargs):
        return Response(self.present(self.get_object()))

    @action(detail=True, methods=["post"])
    def save(self, request, pk=None):
        def operation():
            row = self.get_object()
            save(row, payload(serializers.SaveMarks, request), request)
            return Response(self.present(row))

        return self.write(operation)

    def transition(self, request, target, expected):
        def operation():
            row = self.get_object()
            values = payload(serializers.Transition, request)
            if row.status == target:
                return Response(self.present(row))
            check_version(row, values["version"])
            if (
                row.status not in expected
                or models.ResultPublication.objects.filter(
                    group=row.component.subject.group
                ).exists()
            ):
                raise Conflict("This marks submission cannot advance from its current state.")
            if target == "submitted":
                if row.component.required and row.marks.filter(status="missing").exists():
                    raise ValidationError("Enter every required mark or select an explicit status.")
                row.submitted_by, row.submitted_at = request.user, timezone.now()
            elif target == "verified":
                if row.submitted_by_id == request.user.pk and BROAD not in permission_codes(
                    request.user
                ):
                    raise PermissionDenied("Use a separate reviewer.")
                row.verified_by, row.verified_at = request.user, timezone.now()
            else:
                if not values.get("reason"):
                    raise ValidationError("Enter a reason for returning these marks.")
                row.verified_by = row.verified_at = None
            row.status = target
            row.version += 1
            row.save()
            row.component.subject.group.calculations.update(superseded=True)
            audit(request, "EXAM_MARKS_" + target.upper(), "markssubmission", row)
            return Response(self.present(row))

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self.transition(request, "submitted", {"draft"})

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        return self.transition(request, "verified", {"submitted"})

    @action(detail=True, methods=["post"], url_path="return")
    def return_marks(self, request, pk=None):
        return self.transition(request, "draft", {"submitted", "verified"})

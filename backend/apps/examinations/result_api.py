from typing import ClassVar

from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.academics.access import Conflict, school
from apps.accounts.access import permission_codes
from apps.accounts.authentication import audit

from . import models, serializers
from .catalog import BROAD
from .config_api import ExamView, payload
from .marks_api import mark_values
from .results import calculate


def row_data(row):
    return {"id": row.pk, **row.snapshot}


def summary(run):
    publication = getattr(run, "publication", None)
    return {
        "id": run.pk,
        "group": run.group_id,
        "revision": run.revision,
        "status": "published"
        if publication and publication.active
        else "withdrawn"
        if publication
        else "superseded"
        if run.superseded
        else "approved"
        if run.approved_at
        else "draft",
        "records": run.results.count(),
    }


class Runs(ExamView):
    queryset = models.ResultCalculation.objects.select_related("group__exam", "publication")
    institution_lookup = "group__exam__institution"
    permission_map: ClassVar = {
        "list": ("accounts.view_class_results", BROAD),
        "retrieve": ("accounts.view_class_results", BROAD),
        "create": ("accounts.approve_exam_results", BROAD),
        "approve": ("accounts.approve_exam_results", BROAD),
        "publish": ("accounts.publish_exam_results", BROAD),
        "withdraw": ("accounts.publish_exam_results", BROAD),
        "correct": ("accounts.correct_exam_results", BROAD),
    }
    filterset_fields = ("group", "group__exam")
    ordering = ("-created_at", "id")

    def list(self, request, *args, **kwargs):
        return self.get_paginated_response(
            [
                summary(row)
                for row in self.paginate_queryset(self.filter_queryset(self.get_queryset()))
            ]
        )

    def retrieve(self, request, *args, **kwargs):
        row = self.get_object()
        page = self.paginate_queryset(row.results.order_by("id"))
        data = summary(row)
        results = [row_data(item) for item in page]
        if (
            "accounts.correct_exam_results" in permission_codes(request.user)
            and data["status"] == "withdrawn"
        ):
            marks = models.StudentAssessmentMark.objects.filter(
                registration_id__in=[item.registration_id for item in page]
            ).select_related("submission__component__subject")
            options = {}
            for mark in marks:
                component = mark.submission.component
                options.setdefault(mark.registration_id, []).append(
                    {
                        "registration": mark.registration_id,
                        "component": component.pk,
                        "name": component.subject.subject_name + " · " + component.name,
                    }
                )
            for item, output in zip(page, results, strict=True):
                output["corrections"] = options.get(item.registration_id, [])
        return Response(data | {"results": self.get_paginated_response(results).data})

    def create(self, request, *args, **kwargs):
        def operation():
            field = serializers.Registration().fields["group"]
            key = field.run_validation(request.data.get("group"))
            group = get_object_or_404(models.ExaminationClass, pk=key, exam__institution=school())
            return Response(summary(calculate(group, request)), status=201)

        return self.write(operation)

    def validate_run(self, row):
        if row.superseded or row.group.calculations.filter(revision__gt=row.revision).exists():
            raise Conflict("Calculate an updated result set.")
        submissions = models.MarksSubmission.objects.filter(component__subject__group=row.group)
        if not submissions.exists() or submissions.exclude(status="verified").exists():
            raise ValidationError("Verify all marks before approving or publishing.")
        if not row.results.exists() or row.results.exclude(status__in=["pass", "fail"]).exists():
            raise ValidationError("Incomplete and withheld results cannot be published.")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        def operation():
            row = self.get_object()
            self.validate_run(row)
            if not row.approved_at:
                row.approved_at, row.approved_by = timezone.now(), request.user
                row.save(update_fields=["approved_at", "approved_by", "updated_at"])
                audit(request, "EXAM_RESULTS_APPROVED", "resultcalculation", row)
            return Response(summary(row))

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        def operation():
            row = self.get_object()
            if publication := getattr(row, "publication", None):
                if publication.active:
                    return Response(summary(row))
                raise Conflict("Calculate and approve a new revision before republication.")
            self.validate_run(row)
            if not row.approved_at or request.data.get("confirmed") is not True:
                raise ValidationError("Approve the results and confirm publication.")
            if models.ResultPublication.objects.filter(group=row.group, active=True).exists():
                raise Conflict("Withdraw the currently published revision first.")
            institution = row.group.exam.institution
            models.ResultPublication.objects.create(
                calculation=row,
                group=row.group,
                published_by=request.user,
                branding={"name": institution.name, "address": institution.address},
            )
            audit(request, "EXAM_RESULTS_PUBLISHED", "resultcalculation", row)
            row.refresh_from_db()
            return Response(summary(row))

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        def operation():
            row = self.get_object()
            reason = (
                serializers.Registration()
                .fields["reason"]
                .run_validation(request.data.get("reason"))
            )
            publication = get_object_or_404(models.ResultPublication, calculation=row)
            if publication.active:
                publication.active = False
                publication.withdrawn_at, publication.withdrawn_by = timezone.now(), request.user
                publication.reason = reason
                publication.save()
                audit(request, "EXAM_RESULTS_WITHDRAWN", "resultcalculation", row)
            row.refresh_from_db()
            return Response(summary(row))

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def correct(self, request, pk=None):
        def operation():
            row = self.get_object()
            publication = getattr(row, "publication", None)
            if not publication or publication.active:
                raise Conflict("Withdraw the publication before correcting marks.")
            if models.ResultPublication.objects.filter(group=row.group, active=True).exists():
                raise Conflict("Withdraw the publication before correcting marks.")
            values = payload(serializers.Correction, request)
            mark = get_object_or_404(
                models.StudentAssessmentMark,
                registration__group=row.group,
                registration_id=values["registration"],
                submission__component_id=values["component"],
                submission__status="verified",
            )
            if values["status"] == "missing":
                raise ValidationError("A correction must record an explicit assessment outcome.")
            if (
                values["obtained"] is not None
                and values["obtained"] > mark.submission.component.maximum
            ):
                raise ValidationError("The mark exceeds the component maximum.")
            previous = mark_values(mark)
            for field in ("status", "obtained", "remarks"):
                setattr(mark, field, values[field])
            mark.updated_by = request.user
            mark.save()
            models.MarksCorrection.objects.create(
                mark=mark,
                actor=request.user,
                previous=previous,
                revised=mark_values(mark),
                reason=values["reason"],
            )
            audit(request, "EXAM_MARK_CORRECTED", "studentassessmentmark", mark)
            return Response(summary(calculate(row.group, request)), status=201)

        return self.write(operation)

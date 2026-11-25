from typing import ClassVar

from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.academics.access import Conflict, RecordsView, school
from apps.accounts.authentication import audit

from . import models, serializers
from .ledger import preferences


class FeeView(RecordsView):
    license_feature = "fees"

    def finalize_response(self, request, response, *args, **kwargs):
        result = super().finalize_response(request, response, *args, **kwargs)
        result["Cache-Control"] = "no-store"
        return result


class Registry(FeeView):
    def perform_create(self, serializer):
        record = serializer.save(institution=school())
        audit(self.request, "FEE_CONFIG_CREATED", record._meta.model_name, record)

    def perform_update(self, serializer):
        record = serializer.save()
        audit(
            self.request,
            "FEE_CONFIG_UPDATED",
            record._meta.model_name,
            record,
            fields=sorted(serializer.validated_data),
        )


class Categories(Registry):
    queryset = models.FeeCategory.objects.all()
    serializer_class = serializers.Category
    search_fields = ("name", "code")
    filterset_fields = ("active", "recurrence")
    permission_map: ClassVar = {
        "list": "fees.view_feecategory",
        "retrieve": "fees.view_feecategory",
        "create": "fees.change_feecategory",
        "partial_update": "fees.change_feecategory",
    }


class Structures(Registry):
    queryset = models.FeeStructure.objects.prefetch_related("items")
    serializer_class = serializers.Structure
    search_fields = ("name", "academic_class__name")
    filterset_fields = ("session", "academic_class", "section", "status")
    permission_map: ClassVar = {
        "list": "fees.view_feestructure",
        "retrieve": "fees.view_feestructure",
        "create": "fees.change_feestructure",
        "partial_update": "fees.change_feestructure",
        "activate": "fees.change_feestructure",
        "retire": "fees.change_feestructure",
        "copy": "fees.change_feestructure",
    }

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        def operation():
            record = self.get_object()
            if record.status == "retired":
                raise Conflict("Copy the retired structure into a draft first.")
            if (
                self.get_queryset()
                .filter(
                    session=record.session,
                    academic_class=record.academic_class,
                    section=record.section,
                    status="active",
                    start_date__lte=record.end_date,
                    end_date__gte=record.start_date,
                )
                .exclude(pk=record.pk)
                .exists()
            ):
                raise Conflict("Another active structure overlaps the selected dates.")
            if record.status != "active":
                record.status = "active"
                record.save(update_fields=["status", "updated_at"])
                audit(request, "FEE_STRUCTURE_ACTIVATED", "feestructure", record)
            return Response(self.get_serializer(record).data)

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def retire(self, request, pk=None):
        def operation():
            record = self.get_object()
            if record.status != "retired":
                record.status = "retired"
                record.save(update_fields=["status", "updated_at"])
                audit(request, "FEE_STRUCTURE_RETIRED", "feestructure", record)
            return Response(self.get_serializer(record).data)

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def copy(self, request, pk=None):
        def operation():
            original = self.get_object()
            form = self.get_serializer(
                data={
                    **request.data,
                    "items": serializers.StructureItem(original.items.all(), many=True).data,
                }
            )
            form.is_valid(raise_exception=True)
            self.perform_create(form)
            return Response(form.data, status=201)

        return self.write(operation)


class Assignments(Registry):
    queryset = models.StudentFeeAssignment.objects.all()
    serializer_class = serializers.Assignment
    search_fields = ("enrollment__student__first_name", "enrollment__student__admission_number")
    filterset_fields = ("enrollment", "category", "active")
    permission_map: ClassVar = {
        "list": "fees.view_studentfeeassignment",
        "retrieve": "fees.view_studentfeeassignment",
        "create": "fees.change_studentfeeassignment",
        "partial_update": "fees.change_studentfeeassignment",
    }


class Concessions(Registry):
    queryset = models.StudentConcession.objects.all()
    serializer_class = serializers.Concession
    search_fields = ("label", "student__first_name", "student__admission_number")
    filterset_fields = ("session", "student", "category", "status")
    permission_map: ClassVar = {
        "list": "fees.view_studentconcession",
        "retrieve": "fees.view_studentconcession",
        "create": "fees.change_studentconcession",
        "partial_update": "fees.change_studentconcession",
        "approve": "accounts.approve_fee_concession",
        "retire": "accounts.approve_fee_concession",
    }

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.write(self.transition, "approved")

    @action(detail=True, methods=["post"])
    def retire(self, request, pk=None):
        return self.write(self.transition, "retired")

    def transition(self, status):
        record = self.get_object()
        if record.status == status:
            return Response(self.get_serializer(record).data)
        if status == "approved":
            if record.status != "pending":
                raise Conflict("Only pending concessions can be approved.")
            if (
                self.get_queryset()
                .filter(
                    student=record.student,
                    session=record.session,
                    category=record.category,
                    status="approved",
                    start_date__lte=record.end_date,
                    end_date__gte=record.start_date,
                )
                .exists()
            ):
                raise Conflict("An approved concession already covers that scope and range.")
            record.approved_by = self.request.user
        record.status = status
        record.save(update_fields=["status", "approved_by", "updated_at"])
        audit(self.request, f"FEE_CONCESSION_{status.upper()}", "studentconcession", record)
        return Response(self.get_serializer(record).data)


class Settings(FeeView):
    permission_map: ClassVar = dict.fromkeys(
        ("retrieve", "partial_update"), "accounts.manage_fee_settings"
    )

    def retrieve(self, request):
        return Response(serializers.Settings(preferences(school())).data)

    def partial_update(self, request):
        def operation():
            form = serializers.Settings(preferences(school()), data=request.data, partial=True)
            form.is_valid(raise_exception=True)
            if form.validated_data.get("late_fee", 0) < 0:
                raise ValidationError("Late fees must be nonnegative.")
            record = form.save()
            audit(
                request,
                "FEE_SETTINGS_UPDATED",
                "feesettings",
                record,
                fields=sorted(form.validated_data),
            )
            return Response(form.data)

        return self.write(operation)

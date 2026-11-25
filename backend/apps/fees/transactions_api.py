from typing import ClassVar

from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers as drf
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.academics.access import Conflict, school
from apps.accounts.access import require
from apps.accounts.authentication import audit

from . import models, serializers
from .billing import run_billing
from .config_api import FeeView
from .ledger import ZERO, amounts, post_payment, preferences, today


def clean(schema, request):
    form = schema(data=request.data)
    form.is_valid(raise_exception=True)
    return form.validated_data


def invoice_data(row, day):
    return {
        "id": row.pk,
        "number": row.number,
        "student": row.student_id,
        "session": row.session_id,
        "enrollment": row.enrollment_id,
        "period": row.period,
        "issue_date": row.issue_date,
        "due_date": row.due_date,
        "currency": row.currency,
        "subtotal": str(row.subtotal),
        "discount": str(row.discount),
        **{key: str(value) for key, value in amounts(row, day).items()},
        "details": row.issued_details,
    }


def payment_data(row):
    return {
        "id": row.pk,
        "number": row.number,
        "student": row.student_id,
        "date": row.date,
        "amount": str(row.amount),
        "method": row.method,
        "reversed": bool(row.reversed_at),
        "receipt": row.receipt.number,
        "allocations": [
            {"id": entry.pk, "invoice_id": entry.invoice_id, "amount": str(entry.amount)}
            for entry in row.allocations.all()
        ],
    }


class Transactions(FeeView):
    def list(self, request, *args, **kwargs):
        rows = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response([self.present(row) for row in rows])

    def retrieve(self, request, *args, **kwargs):
        return Response(self.present(self.get_object()))


class Invoices(Transactions):
    queryset = models.FeeInvoice.objects.all()
    filterset_fields = (
        "student",
        "session",
        "period",
        "voided",
        "enrollment__academic_class",
        "enrollment__section",
    )
    search_fields = (
        "number",
        "student__admission_number",
        "student__first_name",
        "student__last_name",
    )
    ordering = ("-issue_date", "-created_at", "id")
    permission_map: ClassVar = {
        "list": "fees.view_feeinvoice",
        "retrieve": "fees.view_feeinvoice",
        "create": "accounts.generate_fee_invoices",
        "void": "accounts.void_fee_invoice",
    }

    def present(self, row):
        return invoice_data(row, today(school()))

    def create(self, request, *args, **kwargs):
        values = clean(serializers.Billing, request)
        if "student" not in values:
            raise drf.ValidationError({"student": "Provide a student for individual generation."})
        return self.write(lambda: Response(run_billing(values, request, post=True), status=201))

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        def operation():
            record = self.get_object()
            values = clean(serializers.Reason, request)
            if record.voided:
                return Response(self.present(record))
            if record.allocations.exists() or record.adjustments.exists():
                raise Conflict("Use a credit adjustment for invoices with financial events.")
            record.voided = True
            record.voided_by = request.user
            record.void_reason = values["reason"]
            record.save(update_fields=["voided", "voided_by", "void_reason", "updated_at"])
            audit(request, "FEE_INVOICE_VOIDED", "feeinvoice", record)
            return Response(self.present(record))

        return self.write(operation)


class Payments(Transactions):
    queryset = models.FeePayment.objects.select_related("receipt")
    search_fields = (
        "number",
        "student__admission_number",
        "student__first_name",
        "receipt__number",
    )
    filterset_fields = ("student", "method", "date")
    ordering = ("-date", "-created_at", "id")
    permission_map: ClassVar = {
        "list": "fees.view_feepayment",
        "retrieve": "fees.view_feepayment",
        "create": "accounts.collect_fees",
        "reverse": "accounts.reverse_fee_payment",
    }

    def present(self, row):
        return payment_data(row)

    def create(self, request, *args, **kwargs):
        def operation():
            payment, created = post_payment(clean(serializers.Payment, request), request)
            return Response(self.present(payment), status=201 if created else 200)

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        def operation():
            record = self.get_object()
            values = clean(serializers.Reason, request)
            if not record.reversed_at:
                if record.allocations.filter(refunds__isnull=False).exists():
                    raise Conflict("Payments with refunds require allocation-level corrections.")
                record.reversed_at = timezone.now()
                record.reversed_by = request.user
                record.reversal_reason = values["reason"]
                record.save(
                    update_fields=["reversed_at", "reversed_by", "reversal_reason", "updated_at"]
                )
                audit(request, "FEE_PAYMENT_REVERSED", "feepayment", record)
            return Response(self.present(record))

        return self.write(operation)


class Billing(Transactions):
    queryset = models.FeeGenerationBatch.objects.all()
    filterset_fields = ("session", "period")
    ordering = ("-created_at", "id")
    permission_map: ClassVar = {
        "preview": "accounts.generate_fee_invoices",
        "generate": "accounts.generate_fee_invoices",
        "list": "fees.view_feeinvoice",
    }

    def present(self, row):
        return {"id": row.pk, "created_at": row.created_at, "period": row.period, **row.result}

    def preview(self, request):
        return Response(run_billing(clean(serializers.Billing, request), request))

    def generate(self, request):
        return self.write(
            lambda: Response(
                run_billing(clean(serializers.Billing, request), request, post=True),
                status=201,
            )
        )


class Adjustments(Transactions):
    queryset = models.FeeAdjustment.objects.all()
    institution_lookup = "invoice__institution"
    filterset_fields = ("invoice", "kind")
    permission_map: ClassVar = {
        "list": "fees.view_feeadjustment",
        "retrieve": "fees.view_feeadjustment",
        "create": "accounts.manage_fee_adjustments",
        "approve": "accounts.approve_fee_adjustment",
    }

    def present(self, row):
        return {
            "id": row.pk,
            "invoice": row.invoice_id,
            "amount": str(row.amount),
            "kind": row.kind,
            "approved_at": row.approved_at,
            "created_at": row.created_at,
        }

    def create(self, request, *args, **kwargs):
        def operation():
            values = clean(serializers.Adjustment, request)
            invoice = get_object_or_404(
                models.FeeInvoice, institution=school(), pk=values.pop("invoice"), voided=False
            )
            record, created = self.get_queryset().get_or_create(
                idempotency_key=values["idempotency_key"],
                defaults={**values, "invoice": invoice, "created_by": request.user},
            )
            if record.invoice_id != invoice.pk or any(
                getattr(record, key) != values[key] for key in ("kind", "amount", "reason")
            ):
                raise Conflict("This adjustment reference belongs to another submission.")
            if created:
                audit(
                    request, "FEE_ADJUSTMENT_REQUESTED", "feeadjustment", record, kind=record.kind
                )
            return Response(self.present(record), status=201 if created else 200)

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        def operation():
            row = self.get_object()
            institution = school()
            if row.approved_at:
                return Response(self.present(row))
            if row.kind == "write_off":
                require(request.user, "accounts.approve_fee_write_off")
            if preferences(institution).dual_approval and row.created_by_id == request.user.pk:
                raise PermissionDenied("Another authorized user must approve this adjustment.")
            if row.invoice.voided or (
                row.kind != "debit"
                and row.amount > amounts(row.invoice, today(institution))["outstanding"]
            ):
                raise Conflict(
                    "This adjustment exceeds the outstanding amount or the invoice is voided."
                )
            row.approved_by = request.user
            row.approved_at = timezone.now()
            row.save(update_fields=["approved_by", "approved_at", "updated_at"])
            audit(request, "FEE_ADJUSTMENT_APPROVED", "feeadjustment", row, kind=row.kind)
            return Response(self.present(row))

        return self.write(operation)


class Refunds(Transactions):
    queryset = models.FeeRefund.objects.all()
    institution_lookup = "allocation__payment__institution"
    filterset_fields = ("date", "allocation")
    permission_map: ClassVar = {
        "list": "fees.view_feerefund",
        "retrieve": "fees.view_feerefund",
        "create": "accounts.approve_fee_refund",
    }

    def present(self, row):
        return {
            "id": row.pk,
            "allocation": row.allocation_id,
            "date": row.date,
            "amount": str(row.amount),
        }

    def create(self, request, *args, **kwargs):
        def operation():
            institution = school()
            values = clean(serializers.Refund, request)
            allocation = get_object_or_404(
                models.FeePaymentAllocation.objects.select_related("payment"),
                payment__institution=institution,
                pk=values.pop("allocation"),
            )
            existing = self.get_queryset().filter(idempotency_key=values["idempotency_key"]).first()
            if existing:
                if existing.allocation_id != allocation.pk or any(
                    getattr(existing, field) != values[field]
                    for field in ("amount", "date", "reason")
                ):
                    raise Conflict("This refund reference belongs to another submission.")
                return Response(self.present(existing))
            refunded = allocation.refunds.aggregate(total=Sum("amount"))["total"] or ZERO
            if allocation.payment.reversed_at or values["amount"] > allocation.amount - refunded:
                raise Conflict("The requested refund exceeds the refundable allocation.")
            if not allocation.payment.date <= values["date"] <= today(institution):
                raise drf.ValidationError("Choose a date between the payment date and today.")
            refund = models.FeeRefund.objects.create(
                allocation=allocation, approved_by=request.user, **values
            )
            audit(request, "FEE_REFUND_POSTED", "feerefund", refund, amount=str(refund.amount))
            return Response(self.present(refund), status=201)

        return self.write(operation)

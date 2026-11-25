from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.access import Conflict
from apps.accounts.authentication import audit

from . import models


def structure_snapshot(row):
    return {
        "name": row.name,
        "code": row.code,
        "basis": row.basis,
        "basic": str(row.basic),
        "unpaid_leave_daily_rate": str(row.unpaid_leave_daily_rate),
        "prorate": row.prorate,
        "effective_from": row.effective_from.isoformat() if row.effective_from else None,
        "effective_through": row.effective_through.isoformat() if row.effective_through else None,
        "components": [
            {"label": label, "kind": kind, "amount": str(amount)}
            for label, kind, amount in row.components.order_by(
                "label", "kind", "amount"
            ).values_list("label", "kind", "amount")
        ],
    }


def validate_dates(start, end):
    if start and end and start > end:
        raise ValidationError("The effective-through date must be on or after the start date.")


def validate_compensation(basis, basic, rate, components):
    if basis not in {"monthly", "contract", "daily", "hourly"}:
        raise ValidationError("Choose a valid salary basis.")
    if Decimal(basic) < 0 or any(Decimal(item["amount"]) < 0 for item in components):
        raise ValidationError("Salary and component amounts must be nonnegative.")
    if any(
        not item["label"].strip() or item["kind"] not in {"earning", "deduction"}
        for item in components
    ):
        raise ValidationError("Each salary component needs a label and a valid kind.")
    if Decimal(rate) < 0 or (Decimal(rate) and basis not in {"monthly", "contract"}):
        raise ValidationError("Set a nonnegative unpaid leave rate for monthly or contract pay.")


def validated_snapshot(row):
    validate_dates(row.effective_from, row.effective_through)
    terms = structure_snapshot(row)
    validate_compensation(
        terms["basis"], terms["basic"], terms["unpaid_leave_daily_rate"], terms["components"]
    )
    return terms


def separate_approver(row):
    flag = (
        models.HRSettings.objects.filter(institution_id=row.institution_id)
        .values_list("separate_salary_structure_approver", flat=True)
        .first()
    )
    return flag is not False


def submit(row, request):
    if row.active or row.salaryassignment_set.exists():
        raise Conflict("Create a draft revision before submitting for approval.")
    snapshot = validated_snapshot(row)
    approval, created = row.approvals.get_or_create(
        revision=row.revision,
        defaults={
            "snapshot": snapshot,
            "submitted_by": request.user,
            "separate_approver": separate_approver(row),
        },
    )
    if not created and (approval.decision != "pending" or approval.snapshot != snapshot):
        raise Conflict("Edit the structure before submitting another revision.")
    if created:
        audit(
            request,
            "HR_SALARY_STRUCTURE_SUBMITTED",
            "salarystructure",
            row,
            approval=str(approval.pk),
            revision=row.revision,
        )
    return approval, created


def current_approval(row, request, required):
    key = serializers.UUIDField().run_validation(request.data.get("approval"))
    approval = row.approvals.filter(pk=key, revision=row.revision, decision=required).first()
    if (
        row.active
        or approval is None
        or approval.activated_at
        or (required == "approved" and (not approval.reviewed_by_id or not approval.reviewed_at))
        or validated_snapshot(row) != approval.snapshot
    ):
        raise Conflict("Select a matching decision for the current salary structure revision.")
    return approval


def decide(row, request, decision):
    approval = current_approval(row, request, "pending")
    if decision == "approved" and (approval.separate_approver or separate_approver(row)):
        if request.user.pk in {approval.submitted_by_id, row.created_by_id}:
            raise PermissionDenied("A different user must approve this salary structure.")
    reason = serializers.CharField(
        max_length=400, allow_blank=decision == "approved"
    ).run_validation(request.data.get("reason", ""))
    approval.decision = decision
    approval.reason = reason
    approval.reviewed_by = request.user
    approval.reviewed_at = timezone.now()
    approval.save(update_fields=["decision", "reason", "reviewed_by", "reviewed_at", "updated_at"])
    audit(
        request,
        "HR_SALARY_STRUCTURE_" + decision.upper(),
        "salarystructure",
        row,
        approval=str(approval.pk),
        revision=row.revision,
    )
    return approval


def activate(row, request):
    approval = current_approval(row, request, "approved")
    approval.activated_by = request.user
    approval.activated_at = timezone.now()
    approval.save(update_fields=["activated_by", "activated_at", "updated_at"])
    row.active = True
    row.save(update_fields=["active", "updated_at"])
    audit(
        request,
        "HR_SALARY_STRUCTURE_ACTIVATED",
        "salarystructure",
        row,
        approval=str(approval.pk),
        revision=row.revision,
    )
    return approval

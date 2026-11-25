import json
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.academics.access import Conflict, school
from apps.accounts.authentication import audit

from .models import FeeInvoice, FeePayment, FeePaymentAllocation, FeeReceipt, FeeSettings

ZERO = Decimal("0.00")
DEFAULT_METHODS = ("cash", "bank_transfer", "cheque", "digital_transfer", "other")


def round_money(amount):
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def today(institution):
    return timezone.localdate(timezone=ZoneInfo(institution.timezone))


def preferences(institution):
    return FeeSettings.objects.filter(institution=institution).first() or FeeSettings(
        institution=institution
    )


def identifier(prefix, day):
    return f"{prefix}-{day:%Y%m}-{uuid4().hex[:16].upper()}"


def amounts(invoice, day):
    if invoice.voided:
        return {
            "adjustment": ZERO,
            "total": ZERO,
            "paid": ZERO,
            "outstanding": ZERO,
            "status": "voided",
        }
    adjustments = invoice.adjustments.filter(approved_at__isnull=False)
    debit = adjustments.filter(kind="debit").aggregate(total=Sum("amount"))["total"] or ZERO
    credit = adjustments.exclude(kind="debit").aggregate(total=Sum("amount"))["total"] or ZERO
    allocations = invoice.allocations.filter(payment__reversed_at__isnull=True)
    applied = allocations.aggregate(total=Sum("amount"))["total"] or ZERO
    refunded = allocations.aggregate(total=Sum("refunds__amount"))["total"] or ZERO
    paid = round_money(applied - refunded)
    total = invoice.issued_total + round_money(debit - credit)
    balance = total - paid
    if balance == 0:
        status = "paid"
    elif invoice.due_date < day:
        status = "overdue"
    else:
        status = "partially_paid" if paid else "issued"
    return {
        "adjustment": round_money(debit - credit),
        "total": total,
        "paid": paid,
        "outstanding": balance,
        "status": status,
    }


def post_payment(values, request):
    institution = school(lock=True)
    config = preferences(institution)
    parts = values["allocations"]
    invoice_ids = [item["invoice"] for item in parts]
    if (
        len(set(invoice_ids)) != len(parts)
        or sum(item["amount"] for item in parts) != values["amount"]
    ):
        raise ValidationError("Allocations must be distinct and match the payment amount.")
    fingerprint = sha256(
        json.dumps(
            {
                **{
                    key: value
                    for key, value in values.items()
                    if key not in {"allocations", "idempotency_key"}
                },
                "allocations": sorted(
                    (str(item["invoice"]), str(item["amount"])) for item in parts
                ),
            },
            default=str,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    existing = FeePayment.objects.filter(idempotency_key=values["idempotency_key"]).first()
    if existing:
        if existing.institution_id != institution.pk or existing.fingerprint != fingerprint:
            raise Conflict("This payment reference belongs to another submission.")
        return existing, False
    if values["date"] > today(institution) or values["method"] not in (
        config.payment_methods or DEFAULT_METHODS
    ):
        raise ValidationError("Choose an allowed payment method and a date through today.")
    invoices = {
        row.pk: row
        for row in FeeInvoice.objects.select_for_update()
        .filter(
            institution=institution,
            pk__in=invoice_ids,
            student_id=values["student"],
            voided=False,
        )
        .order_by("pk")
    }
    if len(invoices) != len(parts) or len({row.currency for row in invoices.values()}) != 1:
        raise ValidationError("Invoices must be issued for this student in the same currency.")
    remaining = {}
    for item in parts:
        invoice = invoices[item["invoice"]]
        if values["date"] < invoice.issue_date:
            raise ValidationError("Payment date cannot precede invoice issue.")
        balance = amounts(invoice, today(institution))["outstanding"]
        if item["amount"] > balance:
            raise Conflict(f"Allocation exceeds the balance on {invoice.number}.")
        remaining[invoice.number] = str(balance - item["amount"])
    payment = FeePayment.objects.create(
        institution=institution,
        student_id=values["student"],
        received_by=request.user,
        number=identifier("PAY", values["date"]),
        fingerprint=fingerprint,
        **{key: value for key, value in values.items() if key not in {"allocations", "student"}},
    )
    FeePaymentAllocation.objects.bulk_create(
        [
            FeePaymentAllocation(payment=payment, invoice_id=item["invoice"], amount=item["amount"])
            for item in parts
        ]
    )
    first = invoices[invoice_ids[0]]
    FeeReceipt.objects.create(
        payment=payment,
        number=identifier(config.receipt_prefix, payment.date),
        details={
            **first.issued_details,
            "institution": institution.name,
            "address": institution.address,
            "date": str(payment.date),
            "amount": str(payment.amount),
            "method": payment.method,
            "currency": first.currency,
            "received_by": request.user.get_username(),
            "allocations": [
                {
                    "invoice": invoices[item["invoice"]].number,
                    "amount": str(item["amount"]),
                    "remaining": remaining[invoices[item["invoice"]].number],
                }
                for item in parts
            ],
            "footer": config.receipt_footer,
        },
    )
    audit(request, "FEE_PAYMENT_POSTED", "feepayment", payment, amount=str(payment.amount))
    return payment, True

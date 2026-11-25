from decimal import Decimal
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Round

from apps.academics.models import NamedRecord, Record

PROTECT = models.PROTECT
RECURRENCES = [
    (kind, kind.replace("_", " ").title())
    for kind in ("monthly", "quarterly", "term", "annual", "one_time", "custom")
]


def money(**kwargs):
    return models.DecimalField(max_digits=14, decimal_places=2, **kwargs)


def institution():
    return models.ForeignKey("accounts.Institution", on_delete=PROTECT)


def session():
    return models.ForeignKey("academics.AcademicSession", on_delete=PROTECT)


def student():
    return models.ForeignKey("students.Student", on_delete=PROTECT)


def actor():
    return models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name="+")


def category(**kwargs):
    return models.ForeignKey("fees.FeeCategory", on_delete=PROTECT, **kwargs)


class FeeSettings(Record):
    institution = models.OneToOneField("accounts.Institution", on_delete=PROTECT)
    currency = models.CharField(max_length=3, default="PKR")
    invoice_prefix = models.SlugField(max_length=16, default="INV")
    receipt_prefix = models.SlugField(max_length=16, default="RCP")
    due_day = models.PositiveSmallIntegerField(default=10)
    billing_day = models.PositiveSmallIntegerField(default=1)
    late_fee_enabled = models.BooleanField(default=False)
    late_fee = money(default=Decimal("0.00"))
    grace_days = models.PositiveSmallIntegerField(default=0)
    payment_methods = models.JSONField(default=list)
    stack_discounts = models.BooleanField(default=False)
    prorate = models.BooleanField(default=False)
    dual_approval = models.BooleanField(default=False)
    receipt_footer = models.CharField(max_length=500, blank=True)
    challan_instructions = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(due_day__range=(1, 31), billing_day__range=(1, 31), late_fee__gte=0),
                name="fee_valid_cycle",
            )
        ]


class FeeCategory(NamedRecord):
    institution = institution()
    description = models.CharField(max_length=500, blank=True)
    recurrence = models.CharField(max_length=12, choices=RECURRENCES, default="monthly")
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(Lower("code"), "institution", name="fee_unique_category_code")
        ]


class FeeStructure(Record):
    institution = institution()
    session = session()
    academic_class = models.ForeignKey("academics.AcademicClass", on_delete=PROTECT)
    section = models.ForeignKey("academics.Section", on_delete=PROTECT, null=True, blank=True)
    name = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=10,
        default="draft",
        choices=[
            ("draft", "Draft"),
            ("active", "Active"),
            ("retired", "Retired"),
        ],
    )

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="fee_structure_dates"
            )
        ]


class FeeStructureItem(Record):
    structure = models.ForeignKey(FeeStructure, on_delete=PROTECT, related_name="items")
    category = category()
    amount = money()
    recurrence = models.CharField(max_length=12, choices=RECURRENCES)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="fee_structure_amount"),
            models.UniqueConstraint(fields=["structure", "category"], name="fee_category_per_plan"),
        ]


class StudentFeeAssignment(Record):
    institution = institution()
    enrollment = models.ForeignKey("admissions.StudentEnrollment", on_delete=PROTECT)
    structure = models.ForeignKey(FeeStructure, on_delete=PROTECT, null=True, blank=True)
    category = category(null=True, blank=True)
    amount = money(null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="fee_assignment_dates"
            ),
            models.CheckConstraint(
                condition=Q(category__isnull=True, amount__isnull=True, structure__isnull=False)
                | Q(
                    category__isnull=False,
                    amount__gte=0,
                    amount__isnull=False,
                    structure__isnull=True,
                ),
                name="fee_assignment_plan_or_override",
            ),
        ]


class StudentConcession(Record):
    institution = institution()
    student = student()
    session = session()
    category = category(null=True, blank=True)
    label = models.CharField(max_length=100)
    kind = models.CharField(
        max_length=10,
        choices=[
            ("fixed", "Fixed amount"),
            ("percent", "Percentage"),
            ("full", "Full"),
        ],
    )
    value = money(default=Decimal("0.00"))
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=8,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("retired", "Retired"),
        ],
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, related_name="+"
    )

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="fee_concession_dates"
            ),
            models.CheckConstraint(
                condition=Q(kind="fixed", value__gt=0)
                | Q(kind="percent", value__gt=0, value__lte=100)
                | Q(kind="full", value=0),
                name="fee_concession_value",
            ),
        ]


class FeeGenerationBatch(Record):
    institution = institution()
    session = session()
    period = models.DateField()
    criteria = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    created_by = actor()


class FeeInvoice(Record):
    institution = institution()
    student = student()
    session = session()
    enrollment = models.ForeignKey("admissions.StudentEnrollment", on_delete=PROTECT)
    batch = models.ForeignKey(FeeGenerationBatch, on_delete=PROTECT, null=True)
    number = models.CharField(max_length=42, unique=True)
    period = models.DateField()
    issue_date = models.DateField()
    due_date = models.DateField()
    currency = models.CharField(max_length=3, default="PKR")
    subtotal = money()
    discount = money()
    issued_total = money()
    issued_details = models.JSONField(default=dict)
    created_by = actor()
    voided = models.BooleanField(default=False)
    void_reason = models.CharField(max_length=400, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, related_name="+"
    )

    class Meta:
        indexes: ClassVar = [
            models.Index(fields=["student", "period"]),
            models.Index(fields=["due_date", "voided"]),
        ]
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(
                    subtotal__gte=0,
                    discount__gte=0,
                    issued_total=Round(F("subtotal") - F("discount"), precision=2),
                    issued_total__gte=0,
                ),
                name="fee_invoice_total",
            )
        ]


class FeeInvoiceItem(Record):
    invoice = models.ForeignKey(FeeInvoice, on_delete=PROTECT, related_name="items")
    student = student()
    session = session()
    category = category()
    identity = models.CharField(max_length=70)
    description = models.CharField(max_length=150)
    amount = money()
    discount = money()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["student", "session", "category", "identity"],
                name="fee_unique_billed_charge",
            ),
            models.CheckConstraint(
                condition=Q(amount__gte=0, discount__gte=0, discount__lte=F("amount")),
                name="fee_invoice_item_amount",
            ),
        ]


class FeePayment(Record):
    institution = institution()
    student = student()
    number = models.CharField(max_length=42, unique=True)
    date = models.DateField()
    amount = money()
    method = models.CharField(max_length=32)
    external_reference = models.CharField(max_length=90, blank=True)
    remarks = models.CharField(max_length=400, blank=True)
    received_by = actor()
    idempotency_key = models.UUIDField(unique=True)
    fingerprint = models.CharField(max_length=64)
    reversed_at = models.DateTimeField(null=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, related_name="+"
    )
    reversal_reason = models.CharField(max_length=400, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="fee_payment_positive")
        ]


class FeePaymentAllocation(Record):
    payment = models.ForeignKey(FeePayment, on_delete=PROTECT, related_name="allocations")
    invoice = models.ForeignKey(FeeInvoice, on_delete=PROTECT, related_name="allocations")
    amount = money()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["payment", "invoice"], name="fee_unique_allocation"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="fee_allocation_positive"),
        ]


class FeeReceipt(Record):
    payment = models.OneToOneField(FeePayment, on_delete=PROTECT, related_name="receipt")
    number = models.CharField(max_length=42, unique=True)
    details = models.JSONField()


class FeeAdjustment(Record):
    invoice = models.ForeignKey(FeeInvoice, on_delete=PROTECT, related_name="adjustments")
    kind = models.CharField(
        max_length=12,
        choices=[
            ("debit", "Debit"),
            ("credit", "Credit"),
            ("write_off", "Write-off"),
        ],
    )
    amount = money()
    reason = models.CharField(max_length=400)
    created_by = actor()
    approved_at = models.DateTimeField(null=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, related_name="+"
    )
    idempotency_key = models.UUIDField(unique=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="fee_adjustment_positive")
        ]


class FeeRefund(Record):
    allocation = models.ForeignKey(FeePaymentAllocation, on_delete=PROTECT, related_name="refunds")
    amount = money()
    reason = models.CharField(max_length=400)
    date = models.DateField()
    approved_by = actor()
    idempotency_key = models.UUIDField(unique=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="fee_refund_positive")
        ]

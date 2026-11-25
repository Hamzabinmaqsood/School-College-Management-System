from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Round

from apps.academics.models import NamedRecord, Record

PROTECT = models.PROTECT


def institution():
    return models.ForeignKey("accounts.Institution", on_delete=PROTECT)


def employee():
    return models.ForeignKey("hr.Employee", on_delete=PROTECT)


def actor(**kwargs):
    return models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name="+", **kwargs
    )


def money(**kwargs):
    return models.DecimalField(max_digits=14, decimal_places=2, **kwargs)


class Department(NamedRecord):
    default_schedule = models.JSONField(default=dict, blank=True)
    institution = institution()
    description = models.CharField(max_length=400, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(Lower("code"), "institution", name="hr_department_code")
        ]


class Designation(NamedRecord):
    institution = institution()
    description = models.CharField(max_length=400, blank=True)
    teaching = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(Lower("code"), "institution", name="hr_designation_code")
        ]


class Employee(Record):
    institution = institution()
    code = models.SlugField(max_length=40)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=PROTECT)
    first_name = models.CharField(max_length=90)
    last_name = models.CharField(max_length=90, blank=True)
    display_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    department = models.ForeignKey(Department, on_delete=PROTECT)
    designation = models.ForeignKey(Designation, on_delete=PROTECT)
    employment_type = models.CharField(max_length=40)
    joined_on = models.DateField()
    ended_on = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=14,
        default="active",
        choices=[
            (x, x.title())
            for x in (
                "active",
                "on_leave",
                "suspended",
                "resigned",
                "terminated",
                "retired",
                "contract_ended",
            )
        ],
    )

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(Lower("code"), "institution", name="hr_employee_code"),
            models.CheckConstraint(
                condition=Q(ended_on__isnull=True) | Q(ended_on__gte=F("joined_on")),
                name="hr_employment_dates",
            ),
        ]


class EmployeePositionHistory(Record):
    employee = employee()
    effective = models.DateField()
    details = models.JSONField(default=dict)
    changed_by = actor()


class EmploymentContract(Record):
    leave_entitlements = models.JSONField(default=dict, blank=True)
    employee = employee()
    kind = models.CharField(max_length=40)
    start_date = models.DateField()
    end_date = models.DateField()
    weekdays = models.JSONField(default=list)
    shift_start = models.TimeField(null=True, blank=True)
    shift_end = models.TimeField(null=True, blank=True)
    break_minutes = models.PositiveSmallIntegerField(default=0)
    late_tolerance_minutes = models.PositiveSmallIntegerField(default=0)
    early_tolerance_minutes = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField(max_length=400, blank=True)
    created_by = actor()
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="hr_contract_dates"
            ),
        ]


class EmployeeAttendance(Record):
    employee = employee()
    date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=[
            (x, x.title())
            for x in (
                "present",
                "absent",
                "late",
                "leave",
                "holiday",
                "excused",
            )
        ],
    )
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    overtime = money(default=0)
    remarks = models.CharField(max_length=300, blank=True)
    recorded_by = actor()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["employee", "date"], name="hr_daily_attendance"),
            models.CheckConstraint(condition=Q(overtime__gte=0), name="hr_nonnegative_overtime"),
        ]


class EmployeeAttendanceCorrection(Record):
    entry = models.ForeignKey(EmployeeAttendance, on_delete=PROTECT)
    previous = models.JSONField()
    revised = models.JSONField()
    reason = models.CharField(max_length=400)
    actor = actor()


class LeaveType(NamedRecord):
    institution = institution()
    paid = models.BooleanField(default=True)
    annual_days = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(Lower("code"), "institution", name="hr_leave_type_code")
        ]

    accrual_mode = models.CharField(
        max_length=10,
        default="legacy",
        choices=[
            (mode, mode.title())
            for mode in ("legacy", "monthly", "annual", "fixed", "manual", "none")
        ],
    )
    accrual_start = models.DateField(null=True, blank=True)
    prorate = models.BooleanField(default=True)
    carry_limit = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    carry_expiry_days = models.PositiveSmallIntegerField(default=0)
    maximum_balance = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    allow_negative = models.BooleanField(default=False)


class LeavePolicyVersion(Record):
    leave_type = models.ForeignKey(LeaveType, on_delete=PROTECT, related_name="versions")
    effective_start = models.DateField()
    terms = models.JSONField()
    published = models.BooleanField(default=False)
    created_by = actor(null=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("leave_type", "effective_start"), name="hr_leave_version_start"
            ),
        ]


class EmployeeLeave(Record):
    employee = employee()
    leave_type = models.ForeignKey(LeaveType, on_delete=PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.PositiveSmallIntegerField()
    reason = models.CharField(max_length=400)
    status = models.CharField(max_length=10, default="pending")
    submitted_by = actor()

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date"), days__gt=0), name="hr_leave_dates"
            )
        ]


class LeaveDecision(Record):
    leave = models.ForeignKey(EmployeeLeave, on_delete=PROTECT, related_name="decisions")
    status = models.CharField(max_length=10)
    reason = models.CharField(max_length=400, blank=True)
    actor = actor()


class SalaryStructure(NamedRecord):
    institution = institution()
    basis = models.CharField(
        max_length=10, choices=[(x, x.title()) for x in ("monthly", "daily", "hourly", "contract")]
    )
    basic = money()
    unpaid_leave_daily_rate = money(default=0)
    prorate = models.BooleanField(default=False)
    active = models.BooleanField(default=False)

    revision = models.PositiveIntegerField(default=1)
    created_by = actor(null=True)
    legacy_active = models.BooleanField(default=False)
    effective_from = models.DateField(null=True, blank=True)
    effective_through = models.DateField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(Lower("code"), "institution", name="hr_salary_code"),
            models.CheckConstraint(condition=Q(basic__gte=0), name="hr_salary_basic"),
        ]


class SalaryStructureApproval(Record):
    structure = models.ForeignKey(SalaryStructure, on_delete=PROTECT, related_name="approvals")
    revision = models.PositiveIntegerField()
    snapshot = models.JSONField()
    submitted_by = actor()
    separate_approver = models.BooleanField(default=True)
    decision = models.CharField(
        max_length=8,
        choices=[(value, value.title()) for value in ("pending", "approved", "rejected")],
        default="pending",
    )
    reason = models.CharField(max_length=400, blank=True)
    reviewed_by = actor(null=True)
    reviewed_at = models.DateTimeField(null=True)
    activated_by = actor(null=True)
    activated_at = models.DateTimeField(null=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("structure", "revision"), name="hr_salary_approval_revision"
            ),
            models.CheckConstraint(
                condition=Q(decision="approved") | Q(activated_at__isnull=True),
                name="hr_salary_approved_activation",
            ),
        ]


class SalaryComponent(Record):
    structure = models.ForeignKey(SalaryStructure, on_delete=PROTECT, related_name="components")
    label = models.CharField(max_length=120)
    kind = models.CharField(
        max_length=10, choices=[("earning", "Earning"), ("deduction", "Deduction")]
    )
    amount = money()

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="hr_component_amount")
        ]


class SalaryAssignment(Record):
    employee = employee()
    structure = models.ForeignKey(SalaryStructure, on_delete=PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    created_by = actor()

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="hr_assignment_dates"
            )
        ]


class SalaryAdvance(Record):
    employee = employee()
    reference = models.UUIDField(unique=True)
    amount = money()
    installment = money()
    recover_from = models.DateField()
    created_by = actor()
    approved_by = actor(null=True)
    disbursed_by = actor(null=True)
    disbursed_at = models.DateTimeField(null=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(amount__gt=0, installment__gt=0, installment__lte=F("amount")),
                name="hr_advance_limits",
            )
        ]


class PayrollPeriod(Record):
    institution = institution()
    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    separate_approver = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="hr_period_dates"
            )
        ]


class PayrollRun(Record):
    period = models.ForeignKey(PayrollPeriod, on_delete=PROTECT)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=PROTECT)
    key = models.UUIDField(unique=True)
    status = models.CharField(max_length=12, default="draft")
    created_by = actor()


class PayrollApproval(Record):
    run = models.ForeignKey(PayrollRun, on_delete=PROTECT, related_name="decisions")
    status = models.CharField(max_length=12)
    reason = models.CharField(max_length=400, blank=True)
    actor = actor()


class PayrollEntry(Record):
    run = models.ForeignKey(PayrollRun, on_delete=PROTECT, related_name="entries")
    period = models.ForeignKey(PayrollPeriod, on_delete=PROTECT)
    employee = employee()
    assignment = models.ForeignKey(SalaryAssignment, on_delete=PROTECT)
    basic = money()
    gross = money()
    deductions = money()
    net = money()
    snapshot = models.JSONField()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["period", "employee"], name="hr_payroll_obligation"),
            models.CheckConstraint(
                condition=Q(
                    gross__gte=0,
                    deductions__gte=0,
                    net__gte=0,
                    net=Round(F("gross") - F("deductions"), precision=2),
                ),
                name="hr_reconcile_payroll",
            ),
        ]


class AdvanceRecovery(Record):
    advance = models.ForeignKey(SalaryAdvance, on_delete=PROTECT, related_name="recoveries")
    entry = models.ForeignKey(PayrollEntry, on_delete=PROTECT)
    amount = money()


class SalaryPayment(Record):
    entry = models.ForeignKey(PayrollEntry, on_delete=PROTECT, related_name="payments")
    key = models.UUIDField(unique=True)
    amount = money()
    date = models.DateField()
    method = models.CharField(max_length=40)
    external_reference = models.CharField(max_length=100, blank=True)
    recorded_by = actor()

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="hr_salary_payment_positive")
        ]


class EmployeeDocument(Record):
    employee = employee()
    label = models.CharField(max_length=120)
    kind = models.CharField(max_length=40)
    content = models.BinaryField(editable=False)
    size = models.PositiveIntegerField()
    uploaded_by = actor()
    archived_at = models.DateTimeField(null=True)
    review_on = models.DateField(null=True, blank=True)
    retention_hold = models.BooleanField(default=False)


class DocumentRetentionReview(Record):
    document = models.ForeignKey(EmployeeDocument, on_delete=PROTECT, related_name="reviews")
    reviewed_by = actor()
    operation = models.CharField(max_length=20)
    reason = models.CharField(max_length=400)
    review_on = models.DateField(null=True)
    retention_hold = models.BooleanField()


class PayrollAdjustment(Record):
    entry = models.ForeignKey(PayrollEntry, on_delete=PROTECT, related_name="adjustments")
    key = models.UUIDField(unique=True)
    amount = money()
    reason = models.CharField(max_length=400)
    approved_by = actor()

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(condition=~Q(amount=0), name="hr_adjustment_nonzero")
        ]


class SalaryPaymentReversal(Record):
    payment = models.OneToOneField(SalaryPayment, on_delete=PROTECT, related_name="reversal")
    reason = models.CharField(max_length=400)
    approved_by = actor()


class HRSettings(Record):
    separate_salary_structure_approver = models.BooleanField(default=True)
    document_retention_by_kind = models.JSONField(default=dict, blank=True)
    institution = models.OneToOneField("accounts.Institution", on_delete=PROTECT)
    employee_prefix = models.SlugField(max_length=16, default="EMP")
    next_employee_number = models.PositiveIntegerField(default=1)
    document_retention_days = models.PositiveIntegerField(null=True, blank=True)


class OvertimePolicy(Record):
    institution = institution()
    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    monthly_divisor = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    regular_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    rest_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    holiday_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    minimum_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    maximum_hours = models.DecimalField(max_digits=5, decimal_places=2)
    separate_approver = models.BooleanField(default=True)


class StaffOvertime(Record):
    attendance = models.OneToOneField(EmployeeAttendance, on_delete=PROTECT)
    policy = models.ForeignKey(OvertimePolicy, on_delete=PROTECT)
    requested_hours = models.DecimalField(max_digits=5, decimal_places=2)
    requested_by = actor()
    status = models.CharField(max_length=10, default="pending")
    decided_by = actor(null=True)
    decided_at = models.DateTimeField(null=True)
    decision_reason = models.CharField(max_length=400, blank=True)
    snapshot = models.JSONField(default=dict)


class LeaveBalanceTransaction(Record):
    employee = employee()
    leave_type = models.ForeignKey(LeaveType, on_delete=PROTECT)
    policy_version = models.ForeignKey(LeavePolicyVersion, on_delete=PROTECT, null=True)
    calculation = models.JSONField(default=dict)
    leave = models.ForeignKey(
        EmployeeLeave, on_delete=PROTECT, null=True, related_name="balance_events"
    )
    effective_date = models.DateField()
    event = models.CharField(max_length=12)
    key = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=7, decimal_places=2)
    reason = models.CharField(max_length=400, blank=True)
    recorded_by = actor()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("employee", "leave_type", "key"), name="hr_leave_event_key"
            ),
        ]

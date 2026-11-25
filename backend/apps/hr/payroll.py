import json
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from typing import ClassVar

from django.db.models import F, Q, Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.academics.access import Conflict, school
from apps.accounts.authentication import audit
from apps.attendance.models import AttendanceHoliday, AttendanceSettings

from . import models, salary_approval
from .api import HRView, contract_for, input_data, schema, today
from .schedule import elapsed, is_overnight, scheduled_day

ZERO = Decimal("0.00")


def round_money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def payable(entry):
    paid = (
        entry.payments.filter(reversal__isnull=True).aggregate(amount=Sum("amount"))["amount"]
        or ZERO
    )
    adjustments = entry.adjustments.aggregate(amount=Sum("amount"))["amount"] or ZERO
    return entry.net + round_money(adjustments) - round_money(paid)


class Component(schema(models.SalaryComponent, ("structure",))):
    pass


class ApprovalSerializer(schema(models.SalaryStructureApproval, ())):
    submitter = serializers.CharField(source="submitted_by.username", read_only=True)
    reviewer = serializers.CharField(source="reviewed_by.username", read_only=True, allow_null=True)
    activator = serializers.CharField(
        source="activated_by.username", read_only=True, allow_null=True
    )


class StructureSerializer(
    schema(models.SalaryStructure, ("institution", "created_by"), ("revision", "legacy_active"))
):
    status = serializers.SerializerMethodField()
    current_approval = serializers.SerializerMethodField()

    @staticmethod
    def get_current_approval(row):
        approval = next(
            (item for item in row.approvals.all() if item.revision == row.revision), None
        )
        return {"id": approval.pk, "decision": approval.decision} if approval else None

    def get_status(self, row):
        if row.active:
            return "legacy_active" if row.legacy_active else "active"
        approval = self.get_current_approval(row)
        return approval["decision"] if approval else "draft"

    components = Component(many=True, allow_empty=True)

    def validate(self, data):
        if data.get("active"):
            raise ValidationError("Activate the approved revision through its activation action.")
        salary_approval.validate_dates(
            data.get("effective_from", getattr(self.instance, "effective_from", None)),
            data.get("effective_through", getattr(self.instance, "effective_through", None)),
        )
        if self.instance and (self.instance.active or self.instance.salaryassignment_set.exists()):
            raise ValidationError("Create a new salary version for future assignments.")
        salary_approval.validate_compensation(
            data.get("basis", getattr(self.instance, "basis", None)),
            data.get("basic", getattr(self.instance, "basic", ZERO)),
            data.get(
                "unpaid_leave_daily_rate", getattr(self.instance, "unpaid_leave_daily_rate", ZERO)
            ),
            data.get("components", ()),
        )
        return data

    def create(self, values):
        items = values.pop("components")
        row = super().create(values)
        models.SalaryComponent.objects.bulk_create(
            [models.SalaryComponent(structure=row, **item) for item in items]
        )
        return row

    def update(self, row, values):
        items = values.pop("components", None)
        values["revision"] = row.revision + 1
        row = super().update(row, values)
        if items is not None:
            row.components.all().delete()
            models.SalaryComponent.objects.bulk_create(
                [models.SalaryComponent(structure=row, **item) for item in items]
            )
        return row


class Structures(HRView):
    queryset = models.SalaryStructure.objects.prefetch_related("components", "approvals")
    serializer_class = StructureSerializer
    license_feature = "payroll"
    search_fields = ("name", "code")
    permission_map: ClassVar = {
        "list": "accounts.view_salary_setup",
        "retrieve": "accounts.view_salary_setup",
        "create": "accounts.manage_salary_setup",
        "partial_update": "accounts.manage_salary_setup",
        "submit": "accounts.submit_salary_structure",
        "approve": "accounts.approve_salary_structure",
        "reject": "accounts.approve_salary_structure",
        "activate": "accounts.activate_salary_structure",
        "approvals": "accounts.view_salary_structure_approvals",
        "pending_approvals": "accounts.view_salary_structure_approvals",
    }

    def perform_create(self, serializer):
        row = serializer.save(institution=school(), created_by=self.request.user)
        audit(self.request, "HR_CREATED", "salarystructure", row)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        def operation():
            approval, created = salary_approval.submit(self.get_object(), request)
            return Response(ApprovalSerializer(approval).data, status=201 if created else 200)

        return self.write(operation)

    def _decide(self, request, decision):
        def operation():
            approval = salary_approval.decide(self.get_object(), request, decision)
            return Response(ApprovalSerializer(approval).data)

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, "approved")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, "rejected")

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        def operation():
            approval = salary_approval.activate(self.get_object(), request)
            return Response(ApprovalSerializer(approval).data)

        return self.write(operation)

    @action(detail=True, methods=["get"])
    def approvals(self, request, pk=None):
        history = (
            self.get_object()
            .approvals.select_related(
                "submitted_by",
                "reviewed_by",
                "activated_by",
            )
            .order_by("-revision")
        )
        return Response(ApprovalSerializer(history, many=True).data)

    @action(detail=False, methods=["get"], url_path="pending-approvals")
    def pending_approvals(self, request):
        pending = (
            models.SalaryStructureApproval.objects.filter(
                structure__institution=school(),
                structure__active=False,
                revision=F("structure__revision"),
                decision="pending",
            )
            .select_related("submitted_by", "reviewed_by", "activated_by")
            .order_by("created_at", "pk")
        )
        page = self.paginate_queryset(pending)
        return self.get_paginated_response(ApprovalSerializer(page, many=True).data)


class Assignments(HRView):
    queryset = models.SalaryAssignment.objects.all()
    serializer_class = schema(models.SalaryAssignment, ("created_by",))
    institution_lookup = "employee__institution"
    license_feature = "payroll"
    filterset_fields = ("employee", "structure")
    permission_map: ClassVar = {
        "list": "accounts.view_salary_setup",
        "retrieve": "accounts.view_salary_setup",
        "create": "accounts.manage_salary_setup",
    }

    def perform_create(self, serializer):
        data = serializer.validated_data
        structure = data["structure"]
        institution = school().pk
        if (
            structure.institution_id != institution
            or data["employee"].institution_id != institution
        ):
            raise ValidationError("Use an employee and salary structure from this institution.")
        if (structure.effective_from and data["start_date"] < structure.effective_from) or (
            structure.effective_through and data["end_date"] > structure.effective_through
        ):
            raise ValidationError("The assignment must fit within the structure's effective dates.")
        if data["end_date"] < data["start_date"] or not structure.active:
            raise ValidationError("Select an active structure and a valid date range.")
        if (
            self.get_queryset()
            .filter(
                employee=data["employee"],
                start_date__lte=data["end_date"],
                end_date__gte=data["start_date"],
            )
            .exists()
        ):
            raise Conflict("An existing salary assignment covers these dates.")
        row = serializer.save(created_by=self.request.user)
        audit(self.request, "HR_SALARY_ASSIGNED", "salaryassignment", row)


class Periods(HRView):
    queryset = models.PayrollPeriod.objects.all()
    serializer_class = schema(models.PayrollPeriod)
    license_feature = "payroll"
    permission_map: ClassVar = {
        "list": "accounts.view_payroll",
        "retrieve": "accounts.view_payroll",
        "create": "accounts.generate_payroll",
    }

    def perform_create(self, serializer):
        data = serializer.validated_data
        if data["start_date"] > data["end_date"]:
            raise ValidationError("The payroll period dates are out of order.")
        if (
            self.get_queryset()
            .filter(start_date__lte=data["end_date"], end_date__gte=data["start_date"])
            .exists()
        ):
            raise Conflict("A payroll period already covers these dates.")
        super().perform_create(serializer)


class Advances(HRView):
    queryset = models.SalaryAdvance.objects.all()
    serializer_class = schema(
        models.SalaryAdvance, ("created_by", "approved_by", "disbursed_by", "disbursed_at")
    )
    institution_lookup = "employee__institution"
    license_feature = "payroll"
    permission_map: ClassVar = {
        "list": "accounts.view_salary_setup",
        "retrieve": "accounts.view_salary_setup",
        "create": "accounts.manage_salary_setup",
        "approve": "accounts.approve_salary_advance",
        "disburse": "accounts.pay_salary",
    }

    def perform_create(self, serializer):
        row = serializer.save(created_by=self.request.user)
        audit(self.request, "HR_ADVANCE_REQUESTED", "salaryadvance", row)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        def operation():
            row = self.get_object()
            if not row.approved_by_id:
                row.approved_by = request.user
                row.save()
                audit(request, "HR_ADVANCE_APPROVED", "salaryadvance", row)
            return Response(self.get_serializer(row).data)

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def disburse(self, request, pk=None):
        def operation():
            row = self.get_object()
            if not row.approved_by_id:
                raise Conflict("Approve the advance before recording its disbursement.")
            if not row.disbursed_at:
                row.disbursed_by, row.disbursed_at = request.user, timezone.now()
                row.save()
                audit(request, "HR_ADVANCE_DISBURSED", "salaryadvance", row)
            return Response(self.get_serializer(row).data)

        return self.write(operation)


class Generate(serializers.Serializer):
    period = serializers.UUIDField()
    department = serializers.UUIDField(required=False, allow_null=True)
    key = serializers.UUIDField(required=False)
    preview_key = serializers.RegexField(r"^[a-f0-9]{64}$", required=False)


def wage_units(employee, start, end, basis):
    units = ZERO
    recorded = {
        row.date: row
        for row in models.EmployeeAttendance.objects.filter(
            employee=employee, date__range=(start, end)
        )
    }
    holidays, fallback = calendar_rules(employee, start, end)
    day = start
    while day <= end:
        contract = contract_for(employee, day)
        if not contract or not contract.weekdays:
            return None
        if scheduled_day(day, contract, holidays.get(day), fallback):
            row = recorded.get(day)
            if row is None:
                return None
            if row.status in {"present", "late"}:
                if basis == "daily":
                    units += 1
                else:
                    if row.check_in is None or row.check_out is None:
                        return None
                    delta = elapsed(row.check_in, row.check_out, overnight=is_overnight(contract))
                    seconds = max(0, delta.total_seconds() - contract.break_minutes * 60)
                    units += Decimal(str(seconds)) / Decimal(3600)
        day += timedelta(days=1)
    return units


def calendar_rules(employee, start, end):
    holidays = {
        row.date: row
        for row in AttendanceHoliday.objects.filter(
            institution=employee.institution, date__range=(start, end)
        )
    }
    settings = AttendanceSettings.objects.filter(institution=employee.institution).first()
    return holidays, settings.non_teaching_weekdays if settings else []


def unpaid_lines(employee, start, end, rate):
    if not rate:
        return []
    holidays, fallback = calendar_rules(employee, start, end)
    items = []
    for leave in models.EmployeeLeave.objects.filter(
        employee=employee,
        status="approved",
        leave_type__paid=False,
        start_date__lte=end,
        end_date__gte=start,
    ).order_by("start_date", "pk"):
        day = max(start, leave.start_date)
        days = 0
        while day <= min(end, leave.end_date):
            if scheduled_day(day, contract_for(employee, day), holidays.get(day), fallback):
                days += 1
            day += timedelta(days=1)
        if days:
            items.append(
                {
                    "label": "Unpaid leave",
                    "kind": "deduction",
                    "amount": str(round_money(rate * days)),
                    "days": days,
                    "rate": str(rate),
                    "leave": str(leave.pk),
                }
            )
    return items


def calculate(period, department):
    rows = models.Employee.objects.filter(
        institution=period.institution, joined_on__lte=period.end_date
    )
    rows = rows.filter(Q(ended_on__isnull=True) | Q(ended_on__gte=period.start_date))
    if department:
        rows = rows.filter(department=department)
    rows = rows.select_related("department", "designation").order_by("code")
    warnings, entries = [], []
    for row in rows:
        if models.PayrollEntry.objects.filter(period=period, employee=row).exists():
            warnings.append({"employee": row.code, "reason": "Already generated"})
            continue
        start = max(period.start_date, row.joined_on)
        end = min(period.end_date, row.ended_on or period.end_date)
        assignment = (
            models.SalaryAssignment.objects.filter(
                employee=row, start_date__lte=start, end_date__gte=end, structure__active=True
            )
            .select_related("structure")
            .first()
        )
        if not assignment:
            warnings.append(
                {
                    "employee": row.code,
                    "reason": "No salary assignment covers this employment interval",
                }
            )
            continue
        structure = assignment.structure
        factor = Decimal(1)
        if structure.basis in {"daily", "hourly"}:
            factor = wage_units(row, start, end, structure.basis)
            if factor is None:
                warnings.append(
                    {"employee": row.code, "reason": "Working schedule or attendance is incomplete"}
                )
                continue
        elif structure.prorate:
            factor = Decimal((end - start).days + 1) / Decimal(
                (period.end_date - period.start_date).days + 1
            )
        basic = round_money(structure.basic * factor)
        lines = [
            {"label": item.label, "kind": item.kind, "amount": str(item.amount)}
            for item in structure.components.order_by("id")
        ]
        lines.extend(
            models.StaffOvertime.objects.filter(
                attendance__employee=row, attendance__date__range=(start, end), status="approved"
            )
            .order_by("attendance__date", "pk")
            .values_list("snapshot", flat=True)
        )
        lines.extend(unpaid_lines(row, start, end, structure.unpaid_leave_daily_rate))
        gross = basic + sum(
            (Decimal(item["amount"]) for item in lines if item["kind"] == "earning"), ZERO
        )
        deductions = sum(
            (Decimal(item["amount"]) for item in lines if item["kind"] == "deduction"), ZERO
        )
        recoveries = []
        for advance in models.SalaryAdvance.objects.filter(
            employee=row, disbursed_at__isnull=False, recover_from__lte=end
        ).order_by("created_at", "id"):
            recovered = advance.recoveries.aggregate(amount=Sum("amount"))["amount"] or ZERO
            amount = min(
                advance.installment, advance.amount - round_money(recovered), gross - deductions
            )
            if amount > ZERO:
                recoveries.append((advance, amount))
                deductions += amount
                lines.append(
                    {"label": "Advance recovery", "kind": "deduction", "amount": str(amount)}
                )
        if deductions > gross:
            warnings.append(
                {"employee": row.code, "reason": "Deductions exceed gross compensation"}
            )
            continue
        entries.append(
            (
                row,
                assignment,
                recoveries,
                {
                    "code": row.code,
                    "name": row.display_name or (row.first_name + " " + row.last_name).strip(),
                    "department": row.department.name,
                    "designation": row.designation.name,
                    "basic": str(basic),
                    "gross": str(gross),
                    "deductions": str(deductions),
                    "net": str(gross - deductions),
                    "items": lines,
                },
            )
        )
    return entries, warnings


def preview_key(entries):
    data = [
        (str(employee.pk), str(assignment.pk), snapshot)
        for employee, assignment, _, snapshot in entries
    ]
    return sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def write_entries(run, rows):
    for row, assignment, recoveries, snapshot in rows:
        entry = models.PayrollEntry.objects.create(
            run=run,
            period=run.period,
            employee=row,
            assignment=assignment,
            snapshot=snapshot,
            **{key: snapshot[key] for key in ("basic", "gross", "deductions", "net")},
        )
        models.AdvanceRecovery.objects.bulk_create(
            [
                models.AdvanceRecovery(advance=advance, entry=entry, amount=amount)
                for advance, amount in recoveries
            ]
        )


class Payroll(HRView):
    queryset = models.PayrollRun.objects.select_related("period")
    serializer_class = schema(models.PayrollRun, ("created_by",))
    institution_lookup = "period__institution"
    license_feature = "payroll"
    filterset_fields = ("period", "department", "status")
    permission_map: ClassVar = {
        "list": "accounts.view_payroll",
        "retrieve": "accounts.view_payroll",
        "preview": "accounts.generate_payroll",
        "generate": "accounts.generate_payroll",
        "recalculate": "accounts.generate_payroll",
        "submit": "accounts.submit_payroll",
        "review": "accounts.review_payroll",
        "approve": "accounts.approve_payroll",
        "finalize": "accounts.finalize_payroll",
        "return_draft": "accounts.review_payroll",
    }

    def scope(self, values):
        period = get_object_or_404(models.PayrollPeriod, pk=values["period"], institution=school())
        department = None
        if values.get("department"):
            department = get_object_or_404(
                models.Department, pk=values["department"], institution=school()
            )
        return period, department

    @action(detail=False, methods=["post"])
    def preview(self, request):
        entries, warnings = calculate(*self.scope(input_data(Generate, request)))
        return Response(
            {
                "entries": [entry[3] for entry in entries],
                "warnings": warnings,
                "preview_key": preview_key(entries),
            }
        )

    @action(detail=False, methods=["post"])
    def generate(self, request):
        def operation():
            values = input_data(Generate, request)
            period, department = self.scope(values)
            if not values.get("key"):
                raise ValidationError("Provide a generation request key.")
            if existing := self.get_queryset().filter(key=values["key"]).first():
                if existing.period_id != period.pk or existing.department != department:
                    raise Conflict("This generation key belongs to another payroll scope.")
                return Response(self.get_serializer(existing).data)
            entries, warnings = calculate(period, department)
            current = preview_key(entries)
            if values.get("preview_key", current) != current:
                raise Conflict(
                    "Payroll inputs changed after the preview. Preview the revised payroll."
                )
            if not entries:
                raise ValidationError(
                    {"warnings": warnings, "detail": "No new eligible payroll obligations."}
                )
            run = models.PayrollRun.objects.create(
                period=period, department=department, key=values["key"], created_by=request.user
            )
            write_entries(run, entries)
            audit(request, "HR_PAYROLL_GENERATED", "payrollrun", run, count=len(entries))
            return Response(
                dict(self.get_serializer(run).data) | {"warnings": warnings}, status=201
            )

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def recalculate(self, request, pk=None):
        def operation():
            run = self.get_object()
            if run.status != "draft":
                raise Conflict("Only draft payroll can be recalculated.")
            models.AdvanceRecovery.objects.filter(entry__run=run).delete()
            run.entries.all().delete()
            rows, warnings = calculate(run.period, run.department)
            if not rows:
                raise ValidationError(
                    {"warnings": warnings, "detail": "No eligible draft payroll entries."}
                )
            write_entries(run, rows)
            models.PayrollApproval.objects.create(
                run=run, status="draft", reason="Draft recalculated", actor=request.user
            )
            audit(request, "HR_PAYROLL_RECALCULATED", "payrollrun", run, count=len(rows))
            return Response(dict(self.get_serializer(run).data) | {"warnings": warnings})

        return self.write(operation)

    def retrieve(self, request, *args, **kwargs):
        run = self.get_object()
        rows = self.paginate_queryset(run.entries.order_by("id"))
        return Response(
            dict(self.get_serializer(run).data)
            | {
                "entries": self.get_paginated_response(
                    [
                        {"id": row.pk, "outstanding": str(payable(row)), **row.snapshot}
                        for row in rows
                    ]
                ).data,
                "decisions": list(
                    run.decisions.order_by("created_at").values(
                        "id", "status", "created_at", "actor_id", "reason"
                    )
                ),
            }
        )

    def move(self, request, source, next_status):
        def operation():
            row = self.get_object()
            if row.status == next_status:
                return Response(self.get_serializer(row).data)
            if row.status not in source:
                raise Conflict("This payroll cannot advance from its current state.")
            if (
                next_status == "approved"
                and row.period.separate_approver
                and row.created_by_id == request.user.pk
            ):
                raise PermissionDenied("A separate operator must approve this payroll.")
            reason = serializers.CharField(max_length=400, allow_blank=True).run_validation(
                request.data.get("reason", "")
            )
            if next_status == "draft" and not reason:
                raise ValidationError("Enter a reason for returning payroll.")
            row.status = next_status
            row.save(update_fields=["status", "updated_at"])
            models.PayrollApproval.objects.create(
                run=row, status=next_status, actor=request.user, reason=reason
            )
            audit(request, "HR_PAYROLL_" + next_status.upper(), "payrollrun", row)
            return Response(self.get_serializer(row).data)

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self.move(request, {"draft"}, "submitted")

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        return self.move(request, {"submitted"}, "reviewed")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.move(request, {"reviewed"}, "approved")

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        return self.move(request, {"approved"}, "finalized")

    @action(detail=True, methods=["post"], url_path="return")
    def return_draft(self, request, pk=None):
        return self.move(request, {"submitted", "reviewed", "approved"}, "draft")


class PaymentInput(serializers.Serializer):
    entry = serializers.UUIDField()
    key = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    date = serializers.DateField()
    method = serializers.ChoiceField(
        choices=["cash", "bank_transfer", "cheque", "digital_transfer", "other"]
    )
    external_reference = serializers.CharField(max_length=100, allow_blank=True, default="")


class Payments(HRView):
    queryset = models.SalaryPayment.objects.all()
    serializer_class = schema(models.SalaryPayment, ("recorded_by",))
    institution_lookup = "entry__period__institution"
    license_feature = "payroll"
    filterset_fields = ("entry", "date", "method", "entry__employee")
    permission_map: ClassVar = {
        "list": "accounts.view_payroll",
        "retrieve": "accounts.view_payroll",
        "create": "accounts.pay_salary",
        "reverse": "accounts.correct_payroll",
    }

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        def operation():
            row = self.get_object()
            reason = serializers.CharField(max_length=400).run_validation(
                request.data.get("reason")
            )
            reversal, created = models.SalaryPaymentReversal.objects.get_or_create(
                payment=row, defaults={"reason": reason, "approved_by": request.user}
            )
            if created:
                audit(request, "HR_SALARY_PAYMENT_REVERSED", "salarypayment", row)
            return Response({"id": reversal.pk, "status": "reversed"})

        return self.write(operation)

    def create(self, request, *args, **kwargs):
        def operation():
            values = input_data(PaymentInput, request)
            entry = get_object_or_404(
                models.PayrollEntry, pk=values.pop("entry"), period__institution=school()
            )
            if existing := self.get_queryset().filter(key=values["key"]).first():
                if existing.entry_id != entry.pk or any(
                    getattr(existing, key) != value for key, value in values.items()
                ):
                    raise Conflict("The payment key belongs to another submission.")
                return Response(self.get_serializer(existing).data)
            if entry.run.status != "finalized":
                raise Conflict("Finalize payroll before recording payments.")
            if values["date"] > today() or values["amount"] > payable(entry):
                raise ValidationError(
                    "Payment must fall within the outstanding balance and use a date through today."
                )
            row = models.SalaryPayment.objects.create(
                entry=entry, recorded_by=request.user, **values
            )
            audit(request, "HR_SALARY_PAYMENT_RECORDED", "salarypayment", row)
            return Response(self.get_serializer(row).data, status=201)

        return self.write(operation)


class AdjustmentInput(serializers.Serializer):
    entry = serializers.UUIDField()
    key = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reason = serializers.CharField(max_length=400)


class Adjustments(HRView):
    queryset = models.PayrollAdjustment.objects.all()
    serializer_class = schema(models.PayrollAdjustment, ("approved_by",))
    institution_lookup = "entry__period__institution"
    license_feature = "payroll"
    permission_map: ClassVar = {
        "list": "accounts.view_payroll",
        "retrieve": "accounts.view_payroll",
        "create": "accounts.correct_payroll",
    }

    def create(self, request, *args, **kwargs):
        def operation():
            values = input_data(AdjustmentInput, request)
            entry = get_object_or_404(
                models.PayrollEntry, pk=values.pop("entry"), period__institution=school()
            )
            if existing := self.get_queryset().filter(key=values["key"]).first():
                if existing.entry_id != entry.pk or any(
                    getattr(existing, key) != value for key, value in values.items()
                ):
                    raise Conflict("The adjustment key belongs to another submission.")
                return Response(self.get_serializer(existing).data)
            if (
                entry.run.status != "finalized"
                or values["amount"] == ZERO
                or payable(entry) + values["amount"] < ZERO
            ):
                raise ValidationError(
                    "An adjustment requires finalized payroll and a nonnegative payable balance."
                )
            row = models.PayrollAdjustment.objects.create(
                entry=entry, approved_by=request.user, **values
            )
            audit(request, "HR_PAYROLL_ADJUSTED", "payrolladjustment", row)
            return Response(self.get_serializer(row).data, status=201)

        return self.write(operation)

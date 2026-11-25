from typing import ClassVar

from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.academics.access import Conflict, school
from apps.accounts.authentication import audit
from apps.attendance.models import AttendanceHoliday

from . import models
from .api import HRView, contract_for, employment, schema
from .payroll import round_money


class Policies(HRView):
    queryset = models.OvertimePolicy.objects.all()
    serializer_class = schema(models.OvertimePolicy)
    license_feature = "payroll"
    permission_map: ClassVar = {
        "list": "accounts.view_payroll",
        "retrieve": "accounts.view_payroll",
        "create": "accounts.generate_payroll",
    }

    def perform_create(self, serializer):
        data = serializer.validated_data
        if data["start_date"] > data["end_date"]:
            raise ValidationError("The policy dates are out of order.")
        if not 0 <= data.get("minimum_hours", 0) <= data["maximum_hours"] <= 24:
            raise ValidationError("Set minimum and maximum hours between zero and 24.")
        if any(
            data.get(field, 1) <= 0
            for field in ("regular_multiplier", "rest_multiplier", "holiday_multiplier")
        ):
            raise ValidationError("Set positive overtime multipliers.")
        if data.get("monthly_divisor") is not None:
            if data["monthly_divisor"] <= 0:
                raise ValidationError("Set a positive monthly divisor.")
        elif data["rate"] <= 0:
            raise ValidationError("Set a positive hourly rate.")
        super().perform_create(serializer)


class Requests(HRView):
    queryset = models.StaffOvertime.objects.select_related("attendance__employee", "policy")
    serializer_class = schema(
        models.StaffOvertime,
        ("requested_by",),
        (
            "status",
            "decided_by",
            "decided_at",
            "decision_reason",
            "snapshot",
        ),
    )
    institution_lookup = "attendance__employee__institution"
    license_feature = "payroll"
    permission_map: ClassVar = {
        "list": "accounts.view_payroll",
        "retrieve": "accounts.view_payroll",
        "create": "accounts.generate_payroll",
        "decision": "accounts.approve_payroll",
    }
    filterset_fields = ("attendance__employee", "status")

    def perform_create(self, serializer):
        values = serializer.validated_data
        attendance, policy = values["attendance"], values["policy"]
        if (
            attendance.employee.institution_id != school().pk
            or policy.institution_id != school().pk
        ):
            raise ValidationError("Choose an attendance record and policy for this institution.")
        if not policy.start_date <= attendance.date <= policy.end_date:
            raise ValidationError("The policy must cover the attendance date.")
        if not employment(attendance.employee, attendance.date):
            raise ValidationError("The attendance date must fall within employment.")
        hours = values["requested_hours"]
        if not 0 < hours <= policy.maximum_hours or hours < policy.minimum_hours:
            raise ValidationError("Requested hours are outside the policy limits.")
        row = serializer.save(requested_by=self.request.user)
        audit(self.request, "HR_OVERTIME_REQUESTED", "staffovertime", row)

    @action(detail=True, methods=["post"])
    def decision(self, request, pk=None):
        def operation():
            row = self.get_object()
            if row.status != "pending":
                raise Conflict("This overtime request has already been decided.")
            if row.policy.separate_approver and row.requested_by_id == request.user.pk:
                raise ValidationError("A different user must decide this request.")
            target = serializers.ChoiceField(("approved", "rejected")).run_validation(
                request.data.get("status")
            )
            reason = serializers.CharField(max_length=400).run_validation(
                request.data.get("reason")
            )
            if target == "approved":
                hours = serializers.DecimalField(max_digits=5, decimal_places=2).run_validation(
                    request.data.get("hours")
                )
                if not 0 < hours <= row.requested_hours or hours < row.policy.minimum_hours:
                    raise ValidationError(
                        "Approved hours are outside the request or policy limits."
                    )
                row.snapshot = earnings(row, hours, request.user)
            row.status = target
            row.decided_by = request.user
            row.decided_at = timezone.now()
            row.decision_reason = reason
            row.save()
            audit(request, "HR_OVERTIME_" + target.upper(), "staffovertime", row)
            return Response(self.get_serializer(row).data)

        return self.write(operation)


def earnings(row, hours, reviewer):
    policy, attendance = row.policy, row.attendance
    employee, day = attendance.employee, attendance.date
    rate = policy.rate
    if policy.monthly_divisor is not None:
        salary = (
            models.SalaryAssignment.objects.filter(
                employee=employee,
                start_date__lte=day,
                end_date__gte=day,
                structure__basis="monthly",
                structure__active=True,
            )
            .select_related("structure")
            .first()
        )
        if not salary:
            raise ValidationError(
                "An active monthly salary is required for salary-derived overtime."
            )
        rate = salary.structure.basic / policy.monthly_divisor
    holiday = AttendanceHoliday.objects.filter(institution=employee.institution, date=day).first()
    contract = contract_for(employee, day)
    kind = "regular"
    if holiday and holiday.kind != "working":
        kind = "holiday"
    elif not holiday and contract and contract.weekdays and day.weekday() not in contract.weekdays:
        kind = "rest"
    multiplier = getattr(policy, kind + "_multiplier")
    return {
        "label": "Overtime",
        "kind": "earning",
        "amount": str(round_money(hours * rate * multiplier)),
        "hours": str(hours),
        "rate": str(rate),
        "multiplier": str(multiplier),
        "day_type": kind,
        "overtime": str(row.pk),
        "attendance": str(attendance.pk),
        "policy": str(policy.pk),
        "approved_by": str(reviewer.pk),
        "date": day.isoformat(),
    }

from decimal import Decimal
from typing import ClassVar

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.academics.access import Conflict, school
from apps.accounts.authentication import audit

from . import models
from .accrual import accrual_plan, balance, post_plan, transactions
from .api import HRView, input_data, schema, today
from .leave_policy import (
    TERM_FIELDS,
    ensure_initial_version,
    policy_terms,
    resolve_effective_leave_policy,
)


class Policy(HRView):
    queryset = models.LeaveType.objects.all()
    serializer_class = schema(models.LeaveType)
    permission_map: ClassVar = {
        "list": "accounts.view_staff_leave",
        "retrieve": "accounts.view_staff_leave",
        "create": "accounts.manage_hr_registry",
        "partial_update": "accounts.manage_hr_registry",
        "versions": "accounts.view_staff_leave",
        "save_version": "accounts.manage_hr_registry",
        "withdraw_version": "accounts.manage_hr_registry",
    }

    def validate_policy(self, serializer):
        values = serializer.validated_data
        for field in ("annual_days", "carry_limit", "maximum_balance"):
            if values.get(field) is not None and values[field] < 0:
                raise ValidationError({field: "Enter zero or a positive amount."})
        if values.get("carry_expiry_days", 0) > 364:
            raise ValidationError({"carry_expiry_days": "Use at most 364 days from January 1."})

    def perform_create(self, serializer):
        self.validate_policy(serializer)
        super().perform_create(serializer)
        ensure_initial_version(serializer.instance, self.request.user)

    def perform_update(self, serializer):
        self.validate_policy(serializer)
        policy = serializer.instance
        changes = serializer.validated_data
        initial = ensure_initial_version(policy, self.request.user)
        used = (
            models.LeaveBalanceTransaction.objects.filter(leave_type=policy).exists()
            or models.EmployeeLeave.objects.filter(leave_type=policy).exists()
            or policy.versions.exclude(pk=initial.pk).exists()
        )
        revised = policy_terms(policy, changes)
        if used and (revised != initial.terms or changes.get("code", policy.code) != policy.code):
            raise Conflict("Schedule a policy revision to change terms for future periods.")
        super().perform_update(serializer)
        if initial.terms != revised:
            initial.terms = revised
            initial.save(update_fields=["terms", "updated_at"])

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        return Response(self.version_history(self.get_object()))

    @staticmethod
    def version_history(policy):
        now = today()
        result = []
        boundary = None
        for row in policy.versions.order_by("-effective_start"):
            if not row.published:
                status = "draft"
            elif row.effective_start > now:
                status = "scheduled"
            elif boundary and boundary <= now:
                status = "historical"
            else:
                status = "effective" if row.terms["active"] else "inactive"
            result.append(
                {
                    "id": row.pk,
                    "effective_start": row.effective_start,
                    "status": status,
                    "effective_end_exclusive": boundary if row.published else None,
                    "terms": row.terms,
                    "created_at": row.created_at,
                    "created_by": row.created_by_id,
                }
            )
            if row.published:
                boundary = row.effective_start
        return result

    @versions.mapping.post
    def save_version(self, request, pk=None):
        def operation():
            policy = self.get_object()
            ensure_initial_version(policy, request.user)
            start = serializers.DateField().run_validation(request.data.get("effective_start"))
            draft = serializers.BooleanField().run_validation(request.data.get("draft", False))
            if start <= today():
                raise ValidationError("Use a future effective date.")
            changes = request.data.get("terms")
            if not isinstance(changes, dict) or set(changes) - set(TERM_FIELDS):
                raise ValidationError("Provide supported policy terms.")
            latest = policy.versions.filter(published=True).latest("effective_start")
            if start <= latest.effective_start:
                raise Conflict("The revision must follow the latest scheduled policy.")
            serializer = self.get_serializer(policy, data={**latest.terms, **changes}, partial=True)
            serializer.is_valid(raise_exception=True)
            self.validate_policy(serializer)
            terms = policy_terms(policy, serializer.validated_data)
            annual = {"annual", "fixed", "legacy"}
            if start.day != 1 or (
                start.month != 1 and {latest.terms["accrual_mode"], terms["accrual_mode"]} & annual
            ):
                raise ValidationError(
                    "Use the first of a month, or January 1 for annual, fixed or legacy policies."
                )
            if models.LeaveBalanceTransaction.objects.filter(
                leave_type=policy,
                effective_date__gte=start,
                event__in=("accrual", "carry", "expiration"),
            ).exists():
                raise Conflict("An accrual period at or after this date has already been posted.")
            version, created = policy.versions.update_or_create(
                effective_start=start,
                defaults={"terms": terms, "published": not draft, "created_by": request.user},
            )
            audit(request, "HR_LEAVE_VERSION_SAVED", "leavepolicyversion", version, draft=draft)
            return Response(self.version_history(policy), status=201 if created else 200)

        return self.write(operation)

    @action(detail=True, methods=["post"], url_path="withdraw-version")
    def withdraw_version(self, request, pk=None):
        def operation():
            policy = self.get_object()
            key = serializers.UUIDField().run_validation(request.data.get("version"))
            version = get_object_or_404(policy.versions, pk=key, published=True)
            if version.effective_start <= today() or version.leavebalancetransaction_set.exists():
                raise Conflict("Only an unused scheduled version can be withdrawn.")
            if policy.versions.filter(
                published=True, effective_start__gt=version.effective_start
            ).exists():
                raise Conflict("Withdraw the latest scheduled version first.")
            version.published = False
            version.save(update_fields=["published", "updated_at"])
            audit(request, "HR_LEAVE_VERSION_WITHDRAWN", "leavepolicyversion", version)
            return Response(self.version_history(policy))

        return self.write(operation)


class Parameters(serializers.Serializer):
    employee = serializers.UUIDField()
    leave_type = serializers.UUIDField()
    through = serializers.DateField()


class Adjustment(Parameters):
    kind = serializers.ChoiceField(("opening", "adjustment"))
    key = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=7, decimal_places=2)
    reason = serializers.CharField(max_length=400)


def context(values, *, preview=False):
    institution = school()
    employee = get_object_or_404(models.Employee, institution=institution, pk=values["employee"])
    policy = get_object_or_404(models.LeaveType, institution=institution, pk=values["leave_type"])
    day = values["through"]
    terms, _ = resolve_effective_leave_policy(policy, day)
    if not terms.paid or terms.accrual_mode == "legacy":
        raise ValidationError("Choose a paid leave type with a ledger policy.")
    if (day > today() and not preview) or day.year < employee.joined_on.year:
        raise ValidationError("Choose an elapsed date in the employee's service history.")
    return employee, policy, day


class Balances(HRView):
    permission_map: ClassVar = {
        "list": "accounts.view_staff_leave",
        "apply": "accounts.approve_staff_leave",
        "adjust": "accounts.approve_staff_leave",
    }

    def list(self, request):
        form = Parameters(data=request.query_params)
        form.is_valid(raise_exception=True)
        employee, policy, day = context(
            form.validated_data, preview=request.query_params.get("preview") == "1"
        )
        records = transactions(employee, policy).filter(
            effective_date__year=day.year, effective_date__lte=day
        )
        terms, version = resolve_effective_leave_policy(policy, day)
        return Response(
            {
                "policy_version": version.pk if version else None,
                "annual_entitlement": terms.annual_days,
                "balance": balance(employee, policy, day.year, through=day),
                "preview": accrual_plan(employee, policy, day),
                "ledger": schema(models.LeaveBalanceTransaction, ())(
                    records.order_by("effective_date", "created_at", "pk"), many=True
                ).data,
            }
        )

    @action(detail=False, methods=["post"])
    def apply(self, request):
        def operation():
            employee, policy, day = context(input_data(Parameters, request))
            rows = post_plan(employee, policy, day, request.user)
            audit(request, "HR_LEAVE_ACCRUAL_APPLIED", "employee", employee, count=len(rows))
            return Response({"posted": len(rows), "balance": balance(employee, policy, day.year)})

        return self.write(operation)

    @action(detail=False, methods=["post"])
    def adjust(self, request):
        def operation():
            values = input_data(Adjustment, request)
            employee, policy, day = context(values)
            event, amount = values["kind"], values["amount"]
            records = transactions(employee, policy)
            key = str(values["key"])
            found = records.filter(key=key).first()
            if found:
                if (found.event, found.amount, found.effective_date, found.reason) != (
                    event,
                    amount,
                    day,
                    values["reason"],
                ):
                    raise Conflict("This adjustment key was already used.")
                return Response(schema(models.LeaveBalanceTransaction, ())(found).data)
            if not amount or (
                event == "opening"
                and (
                    amount < 0
                    or records.filter(event="opening", effective_date__year=day.year).exists()
                )
            ):
                raise ValidationError("Use a nonzero amount and one positive opening per year.")
            terms, version = resolve_effective_leave_policy(policy, day)
            if not terms.allow_negative and balance(employee, policy, day.year) + amount < Decimal(
                0
            ):
                raise Conflict("This adjustment would create a negative balance.")
            row = records.create(
                employee=employee,
                leave_type=policy,
                effective_date=day,
                event=event,
                policy_version=version,
                amount=amount,
                key=key,
                reason=values["reason"],
                recorded_by=request.user,
            )
            audit(request, "HR_LEAVE_BALANCE_ADJUSTED", "leavebalancetransaction", row)
            return Response(schema(models.LeaveBalanceTransaction, ())(row).data, status=201)

        return self.write(operation)

from calendar import monthrange
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum

from . import models
from .leave_policy import ensure_initial_version, resolve_effective_leave_policy

CENT = Decimal("0.01")


def transactions(employee, policy):
    return models.LeaveBalanceTransaction.objects.filter(employee=employee, leave_type=policy)


def balance(employee, policy, year, *, through=None):
    records = transactions(employee, policy).filter(effective_date__year=year)
    historical = models.EmployeeLeave.objects.filter(
        employee=employee,
        leave_type=policy,
        status="approved",
        start_date__year=year,
        balance_events__isnull=True,
    )
    if through:
        records = records.filter(effective_date__lte=through)
        historical = historical.filter(start_date__lte=through)
    total = records.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    return total - (historical.aggregate(total=Sum("days"))["total"] or 0)


def accrual_plan(employee, policy, through):
    year = through.year
    first, last = date(year, 1, 1), date(year, 12, 31)
    records = transactions(employee, policy)
    existing = set(records.values_list("key", flat=True))
    total = balance(employee, policy, year)
    versions = list(policy.versions.filter(published=True).order_by("-effective_start"))
    year_terms, year_version = resolve_effective_leave_policy(policy, first, versions)
    eligible_start = max(employee.joined_on, year_terms.accrual_start or first)
    eligible_end = employee.ended_on or last
    entries = []

    def add(event, key, effective, amount, terms, version, calculation):
        nonlocal total
        if key in existing or effective > through or not amount:
            return
        if event in {"accrual", "carry"} and terms.maximum_balance is not None:
            amount = min(amount, max(0, terms.maximum_balance - total))
        amount = Decimal(amount).quantize(CENT, rounding=ROUND_HALF_UP)
        if amount:
            entries.append(
                {
                    "event": event,
                    "key": key,
                    "effective_date": effective,
                    "amount": amount,
                    "policy_version_id": version.pk if version else None,
                    "calculation": calculation,
                }
            )
            total += amount

    if eligible_start <= first <= eligible_end and year_terms.active and year_terms.carry_limit:
        previous = min(year_terms.carry_limit, max(0, balance(employee, policy, year - 1)))
        existing_carry = records.filter(key=f"carry:{year}").first()
        if previous:
            add(
                "carry",
                f"carry:{year}",
                first,
                previous,
                year_terms,
                year_version,
                {"carry_limit": str(year_terms.carry_limit)},
            )
        carried = (
            existing_carry.amount
            if existing_carry
            else next(
                (entry["amount"] for entry in entries if entry["event"] == "carry"), Decimal(0)
            )
        )
        if year_terms.carry_expiry_days and carried:
            expiry = first + timedelta(days=year_terms.carry_expiry_days)
            used = (
                models.EmployeeLeave.objects.filter(
                    employee=employee,
                    leave_type=policy,
                    status="approved",
                    start_date__gte=first,
                    start_date__lt=expiry,
                ).aggregate(total=Sum("days"))["total"]
                or 0
            )
            add(
                "expiration",
                f"expire:{year}",
                expiry,
                -max(0, carried - used),
                year_terms,
                year_version,
                {"carried": str(carried), "used": used},
            )

    contracts = list(
        models.EmploymentContract.objects.filter(
            employee=employee,
            active=True,
            start_date__lte=last,
            end_date__gte=first,
        ).order_by("-start_date", "-pk")
    )
    for month in range(1, through.month + 1):
        start = date(year, month, 1)
        terms, version = resolve_effective_leave_policy(policy, start, versions)
        mode = terms.accrual_mode
        if not terms.active or not terms.paid or mode not in ("annual", "fixed", "monthly"):
            continue
        if mode != "monthly" and month != 1:
            continue
        end = date(year, month, monthrange(year, month)[1]) if mode == "monthly" else last
        effective_start = max(start, employee.joined_on, terms.accrual_start or first)
        days = (min(end, eligible_end) - effective_start).days + 1
        if days <= 0:
            continue
        contract = next(
            (row for row in contracts if row.start_date <= effective_start <= row.end_date), None
        )
        override = contract.leave_entitlements.get(policy.code.casefold()) if contract else None
        annual = Decimal(override if override is not None else terms.annual_days)
        amount = annual / (12 if mode == "monthly" else 1)
        period_days = (end - start).days + 1
        if terms.prorate and mode != "fixed":
            amount *= Decimal(days) / period_days
        effective = end if mode == "monthly" else effective_start
        add(
            "accrual",
            f"accrual:{year}:{month:02d}",
            effective,
            amount,
            terms,
            version,
            {
                "period_start": str(start),
                "period_end": str(end),
                "mode": mode,
                "annual_entitlement": str(annual),
                "eligible_days": days,
                "period_days": period_days,
                "contract": str(contract.pk) if contract else None,
                "contract_override": str(override) if override is not None else None,
            },
        )
    return entries


def post_plan(employee, policy, through, actor):
    ensure_initial_version(policy)
    entries = accrual_plan(employee, policy, through)
    return models.LeaveBalanceTransaction.objects.bulk_create(
        [
            models.LeaveBalanceTransaction(
                employee=employee, leave_type=policy, recorded_by=actor, **entry
            )
            for entry in entries
        ]
    )


def post_leave(row, event, actor, reason):
    amount = -row.days if event == "consumption" else row.days
    return models.LeaveBalanceTransaction.objects.create(
        employee=row.employee,
        leave_type=row.leave_type,
        leave=row,
        policy_version=resolve_effective_leave_policy(row.leave_type, row.start_date)[1],
        effective_date=row.start_date,
        amount=amount,
        event=event,
        key=f"{event}:{row.pk}",
        recorded_by=actor,
        reason=reason,
    )

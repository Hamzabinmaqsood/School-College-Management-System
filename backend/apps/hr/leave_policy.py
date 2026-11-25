from datetime import date
from types import SimpleNamespace

from .models import LeaveType

TERM_FIELDS = (
    "paid",
    "annual_days",
    "accrual_mode",
    "accrual_start",
    "prorate",
    "carry_limit",
    "carry_expiry_days",
    "maximum_balance",
    "allow_negative",
    "active",
)


def policy_terms(policy, changes=None):
    values = {field: getattr(policy, field) for field in TERM_FIELDS}
    values.update({key: value for key, value in (changes or {}).items() if key in values})
    for field in ("accrual_start", "carry_limit", "maximum_balance"):
        if values[field] is not None:
            values[field] = str(values[field])
    return values


def resolve_effective_leave_policy(policy, effective, versions=None):
    if versions is None:
        versions = policy.versions.filter(published=True).order_by("-effective_start")
    version = next((row for row in versions if row.effective_start <= effective), None)
    if version is None:
        return policy, None
    terms = {
        key: LeaveType._meta.get_field(key).to_python(value) for key, value in version.terms.items()
    }
    return SimpleNamespace(**terms), version


def ensure_initial_version(policy, actor=None):
    return policy.versions.get_or_create(
        effective_start=date.min,
        defaults={"terms": policy_terms(policy), "published": True, "created_by": actor},
    )[0]

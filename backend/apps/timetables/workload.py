from datetime import timedelta
from itertools import pairwise

from rest_framework.exceptions import ValidationError

from . import models, service


def minutes(value):
    return value.hour * 60 + value.minute


def breaches(policy, lessons, day):
    today = sorted((period for date, period in lessons if date == day), key=lambda p: p.starts_at)
    if policy.weekly_max is not None and len(lessons) > policy.weekly_max:
        return "weekly teaching limit"
    if policy.daily_max is not None and len(today) > policy.daily_max:
        return "daily teaching limit"
    if today and policy.consecutive_max == 0:
        return "consecutive teaching limit"
    consecutive = 1
    for earlier, later in pairwise(today):
        gap = minutes(later.starts_at) - minutes(earlier.ends_at)
        consecutive = consecutive + 1 if gap == 0 else 1
        if policy.rest_minutes and gap < policy.rest_minutes:
            return "minimum rest interval"
        if policy.consecutive_max is not None and consecutive > policy.consecutive_max:
            return "consecutive teaching limit"
    return None


def lessons_in_week(slot, day, *, draft, omit=None):
    week = day - timedelta(days=day.weekday())
    version = slot.version
    result = []
    draft_entries = (
        list(
            version.entries.filter(teacher=slot.teacher)
            .exclude(pk=slot.pk)
            .select_related("period")
        )
        if draft
        else []
    )
    for offset in range(7):
        date = week + timedelta(days=offset)
        uses_draft = draft and version.effective_start <= date <= version.effective_end
        for entry, period, teacher, _, change in service.daily(version.plan.institution, date):
            if teacher.pk != slot.teacher_id or service.inactive(change, date):
                continue
            if omit == (entry.pk, date) or (
                uses_draft and entry.version.plan_id == version.plan_id
            ):
                continue
            result.append((date, period))
        if uses_draft and service.working_date(version.plan, date):
            result.extend(
                (date, entry.period) for entry in draft_entries if entry.weekday == date.weekday()
            )
            if date.weekday() == slot.weekday:
                result.append((date, slot.period))
    if not draft:
        result.append((day, slot.period))
    return result


def check(slot, *, date=None, omit=None):
    start = date or service.first_on(slot.version.effective_start, slot.weekday)
    end = date or slot.version.effective_end
    policies = list(
        models.WorkloadPolicy.objects.filter(
            institution=slot.version.plan.institution,
            teacher=slot.teacher,
            effective_start__lte=end,
            effective_end__gte=start,
        )
    )
    warnings = set()
    day = start
    while policies and day <= end:
        applicable = [
            policy for policy in policies if policy.effective_start <= day <= policy.effective_end
        ]
        if applicable and service.working_date(slot.version.plan, day):
            lessons = lessons_in_week(slot, day, draft=date is None, omit=omit)
            for policy in applicable:
                if issue := breaches(policy, lessons, day):
                    if policy.hard:
                        raise ValidationError(f"The teacher exceeds the configured {issue}.")
                    warnings.add(issue)
        day += timedelta(days=7)
    return sorted(warnings)

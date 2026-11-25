from django.db.models import Q

from apps.accounts.access import permission_codes

from .models import TeachingAssignment

BROAD = "accounts.scope_all_attendance"


def covered(queryset, day):
    return queryset.filter(
        Q(effective_start__isnull=True) | Q(effective_start__lte=day),
        Q(effective_end__isnull=True) | Q(effective_end__gte=day),
    )


def assignments_for(user, *, operational=False):
    from .service import today

    day = today()
    rows = TeachingAssignment.objects.filter(user=user, active=True, user__is_active=True)
    rows = rows.filter(
        Q(user__employee__isnull=True)
        | (
            Q(user__employee__status__in=("active", "on_leave"), user__employee__joined_on__lte=day)
            & (Q(user__employee__ended_on__isnull=True) | Q(user__employee__ended_on__gte=day))
        )
    )
    return covered(rows, day) if operational else rows


def dated_scope(assignment, field):
    scope = Q()
    if assignment.effective_start:
        scope &= Q(**{field + "__gte": assignment.effective_start})
    if assignment.effective_end:
        scope &= Q(**{field + "__lte": assignment.effective_end})
    return scope


def scoped(
    queryset, user, prefix="", *, leave=False, enrollment=False, operational=False, day=None
):
    if BROAD in permission_codes(user):
        return queryset
    groups = assignments_for(user, operational=operational or enrollment)
    if day is not None:
        groups = covered(groups, day)
    if leave or enrollment:
        groups = groups.filter(subject__isnull=True)
    condition = Q(pk__in=[])
    for assignment in groups:
        fields = {
            "session_id": assignment.session_id,
            "academic_class_id": assignment.academic_class_id,
            "section_id": assignment.section_id,
        }
        if not (leave or enrollment):
            fields.update(
                mode="period" if assignment.subject_id else "daily",
                subject_id=assignment.subject_id,
            )
        match = Q(**{prefix + key: value for key, value in fields.items()})
        if leave:
            match &= dated_scope(assignment, "start_date") & dated_scope(assignment, "end_date")
        elif not enrollment:
            match &= dated_scope(assignment, prefix + "date")
        condition |= match
    return queryset.filter(condition)


def group_allowed(user, values, *, operational=True):
    if BROAD in permission_codes(user):
        return True
    rows = assignments_for(user, operational=operational).filter(
        session=values["session"],
        academic_class=values["academic_class"],
        section=values.get("section"),
        subject=values.get("subject"),
    )
    for key in ("date", "end_date"):
        if key in values:
            rows = covered(rows, values[key])
    return rows.exists()

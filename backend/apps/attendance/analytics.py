from datetime import timedelta

from django.db.models import Count, Q
from rest_framework import serializers

from .models import MARKS

KEYS = [key for key, _ in MARKS]
FINAL = Q(register__status="finalized")
MARKED = ~Q(status="unmarked")
ATTENDED = (
    Q(status="present")
    | Q(status="late", register__late_attended=True)
    | Q(status="excused", register__excused_policy="attended")
)
DENOMINATOR = MARKED & ~Q(status="excused", register__excused_policy="exclude")


def metrics():
    return {
        "eligible": Count("pk"),
        "draft": Count("pk", filter=~FINAL),
        **{key: Count("pk", filter=FINAL & Q(status=key)) for key in KEYS},
        "attended": Count("pk", filter=FINAL & ATTENDED),
        "denominator": Count("pk", filter=FINAL & DENOMINATOR),
    }


def percentage(result):
    return result | {
        "percentage": round(100 * result["attended"] / result["denominator"], 1)
        if result["denominator"]
        else None
    }


def totals(rows):
    return percentage(rows.aggregate(**metrics()))


def grouped(rows, *columns):
    return [
        percentage(item) for item in rows.values(*columns).annotate(**metrics()).order_by(*columns)
    ]


class ReportCriteria(serializers.Serializer):
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    mode = serializers.ChoiceField(choices=["daily", "period"], required=False)
    session = serializers.UUIDField(required=False)
    academic_class = serializers.UUIDField(required=False)
    section = serializers.UUIDField(required=False)
    subject = serializers.UUIDField(required=False)
    student = serializers.UUIDField(required=False)
    report = serializers.ChoiceField(
        choices=["daily", "class", "monthly", "student", "subject", "percentage", "low", "leave"],
        required=False,
    )
    threshold = serializers.IntegerField(min_value=0, max_value=100, required=False)

    def validate(self, values):
        start, end = values.get("from_date"), values.get("to_date")
        if start and end and not start <= end <= start + timedelta(days=366):
            raise serializers.ValidationError("Enter an ordered date range up to 366 days.")
        return values

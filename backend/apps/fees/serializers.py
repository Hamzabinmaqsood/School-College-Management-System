from decimal import Decimal

from rest_framework import serializers

from apps.academics.access import school

from . import models


def positive():
    return serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))


class Category(serializers.ModelSerializer):
    class Meta:
        model = models.FeeCategory
        fields = (
            "id",
            "name",
            "code",
            "description",
            "recurrence",
            "active",
            "created_at",
            "updated_at",
        )


class StructureItem(serializers.ModelSerializer):
    class Meta:
        model = models.FeeStructureItem
        fields = ("category", "amount", "recurrence")


class Structure(serializers.ModelSerializer):
    items = StructureItem(many=True, allow_empty=False)

    class Meta:
        model = models.FeeStructure
        fields = (
            "id",
            "name",
            "session",
            "academic_class",
            "section",
            "start_date",
            "end_date",
            "status",
            "items",
            "created_at",
        )
        read_only_fields = ("status",)

    def validate(self, values):
        if self.instance and self.instance.status != "draft":
            raise serializers.ValidationError("Only draft structures can be edited.")
        institution = school()
        values = dict(values)
        current = self.instance
        term = values.get("session", getattr(current, "session", None))
        academic_class = values.get("academic_class", getattr(current, "academic_class", None))
        section = values.get("section", getattr(current, "section", None))
        start = values.get("start_date", getattr(current, "start_date", None))
        end = values.get("end_date", getattr(current, "end_date", None))
        items = values.get("items", [])
        if (
            term.institution_id != institution.pk
            or academic_class.institution_id != institution.pk
            or (section and section.academic_class_id != academic_class.pk)
            or not term.start_date <= start <= end <= term.end_date
        ):
            raise serializers.ValidationError(
                "Choose a valid placement and dates inside the session."
            )
        if len({row["category"].pk for row in items}) != len(items) or any(
            row["category"].institution_id != institution.pk or row["amount"] < 0 for row in items
        ):
            raise serializers.ValidationError("Use distinct categories and nonnegative amounts.")
        return values

    def create(self, values):
        items = values.pop("items")
        record = super().create(values)
        models.FeeStructureItem.objects.bulk_create(
            [models.FeeStructureItem(structure=record, **row) for row in items]
        )
        return record

    def update(self, record, values):
        items = values.pop("items", None)
        record = super().update(record, values)
        if items is not None:
            record.items.all().delete()
            models.FeeStructureItem.objects.bulk_create(
                [models.FeeStructureItem(structure=record, **row) for row in items]
            )
        return record


class Assignment(serializers.ModelSerializer):
    class Meta:
        model = models.StudentFeeAssignment
        fields = (
            "id",
            "enrollment",
            "structure",
            "category",
            "amount",
            "start_date",
            "end_date",
            "active",
        )

    def validate(self, values):
        base = self.instance
        if base and set(values) - {"active"}:
            raise serializers.ValidationError(
                "Retire the assignment and create a new dated version."
            )
        data = {
            field: values.get(field, getattr(base, field, None))
            for field in ("enrollment", "structure", "category", "amount", "start_date", "end_date")
        }
        enrollment, structure, category = data["enrollment"], data["structure"], data["category"]
        start, end = data["start_date"], data["end_date"]
        if (
            not enrollment
            or not start
            or not end
            or not enrollment.session.start_date <= start <= end <= enrollment.session.end_date
        ):
            raise serializers.ValidationError(
                "Choose enrollment and dates within the academic session."
            )
        if structure:
            if (
                category
                or data["amount"] is not None
                or structure.session_id != enrollment.session_id
                or structure.academic_class_id != enrollment.academic_class_id
                or structure.section_id not in (None, enrollment.section_id)
            ):
                raise serializers.ValidationError(
                    "Choose a compatible structure or a category override."
                )
        elif not category or data["amount"] is None or data["amount"] < 0:
            raise serializers.ValidationError(
                "Provide a category and a nonnegative override amount."
            )
        if (
            values.get("active", True)
            and models.StudentFeeAssignment.objects.filter(
                enrollment=enrollment,
                category=category,
                active=True,
                start_date__lte=end,
                end_date__gte=start,
            )
            .exclude(pk=getattr(base, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError("An assignment already covers these dates.")
        return values


class Concession(serializers.ModelSerializer):
    class Meta:
        model = models.StudentConcession
        fields = (
            "id",
            "student",
            "session",
            "category",
            "label",
            "kind",
            "value",
            "start_date",
            "end_date",
            "status",
            "approved_by",
        )
        read_only_fields = ("status", "approved_by")

    def validate(self, values):
        base = self.instance
        if base and base.status != "pending":
            raise serializers.ValidationError("Approved concessions are historical records.")
        current = {
            key: values.get(key, getattr(base, key, None))
            for key in ("kind", "value", "student", "session", "start_date", "end_date")
        }
        kind, value = current["kind"], current["value"]
        value = value if value is not None else Decimal("0")
        if (
            (kind == "full" and value != 0)
            or (kind == "percent" and not 0 < value <= 100)
            or (kind == "fixed" and value <= 0)
        ):
            raise serializers.ValidationError("Enter a valid concession amount or percentage.")
        session = current["session"]
        if (
            not session.start_date
            <= current["start_date"]
            <= current["end_date"]
            <= session.end_date
            or not current["student"].enrollments.filter(session=session).exists()
        ):
            raise serializers.ValidationError(
                "Choose an enrolled student and dates in the session."
            )
        return values


class Billing(serializers.Serializer):
    preview_key = serializers.RegexField(r"^[0-9a-f]{64}$", required=False)
    session = serializers.UUIDField()
    period = serializers.DateField()
    academic_class = serializers.UUIDField(required=False)
    section = serializers.UUIDField(required=False)
    structure = serializers.UUIDField(required=False)
    student = serializers.UUIDField(required=False)
    reference = serializers.SlugField(max_length=46, required=False)


class Allocation(serializers.Serializer):
    invoice = serializers.UUIDField()
    amount = positive()


class Payment(serializers.Serializer):
    student = serializers.UUIDField()
    date = serializers.DateField()
    amount = positive()
    method = serializers.SlugField(max_length=32)
    external_reference = serializers.CharField(max_length=90, allow_blank=True, default="")
    remarks = serializers.CharField(max_length=400, allow_blank=True, default="")
    idempotency_key = serializers.UUIDField()
    allocations = Allocation(many=True, allow_empty=False, max_length=100)


class Reason(serializers.Serializer):
    reason = serializers.CharField(max_length=400)


class Correction(Reason):
    idempotency_key = serializers.UUIDField()
    amount = positive()


class Adjustment(Correction):
    invoice = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["debit", "credit", "write_off"])


class Refund(Correction):
    allocation = serializers.UUIDField()
    date = serializers.DateField()


class Settings(serializers.ModelSerializer):
    payment_methods = serializers.ListField(
        child=serializers.SlugField(max_length=32), max_length=20
    )
    currency = serializers.ChoiceField(choices=["PKR"])
    due_day = serializers.IntegerField(min_value=1, max_value=31)
    billing_day = serializers.IntegerField(min_value=1, max_value=31)

    class Meta:
        model = models.FeeSettings
        exclude = ("institution", "created_at", "updated_at")

    def validate_payment_methods(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("Use each method once.")
        return values

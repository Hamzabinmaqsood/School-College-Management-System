from decimal import Decimal

from rest_framework import serializers

from apps.academics.access import school
from apps.attendance.service import assignment_for

from . import models


class ExamType(serializers.ModelSerializer):
    class Meta:
        model = models.ExamType
        exclude = ("institution",)


class Band(serializers.ModelSerializer):
    class Meta:
        model = models.GradeBand
        fields = ("label", "minimum", "points", "passing", "description")


class Scheme(serializers.ModelSerializer):
    bands = Band(many=True, allow_empty=False)

    class Meta:
        model = models.GradingScheme
        exclude = ("institution",)
        read_only_fields = ("version",)

    def validate(self, values):
        limits = [band["minimum"] for band in values["bands"]]
        points = [band.get("points") for band in values["bands"]]
        if min(limits) != 0 or len(set(limits)) != len(limits):
            raise serializers.ValidationError("Start grading at zero and use distinct boundaries.")
        if values["basis"] == "percentage" and max(limits) > 100:
            raise serializers.ValidationError("Percentage grades must be within 0 and 100.")
        if values["effective_to"] < values["effective_from"]:
            raise serializers.ValidationError("The effective dates are out of order.")
        if any(point is not None for point in points) and any(
            point is None or point < 0 for point in points
        ):
            raise serializers.ValidationError("Configure nonnegative points on every band or none.")
        return values

    def create(self, values):
        bands = values.pop("bands")
        versions = models.GradingScheme.objects.filter(
            institution=values["institution"], name=values["name"]
        ).order_by("-version")
        last = versions.first()
        row = super().create(values | {"version": last.version + 1 if last else 1})
        models.GradeBand.objects.bulk_create(
            [models.GradeBand(scheme=row, **band) for band in bands]
        )
        return row


class Exam(serializers.ModelSerializer):
    class Meta:
        model = models.Examination
        exclude = ("institution", "created_by")
        read_only_fields = ("status",)

    def validate(self, values):
        base = self.instance
        if base and base.status != "draft":
            raise serializers.ValidationError("Only draft examinations can be edited.")
        institution = school()
        session, exam_type, scheme, start, end = [
            values.get(key, getattr(base, key, None))
            for key in ("session", "exam_type", "scheme", "start_date", "end_date")
        ]
        if any(record.institution_id != institution.pk for record in (session, exam_type, scheme)):
            raise serializers.ValidationError("Choose this institution's configuration.")
        if not session.start_date <= start <= end <= session.end_date:
            raise serializers.ValidationError("Use dates within the academic session.")
        if not scheme.effective_from <= start <= end <= scheme.effective_to:
            raise serializers.ValidationError("Grading scheme dates must cover the exam.")
        if not exam_type.active:
            raise serializers.ValidationError("Choose an active exam type.")
        if (
            base
            and base.groups.exists()
            and (session.pk != base.session_id or start != base.start_date or end != base.end_date)
        ):
            raise serializers.ValidationError(
                "The session and dates are fixed once classes are assigned."
            )
        return values


class Group(serializers.ModelSerializer):
    class Meta:
        model = models.ExaminationClass
        fields = ("id", "exam", "academic_class")

    def validate(self, values):
        exam, academic_class = values["exam"], values["academic_class"]
        if exam.status != "draft" or academic_class.institution_id != exam.institution_id:
            raise serializers.ValidationError(
                "Select a class in this draft examination's institution."
            )
        return values


class Component(serializers.ModelSerializer):
    class Meta:
        model = models.ExamAssessmentComponent
        exclude = ("subject", "created_at", "updated_at")


class Subject(serializers.ModelSerializer):
    components = Component(many=True, allow_empty=False)

    class Meta:
        model = models.ExaminationSubject
        fields = (
            "id",
            "group",
            "subject",
            "scheme",
            "subject_name",
            "weighted",
            "optional",
            "passing_percentage",
            "components",
        )
        read_only_fields = ("subject_name",)

    def validate(self, values):
        if self.instance:
            supplied = {
                key: values.get(key, getattr(self.instance, key))
                for key in (
                    "group",
                    "subject",
                    "scheme",
                    "optional",
                    "weighted",
                    "passing_percentage",
                )
            }
            if (
                supplied["group"] != self.instance.group
                or supplied["subject"] != self.instance.subject
            ):
                raise serializers.ValidationError("The class and subject cannot change.")
            values = supplied | values
            values.setdefault(
                "components", Component(self.instance.components.all(), many=True).data
            )
            if "components" not in self.initial_data:
                form = Component(data=values["components"], many=True)
                form.is_valid(raise_exception=True)
                values["components"] = form.validated_data
        group, subject = values["group"], values["subject"]
        exam = group.exam
        curriculum = assignment_for(exam.session, group.academic_class, subject)
        if exam.status != "draft" or not curriculum or not curriculum.active:
            raise serializers.ValidationError(
                "Choose an active class-subject assignment in this draft."
            )
        if scheme := values.get("scheme"):
            if (
                scheme.institution_id != exam.institution_id
                or not scheme.effective_from
                <= exam.start_date
                <= exam.end_date
                <= scheme.effective_to
            ):
                raise serializers.ValidationError("Choose a scheme effective for this examination.")
        if not 0 <= values.get("passing_percentage", 0) <= 100:
            raise serializers.ValidationError("Passing percentage must be between 0 and 100.")
        components = values["components"]
        if len({row["name"].casefold() for row in components}) != len(components):
            raise serializers.ValidationError("Use distinct assessment component names.")
        for row in components:
            minimum = row.get("minimum")
            if row["maximum"] <= 0 or (minimum is not None and not 0 <= minimum <= row["maximum"]):
                raise serializers.ValidationError("Review component maximum and minimum marks.")
        weights = [row.get("weight") for row in components]
        if values.get("weighted"):
            if any(weight is None or weight <= 0 for weight in weights) or sum(weights) != Decimal(
                "100"
            ):
                raise serializers.ValidationError("Positive component weights must total 100.")
        elif any(weight is not None for weight in weights):
            raise serializers.ValidationError("Remove weights for raw-mark subjects.")
        return values | {
            "subject_name": subject.name,
            "optional": values.get("optional", False) or not curriculum.mandatory,
        }

    def create(self, values):
        components = values.pop("components")
        row = super().create(values)
        models.ExamAssessmentComponent.objects.bulk_create(
            [models.ExamAssessmentComponent(subject=row, **component) for component in components]
        )
        return row

    def update(self, row, values):
        components = values.pop("components")
        row = super().update(row, values)
        row.components.all().delete()
        models.ExamAssessmentComponent.objects.bulk_create(
            [models.ExamAssessmentComponent(subject=row, **item) for item in components]
        )
        return row


class Schedule(serializers.ModelSerializer):
    class Meta:
        model = models.ExamSchedule
        exclude = ("created_at", "updated_at")

    def validate(self, values):
        base = self.instance
        if base and base.subject.group.exam.status != "draft":
            raise serializers.ValidationError("Only draft schedules can be edited.")
        subject, day, start, end, room = [
            values.get(key, getattr(base, key, "" if key == "room" else None))
            for key in ("subject", "date", "start_time", "end_time", "room")
        ]
        exam = subject.group.exam
        if exam.status != "draft" or not exam.start_date <= day <= exam.end_date or end <= start:
            raise serializers.ValidationError(
                "Use an ordered time inside the draft examination dates."
            )
        from django.db.models import Q

        conflicts = models.ExamSchedule.objects.filter(
            subject__group__exam__institution=exam.institution,
            date=day,
            start_time__lt=end,
            end_time__gt=start,
        ).exclude(pk=getattr(base, "pk", None))
        scope = Q(subject__group__academic_class=subject.group.academic_class)
        if room:
            scope |= Q(room__iexact=room)
        if conflicts.filter(scope).exists():
            raise serializers.ValidationError("This class or room already has an overlapping exam.")
        return values


class Registration(serializers.Serializer):
    group = serializers.UUIDField()
    enrollment = serializers.UUIDField()
    optional_subjects = serializers.ListField(child=serializers.UUIDField(), default=list)
    excluded = serializers.BooleanField(default=False)
    reason = serializers.CharField(max_length=400)


class RegisterKey(serializers.Serializer):
    component = serializers.UUIDField()
    section = serializers.UUIDField(required=False, allow_null=True)


class Mark(serializers.Serializer):
    registration = serializers.UUIDField()
    status = serializers.ChoiceField(choices=models.STATUSES)
    obtained = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    remarks = serializers.CharField(max_length=300, allow_blank=True, default="")

    def validate(self, values):
        mark = values.get("obtained")
        if (values["status"] == "marked") != (mark is not None) or (mark is not None and mark < 0):
            raise serializers.ValidationError(
                "Enter a nonnegative score only for a marked assessment."
            )
        return values | {"obtained": mark}


class SaveMarks(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    marks = Mark(many=True, allow_empty=False, max_length=1000)


class Transition(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=400, required=False)


class Correction(Mark):
    component = serializers.UUIDField()
    reason = serializers.CharField(max_length=400)

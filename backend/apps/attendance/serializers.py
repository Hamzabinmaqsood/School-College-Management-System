from datetime import date

from django.db.models import Q
from rest_framework import serializers

from apps.academics.access import school
from apps.academics.models import AcademicClass, AcademicSession, Section, Subject
from apps.accounts.models import User

from .models import (
    MARKS,
    MODES,
    AttendanceHoliday,
    AttendanceSettings,
    StudentLeaveRequest,
    TeachingAssignment,
)
from .service import today, validate_group


class GroupFields(serializers.Serializer):
    session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.all())
    academic_class = serializers.PrimaryKeyRelatedField(queryset=AcademicClass.objects.all())
    section = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(), allow_null=True, required=False
    )
    subject = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all(), allow_null=True, required=False
    )


class RegisterInput(GroupFields):
    date = serializers.DateField()
    mode = serializers.ChoiceField(choices=MODES)
    period = serializers.SlugField(max_length=32, required=False, allow_blank=True)
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)
    calendar_override = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def validate_period(self, value):
        return value.upper()

    def validate(self, values):
        period = values.get("period", "")
        subject = values.get("subject")
        start, end = values.get("start_time"), values.get("end_time")
        if values["mode"] == "daily" and (period or subject):
            raise serializers.ValidationError("Daily attendance has no subject or period.")
        if values["mode"] == "period" and not (period and subject):
            raise serializers.ValidationError("Period attendance requires a subject and period.")
        if (start or end) and not (start and end and start < end):
            raise serializers.ValidationError("Select both times, with the end after the start.")
        return values


class VersionInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class MarkInput(serializers.Serializer):
    record = serializers.UUIDField()
    status = serializers.ChoiceField(choices=MARKS)
    remarks = serializers.CharField(max_length=300, required=False, allow_blank=True)


class MarksInput(VersionInput):
    marks = MarkInput(many=True, max_length=5000)


class FinalizeInput(VersionInput):
    acknowledge_unmarked = serializers.BooleanField(default=False)


class CorrectionInput(VersionInput):
    record = serializers.UUIDField()
    status = serializers.ChoiceField(choices=MARKS, required=False)
    remarks = serializers.CharField(max_length=300, required=False, allow_blank=True)
    reason = serializers.CharField(max_length=400)
    use_leave = serializers.BooleanField(default=False)

    def validate(self, values):
        if values["use_leave"] == ("status" in values):
            raise serializers.ValidationError(
                "Choose one corrected mark or reconcile approved leave."
            )
        return values


class SettingsFields(serializers.ModelSerializer):
    non_teaching_weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6), max_length=7
    )

    class Meta:
        model = AttendanceSettings
        fields = (
            "primary_mode",
            "late_attended",
            "excused_policy",
            "non_teaching_weekdays",
            "require_rejection_reason",
        )

    def validate_non_teaching_weekdays(self, values):
        if len(set(values)) != len(values):
            raise serializers.ValidationError("Choose each weekday once.")
        return sorted(values)


class HolidayFields(serializers.ModelSerializer):
    class Meta:
        model = AttendanceHoliday
        fields = ("id", "date", "name", "kind")


class AssignmentFields(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    session_name = serializers.CharField(source="session.name", read_only=True)
    class_name = serializers.CharField(source="academic_class.name", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True, default=None)
    subject_name = serializers.CharField(source="subject.name", read_only=True, default=None)
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True))

    effective_status = serializers.SerializerMethodField()

    class Meta:
        model = TeachingAssignment
        fields = (
            "id",
            "user",
            "username",
            "session",
            "session_name",
            "academic_class",
            "class_name",
            "section",
            "section_name",
            "subject",
            "subject_name",
            "active",
            "effective_start",
            "effective_end",
            "effective_status",
        )

    def validate(self, values):
        if self.instance:
            if set(values) - {"active", "effective_start", "effective_end"}:
                raise serializers.ValidationError(
                    "Deactivate an assignment and create a replacement to change its scope."
                )
        else:
            validate_group(values)
        existing = self.instance
        start = values.get("effective_start", getattr(existing, "effective_start", None))
        end = values.get("effective_end", getattr(existing, "effective_end", None))
        if start and end and start > end:
            raise serializers.ValidationError(
                {"effective_end": "Choose a date on or after the start."}
            )
        if values.get("active", getattr(existing, "active", True)):
            scope = {
                key: getattr(existing, key) if existing else values.get(key)
                for key in ("user", "session", "academic_class", "section", "subject")
            }
            overlap = TeachingAssignment.objects.filter(active=True, **scope)
            if existing:
                overlap = overlap.exclude(pk=existing.pk)
            if overlap.filter(
                Q(effective_start__isnull=True) | Q(effective_start__lte=end or date.max),
                Q(effective_end__isnull=True) | Q(effective_end__gte=start or date.min),
            ).exists():
                raise serializers.ValidationError("An active assignment overlaps this date range.")
        return values

    def get_effective_status(self, row):
        day = today()
        if not row.active:
            return "inactive"
        if row.effective_start and row.effective_start > day:
            return "upcoming"
        if row.effective_end and row.effective_end < day:
            return "expired"
        return "current"


class LeaveFields(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.first_name", read_only=True)
    class_name = serializers.CharField(source="enrollment.academic_class.name", read_only=True)
    session_name = serializers.CharField(source="session.name", read_only=True)

    class Meta:
        model = StudentLeaveRequest
        fields = (
            "id",
            "student",
            "student_name",
            "session",
            "session_name",
            "class_name",
            "start_date",
            "end_date",
            "reason",
            "status",
            "submitted_by",
            "reviewed_by",
            "reviewed_at",
            "review_remarks",
            "created_at",
        )
        read_only_fields = (
            "status",
            "submitted_by",
            "reviewed_by",
            "reviewed_at",
            "review_remarks",
        )

    def validate(self, values):
        session, student = values["session"], values["student"]
        if (
            session.institution_id != school().pk
            or student.institution_id != session.institution_id
        ):
            raise serializers.ValidationError("Choose a student and session in this institution.")
        if not session.start_date <= values["start_date"] <= values["end_date"] <= session.end_date:
            raise serializers.ValidationError(
                "The leave dates must be ordered and within the academic session."
            )
        return values


class ReviewFields(serializers.Serializer):
    remarks = serializers.CharField(max_length=400, required=False, allow_blank=True)

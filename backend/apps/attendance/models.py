from datetime import date
from typing import ClassVar
from uuid import UUID

from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce

from apps.academics.models import Record

MODES = (("daily", "Daily"), ("period", "Subject or period"))
MARKS = (
    ("unmarked", "Unmarked"),
    ("present", "Present"),
    ("absent", "Absent"),
    ("late", "Late"),
    ("excused", "Excused"),
)
EXCUSED = (
    ("exclude", "Exclude"),
    ("attended", "Count as attended"),
    ("absent", "Count as not attended"),
)
ZERO_UUID = Value(UUID(int=0), output_field=models.UUIDField())


class AttendanceSettings(Record):
    institution = models.OneToOneField("accounts.Institution", on_delete=models.PROTECT)
    primary_mode = models.CharField(max_length=8, choices=MODES, default="daily")
    late_attended = models.BooleanField(default=True)
    excused_policy = models.CharField(max_length=8, choices=EXCUSED, default="exclude")
    non_teaching_weekdays = models.JSONField(default=list, blank=True)
    require_rejection_reason = models.BooleanField(default=True)


class AttendanceSession(Record):
    session = models.ForeignKey("academics.AcademicSession", on_delete=models.PROTECT)
    academic_class = models.ForeignKey("academics.AcademicClass", on_delete=models.PROTECT)
    section = models.ForeignKey(
        "academics.Section", on_delete=models.PROTECT, null=True, blank=True
    )
    date = models.DateField()
    mode = models.CharField(max_length=8, choices=MODES)
    subject = models.ForeignKey(
        "academics.Subject", on_delete=models.PROTECT, null=True, blank=True
    )
    period = models.SlugField(max_length=32, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=[("draft", "Draft"), ("finalized", "Finalized")], default="draft"
    )
    version = models.PositiveIntegerField(default=1)
    late_attended = models.BooleanField()
    excused_policy = models.CharField(max_length=8, choices=EXCUSED)
    calendar_override = models.CharField(max_length=300, blank=True)
    schedule_snapshot = models.JSONField(default=dict, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    finalized_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    finalized_at = models.DateTimeField(null=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                F("session"),
                F("academic_class"),
                Coalesce("section", ZERO_UUID),
                F("date"),
                condition=Q(mode="daily"),
                name="attendance_daily_identity",
            ),
            models.UniqueConstraint(
                F("session"),
                F("academic_class"),
                Coalesce("section", ZERO_UUID),
                F("date"),
                F("subject"),
                F("period"),
                condition=Q(mode="period"),
                name="attendance_period_identity",
            ),
            models.CheckConstraint(
                condition=(
                    Q(mode="daily", subject__isnull=True, period="")
                    | (Q(mode="period", subject__isnull=False) & ~Q(period=""))
                ),
                name="attendance_mode_fields",
            ),
            models.CheckConstraint(
                condition=Q(start_time__isnull=True, end_time__isnull=True)
                | Q(start_time__isnull=False, end_time__isnull=False, end_time__gt=F("start_time")),
                name="attendance_time_order",
            ),
            models.UniqueConstraint(
                fields=["id", "session", "date", "mode"], name="attendance_snapshot_scope_key"
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["session", "mode", "date"])]


class AttendanceRecord(Record):
    register = models.ForeignKey(
        AttendanceSession, on_delete=models.PROTECT, related_name="records"
    )
    enrollment = models.ForeignKey("admissions.StudentEnrollment", on_delete=models.PROTECT)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT)
    session = models.ForeignKey(
        "academics.AcademicSession", on_delete=models.PROTECT, editable=False
    )
    date = models.DateField(editable=False)
    mode = models.CharField(max_length=8, choices=MODES, editable=False)
    roll_number = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=8, choices=MARKS, default="unmarked")
    remarks = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    recorded_at = models.DateTimeField(null=True)
    updated_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["register", "student"], name="attendance_one_student_in_register"
            ),
            models.UniqueConstraint(
                fields=["session", "date", "student"],
                condition=Q(mode="daily"),
                name="attendance_student_once_daily",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[key for key, _ in MARKS]), name="valid_attendance_status"
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["student", "mode", "date"])]


class AttendanceCorrection(Record):
    record = models.ForeignKey(
        AttendanceRecord, on_delete=models.PROTECT, related_name="corrections"
    )
    previous_status = models.CharField(max_length=8, choices=MARKS)
    status = models.CharField(max_length=8, choices=MARKS)
    previous_remarks = models.CharField(max_length=300, blank=True)
    remarks = models.CharField(max_length=300, blank=True)
    reason = models.CharField(max_length=400)
    actor = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True)
    leave = models.ForeignKey("StudentLeaveRequest", on_delete=models.PROTECT, null=True)


class AttendanceHoliday(Record):
    institution = models.ForeignKey("accounts.Institution", on_delete=models.PROTECT)
    date = models.DateField()
    name = models.CharField(max_length=150)
    kind = models.CharField(
        max_length=12,
        choices=[
            ("public", "Public holiday"),
            ("institution", "Institution holiday"),
            ("closure", "Special closure"),
            ("working", "Working-day override"),
        ],
    )

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["institution", "date"], name="attendance_one_calendar_override"
            )
        ]


class TeachingAssignment(Record):
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    session = models.ForeignKey("academics.AcademicSession", on_delete=models.PROTECT)
    academic_class = models.ForeignKey("academics.AcademicClass", on_delete=models.PROTECT)
    section = models.ForeignKey(
        "academics.Section", on_delete=models.PROTECT, null=True, blank=True
    )
    subject = models.ForeignKey(
        "academics.Subject", on_delete=models.PROTECT, null=True, blank=True
    )
    active = models.BooleanField(default=True)

    effective_start = models.DateField(null=True, blank=True)
    effective_end = models.DateField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                F("user"),
                F("session"),
                F("academic_class"),
                Coalesce("section", ZERO_UUID),
                Coalesce("subject", ZERO_UUID),
                Coalesce("effective_start", date(1, 1, 1)),
                name="attendance_unique_dated_assignment",
            ),
            models.CheckConstraint(
                condition=Q(effective_start__isnull=True)
                | Q(effective_end__isnull=True)
                | Q(effective_start__lte=F("effective_end")),
                name="attendance_assignment_date_order",
            ),
        ]


class StudentLeaveRequest(Record):
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT)
    enrollment = models.ForeignKey("admissions.StudentEnrollment", on_delete=models.PROTECT)
    session = models.ForeignKey("academics.AcademicSession", on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=400)
    status = models.CharField(
        max_length=10,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
    )
    submitted_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True)
    review_remarks = models.CharField(max_length=400, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="attendance_leave_date_range"
            ),
        ]
        indexes: ClassVar = [
            models.Index(fields=["student", "session", "status", "start_date", "end_date"])
        ]


class LeaveDecision(Record):
    leave = models.ForeignKey(
        StudentLeaveRequest, on_delete=models.PROTECT, related_name="decisions"
    )
    status = models.CharField(max_length=10)
    actor = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True)
    remarks = models.CharField(max_length=400, blank=True)

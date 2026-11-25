from typing import ClassVar
from uuid import UUID

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Coalesce, Lower

from apps.academics.models import NamedRecord, Record

PROTECT = models.PROTECT
INSTITUTION = "accounts.Institution"
ZERO_UUID = UUID(int=0)
STATUSES = ("missing", "marked", "absent", "excused", "exempt", "withheld")


def actor(**options):
    return models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name="+", **options
    )


def score(**options):
    return models.DecimalField(max_digits=10, decimal_places=2, **options)


class ExamType(NamedRecord):
    institution = models.ForeignKey(INSTITUTION, on_delete=PROTECT)
    description = models.CharField(max_length=400, blank=True)
    active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(Lower("code"), "institution", name="exam_type_code")
        ]


class GradingScheme(Record):
    institution = models.ForeignKey(INSTITUTION, on_delete=PROTECT)
    name = models.CharField(max_length=150)
    version = models.PositiveIntegerField(default=1)
    basis = models.CharField(
        max_length=10,
        choices=[
            ("percentage", "Percentage"),
            ("marks", "Obtained marks"),
        ],
    )
    effective_from = models.DateField()
    effective_to = models.DateField()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["institution", "name", "version"], name="exam_scheme_version"
            ),
            models.CheckConstraint(
                condition=Q(effective_to__gte=F("effective_from")), name="exam_scheme_dates"
            ),
        ]


class GradeBand(Record):
    scheme = models.ForeignKey(GradingScheme, on_delete=PROTECT, related_name="bands")
    label = models.CharField(max_length=30)
    minimum = score()
    points = score(null=True, blank=True)
    passing = models.BooleanField(default=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-minimum",)
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["scheme", "minimum"], name="exam_grade_boundary"),
            models.CheckConstraint(
                condition=Q(minimum__gte=0) & (Q(points__isnull=True) | Q(points__gte=0)),
                name="exam_grade_nonnegative",
            ),
        ]


class Examination(NamedRecord):
    institution = models.ForeignKey(INSTITUTION, on_delete=PROTECT)
    exam_type = models.ForeignKey(ExamType, on_delete=PROTECT)
    session = models.ForeignKey("academics.AcademicSession", on_delete=PROTECT)
    scheme = models.ForeignKey(GradingScheme, on_delete=PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    description = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=12,
        default="draft",
        choices=[
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("open", "Marks entry"),
            ("closed", "Closed"),
        ],
    )
    ranking = models.CharField(
        max_length=12,
        default="disabled",
        choices=[
            ("disabled", "Disabled"),
            ("competition", "Competition"),
            ("dense", "Dense"),
        ],
    )
    rank_by_section = models.BooleanField(default=False)
    created_by = actor()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(Lower("code"), "session", name="exam_session_code"),
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="exam_date_order"
            ),
        ]


class ExaminationClass(Record):
    exam = models.ForeignKey(Examination, on_delete=PROTECT, related_name="groups")
    academic_class = models.ForeignKey("academics.AcademicClass", on_delete=PROTECT)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["exam", "academic_class"], name="exam_unique_class")
        ]


class ExaminationSubject(Record):
    group = models.ForeignKey(ExaminationClass, on_delete=PROTECT, related_name="subjects")
    subject = models.ForeignKey("academics.Subject", on_delete=PROTECT)
    subject_name = models.CharField(max_length=150)
    scheme = models.ForeignKey(GradingScheme, on_delete=PROTECT, null=True, blank=True)
    optional = models.BooleanField(default=False)
    weighted = models.BooleanField(default=False)
    passing_percentage = score(default=0)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["group", "subject"], name="exam_unique_subject"),
            models.CheckConstraint(
                condition=Q(passing_percentage__range=(0, 100)), name="exam_subject_pass_range"
            ),
        ]


class ExamAssessmentComponent(Record):
    subject = models.ForeignKey(ExaminationSubject, on_delete=PROTECT, related_name="components")
    name = models.CharField(max_length=100)
    maximum = score()
    minimum = score(null=True, blank=True)
    weight = score(null=True, blank=True)
    required = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(Lower("name"), "subject", name="exam_unique_component"),
            models.CheckConstraint(
                condition=Q(maximum__gt=0)
                & (Q(minimum__isnull=True) | Q(minimum__range=(0, F("maximum")))),
                name="exam_component_limits",
            ),
            models.CheckConstraint(
                condition=Q(weight__isnull=True) | Q(weight__gt=0, weight__lte=100),
                name="exam_component_weight",
            ),
        ]


class ExamSchedule(Record):
    subject = models.ForeignKey(ExaminationSubject, on_delete=PROTECT, related_name="schedules")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=80, blank=True)
    instructions = models.CharField(max_length=400, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")), name="exam_schedule_time"
            )
        ]


class StudentExamRegistration(Record):
    group = models.ForeignKey(ExaminationClass, on_delete=PROTECT, related_name="registrations")
    enrollment = models.ForeignKey("admissions.StudentEnrollment", on_delete=PROTECT)
    student = models.ForeignKey("students.Student", on_delete=PROTECT)
    section = models.ForeignKey("academics.Section", null=True, on_delete=PROTECT)
    details = models.JSONField(default=dict)
    reason = models.CharField(max_length=400, blank=True)
    excluded = models.BooleanField(default=False)
    optional_subjects = models.ManyToManyField(ExaminationSubject, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["group", "student"], name="exam_unique_registration")
        ]


class MarksSubmission(Record):
    component = models.ForeignKey(ExamAssessmentComponent, on_delete=PROTECT)
    section = models.ForeignKey("academics.Section", null=True, on_delete=PROTECT)
    status = models.CharField(
        max_length=10,
        default="draft",
        choices=[
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("verified", "Verified"),
        ],
    )
    version = models.PositiveIntegerField(default=1)
    submitted_by = actor(null=True)
    submitted_at = models.DateTimeField(null=True)
    verified_by = actor(null=True)
    verified_at = models.DateTimeField(null=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                "component", Coalesce("section", ZERO_UUID), name="exam_unique_submission"
            )
        ]


class StudentAssessmentMark(Record):
    submission = models.ForeignKey(MarksSubmission, on_delete=PROTECT, related_name="marks")
    registration = models.ForeignKey(
        StudentExamRegistration, on_delete=PROTECT, related_name="marks"
    )
    status = models.CharField(
        max_length=10, choices=[(key, key.title()) for key in STATUSES], default="missing"
    )
    obtained = score(null=True)
    remarks = models.CharField(max_length=300, blank=True)
    entered_by = actor(null=True)
    updated_by = actor(null=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["submission", "registration"], name="exam_unique_mark"),
            models.CheckConstraint(
                condition=Q(status="marked", obtained__gte=0, obtained__isnull=False)
                | Q(
                    status__in=[status for status in STATUSES if status != "marked"],
                    obtained__isnull=True,
                ),
                name="exam_mark_status_value",
            ),
        ]


class ResultCalculation(Record):
    group = models.ForeignKey(ExaminationClass, on_delete=PROTECT, related_name="calculations")
    revision = models.PositiveIntegerField()
    created_by = actor()
    approved_by = actor(null=True)
    approved_at = models.DateTimeField(null=True)
    superseded = models.BooleanField(default=False)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["group", "revision"], name="exam_result_revision")
        ]


class StudentExamResult(Record):
    calculation = models.ForeignKey(ResultCalculation, on_delete=PROTECT, related_name="results")
    registration = models.ForeignKey(StudentExamRegistration, on_delete=PROTECT)
    status = models.CharField(max_length=12)
    percentage = score(null=True)
    snapshot = models.JSONField(default=dict)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["calculation", "registration"], name="exam_unique_result"
            )
        ]


class ResultPublication(Record):
    calculation = models.OneToOneField(
        ResultCalculation, on_delete=PROTECT, related_name="publication"
    )
    group = models.ForeignKey(ExaminationClass, on_delete=PROTECT)
    published_by = actor()
    active = models.BooleanField(default=True)
    withdrawn_at = models.DateTimeField(null=True)
    withdrawn_by = actor(null=True)
    reason = models.CharField(max_length=400, blank=True)
    branding = models.JSONField(default=dict)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["group"], condition=Q(active=True), name="exam_single_current_publication"
            )
        ]


class MarksCorrection(Record):
    mark = models.ForeignKey(StudentAssessmentMark, on_delete=PROTECT, related_name="corrections")
    actor = actor()
    previous = models.JSONField(default=dict)
    revised = models.JSONField(default=dict)
    reason = models.CharField(max_length=400)

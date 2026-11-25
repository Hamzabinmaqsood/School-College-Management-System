from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.academics.models import NamedRecord, Record

PROTECT = models.PROTECT


def institution():
    return models.ForeignKey("accounts.Institution", on_delete=PROTECT)


def actor():
    return models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, related_name="+"
    )


class Settings(Record):
    institution = models.OneToOneField("accounts.Institution", on_delete=PROTECT)
    separate_approver = models.BooleanField(default=True)
    enforce_capacity = models.BooleanField(default=True)


class Shift(NamedRecord):
    institution = institution()
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    weekdays = models.JSONField()
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=("institution", "code"), name="tt_shift_code"),
            models.CheckConstraint(condition=Q(starts_at__lt=F("ends_at")), name="tt_shift_time"),
        ]


class Period(NamedRecord):
    shift = models.ForeignKey(Shift, on_delete=PROTECT, related_name="periods")
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    teaching = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=("shift", "code"), name="tt_period_code"),
            models.CheckConstraint(condition=Q(starts_at__lt=F("ends_at")), name="tt_period_time"),
        ]


class Room(NamedRecord):
    institution = institution()
    kind = models.CharField(max_length=30, default="classroom")
    capacity = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=("institution", "code"), name="tt_room_code"),
        ]


class Availability(Record):
    institution = institution()
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT)
    weekday = models.PositiveSmallIntegerField()
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    effective_start = models.DateField()
    effective_end = models.DateField()
    reason = models.CharField(max_length=200, blank=True)

    preference = models.CharField(
        max_length=12,
        choices=[
            ("hard", "Hard unavailability"),
            ("prefer", "Preferred time"),
            ("avoid", "Non-preferred time"),
        ],
        default="hard",
    )
    priority = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(condition=Q(weekday__lte=6), name="tt_availability_weekday"),
            models.CheckConstraint(
                condition=Q(starts_at__lt=F("ends_at"), effective_start__lte=F("effective_end")),
                name="tt_availability_bounds",
            ),
        ]


class Plan(Record):
    institution = institution()
    session = models.ForeignKey("academics.AcademicSession", on_delete=PROTECT)
    section = models.ForeignKey("academics.Section", on_delete=PROTECT)
    shift = models.ForeignKey(Shift, on_delete=PROTECT)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=("session", "section"), name="tt_plan_section_session"),
        ]


class Version(Record):
    plan = models.ForeignKey(Plan, on_delete=PROTECT, related_name="versions")
    number = models.PositiveIntegerField()
    effective_start = models.DateField()
    effective_end = models.DateField()
    superseded_on = models.DateField(null=True)
    status = models.CharField(max_length=12, default="draft")
    created_by = actor()
    submitted_by = actor()
    submitted_at = models.DateTimeField(null=True)
    approved_by = actor()
    approved_at = models.DateTimeField(null=True)
    published_by = actor()
    published_at = models.DateTimeField(null=True)
    separate_approver = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=("plan", "number"), name="tt_version_number"),
            models.CheckConstraint(
                condition=Q(effective_start__lte=F("effective_end")), name="tt_version_bounds"
            ),
        ]
        indexes: ClassVar = [models.Index(fields=("status", "effective_start", "effective_end"))]


class TeachingGroup(NamedRecord):
    institution = institution()
    session = models.ForeignKey("academics.AcademicSession", on_delete=PROTECT)
    section = models.ForeignKey("academics.Section", on_delete=PROTECT)
    subject = models.ForeignKey("academics.Subject", on_delete=PROTECT)
    enrollments = models.ManyToManyField("admissions.StudentEnrollment", blank=True)
    predecessor = models.OneToOneField(
        "self", on_delete=PROTECT, null=True, related_name="successor"
    )
    effective_version = models.ForeignKey(Version, on_delete=PROTECT, null=True)
    capacity = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("session", "section", "subject"),
                condition=Q(predecessor__isnull=True),
                name="tt_option_group_root",
            ),
            models.CheckConstraint(
                condition=(
                    Q(predecessor__isnull=True, effective_version__isnull=True)
                    | Q(predecessor__isnull=False, effective_version__isnull=False)
                ),
                name="tt_option_group_version_link",
            ),
        ]


class Entry(Record):
    version = models.ForeignKey(Version, on_delete=PROTECT, related_name="entries")
    period = models.ForeignKey(Period, on_delete=PROTECT)
    weekday = models.PositiveSmallIntegerField()
    subject = models.ForeignKey("academics.Subject", on_delete=PROTECT)
    group = models.ForeignKey(TeachingGroup, on_delete=PROTECT, null=True, blank=True)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT)
    room = models.ForeignKey(Room, on_delete=PROTECT, null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("version", "weekday", "period"),
                condition=Q(group__isnull=True),
                name="tt_section_slot_unique",
            ),
            models.UniqueConstraint(
                fields=("version", "weekday", "period", "group"),
                condition=Q(group__isnull=False),
                name="tt_group_slot_unique",
            ),
            models.CheckConstraint(condition=Q(weekday__lte=6), name="tt_entry_weekday"),
        ]
        indexes: ClassVar = [
            models.Index(fields=("teacher", "weekday")),
            models.Index(fields=("room", "weekday")),
        ]


class Exception(Record):
    entry = models.ForeignKey(Entry, on_delete=PROTECT, related_name="exceptions")
    date = models.DateField()
    destination_date = models.DateField(null=True, blank=True, db_index=True)
    destination_version = models.ForeignKey(Version, on_delete=PROTECT, null=True)
    destination_group = models.ForeignKey(TeachingGroup, on_delete=PROTECT, null=True)
    kind = models.CharField(
        max_length=12,
        choices=[
            ("cancelled", "Cancelled"),
            ("substitute", "Substitute"),
            ("rescheduled", "Rescheduled"),
        ],
    )
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, blank=True)
    period = models.ForeignKey(Period, on_delete=PROTECT, null=True, blank=True)
    room = models.ForeignKey(Room, on_delete=PROTECT, null=True, blank=True)
    reason = models.CharField(max_length=400)
    recorded_by = actor()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=("entry", "date"), name="tt_exception_day"),
        ]


class SubjectRequirement(Record):
    institution = institution()
    session = models.ForeignKey("academics.AcademicSession", on_delete=PROTECT)
    section = models.ForeignKey("academics.Section", on_delete=PROTECT)
    subject = models.ForeignKey("academics.Subject", on_delete=PROTECT)
    minimum = models.PositiveSmallIntegerField(default=0)
    maximum = models.PositiveSmallIntegerField()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("session", "section", "subject"), name="tt_subject_requirement"
            ),
            models.CheckConstraint(
                condition=Q(maximum__gte=F("minimum"), maximum__lte=70),
                name="tt_subject_requirement_bounds",
            ),
        ]


class WorkloadPolicy(Record):
    institution = institution()
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT)
    effective_start = models.DateField()
    effective_end = models.DateField()
    daily_max = models.PositiveSmallIntegerField(null=True, blank=True)
    weekly_max = models.PositiveSmallIntegerField(null=True, blank=True)
    consecutive_max = models.PositiveSmallIntegerField(null=True, blank=True)
    rest_minutes = models.PositiveSmallIntegerField(default=0)
    hard = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(effective_start__lte=F("effective_end")), name="tt_workload_dates"
            ),
            models.UniqueConstraint(
                fields=("teacher", "effective_start"), name="tt_workload_start"
            ),
        ]

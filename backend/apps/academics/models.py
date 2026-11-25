import uuid
from typing import ClassVar

from django.db import models
from django.db.models import F, Q


class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class NamedRecord(Record):
    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=40)

    class Meta:
        abstract = True


class AcademicSession(NamedRecord):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    institution = models.ForeignKey("accounts.Institution", on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status, default=Status.PLANNED)
    is_current = models.BooleanField(default=False)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["institution", "code"], name="academic_session_code_unique"
            ),
            models.UniqueConstraint(
                fields=["institution"], condition=Q(is_current=True), name="one_current_session"
            ),
            models.CheckConstraint(
                condition=Q(end_date__gt=F("start_date")), name="valid_session_dates"
            ),
            models.CheckConstraint(
                condition=Q(is_current=False) | Q(status="active"), name="current_session_active"
            ),
        ]


class AcademicClass(NamedRecord):
    institution = models.ForeignKey("accounts.Institution", on_delete=models.PROTECT)
    category = models.CharField(max_length=100, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["institution", "code"], name="academic_class_code_unique"
            ),
        ]


class Section(NamedRecord):
    academic_class = models.ForeignKey(
        AcademicClass, on_delete=models.PROTECT, related_name="sections"
    )
    capacity = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["academic_class", "code"], name="section_code_unique"),
            models.UniqueConstraint(
                fields=["id", "academic_class"], name="section_class_reference"
            ),
            models.CheckConstraint(
                condition=Q(capacity__gt=0) | Q(capacity__isnull=True),
                name="positive_section_capacity",
            ),
        ]


class Subject(NamedRecord):
    institution = models.ForeignKey("accounts.Institution", on_delete=models.PROTECT)
    description = models.TextField(max_length=600, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["institution", "code"], name="subject_code_unique"),
        ]


class ClassSubject(Record):
    academic_class = models.ForeignKey(AcademicClass, on_delete=models.PROTECT)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, null=True, blank=True)
    mandatory = models.BooleanField(default=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["academic_class", "subject"],
                condition=Q(session__isnull=True),
                name="one_default_subject_assignment",
            ),
            models.UniqueConstraint(
                fields=["academic_class", "subject", "session"],
                condition=Q(session__isnull=False),
                name="one_session_subject_assignment",
            ),
        ]

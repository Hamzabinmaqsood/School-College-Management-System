from typing import ClassVar

from django.db import models
from django.db.models import Q

from apps.academics.models import Record


class Student(Record):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        TRANSFERRED = "transferred", "Transferred out"
        WITHDRAWN = "withdrawn", "Withdrawn"
        GRADUATED = "graduated", "Graduated"

    institution = models.ForeignKey("accounts.Institution", on_delete=models.PROTECT)
    admission_number = models.CharField(max_length=48)
    registration_number = models.CharField(max_length=48, blank=True)
    first_name = models.CharField(max_length=90)
    last_name = models.CharField(max_length=90, blank=True)
    preferred_name = models.CharField(max_length=150, blank=True)
    birth_date = models.DateField()
    gender = models.CharField(max_length=32, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(max_length=500, blank=True)
    city = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=100, blank=True)
    admission_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status, default=Status.ACTIVE)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["institution", "admission_number"], name="one_admission_number"
            ),
            models.CheckConstraint(
                condition=Q(birth_date__lt=models.F("admission_date")),
                name="birth_before_admission",
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["institution", "status", "admission_date"])]


class AdmissionNumberPolicy(Record):
    institution = models.OneToOneField("accounts.Institution", on_delete=models.PROTECT)
    prefix = models.CharField(max_length=16, default="ADM")
    padding = models.PositiveSmallIntegerField(default=5)
    next_number = models.PositiveBigIntegerField(default=1)
    allow_unsectioned = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(padding__gte=1, padding__lte=12), name="admission_number_padding_range"
            ),
            models.CheckConstraint(
                condition=Q(next_number__gt=0), name="positive_admission_sequence"
            ),
        ]


class Guardian(Record):
    institution = models.ForeignKey("accounts.Institution", on_delete=models.PROTECT)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=40)
    alternate_phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(max_length=500, blank=True)
    occupation = models.CharField(max_length=100, blank=True)


class StudentGuardian(Record):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="guardian_links")
    guardian = models.ForeignKey(Guardian, on_delete=models.PROTECT)
    relationship = models.CharField(max_length=64)
    primary = models.BooleanField(default=False)
    emergency = models.BooleanField(default=False)
    pickup = models.BooleanField(default=False)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["student", "guardian"], name="one_guardian_link"),
            models.UniqueConstraint(
                fields=["student"], condition=Q(primary=True), name="one_primary_guardian"
            ),
        ]


class StudentDocument(Record):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="documents")
    kind = models.SlugField(max_length=48)
    label = models.CharField(max_length=120)
    content = models.BinaryField(editable=False)
    size = models.PositiveIntegerField()
    archived_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["student", "archived_at"])]

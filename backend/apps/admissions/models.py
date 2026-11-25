from typing import ClassVar

from django.db import models
from django.db.models import Q

from apps.academics.models import Record


class StudentEnrollment(Record):
    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="enrollments"
    )
    session = models.ForeignKey("academics.AcademicSession", on_delete=models.PROTECT)
    academic_class = models.ForeignKey("academics.AcademicClass", on_delete=models.PROTECT)
    section = models.ForeignKey(
        "academics.Section", on_delete=models.PROTECT, null=True, blank=True
    )
    roll_number = models.CharField(max_length=32, blank=True)
    enrollment_date = models.DateField()
    status = models.CharField(
        max_length=16,
        default="active",
        choices=[
            ("active", "Active"),
            ("promoted", "Promoted"),
            ("repeated", "Repeated"),
            ("transferred", "Section transfer"),
            ("transferred_out", "Transferred out"),
            ("withdrawn", "Withdrawn"),
            ("graduated", "Graduated"),
        ],
    )
    ended_on = models.DateField(null=True, editable=False)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["student", "session"],
                condition=Q(status="active"),
                name="one_active_enrollment_per_session",
            ),
            models.UniqueConstraint(
                fields=["session", "academic_class", "section", "roll_number"],
                condition=Q(status="active", section__isnull=False) & ~Q(roll_number=""),
                name="unique_active_section_roll",
            ),
            models.UniqueConstraint(
                fields=["session", "academic_class", "roll_number"],
                condition=Q(status="active", section__isnull=True) & ~Q(roll_number=""),
                name="unique_active_unsectioned_roll",
            ),
            models.CheckConstraint(
                condition=(
                    Q(ended_on__isnull=True, status="active")
                    | (
                        ~Q(status="active")
                        & Q(ended_on__isnull=False, ended_on__gte=models.F("enrollment_date"))
                    )
                ),
                name="valid_enrollment_end",
            ),
        ]
        indexes: ClassVar = [
            models.Index(fields=["session", "academic_class", "section", "status"])
        ]


class ProgressionEvent(Record):
    enrollment = models.ForeignKey(
        StudentEnrollment, on_delete=models.PROTECT, related_name="progression"
    )
    successor = models.ForeignKey(
        StudentEnrollment, on_delete=models.PROTECT, null=True, related_name="+"
    )
    action = models.SlugField(max_length=40)
    effective_date = models.DateField()
    actor = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True)

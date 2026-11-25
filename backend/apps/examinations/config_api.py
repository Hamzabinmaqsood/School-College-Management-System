from typing import ClassVar

from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.academics.access import Conflict, RecordsView, school
from apps.accounts.authentication import audit
from apps.admissions.models import StudentEnrollment

from . import models, serializers
from .workflow import registration_defaults, snapshot

VIEW = "accounts.view_examinations"
MANAGE = "accounts.manage_examinations"
CONFIGURE = "accounts.configure_exam_assessments"


def payload(schema, request):
    form = schema(data=request.data)
    form.is_valid(raise_exception=True)
    return form.validated_data


class ExamView(RecordsView):
    license_feature = "examinations"

    def finalize_response(self, request, response, *args, **kwargs):
        result = super().finalize_response(request, response, *args, **kwargs)
        result["Cache-Control"] = "no-store"
        return result


def grants(write):
    return {"list": VIEW, "retrieve": VIEW, "create": write, "partial_update": write}


class Types(ExamView):
    queryset = models.ExamType.objects.all()
    serializer_class = serializers.ExamType
    permission_map: ClassVar = grants(MANAGE)
    search_fields = ("name", "code")
    ordering = ("position", "name", "id")


class Schemes(ExamView):
    queryset = models.GradingScheme.objects.prefetch_related("bands")
    serializer_class = serializers.Scheme
    permission_map: ClassVar = {
        key: value
        for key, value in grants("accounts.manage_exam_grading").items()
        if key != "partial_update"
    }
    search_fields = ("name",)
    ordering = ("name", "-version")


class Exams(ExamView):
    queryset = models.Examination.objects.select_related("session", "scheme")
    serializer_class = serializers.Exam
    permission_map: ClassVar = grants(MANAGE) | {
        "schedule": MANAGE,
        "open": MANAGE,
        "close": MANAGE,
    }
    filterset_fields = ("session", "status")
    search_fields = ("name", "code")
    ordering = ("-start_date", "name", "id")

    def perform_create(self, serializer):
        row = serializer.save(institution=school(), created_by=self.request.user)
        audit(self.request, "EXAM_CREATED", "examination", row)

    def progress(self, target, expected):
        def operation():
            exam = self.get_object()
            if exam.status == target:
                return Response(self.get_serializer(exam).data)
            if exam.status not in expected:
                raise Conflict("The examination cannot advance from this state.")
            if not exam.groups.exists():
                raise ValidationError("Assign at least one class.")
            if (
                target in {"scheduled", "open"}
                and exam.groups.filter(subjects__isnull=True).exists()
            ):
                raise ValidationError("Configure at least one subject for each class.")
            if (
                target == "scheduled"
                and models.ExaminationSubject.objects.filter(
                    group__exam=exam,
                    schedules__isnull=True,
                ).exists()
            ):
                raise ValidationError("Add a schedule for each configured subject.")
            if target == "open":
                snapshot(exam, self.request)
            if (
                target == "closed"
                and exam.groups.exclude(
                    pk__in=models.ResultPublication.objects.filter(
                        group__exam=exam, active=True
                    ).values("group_id")
                ).exists()
            ):
                raise ValidationError("Publish every participating class before closing.")
            exam.status = target
            exam.save(update_fields=["status", "updated_at"])
            audit(self.request, "EXAM_" + target.upper(), "examination", exam)
            return Response(self.get_serializer(exam).data)

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        return self.progress("scheduled", {"draft"})

    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        return self.progress("open", {"draft", "scheduled"})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self.progress("closed", {"open"})


class Groups(ExamView):
    queryset = models.ExaminationClass.objects.all()
    serializer_class = serializers.Group
    institution_lookup = "exam__institution"
    permission_map: ClassVar = {
        key: value for key, value in grants(CONFIGURE).items() if key != "partial_update"
    }
    filterset_fields = ("exam", "academic_class")
    search_fields = ("academic_class__name", "exam__name")


class Subjects(ExamView):
    queryset = models.ExaminationSubject.objects.prefetch_related("components")
    serializer_class = serializers.Subject
    institution_lookup = "group__exam__institution"
    permission_map: ClassVar = grants(CONFIGURE)
    filterset_fields = ("group", "subject", "group__exam")
    search_fields = ("subject_name",)


class Schedules(ExamView):
    queryset = models.ExamSchedule.objects.all()
    serializer_class = serializers.Schedule
    institution_lookup = "subject__group__exam__institution"
    permission_map: ClassVar = grants("accounts.manage_exam_schedule")
    filterset_fields = ("subject", "date", "subject__group__exam", "subject__group__academic_class")
    search_fields = ("room", "subject__subject_name", "subject__group__academic_class__name")
    ordering = ("date", "start_time", "id")


class Registrations(ExamView):
    permission_map: ClassVar = {"create": CONFIGURE, "list": CONFIGURE, "choices": CONFIGURE}

    @action(detail=False, methods=["get"])
    def choices(self, request):
        from django.db.models import Q

        key = (
            serializers.Registration()
            .fields["group"]
            .run_validation(request.query_params.get("group"))
        )
        group = get_object_or_404(models.ExaminationClass, pk=key, exam__institution=school())
        rows = StudentEnrollment.objects.filter(
            session=group.exam.session,
            academic_class=group.academic_class,
            enrollment_date__lte=group.exam.end_date,
        ).filter(Q(ended_on__isnull=True) | Q(ended_on__gt=group.exam.start_date))
        if search := request.query_params.get("search", "")[:100]:
            rows = rows.filter(
                Q(student__first_name__icontains=search)
                | Q(student__admission_number__icontains=search)
            )
        page = self.paginate_queryset(
            rows.select_related("student", "section").order_by("student__first_name", "id")
        )
        return Response(
            {
                "enrollments": [
                    {
                        "id": row.pk,
                        "name": f"{row.student.first_name} {row.student.last_name}".strip()
                        + " · "
                        + row.student.admission_number
                        + (" · " + row.section.name if row.section else ""),
                    }
                    for row in page
                ],
                "subjects": list(group.subjects.filter(optional=True).values("id", "subject_name")),
            }
        )

    def list(self, request, *args, **kwargs):
        rows = models.StudentExamRegistration.objects.filter(group__exam__institution=school())
        if group := request.query_params.get("group"):
            group = serializers.RegisterKey().fields["component"].run_validation(group)
            rows = rows.filter(group_id=group)
        rows = rows.order_by("id")
        return self.get_paginated_response(
            [
                {"id": row.pk, "group": row.group_id, **row.details, "excluded": row.excluded}
                for row in self.paginate_queryset(rows)
            ]
        )

    def create(self, request, *args, **kwargs):
        def operation():
            values = payload(serializers.Registration, request)
            group = get_object_or_404(
                models.ExaminationClass, pk=values["group"], exam__institution=school()
            )
            if group.exam.status not in {"draft", "scheduled"}:
                raise Conflict("The examination roster is frozen.")
            enrollment = get_object_or_404(
                StudentEnrollment,
                pk=values["enrollment"],
                session=group.exam.session,
                academic_class=group.academic_class,
            )
            if (
                enrollment.ended_on
                and enrollment.ended_on <= group.exam.start_date
                and not values["excluded"]
            ):
                raise ValidationError("This placement ended before the examination.")
            if enrollment.enrollment_date > group.exam.end_date:
                raise ValidationError("This placement begins after the examination.")
            subjects = group.subjects.filter(optional=True, pk__in=values["optional_subjects"])
            if subjects.count() != len(values["optional_subjects"]):
                raise ValidationError("Choose distinct optional subjects in this class.")
            row, created = models.StudentExamRegistration.objects.update_or_create(
                group=group,
                student=enrollment.student,
                defaults=registration_defaults(enrollment)
                | {
                    "excluded": values["excluded"],
                    "reason": values["reason"],
                },
            )
            row.optional_subjects.set(subjects)
            audit(request, "EXAM_ROSTER_EXCEPTION", "studentexamregistration", row)
            return Response({"id": row.pk, **row.details}, status=201 if created else 200)

        return self.write(operation)

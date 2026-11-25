from collections import Counter
from typing import ClassVar

from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.academics.access import RecordsView, school
from apps.academics.models import AcademicClass, AcademicSession, Section, Subject
from apps.accounts.access import permission_codes

from .access import BROAD, assignments_for, group_allowed, scoped
from .models import MARKS, AttendanceSession
from .serializers import CorrectionInput, FinalizeInput, MarksInput, RegisterInput
from .service import (
    approved_for,
    available_roster,
    correct,
    create_register,
    finalize,
    policy,
    register_key,
    save_marks,
    section_roster,
    today,
    validate_day,
    validate_group,
    working_day,
)


def record_status(register):
    return {
        "id": register.pk,
        "session": register.session_id,
        "session_name": register.session.name,
        "academic_class": register.academic_class_id,
        "class_name": register.academic_class.name,
        "section": register.section_id,
        "section_name": register.section.name if register.section else None,
        "subject": register.subject_id,
        "subject_name": register.subject.name if register.subject else None,
        "date": register.date,
        "mode": register.mode,
        "period": register.period,
        "version": register.version,
        "status": register.status,
        "start_time": register.start_time,
        "end_time": register.end_time,
        "recorded_by": register.recorded_by_id,
        "finalized_by": register.finalized_by_id,
        "finalized_at": register.finalized_at,
        "created_at": register.created_at,
        "updated_at": register.updated_at,
    }


def student_name(student):
    return student.preferred_name or f"{student.first_name} {student.last_name}".strip()


def snapshot(register, user):
    approved_leaves = set(approved_for(register).values_list("student_id", flat=True))
    include_history = "accounts.view_attendance_history" in permission_codes(user)
    records = register.records.select_related("student").order_by(
        "roll_number", "student__admission_number", "pk"
    )
    if include_history:
        records = records.prefetch_related("corrections")
    rows = []
    for entry in records:
        row = {
            "id": entry.pk,
            "student": entry.student_id,
            "enrollment": entry.enrollment_id,
            "student_name": student_name(entry.student),
            "admission_number": entry.student.admission_number,
            "roll_number": entry.roll_number,
            "status": entry.status,
            "remarks": entry.remarks,
            "approved_leave": entry.student_id in approved_leaves,
        }
        if include_history:
            row["corrections"] = [
                {
                    "id": revision.pk,
                    "previous_status": revision.previous_status,
                    "status": revision.status,
                    "previous_remarks": revision.previous_remarks,
                    "remarks": revision.remarks,
                    "reason": revision.reason,
                    "actor": revision.actor_id,
                    "leave": revision.leave_id,
                    "at": revision.created_at,
                }
                for revision in sorted(
                    entry.corrections.all(), key=lambda item: item.created_at, reverse=True
                )
            ]
        rows.append(row)
    counts = Counter(row["status"] for row in rows)
    return record_status(register) | {
        "records": rows,
        "counts": {key: counts[key] for key, _ in MARKS},
        "calendar_override": register.calendar_override,
        "schedule_snapshot": register.schedule_snapshot,
    }


class Attendance(RecordsView):
    queryset = AttendanceSession.objects.select_related(
        "session", "academic_class", "section", "subject"
    )
    institution_lookup = "session__institution"
    license_feature = "attendance"
    filterset_fields = ("session", "academic_class", "section", "mode", "subject", "status", "date")
    search_fields = ("academic_class__name", "section__name", "subject__name", "period")
    ordering_fields = ("date", "created_at")
    ordering = ("-date", "-created_at", "pk")
    permission_map: ClassVar = {
        "list": "accounts.view_attendance",
        "history": "accounts.view_attendance_history",
        "lookups": "attendance.view_attendancesession",
        "retrieve": "attendance.view_attendancesession",
        "create": ["attendance.add_attendancesession", "attendance.view_attendancesession"],
        "roster": "attendance.view_attendancesession",
        "groups": "attendance.view_attendancesession",
        "partial_update": [
            "attendance.change_attendancerecord",
            "attendance.view_attendancesession",
        ],
        "save": ["attendance.change_attendancerecord", "attendance.view_attendancesession"],
        "finalize": ["accounts.finalize_attendance", "attendance.view_attendancesession"],
        "correct": ["attendance.add_attendancecorrection", "attendance.view_attendancesession"],
    }

    def get_queryset(self):
        rows = scoped(
            super().get_queryset(),
            self.request.user,
            operational=self.request.method not in {"GET", "HEAD", "OPTIONS"},
        )
        for key, lookup in (("from_date", "date__gte"), ("to_date", "date__lte")):
            if value := self.request.query_params.get(key):
                from rest_framework.serializers import DateField

                rows = rows.filter(**{lookup: DateField().run_validation(value)})
        return rows

    def list(self, request, *args, **kwargs):
        rows = self.filter_queryset(self.get_queryset())
        return self.get_paginated_response(
            [record_status(row) for row in self.paginate_queryset(rows)]
        )

    @action(detail=False, methods=["get"])
    def history(self, request):
        return self.list(request)

    @action(detail=False, methods=["get"])
    def lookups(self, request):
        if BROAD not in permission_codes(request.user):
            raise PermissionDenied("Use the teaching groups assigned to you.")
        institution = school()
        return Response(
            {
                "sessions": list(
                    AcademicSession.objects.filter(institution=institution)
                    .order_by("-start_date")
                    .values("id", "name", "is_current")
                ),
                "classes": list(
                    AcademicClass.objects.filter(institution=institution)
                    .order_by("name")
                    .values("id", "name")
                ),
                "sections": list(
                    Section.objects.filter(academic_class__institution=institution)
                    .order_by("name")
                    .values("id", "name", "academic_class")
                ),
                "subjects": list(
                    Subject.objects.filter(institution=institution)
                    .order_by("name")
                    .values("id", "name")
                ),
            }
        )

    def retrieve(self, request, *args, **kwargs):
        return Response(
            snapshot(self.get_object(), request.user), headers={"Cache-Control": "no-store"}
        )

    def create(self, request, *args, **kwargs):
        def operation():
            form = RegisterInput(data=request.data)
            form.is_valid(raise_exception=True)
            register, created = create_register(form.validated_data, request)
            return Response(snapshot(register, request.user), status=201 if created else 200)

        return self.write(operation)

    @action(detail=False, methods=["get"])
    def roster(self, request):
        form = RegisterInput(data=request.query_params)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        if not group_allowed(request.user, values, operational=False):
            raise PermissionDenied("This attendance group is outside your teaching assignments.")
        if existing := self.queryset.filter(
            **register_key(values), session__institution=school()
        ).first():
            return Response({"register": snapshot(existing, request.user), "roster": []})
        validate_group(values)
        validate_day(values)
        rows = [
            {
                "student": row.student_id,
                "student_name": student_name(row.student),
                "admission_number": row.student.admission_number,
                "roll_number": row.roll_number,
            }
            for row in available_roster(values)
        ]
        return Response(
            {
                "register": None,
                "roster": rows,
                "working_day": working_day(values["date"], policy()),
                "reserved": section_roster(values).count() - len(rows),
            }
        )

    @action(detail=False, methods=["get"])
    def groups(self, request):
        configuration = policy()
        assignments = assignments_for(request.user, operational=True).filter(
            session__institution=school()
        )
        rows = assignments.select_related(
            "session", "academic_class", "section", "subject"
        ).order_by("session__name", "academic_class__name", "section__name", "subject__name")
        return Response(
            {
                "broad": BROAD in permission_codes(request.user),
                "primary_mode": configuration.primary_mode,
                "date": today(),
                "assignments": [
                    {
                        "session": row.session_id,
                        "session_name": row.session.name,
                        "academic_class": row.academic_class_id,
                        "class_name": row.academic_class.name,
                        "section": row.section_id,
                        "section_name": row.section.name if row.section else None,
                        "subject": row.subject_id,
                        "subject_name": row.subject.name if row.subject else None,
                    }
                    for row in rows
                ],
            }
        )

    def change(self, request, schema, handler):
        def operation():
            register = self.get_object()
            form = schema(data=request.data)
            form.is_valid(raise_exception=True)
            handler(register, form.validated_data, request)
            return Response(snapshot(register, request.user))

        return self.write(operation)

    def partial_update(self, request, *args, **kwargs):
        return self.change(request, MarksInput, save_marks)

    @action(detail=True, methods=["post"])
    def save(self, request, pk=None):
        return self.change(request, MarksInput, save_marks)

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        return self.change(request, FinalizeInput, finalize)

    @action(detail=True, methods=["post"])
    def correct(self, request, pk=None):
        return self.change(request, CorrectionInput, correct)

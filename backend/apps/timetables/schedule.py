from datetime import timedelta

from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.access import school
from apps.accounts.access import permission_codes
from apps.attendance.models import AttendanceSession
from apps.examinations.models import ExamSchedule
from apps.hr.api import today
from apps.students.reports import csv_download

from . import models, service


class ScheduleQuery(serializers.Serializer):
    date = serializers.DateField(required=False)
    section = serializers.UUIDField(required=False)
    teacher = serializers.UUIDField(required=False)
    room = serializers.UUIDField(required=False)
    session = serializers.UUIDField(required=False)
    academic_class = serializers.UUIDField(required=False)
    subject = serializers.UUIDField(required=False)
    group = serializers.UUIDField(required=False)
    version = serializers.UUIDField(required=False)
    through = serializers.DateField(required=False)
    status = serializers.ChoiceField(
        choices=["draft", "review", "approved", "published"], required=False
    )


def lesson_data(entry, period, teacher, room, change, day):
    plan = entry.version.plan
    return {
        "entry": entry.pk,
        "exception": change.pk if change else None,
        "version": entry.version_id,
        "source_version": change.entry.version_id
        if change and change.destination_version_id
        else None,
        "destination_version": change.destination_version_id if change else None,
        "revision": entry.version.number,
        "session_name": plan.session.name,
        "date": day,
        "session": plan.session_id,
        "academic_class": plan.section.academic_class_id,
        "section": plan.section_id,
        "group": entry.group_id,
        "group_name": entry.group.name if entry.group_id else None,
        "class_name": plan.section.academic_class.name,
        "section_name": plan.section.name,
        "period": period.code,
        "starts_at": period.starts_at,
        "ends_at": period.ends_at,
        "subject": entry.subject_id,
        "subject_name": entry.subject.name,
        "teacher": teacher.pk,
        "teacher_name": teacher.get_full_name() or teacher.username,
        "room": room.pk if room else None,
        "room_name": room.name if room else None,
        "original_date": change.date if change else day,
        "destination_date": change.destination_date if change else None,
        "original_teacher": entry.teacher.get_full_name() or entry.teacher.username,
        "change": "rescheduled_out"
        if change and change.destination_date and change.destination_date != day
        else change.kind
        if change
        else None,
        "warning": None
        if service.inactive(change, day)
        else service.staff_issue(teacher, day, period),
    }


class Schedule(APIView):
    permission_classes = (IsAuthenticated,)
    mode = "daily"
    report = ""

    def get(self, request):
        grants = permission_codes(request.user)
        admin_view = "accounts.view_timetable" in grants
        if request.user.password_change_required or (
            not admin_view and "accounts.view_own_timetable" not in grants
        ):
            raise PermissionDenied()
        query = ScheduleQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        start = filters.pop("date", today())
        status = filters.pop("status", None)
        report = self.report or request.query_params.get("report", "")
        through = filters.pop("through", start + timedelta(days=6 if self.mode != "daily" else 0))
        if not start <= through <= start + timedelta(days=30):
            raise serializers.ValidationError("Choose an ordered report range of up to 31 days.")
        if not admin_view:
            if filters.get("teacher", request.user.pk) != request.user.pk:
                raise PermissionDenied()
            filters["teacher"] = request.user.pk
        if report in {"allocations", "unassigned", "revisions"}:
            if not admin_view:
                raise PermissionDenied()
            data = self.plan_report(filters, start, through, report, status)
            return self.render_report(request, grants, report, data)
        found = []
        exams = []
        for index in range((through - start).days + 1):
            day = start + timedelta(days=index)
            selected = []
            for row in service.daily(school(), day):
                entry, period, teacher, room, _ = row
                if status and status != entry.version.status:
                    continue
                plan = entry.version.plan
                attributes = {
                    "section": plan.section_id,
                    "session": plan.session_id,
                    "academic_class": plan.section.academic_class_id,
                    "subject": entry.subject_id,
                    "group": entry.group_id,
                    "version": entry.version_id,
                    "teacher": teacher.pk,
                    "room": room.pk if room else None,
                }
                if any(attributes[key] != value for key, value in filters.items()):
                    continue
                lesson = lesson_data(*row, day)
                if admin_view and "attendance.view_attendancesession" in grants:
                    lesson["attendance"] = (
                        AttendanceSession.objects.filter(
                            session_id=lesson["session"],
                            section_id=lesson["section"],
                            date=day,
                            subject_id=lesson["subject"],
                            period__iexact=period.code,
                            mode="period",
                        )
                        .values_list("status", flat=True)
                        .first()
                    )
                selected.append(lesson)
            if "accounts.view_examinations" in grants or request.user.is_superuser:
                classes = {row["academic_class"] for row in selected}
                names = {row["room_name"] for row in selected if row["room_name"]}
                scoped = Q(subject__group__academic_class_id__in=classes)
                for name in names:
                    scoped |= Q(room__iexact=name)
                scheduled = (
                    ExamSchedule.objects.filter(
                        subject__group__exam__institution=school(),
                        date=day,
                    )
                    .filter(scoped)
                    .exclude(subject__group__exam__status="draft")
                    .select_related("subject__group__exam")
                )
                for exam in scheduled:
                    exams.append(
                        {
                            "date": day,
                            "name": exam.subject.group.exam.name,
                            "subject": exam.subject.subject_name,
                            "room": exam.room,
                            "starts_at": exam.start_time,
                            "ends_at": exam.end_time,
                        }
                    )
                    for lesson in selected:
                        class_overlap = (
                            lesson["academic_class"] == exam.subject.group.academic_class_id
                        )
                        room_overlap = (
                            lesson["room_name"] or ""
                        ).casefold() == exam.room.casefold() and bool(exam.room)
                        if (class_overlap or room_overlap) and service.overlaps(
                            lesson["starts_at"], lesson["ends_at"], exam.start_time, exam.end_time
                        ):
                            lesson["warning"] = (
                                "exam_overlap" if class_overlap else "exam_room_overlap"
                            )
            found.extend(
                sorted(
                    selected,
                    key=lambda row: (row["starts_at"], row["class_name"], row["section_name"]),
                )
            )
        workload = {}
        utilization = {}
        attendance = {"expected": 0, "finalized": 0, "draft": 0, "missing": 0}
        for row in found:
            if row["change"] in {"cancelled", "rescheduled_out"}:
                continue
            key = row["teacher"]
            item = workload.setdefault(
                key, {"teacher_name": row["teacher_name"], "lessons": 0, "minutes": 0}
            )
            item["lessons"] += 1
            start_time, end_time = row["starts_at"], row["ends_at"]
            minutes = (end_time.hour - start_time.hour) * 60 + end_time.minute - start_time.minute
            item["minutes"] += minutes
            if row["room"]:
                space = utilization.setdefault(
                    row["room"], {"room_name": row["room_name"], "lessons": 0, "minutes": 0}
                )
                space["lessons"] += 1
                space["minutes"] += minutes
            if "attendance" in row:
                attendance["expected"] += 1
                attendance[row["attendance"] or "missing"] += 1
        if report or self.mode == "export":
            moves = {}
            for row in found:
                if row["change"] == "rescheduled":
                    moves[row["exception"]] = row
                elif row["change"] == "rescheduled_out":
                    moves.setdefault(row["exception"], row)

            reports = {
                "workload": list(workload.values()),
                "rooms": list(utilization.values()),
                "attendance": [attendance],
                "conflicts": [row for row in found if row["warning"]],
                "substitutions": [row for row in found if row["change"] == "substitute"],
                "cancellations": [row for row in found if row["change"] == "cancelled"],
                "reschedules": list(moves.values()),
            }
            return self.render_report(
                request, grants, report or "timetable", reports.get(report, found)
            )
        return Response(
            {
                "from": start,
                "lessons": found,
                "examinations": exams,
                "workload": list(workload.values()),
                "rooms": list(utilization.values()),
                "attendance": attendance,
            }
        )

    @staticmethod
    def plan_report(filters, start, through, report, status):
        query = (
            models.Version.objects.filter(
                plan__institution=school(),
                effective_start__lte=through,
                effective_end__gte=start,
            )
            .select_related("plan__section__academic_class", "plan__session")
            .order_by(
                "plan__section__name",
                "number",
            )
        )
        version_filters = {
            "session": "plan__session_id",
            "section": "plan__section_id",
            "academic_class": "plan__section__academic_class_id",
            "version": "pk",
        }
        query = query.filter(
            **{field: filters[key] for key, field in version_filters.items() if key in filters}
        )
        if status:
            query = query.filter(status=status)
        data = []
        for version in query:
            plan = version.plan
            info = {
                "session": plan.session.name,
                "class": plan.section.academic_class.name,
                "section": plan.section.name,
                "version": version.number,
                "status": version.status,
                "effective_start": version.effective_start,
                "effective_end": version.effective_end,
                "superseded_on": version.superseded_on,
            }
            if report == "revisions":
                data.append(info)
                continue
            for row in service.subject_requirements(version):
                if "subject" in filters and row["subject"] != filters["subject"]:
                    continue
                if report == "unassigned" and row["allocated"] >= row["minimum"]:
                    continue
                data.append({**info, **row, "missing": max(0, row["minimum"] - row["allocated"])})
        return data

    def render_report(self, request, grants, report, data):
        if self.mode == "export" or request.query_params.get("format_type") == "csv":
            if "accounts.export_timetable" not in grants:
                raise PermissionDenied()
            headings = (
                [
                    key
                    for key in data[0]
                    if key not in {"entry", "exception", "group", "teacher", "room", "subject"}
                ]
                if data
                else []
            )
            return csv_download(report, headings, ([row[key] for key in headings] for row in data))
        paginator = LimitOffsetPagination()
        paginator.default_limit = 25
        paginator.max_limit = 100
        page = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response(page)

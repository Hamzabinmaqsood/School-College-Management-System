from datetime import timedelta
from typing import ClassVar

from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils.html import format_html, format_html_join
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.academics.access import RecordsView, school
from apps.academics.models import AcademicClass, AcademicSession, Section, Subject
from apps.accounts.access import permission_codes, require
from apps.students.models import Student
from apps.students.reports import csv_download

from .access import scoped
from .analytics import ReportCriteria, grouped, totals
from .models import AttendanceRecord, StudentLeaveRequest
from .service import eligible, policy, today, working_day


class Reports(RecordsView):
    license_feature = "attendance"

    def filters(self, request):
        form = ReportCriteria(data=request.query_params)
        form.is_valid(raise_exception=True)
        rows = scoped(
            AttendanceRecord.objects.filter(session__institution=school()),
            request.user,
            prefix="register__",
        )
        if student := form.validated_data.get("student"):
            rows = rows.filter(student_id=student)
        rows = rows.order_by()
        sessions = AcademicSession.objects.filter(pk__in=rows.values("session_id"))
        if student and "attendance.view_studentleaverequest" in permission_codes(request.user):
            leave = scoped(
                StudentLeaveRequest.objects.filter(
                    session__institution=school(), student_id=student, status="approved"
                ),
                request.user,
                prefix="enrollment__",
                leave=True,
            ).order_by()
            sessions = sessions | AcademicSession.objects.filter(pk__in=leave.values("session_id"))
        return Response(
            {
                "primary_mode": policy().primary_mode,
                "sessions": list(sessions.order_by("-start_date").values("id", "name")),
                "classes": list(
                    AcademicClass.objects.filter(pk__in=rows.values("register__academic_class_id"))
                    .order_by("name")
                    .values("id", "name")
                ),
                "sections": list(
                    Section.objects.filter(pk__in=rows.values("register__section_id"))
                    .order_by("name")
                    .values("id", "name", "academic_class")
                ),
                "subjects": list(
                    Subject.objects.filter(pk__in=rows.values("register__subject_id"))
                    .order_by("name")
                    .values("id", "name")
                ),
                "students": list(
                    Student.objects.filter(pk__in=rows.values("student_id"))
                    .order_by("first_name", "pk")
                    .values("id", "first_name", "last_name", "admission_number")[:250]
                )
                if not student
                else [],
            }
        )

    permission_map: ClassVar = {
        "summary": "accounts.view_attendance",
        "filters": "accounts.view_attendance_history",
        "report": "accounts.view_attendance_history",
        "student": "accounts.view_attendance_history",
        "export": "accounts.export_attendance",
        "print_report": "accounts.print_attendance",
    }

    def criteria(self, request, days=30):
        form = ReportCriteria(data=request.query_params)
        form.is_valid(raise_exception=True)
        values = dict(form.validated_data)
        end = values.setdefault("to_date", today())
        start = values.setdefault("from_date", end - timedelta(days=days - 1))
        if not start <= end <= start + timedelta(days=366):
            raise ValidationError({"to_date": "Enter an ordered date range up to 366 days."})
        values.setdefault("mode", policy().primary_mode)
        return values

    def rows(self, request, criteria):
        rows = AttendanceRecord.objects.filter(
            session__institution=school(),
            mode=criteria["mode"],
            date__range=(criteria["from_date"], criteria["to_date"]),
        )
        for name in ("session", "student", "academic_class", "section", "subject"):
            if name in criteria:
                field = (
                    f"register__{name}_id" if name not in {"session", "student"} else f"{name}_id"
                )
                rows = rows.filter(**{field: criteria[name]})
        return scoped(rows, request.user, prefix="register__")

    def summary(self, request):
        criteria = self.criteria(request, 14)

        active = AcademicSession.objects.filter(institution=school(), is_current=True).first()
        if active and "session" not in criteria:
            criteria["session"] = active.pk
        rows = self.rows(request, criteria)
        current = rows.filter(date=criteria["to_date"])
        counts = totals(current)
        expected = counts["eligible"]
        if active and criteria["mode"] == "daily" and criteria.get("session") == active.pk:
            if working_day(criteria["to_date"], policy()):
                expected = scoped(
                    eligible(active, criteria["to_date"]), request.user, enrollment=True
                ).count()
        status = "empty"
        if counts["eligible"]:
            status = (
                "incomplete"
                if counts["draft"] or counts["unmarked"] or expected > counts["eligible"]
                else "finalized"
            )
        return Response(
            {
                "date": criteria["to_date"],
                "mode": criteria["mode"],
                "totals": counts,
                "status": status,
                "expected": expected,
                "trend": grouped(rows, "date"),
                "classes": grouped(
                    current, "register__academic_class__name", "register__section__name"
                ),
            }
        )

    def student(self, request, student_id):
        criteria = self.criteria(request) | {"student": student_id}
        rows = self.rows(request, criteria)
        placement = scoped(
            StudentLeaveRequest.objects.filter(
                student_id=student_id,
                session__institution=school(),
                status="approved",
                start_date__lte=criteria["to_date"],
                end_date__gte=criteria["from_date"],
            ),
            request.user,
            prefix="enrollment__",
            leave=True,
        )
        if session := criteria.get("session"):
            placement = placement.filter(session_id=session)
        can_view_leave = "attendance.view_studentleaverequest" in permission_codes(request.user)
        return Response(
            {
                "mode": criteria["mode"],
                "totals": totals(rows),
                "calendar": grouped(rows, "date"),
                "subjects": grouped(
                    rows.exclude(register__subject=None), "register__subject__name"
                ),
                "records": self.get_page(self.table(rows, "daily", criteria)),
                "approved_leaves": list(
                    placement.order_by("-start_date").values(
                        "id", "start_date", "end_date", "session__name"
                    )
                )
                if can_view_leave
                else None,
            }
        )

    def get_page(self, rows):
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(page).data

    def table(self, rows, kind, criteria):
        student = ("student__admission_number", "student__first_name", "student__last_name")
        academic_class = ("register__academic_class__name", "register__section__name")
        if kind == "daily":
            return rows.order_by("-date", "pk").values(
                "date",
                "mode",
                *student,
                *academic_class,
                "register__subject__name",
                "register__period",
                "register__status",
                "status",
            )
        if kind == "class":
            return grouped(rows, "date", *academic_class)
        if kind == "monthly":
            return grouped(rows.annotate(month=TruncMonth("date")), "month", *academic_class)
        if kind == "subject":
            return grouped(
                rows.exclude(register__subject=None), "register__subject__name", *academic_class
            )
        values = grouped(rows, *student)
        if kind == "low":
            return [
                row
                for row in values
                if row["percentage"] is not None
                and row["percentage"] < criteria.get("threshold", 75)
            ]
        return values

    def report_rows(self, request):
        criteria = self.criteria(request)
        kind = criteria.get("report", "class")
        if kind != "leave":
            return self.table(self.rows(request, criteria), kind, criteria)
        require(request.user, "attendance.view_studentleaverequest")
        rows = StudentLeaveRequest.objects.filter(
            session__institution=school(),
            end_date__gte=criteria["from_date"],
            start_date__lte=criteria["to_date"],
        )
        for name in ("session", "student", "academic_class", "section"):
            if name in criteria:
                field = (
                    f"enrollment__{name}_id"
                    if name in ("academic_class", "section")
                    else f"{name}_id"
                )
                rows = rows.filter(**{field: criteria[name]})
        return (
            scoped(rows, request.user, prefix="enrollment__", leave=True)
            .order_by("-start_date", "id")
            .values(
                "start_date",
                "end_date",
                "student__admission_number",
                "student__first_name",
                "student__last_name",
                "status",
            )
        )

    def report(self, request):
        return Response(self.get_page(self.report_rows(request)))

    def columns(self, rows):
        return (
            [
                key.replace("register__", "")
                .replace("student__", "")
                .replace("__", " ")
                .replace("_", " ")
                for key in rows[0]
            ]
            if rows
            else ["No records for these filters"]
        )

    def export(self, request):
        rows = self.report_rows(request)
        return csv_download("attendance", self.columns(rows), (row.values() for row in rows))

    def print_report(self, request):
        rows = self.report_rows(request)
        headers = format_html_join(
            "", "<th scope='col'>{}</th>", ((key,) for key in self.columns(rows))
        )
        body = format_html_join(
            "",
            "<tr>{}</tr>",
            (
                (
                    format_html_join(
                        "",
                        "<td>{}</td>",
                        ((value if value is not None else "—",) for value in row.values()),
                    ),
                )
                for row in rows
            ),
        )
        return HttpResponse(
            format_html(
                "<!doctype html><html lang='en'><meta charset='utf-8'>"
                "<title>Attendance report</title>"
                "<style>body{{font:14px system-ui;margin:2rem}}table{{border-collapse:collapse}}"
                "td,th{{border:1px solid #aaa;padding:.4rem;text-align:left}}"
                "thead{{display:table-header-group}}"
                "</style><h1>Attendance report</h1><table><thead><tr>{}</tr></thead>"
                "<tbody>{}</tbody></table></html>",
                headers,
                body,
            ),
            headers={"Cache-Control": "no-store"},
        )

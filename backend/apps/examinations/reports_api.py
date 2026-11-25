from base64 import b64encode
from collections import Counter, defaultdict
from decimal import Decimal
from typing import ClassVar

from django.http import HttpResponse
from django.utils.html import format_html, format_html_join
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.academics.access import school
from apps.students.reports import csv_download

from . import models
from .config_api import ExamView
from .result_api import row_data
from .results import rounded


class Filters(serializers.Serializer):
    exam = serializers.UUIDField(required=False)
    session = serializers.UUIDField(required=False)
    academic_class = serializers.UUIDField(required=False)
    section = serializers.UUIDField(required=False)
    subject = serializers.UUIDField(required=False)


def document(title, contents):
    return HttpResponse(
        format_html(
            '<!doctype html><html lang="en"><meta charset="utf-8"><title>{}</title>'
            "<style>@page{{size:A4;margin:18mm}}body{{font:15px system-ui}}"
            "article{{break-after:page}}article:last-child{{break-after:auto}}"
            "table{{width:100%;border-collapse:collapse}}"
            "td,th{{text-align:start;border:1px solid;padding:6px}}"
            "</style><main><h1>{}</h1>{}</main></html>",
            title,
            title,
            contents,
        )
    )


def table(headers, rows):
    return format_html(
        "<table><thead><tr>{}</tr></thead><tbody>{}</tbody></table>",
        format_html_join("", "<th>{}</th>", ((key,) for key in headers)),
        format_html_join(
            "",
            "<tr>{}</tr>",
            (
                (
                    format_html_join(
                        "", "<td>{}</td>", ((value if value is not None else "—",) for value in row)
                    ),
                )
                for row in rows
            ),
        ),
    )


class Reports(ExamView):
    permission_map: ClassVar = {
        "student": "accounts.view_student_results",
        "class_results": "accounts.view_class_results",
        "card": "accounts.print_exam_results",
        "batch": "accounts.print_exam_results",
        "report": "accounts.view_class_results",
        "export": "accounts.export_exam_results",
        "date_sheet": "accounts.view_examinations",
        "overview": "accounts.view_exam_analytics",
    }

    def criteria(self, request):
        form = Filters(data=request.query_params)
        form.is_valid(raise_exception=True)
        return form.validated_data

    def rows(self, request, history=False):
        clauses = {
            "calculation__publication__isnull": False,
            "calculation__group__exam__institution": school(),
        }
        if not history:
            clauses["calculation__publication__active"] = True
        fields = {
            "exam": "calculation__group__exam_id",
            "session": "calculation__group__exam__session_id",
            "academic_class": "calculation__group__academic_class_id",
            "section": "registration__section_id",
        }
        for key, value in self.criteria(request).items():
            if key in fields:
                clauses[fields[key]] = value
        return (
            models.StudentExamResult.objects.filter(**clauses)
            .select_related("calculation__publication", "calculation__group__exam")
            .order_by("-calculation__publication__created_at", "id")
        )

    def student(self, request, student_id):
        rows = self.rows(request, history=True).filter(registration__student_id=student_id)
        return self.get_paginated_response(
            [
                row_data(row)
                | {
                    "revision": row.calculation.revision,
                    "active": row.calculation.publication.active,
                }
                for row in self.paginate_queryset(rows)
            ]
        )

    def class_results(self, request, class_id):
        return self.get_paginated_response(
            [
                row_data(row)
                for row in self.paginate_queryset(
                    self.rows(request).filter(calculation__group__academic_class_id=class_id)
                )
            ]
        )

    def render_card(self, row):
        snapshot = row.snapshot
        published = row.calculation.publication
        logo = school().logo_png
        mark = (
            format_html(
                '<img width="80" alt="Institution logo" src="data:image/png;base64,{}">',
                b64encode(logo).decode(),
            )
            if logo
            else ""
        )
        subjects = table(
            ("Subject", "Maximum", "Obtained", "Grade", "Outcome"),
            (
                (item[key] for key in ("subject", "maximum", "obtained", "grade", "status"))
                for item in snapshot["subjects"]
            ),
        )
        return format_html(
            "<article>{}<h2>{}</h2><p>{}</p><h3>{} · {}</h3>"
            "<p>{} · Admission {} · Roll {} · {} {}</p>"
            "<p>Issued {} · Revision {} · {}</p>{}"
            "<p>Total {} / {} · {}% · {} · {} · Position {}</p>"
            "<p>Principal __________________ · Examination officer __________________</p>"
            "</article>",
            mark,
            published.branding["name"],
            published.branding["address"],
            snapshot["exam"],
            snapshot["session"],
            snapshot["student"],
            snapshot["admission"],
            snapshot["roll"],
            snapshot["class"],
            snapshot["section"],
            published.created_at.date(),
            row.calculation.revision,
            "Official" if published.active else "Withdrawn historical copy",
            subjects,
            snapshot["obtained"],
            snapshot["maximum"],
            snapshot["percentage"],
            snapshot["grade"],
            snapshot["status"],
            snapshot["rank"] or "—",
        )

    def card(self, request, pk):
        return document(
            "Student report card",
            self.render_card(get_object_or_404(self.rows(request, history=True), pk=pk)),
        )

    def batch(self, request, class_id):
        rows = self.rows(request).filter(calculation__group__academic_class_id=class_id)
        page = self.paginate_queryset(rows)
        return document(
            "Class report cards",
            format_html_join("", "{}", ((self.render_card(row),) for row in page)),
        )

    def date_sheet(self, request):
        rows = models.ExamSchedule.objects.filter(subject__group__exam__institution=school())
        filter_fields = {
            "exam": "subject__group__exam_id",
            "academic_class": "subject__group__academic_class_id",
            "session": "subject__group__exam__session_id",
            "subject": "subject__subject_id",
        }
        rows = rows.filter(
            **{
                filter_fields[key]: value
                for key, value in self.criteria(request).items()
                if key in filter_fields
            }
        )
        return document(
            "Examination date sheet",
            table(
                ("Subject", "Date", "Start", "End", "Room"),
                rows.order_by("date", "start_time").values_list(
                    "subject__subject_name", "date", "start_time", "end_time", "room"
                ),
            ),
        )

    def submission_report(self, request):
        from apps.accounts.access import require

        from .catalog import BROAD
        from .marks_api import header

        require(request.user, "accounts.view_exam_marks", BROAD)
        rows = models.MarksSubmission.objects.filter(
            component__subject__group__exam__institution=school()
        ).select_related(
            "component__subject__group__exam",
            "component__subject__group__academic_class",
            "section",
        )
        fields = {
            "exam": "component__subject__group__exam_id",
            "session": "component__subject__group__exam__session_id",
            "academic_class": "component__subject__group__academic_class_id",
            "section": "section_id",
            "subject": "component__subject__subject_id",
        }
        rows = rows.filter(**{fields[key]: value for key, value in self.criteria(request).items()})
        return [
            {
                key: value
                for key, value in header(row).items()
                if key not in {"id", "group", "version"}
            }
            | {
                "recorded": row.marks.exclude(status="missing").count(),
                "eligible": row.marks.count(),
                "submitted_at": row.submitted_at,
                "verified_at": row.verified_at,
            }
            for row in rows
        ]

    def dataset(self, request, kind):
        if kind in {"completion", "submissions"}:
            return self.submission_report(request)
        rows = self.rows(request)
        subject = self.criteria(request).get("subject")
        if kind in {"grade-distribution", "pass-fail", "examination-summary"}:
            field = {
                "grade-distribution": "grade",
                "pass-fail": "status",
                "examination-summary": "exam",
            }[kind]
            counts = Counter(row.snapshot[field] for row in rows)
            return [{"group": key, "students": count} for key, count in sorted(counts.items())]
        if kind in {"subject-performance", "subject-marks"}:
            grouped = defaultdict(list)
            marks = []
            for row in rows:
                for entry in row.snapshot["subjects"]:
                    if subject and entry["subject_id"] != str(subject):
                        continue
                    if entry["percentage"] is not None:
                        grouped[entry["subject"]].append(Decimal(entry["percentage"]))
                    marks.append(
                        {
                            "student": row.snapshot["student"],
                            "admission": row.snapshot["admission"],
                            **{key: value for key, value in entry.items() if key != "subject_id"},
                        }
                    )
            if kind == "subject-marks":
                return marks
            return [
                {
                    "subject": name,
                    "students": len(values),
                    "average": str(rounded(sum(values) / len(values))),
                }
                for name, values in sorted(grouped.items())
            ]
        if kind == "high-achievers":
            rows = rows.filter(percentage__gte=80).order_by("-percentage")
        elif kind == "support":
            rows = rows.filter(status="fail")
        elif kind not in {"class-results", "history"}:
            from rest_framework.exceptions import NotFound

            raise NotFound()
        return [
            {
                key: row.snapshot[key]
                for key in (
                    "student",
                    "admission",
                    "exam",
                    "session",
                    "class",
                    "section",
                    "grade",
                    "percentage",
                    "status",
                    "rank",
                )
            }
            for row in rows
        ]

    def report(self, request, kind):
        return self.get_paginated_response(self.paginate_queryset(self.dataset(request, kind)))

    def export(self, request, kind):
        rows = self.dataset(request, kind)
        headers = list(rows[0]) if rows else ["No results"]
        values = [row.values() for row in rows]
        if request.query_params.get("output") == "print":
            return document(kind.replace("-", " ").title(), table(headers, values))
        return csv_download(kind, headers, values)

    def overview(self, request):
        exams = models.Examination.objects.filter(institution=school())
        submissions = models.MarksSubmission.objects.filter(
            component__subject__group__exam__in=exams
        )
        runs = models.ResultCalculation.objects.filter(group__exam__in=exams, superseded=False)
        published = models.ResultPublication.objects.filter(group__exam__in=exams, active=True)
        latest = published.order_by("-created_at").first()
        return Response(
            {
                "active": exams.filter(status__in=["scheduled", "open"]).count(),
                "pending": submissions.exclude(status="verified").count(),
                "awaiting": runs.filter(approved_at__isnull=True).count(),
                "published": published.values("group__exam").distinct().count(),
                "latest": {
                    "exam": latest.group.exam.name,
                    "outcomes": dict(
                        Counter(latest.calculation.results.values_list("status", flat=True))
                    ),
                }
                if latest
                else None,
            }
        )

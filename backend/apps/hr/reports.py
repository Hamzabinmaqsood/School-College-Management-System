from base64 import b64encode
from decimal import Decimal
from typing import ClassVar

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils.html import format_html, format_html_join
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.academics.access import school
from apps.accounts.access import permission_codes, require
from apps.students.reports import csv_download

from . import models
from .api import HRView, today
from .payroll import payable


def html(title, rows, *, logo=None):
    body = format_html_join("", "<p><strong>{}</strong> {}</p>", rows)
    mark = ""
    if logo:
        mark = format_html(
            '<img width="80" alt="Institution logo" src="data:image/png;base64,{}">',
            b64encode(logo).decode(),
        )
    return HttpResponse(
        format_html(
            '<!doctype html><html lang="en"><meta charset="utf-8"><title>{}</title>'
            "<style>@page{{size:A4;margin:18mm}}body{{font:15px system-ui}}</style>{}<h1>{}</h1>{}",
            title,
            mark,
            title,
            body,
        )
    )


class Reports(HRView):
    permission_map: ClassVar = {
        "overview": "accounts.view_staff",
        "report": "accounts.view_staff",
        "export": "accounts.export_hr",
        "payslip": "accounts.print_payslip",
        "payslips": "accounts.view_payroll",
        "statement": "accounts.view_payroll",
    }

    def overview(self, request):
        rows = models.Employee.objects.filter(institution=school())
        active = rows.filter(status__in=("active", "on_leave"))
        stats = {
            "employees": rows.count(),
            "active": active.count(),
            "teachers": active.filter(designation__teaching=True).count(),
        }
        grants = permission_codes(request.user)
        if "accounts.view_staff_attendance" in grants:
            entries = models.EmployeeAttendance.objects.filter(employee__in=active, date=today())
            stats.update(
                present=entries.filter(status__in=("present", "late")).count(),
                unrecorded=active.count() - entries.count(),
            )
        if "accounts.view_staff_leave" in grants:
            leaves = models.EmployeeLeave.objects.filter(employee__in=rows)
            stats.update(
                pending=leaves.filter(status="pending").count(),
                on_leave=leaves.filter(
                    status="approved", start_date__lte=today(), end_date__gte=today()
                ).count(),
            )
        if "accounts.view_payroll" in grants:
            day = today()
            payroll = models.PayrollEntry.objects.filter(
                period__institution=school(),
                period__start_date__lte=day,
                period__end_date__gte=day,
                run__status="finalized",
            )
            from .payroll import ZERO, round_money

            stats["payroll_amount"] = str(
                round_money(payroll.aggregate(net=Sum("net"))["net"] or ZERO)
            )
            stats["payroll_due"] = str(sum((payable(row) for row in payroll), ZERO))
        return Response(
            stats
            | {"departments": list(active.values("department__name").annotate(count=Count("pk")))}
        )

    def payslip(self, request, pk):
        institution = school()
        row = get_object_or_404(
            models.PayrollEntry,
            pk=pk,
            period__institution=institution,
            run__status="finalized",
        )
        data = row.snapshot
        paid = row.payments.filter(reversal__isnull=True).aggregate(amount=Sum("amount"))[
            "amount"
        ] or Decimal("0")
        return html(
            "Salary payslip",
            [
                ("Institution", institution.name),
                ("Address", institution.address),
                ("Period", row.period.name),
                ("Issued", row.run.updated_at.date()),
                ("Currency", "PKR"),
                *((key.title(), val) for key, val in data.items() if key != "items"),
                *((item["label"], item["amount"]) for item in data["items"]),
                ("Recorded payments", f"{paid:.2f}"),
                ("Outstanding payable", str(payable(row))),
                ("Authorized signature", "___________________"),
            ],
            logo=institution.logo_png,
        )

    def payslips(self, request):
        rows = models.PayrollEntry.objects.filter(
            period__institution=school(), run__status="finalized"
        ).order_by("-period__start_date", "id")
        return self.get_paginated_response(
            [
                {
                    "id": row.pk,
                    "period": row.period.name,
                    "employee": row.snapshot["name"],
                    "net": row.snapshot["net"],
                    "outstanding": str(payable(row)),
                }
                for row in self.paginate_queryset(rows)
            ]
        )

    def statement(self, request, employee_id):
        rows = models.PayrollEntry.objects.filter(
            employee_id=employee_id, period__institution=school(), run__status="finalized"
        ).order_by("-period__start_date")
        return self.get_paginated_response(
            [
                {
                    "id": row.pk,
                    "period": row.period.name,
                    "outstanding": str(payable(row)),
                    **row.snapshot,
                }
                for row in self.paginate_queryset(rows)
            ]
        )

    def dataset(self, request, kind):
        from rest_framework import serializers
        from rest_framework.exceptions import NotFound, ValidationError

        def date_filter(rows, field, end_field=None):
            start = request.query_params.get("from_date")
            end = request.query_params.get("to_date")
            start = serializers.DateField().run_validation(start) if start else None
            end = serializers.DateField().run_validation(end) if end else None
            if start and end and end < start:
                raise ValidationError("Choose an ordered date range.")
            if start:
                rows = rows.filter(**{(end_field or field) + "__gte": start})
            if end:
                rows = rows.filter(**{field + "__lte": end})
            return rows

        employees = models.Employee.objects.filter(institution=school())
        for key in ("department", "employee"):
            if value := request.query_params.get(key):
                value = serializers.UUIDField().run_validation(value)
                employees = employees.filter(
                    **{("pk" if key == "employee" else "department_id"): value}
                )
        status = request.query_params.get("status")
        if kind == "department-summary":
            return list(
                employees.values("department__name")
                .annotate(employees=Count("pk"))
                .order_by("department__name")
            )
        if kind in {"employees", "joining-exits"}:
            if status:
                employees = employees.filter(status=status)
            if kind == "joining-exits":
                from django.db.models import Q

                employees = employees.filter(
                    Q(pk__in=date_filter(employees, "joined_on").values("pk"))
                    | Q(
                        pk__in=date_filter(employees.exclude(ended_on=None), "ended_on").values(
                            "pk"
                        )
                    )
                )
            else:
                employees = date_filter(employees, "joined_on")
            return list(
                employees.values(
                    "code",
                    "first_name",
                    "last_name",
                    "department__name",
                    "designation__name",
                    "status",
                    "joined_on",
                    "ended_on",
                )
            )
        if kind == "teacher-assignments":
            require(request.user, "accounts.view_teachers")
            from apps.attendance.models import TeachingAssignment

            return list(
                TeachingAssignment.objects.filter(
                    user_id__in=employees.exclude(user=None).values("user_id")
                ).values(
                    "user__username",
                    "session__name",
                    "academic_class__name",
                    "section__name",
                    "subject__name",
                    "active",
                )
            )
        if kind == "leave-balances":
            require(request.user, "accounts.view_staff_leave")
            types = models.LeaveType.objects.filter(institution=school(), paid=True, active=True)
            used = models.EmployeeLeave.objects.filter(
                employee__in=employees, status="approved", start_date__year=today().year
            )
            totals = {
                (row["employee"], row["leave_type"]): row["used"]
                for row in used.values("employee", "leave_type").annotate(used=Sum("days"))
            }
            return [
                {
                    "employee": person.code,
                    "type": kind.name,
                    "annual": kind.annual_days,
                    "used": totals.get((person.pk, kind.pk), 0),
                    "remaining": kind.annual_days - totals.get((person.pk, kind.pk), 0),
                }
                for person in employees
                for kind in types
            ]
        if kind in {"attendance", "monthly-attendance"}:
            require(request.user, "accounts.view_staff_attendance")
            rows = date_filter(
                models.EmployeeAttendance.objects.filter(employee__in=employees), "date"
            )
            if status:
                rows = rows.filter(status=status)
            if kind == "monthly-attendance":
                return list(
                    rows.annotate(month=TruncMonth("date"))
                    .values("month", "employee__department__name", "status")
                    .annotate(records=Count("pk"))
                    .order_by("-month", "employee__department__name", "status")
                )
            return list(
                rows.values("employee__code", "date", "status", "check_in", "check_out", "overtime")
            )
        if kind == "leaves":
            require(request.user, "accounts.view_staff_leave")
            rows = date_filter(
                models.EmployeeLeave.objects.filter(employee__in=employees),
                "start_date",
                "end_date",
            )
            if status:
                rows = rows.filter(status=status)
            return list(
                rows.values(
                    "employee__code", "leave_type__name", "start_date", "end_date", "days", "status"
                )
            )
        if kind == "salary-structures":
            require(request.user, "accounts.view_salary_setup")
            return list(
                models.SalaryStructure.objects.filter(institution=school()).values(
                    "code", "name", "basis", "basic", "active"
                )
            )
        if kind == "advances":
            require(request.user, "accounts.view_salary_setup")
            return list(
                models.SalaryAdvance.objects.filter(employee__in=employees).values(
                    "employee__code", "amount", "installment", "recover_from", "disbursed_at"
                )
            )
        if kind == "adjustments":
            require(request.user, "accounts.view_payroll")
            return list(
                models.PayrollAdjustment.objects.filter(entry__employee__in=employees).values(
                    "entry__employee__code", "entry__period__name", "amount", "created_at"
                )
            )
        if kind in {"payroll", "outstanding-payables", "salary-payments"}:
            require(request.user, "accounts.view_payroll")
            rows = models.PayrollEntry.objects.filter(
                employee__in=employees, run__status="finalized"
            )
            if period := request.query_params.get("period"):
                rows = rows.filter(period_id=serializers.UUIDField().run_validation(period))
            if kind == "salary-payments":
                return list(
                    date_filter(models.SalaryPayment.objects.filter(entry__in=rows), "date").values(
                        "entry__employee__code",
                        "entry__period__name",
                        "date",
                        "amount",
                        "method",
                        "reversal__created_at",
                    )
                )
            rows = date_filter(rows, "period__start_date", "period__end_date")
            results = []
            for row in rows.select_related("period"):
                due = payable(row)
                if kind != "outstanding-payables" or due > 0:
                    results.append(
                        {
                            "period": row.period.name,
                            "code": row.snapshot["code"],
                            "name": row.snapshot["name"],
                            "department": row.snapshot["department"],
                            "gross": row.snapshot["gross"],
                            "net": row.snapshot["net"],
                            "outstanding": str(due),
                        }
                    )
            return results
        raise NotFound()

    def report(self, request, kind):
        page = self.paginate_queryset(self.dataset(request, kind))
        return self.get_paginated_response(
            [
                {
                    key: str(value) if isinstance(value, Decimal) else value
                    for key, value in row.items()
                }
                for row in page
            ]
        )

    def export(self, request, kind):
        if kind in {
            "payroll",
            "outstanding-payables",
            "salary-payments",
            "adjustments",
            "salary-structures",
            "advances",
        }:
            require(request.user, "accounts.export_payroll")
        rows = self.dataset(request, kind)
        labels = list(rows[0]) if rows else ["No records"]
        if request.query_params.get("output") == "print":
            return html(
                kind.replace("-", " ").title(),
                ((" · ".join(labels), " · ".join(map(str, row.values()))) for row in rows),
            )
        return csv_download(kind, labels, (row.values() for row in rows))

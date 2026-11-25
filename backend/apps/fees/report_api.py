from base64 import b64encode
from collections import defaultdict
from decimal import Decimal
from typing import ClassVar

from django.db.models import Q
from django.http import HttpResponse
from django.utils.html import format_html, format_html_join
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.academics.access import school
from apps.academics.models import AcademicClass, AcademicSession, Section
from apps.accounts.access import permission_codes
from apps.admissions.models import StudentEnrollment
from apps.students.models import Student
from apps.students.reports import csv_download

from . import models
from .billing import plans
from .config_api import FeeView
from .ledger import DEFAULT_METHODS, ZERO, amounts, preferences, round_money, today
from .transactions_api import invoice_data, payment_data


class Criteria(serializers.Serializer):
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    session = serializers.UUIDField(required=False)
    academic_class = serializers.UUIDField(required=False)
    section = serializers.UUIDField(required=False)
    student = serializers.UUIDField(required=False)
    method = serializers.SlugField(required=False)
    batch = serializers.UUIDField(required=False)
    offset = serializers.IntegerField(min_value=0, required=False)
    search = serializers.CharField(required=False, max_length=120)


def html_document(title, rows, *, logo=None):
    mark = ""
    if logo:
        mark = format_html(
            '<img alt="Institution logo" width="80" src="data:image/png;base64,{}">',
            b64encode(logo).decode(),
        )
    content = format_html_join("", "<p><strong>{}</strong> {}</p>", rows)
    return HttpResponse(
        format_html(
            '<!doctype html><html lang="en"><meta charset="utf-8"><title>{}</title>'
            "<style>body{{font:16px system-ui;margin:2rem;overflow-wrap:anywhere}}</style>"
            "<main>{}<h1>{}</h1>{}</main></html>",
            title,
            mark,
            title,
            content,
        ),
        headers={"Cache-Control": "no-store"},
    )


class Reports(FeeView):
    permission_map: ClassVar = {
        "overview": "accounts.view_fees",
        "report": "accounts.view_fee_reports",
        "statement": ("fees.view_feeinvoice", "fees.view_feepayment"),
        "outstanding": "fees.view_feeinvoice",
        "export": "accounts.export_fee_reports",
        "challan": "accounts.print_fee_challan",
        "receipt": "accounts.print_fee_receipt",
        "batch_challans": "accounts.print_fee_challan",
        "lookups": "accounts.view_fees",
    }

    def criteria(self, request):
        form = Criteria(data=request.query_params)
        form.is_valid(raise_exception=True)
        return form.validated_data

    def invoices(self, request, *, filter_dates=True):
        criteria = self.criteria(request)
        rows = models.FeeInvoice.objects.filter(institution=school()).select_related("student")
        for name in ("session", "student", "academic_class", "section", "batch"):
            if name in criteria:
                field = (
                    f"enrollment__{name}_id"
                    if name in {"academic_class", "section"}
                    else f"{name}_id"
                )
                rows = rows.filter(**{field: criteria[name]})
        if search := criteria.get("search"):
            rows = rows.filter(
                Q(student__first_name__icontains=search)
                | Q(student__last_name__icontains=search)
                | Q(student__admission_number__icontains=search)
            )
        if filter_dates:
            if start := criteria.get("from_date"):
                rows = rows.filter(due_date__gte=start)
            if end := criteria.get("to_date"):
                rows = rows.filter(due_date__lte=end)
        return rows.order_by("-due_date", "-number")

    def lookups(self, request):
        institution = school()
        grants = permission_codes(request.user)
        students = Student.objects.filter(institution=institution).order_by("first_name", "pk")
        if search := self.criteria(request).get("search"):
            students = students.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(admission_number__icontains=search)
            )
        return Response(
            {
                "date": today(institution),
                "methods": preferences(institution).payment_methods or DEFAULT_METHODS,
                "sessions": list(
                    AcademicSession.objects.filter(institution=institution).values("id", "name")
                ),
                "classes": list(
                    AcademicClass.objects.filter(institution=institution).values("id", "name")
                ),
                "sections": list(
                    Section.objects.filter(academic_class__institution=institution).values(
                        "id", "name"
                    )
                ),
                "students": list(
                    students.values("id", "first_name", "last_name", "admission_number")[:100]
                )
                if grants.intersection(
                    {
                        "accounts.collect_fees",
                        "fees.view_feeinvoice",
                        "fees.change_studentconcession",
                    }
                )
                else [],
                "enrollments": list(
                    StudentEnrollment.objects.filter(student__in=students).values(
                        "id",
                        "student_id",
                        "student__first_name",
                        "student__admission_number",
                        "academic_class__name",
                        "session__name",
                    )[:100]
                )
                if "fees.change_studentfeeassignment" in grants
                else [],
            }
        )

    def statement(self, request, student_id):
        institution = school()
        student = get_object_or_404(Student, institution=institution, pk=student_id)
        day = today(institution)
        invoices = self.invoices(request).filter(student=student)
        rows = [invoice_data(row, day) for row in invoices]
        payments = models.FeePayment.objects.filter(institution=institution, student=student)
        totals = {
            key: str(sum((Decimal(row[key]) for row in rows), ZERO))
            for key in ("total", "paid", "outstanding")
        }
        overdue = sum((Decimal(row["outstanding"]) for row in rows if row["due_date"] < day), ZERO)
        current = student.enrollments.filter(
            session__is_current=True, enrollment_date__lte=day, ended_on__isnull=True
        ).first()
        names = (
            sorted({item.category.name for item in plans(institution, current, day, None).values()})
            if current
            else []
        )
        concessions = models.StudentConcession.objects.filter(
            student=student,
            status="approved",
            start_date__lte=day,
            end_date__gte=day,
        ).values_list("label", flat=True)
        adjustments = models.FeeAdjustment.objects.filter(invoice__in=invoices)
        return Response(
            {
                "invoices": rows,
                "payments": [payment_data(row) for row in payments],
                "invoiced": totals["total"],
                "outstanding": totals["outstanding"],
                "paid": totals["paid"],
                "overdue": str(overdue),
                "plans": names,
                "concessions": list(concessions),
                "adjustments": [
                    {
                        "id": row.pk,
                        "kind": row.kind,
                        "amount": str(row.amount),
                        "approved": bool(row.approved_at),
                    }
                    for row in adjustments
                ],
            },
            headers={"Cache-Control": "no-store"},
        )

    def outstanding(self, request, student_id):
        day = today(school())
        rows = (
            invoice_data(row, day)
            for row in self.invoices(request).filter(student_id=student_id, voided=False)
        )
        return Response([row for row in rows if Decimal(row["outstanding"]) > 0])

    def collections(self, request, kind):
        from zoneinfo import ZoneInfo

        criteria = self.criteria(request)
        zone = ZoneInfo(school().timezone)
        invoices = self.invoices(request, filter_dates=False)
        rows = (
            models.FeePaymentAllocation.objects.filter(invoice__in=invoices)
            .select_related("payment", "invoice")
            .prefetch_related("refunds")
        )
        if method := criteria.get("method"):
            rows = rows.filter(payment__method=method)
        totals = defaultdict(lambda: ZERO)

        def record(day, amount, method):
            if day < criteria.get("from_date", day) or day > criteria.get("to_date", day):
                return
            key = method if kind == "methods" else str(day)[: 7 if kind == "monthly" else 10]
            totals[key] += amount

        for row in rows:
            payment = row.payment
            if kind != "refunds":
                record(payment.date, row.amount, payment.method)
            if payment.reversed_at:
                day = payment.reversed_at.astimezone(zone).date()
                record(day, row.amount if kind == "refunds" else -row.amount, payment.method)
            for refund in row.refunds.all():
                record(
                    refund.date,
                    refund.amount if kind == "refunds" else -refund.amount,
                    payment.method,
                )
        return [{"period": day, "amount": str(value)} for day, value in sorted(totals.items())]

    def invoices_report(self, request, kind):
        day = today(school())
        groups = defaultdict(lambda: {"total": ZERO, "paid": ZERO, "outstanding": ZERO})
        rows = []
        for invoice in self.invoices(request):
            values = invoice_data(invoice, day)
            balance = Decimal(values["outstanding"])
            late = max(0, (day - invoice.due_date).days)
            if kind in {"outstanding", "defaulters", "aging"} and (
                not balance or (kind == "defaulters" and not late)
            ):
                continue
            if kind in {"aging", "class-summary", "session-summary"}:
                bucket = (
                    "Current"
                    if not late
                    else "1-30"
                    if late <= 30
                    else "31-60"
                    if late <= 60
                    else "61-90"
                    if late <= 90
                    else "Over 90"
                )
                key = {
                    "aging": bucket,
                    "class-summary": invoice.issued_details.get("class", ""),
                    "session-summary": invoice.issued_details.get("session", ""),
                }[kind]
                for field in groups[key]:
                    groups[key][field] += Decimal(values[field])
            else:
                rows.append(
                    {
                        "invoice": invoice.number,
                        **(
                            {"invoice_id": invoice.pk, "student_id": invoice.student_id}
                            if kind == "outstanding"
                            else {}
                        ),
                        "admission": invoice.student.admission_number,
                        "student": invoice.issued_details.get("student", ""),
                        "class": invoice.issued_details.get("class", ""),
                        "due_date": invoice.due_date,
                        **{key: values[key] for key in ("total", "paid", "outstanding", "status")},
                        "overdue_days": late if balance else 0,
                    }
                )
        return (
            [
                {"group": key, **{field: str(value) for field, value in group.items()}}
                for key, group in sorted(groups.items())
            ]
            if groups
            else rows
        )

    def student_ledger(self, request):
        from zoneinfo import ZoneInfo

        criteria = self.criteria(request)
        zone = ZoneInfo(school().timezone)
        invoices = self.invoices(request, filter_dates=False).prefetch_related(
            "adjustments",
            "allocations__payment",
            "allocations__refunds",
        )
        events = []
        for invoice in invoices:
            detail = invoice.issued_details

            def add(day, action, reference, value):
                if criteria.get("from_date", day) <= day <= criteria.get("to_date", day):
                    events.append(
                        {
                            "date": day,
                            "admission": detail.get("admission", ""),
                            "student": detail.get("student", ""),
                            "invoice": invoice.number,
                            "event": action,
                            "reference": reference,
                            "change": str(value),
                        }
                    )

            if invoice.voided:
                add(invoice.issue_date, "Voided invoice", invoice.number, ZERO)
                continue
            add(invoice.issue_date, "Invoice", invoice.number, invoice.issued_total)
            for correction in invoice.adjustments.all():
                if correction.approved_at:
                    day = correction.approved_at.astimezone(zone).date()
                    amount = correction.amount if correction.kind == "debit" else -correction.amount
                    add(day, correction.kind, correction.pk, amount)
            for allocation in invoice.allocations.all():
                payment = allocation.payment
                if criteria.get("method") not in (None, payment.method):
                    continue
                add(payment.date, "Payment", payment.number, -allocation.amount)
                if payment.reversed_at:
                    day = payment.reversed_at.astimezone(zone).date()
                    add(day, "Reversal", payment.number, allocation.amount)
                for refund in allocation.refunds.all():
                    add(refund.date, "Refund", refund.pk, refund.amount)
        return sorted(events, key=lambda row: (row["date"], row["invoice"], str(row["reference"])))

    def table(self, request, kind):
        if kind == "student-ledger":
            return self.student_ledger(request)
        if kind in {"collections", "monthly", "methods", "refunds"}:
            return self.collections(request, kind)
        if kind in {
            "aging",
            "outstanding",
            "defaulters",
            "class-summary",
            "session-summary",
            "invoices",
            "student-ledger",
        }:
            return self.invoices_report(request, kind)
        institution = school()
        if kind == "structures":
            return list(
                models.FeeStructureItem.objects.filter(structure__institution=institution).values(
                    "structure__name",
                    "category__name",
                    "recurrence",
                    "amount",
                )
            )
        if kind == "concessions":
            return list(
                models.StudentConcession.objects.filter(institution=institution).values(
                    "label",
                    "kind",
                    "value",
                    "status",
                    "student__admission_number",
                )
            )
        if kind == "receipts":
            return list(
                models.FeeReceipt.objects.filter(payment__institution=institution).values(
                    "number",
                    "payment__number",
                    "payment__date",
                    "payment__amount",
                    "payment__reversed_at",
                )
            )
        raise NotFound()

    def report(self, request, kind):
        rows = self.paginate_queryset(self.table(request, kind))
        return self.get_paginated_response(
            [
                {
                    key: str(value) if isinstance(value, Decimal) else value
                    for key, value in row.items()
                }
                for row in rows
            ]
        )

    def export(self, request, kind):
        rows = [
            {key: value for key, value in row.items() if key not in {"invoice_id", "student_id"}}
            for row in self.table(request, kind)
        ]
        if request.query_params.get("format_type") == "print":
            return html_document(
                "Fee report",
                [(" · ".join(row), " · ".join(map(str, row.values()))) for row in rows],
            )
        return csv_download(
            "fees-" + kind,
            list(rows[0]) if rows else ["No records"],
            (row.values() for row in rows),
        )

    def overview(self, request):
        day = today(school())
        total = paid = due = late = ZERO
        for row in self.invoices(request).filter(voided=False):
            record = amounts(row, day)
            total += record["total"]
            paid += record["paid"]
            due += record["outstanding"]
            if row.due_date < day:
                late += record["outstanding"]
        monthly = self.collections(request, "monthly")
        daily = self.collections(request, "collections")
        return Response(
            {
                "invoiced": str(total),
                "outstanding": str(due),
                "overdue": str(late),
                "collected_this_month": next(
                    (row["amount"] for row in monthly if row["period"] == str(day)[:7]), "0.00"
                ),
                "collected_today": next(
                    (row["amount"] for row in daily if row["period"] == str(day)), "0.00"
                ),
                "collection_rate": str(round_money(paid * 100 / total)) if total else None,
                "trend": monthly[-12:],
                "methods": self.collections(request, "methods"),
                "classes": self.invoices_report(request, "class-summary"),
            }
        )

    def challan_rows(self, invoice):
        day = today(school())
        current = invoice_data(invoice, day)
        older = models.FeeInvoice.objects.filter(
            student=invoice.student,
            voided=False,
            period__lt=invoice.period,
        )
        past_due = sum((amounts(row, day)["outstanding"] for row in older), ZERO)
        return [
            *invoice.issued_details.items(),
            ("Invoice", invoice.number),
            ("Month", invoice.period),
            ("Due date", invoice.due_date),
            ("Status", current["status"]),
            *(
                (item.description, f"{item.amount} less {item.discount}")
                for item in invoice.items.all()
            ),
            ("Current charges", f"{invoice.currency} {current['total']}"),
            ("Discount", f"{invoice.currency} {invoice.discount}"),
            ("Outstanding", f"{invoice.currency} {current['outstanding']}"),
            ("Previous dues", f"{invoice.currency} {past_due}"),
            ("Total payable", f"{invoice.currency} {Decimal(current['outstanding']) + past_due}"),
        ]

    def challan(self, request, pk):
        invoice = get_object_or_404(self.invoices(request), pk=pk)
        return html_document("Fee challan", self.challan_rows(invoice), logo=school().logo_png)

    def batch_challans(self, request):
        rows = self.invoices(request).filter(voided=False)
        offset = self.criteria(request).get("offset", 0)
        return html_document(
            "Fee challans",
            [item for row in rows[offset : offset + 200] for item in self.challan_rows(row)],
        )

    def receipt(self, request, pk):
        receipt = get_object_or_404(
            models.FeeReceipt.objects.select_related("payment"),
            payment__institution=school(),
            payment_id=pk,
        )
        parts = [(key, value) for key, value in receipt.details.items() if key != "allocations"]
        has_refund = receipt.payment.allocations.filter(refunds__isnull=False).exists()
        status = (
            "Reversed"
            if receipt.payment.reversed_at
            else "Refund recorded"
            if has_refund
            else "Posted"
        )
        return html_document(
            "Payment receipt",
            [
                ("Receipt", receipt.number),
                ("Status", status),
                *parts,
                *(
                    (item["invoice"], f"Applied {item['amount']} · Remaining {item['remaining']}")
                    for item in receipt.details["allocations"]
                ),
            ],
            logo=school().logo_png,
        )

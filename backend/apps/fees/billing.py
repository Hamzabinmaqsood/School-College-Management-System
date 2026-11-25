import json
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.academics.access import Conflict, school
from apps.academics.models import AcademicClass, AcademicSession, Section
from apps.accounts.authentication import audit
from apps.admissions.models import StudentEnrollment

from .ledger import ZERO, amounts, identifier, preferences, round_money, today
from .models import (
    FeeCategory,
    FeeGenerationBatch,
    FeeInvoice,
    FeeInvoiceItem,
    FeeStructure,
    StudentConcession,
    StudentFeeAssignment,
)


def identity(item, period, reference):
    kind = item.recurrence
    if kind == "monthly":
        return period.strftime("%Y-%m")
    if kind == "quarterly":
        return f"{period.year}-Q{(period.month - 1) // 3 + 1}"
    if kind == "annual":
        return f"{period.year}-annual"
    if kind == "term":
        return "term"
    return f"{kind}:{reference}" if reference else None


def plans(institution, enrollment, day, structure_id):
    active = FeeStructure.objects.filter(
        institution=institution,
        session=enrollment.session,
        academic_class=enrollment.academic_class,
        status="active",
        start_date__lte=day,
        end_date__gte=day,
    )
    exact = active.filter(section=enrollment.section).first()
    plan = exact or active.filter(section=None).first()
    assignments = list(
        StudentFeeAssignment.objects.filter(
            institution=institution,
            enrollment=enrollment,
            active=True,
            start_date__lte=day,
            end_date__gte=day,
        ).select_related("structure", "category")
    )
    override = next((row.structure for row in assignments if row.structure), None)
    if override and override.status == "active" and override.start_date <= day <= override.end_date:
        plan = override
    if structure_id and (not plan or plan.pk != structure_id):
        return {}
    items = (
        {
            row.category_id: row
            for row in plan.items.filter(category__active=True).select_related("category")
        }
        if plan
        else {}
    )
    for row in assignments:
        if row.category and row.category.active:
            row.recurrence = row.category.recurrence
            items[row.category_id] = row
    return items


def discount_for(amount, concessions, category_id, stack):
    matching = [row for row in concessions if row.category_id in (None, category_id)]
    discounts = []
    for row in matching:
        if row.kind == "full":
            discounts.append(amount)
        elif row.kind == "percent":
            discounts.append(round_money(amount * row.value / Decimal("100")))
        else:
            discounts.append(row.value)
    return min(amount, sum(discounts, ZERO) if stack else max(discounts, default=ZERO))


def calculate(values, institution):
    period = values["period"]
    if period.day != 1:
        raise ValidationError({"period": "Use the first day of the billing month."})
    session = AcademicSession.objects.filter(pk=values["session"], institution=institution).first()
    last = period.replace(day=monthrange(period.year, period.month)[1])
    if not session or session.end_date < period or session.start_date > last:
        raise ValidationError("Choose a billing month in the academic session.")
    selected_class = values.get("academic_class")
    if (
        selected_class
        and not AcademicClass.objects.filter(pk=selected_class, institution=institution).exists()
    ):
        raise ValidationError({"academic_class": "Choose an institution class."})
    if section := values.get("section"):
        group = Section.objects.filter(pk=section, academic_class__institution=institution).first()
        if not group or (selected_class and group.academic_class_id != selected_class):
            raise ValidationError({"section": "Choose a section in the selected class."})
    if (structure := values.get("structure")) and not FeeStructure.objects.filter(
        pk=structure,
        institution=institution,
        session=session,
        status="active",
    ).exists():
        raise ValidationError({"structure": "Choose an active structure in this session."})
    config = preferences(institution)
    cutoff = min(last, session.end_date)
    rows = (
        StudentEnrollment.objects.filter(
            session=session,
            enrollment_date__lte=cutoff,
            student__admission_date__lte=cutoff,
        )
        .filter(Q(ended_on__isnull=True) | Q(ended_on__gt=period))
        .select_related(
            "student",
            "academic_class",
            "section",
            "session",
        )
        .order_by("student_id", "-enrollment_date", "-created_at", "-pk")
    )
    if student := values.get("student"):
        rows = rows.filter(student_id=student)
    seen, invoices, errors, skipped = set(), [], [], 0
    eligible = 0
    late_category = None
    if config.late_fee_enabled and config.late_fee and not values.get("reference"):
        late_category = FeeCategory.objects.filter(
            institution=institution, code__iexact="LATE", active=True
        ).first()
        if not late_category:
            raise ValidationError(
                "Activate a LATE fee category before enabling automatic late fees."
            )
    assessment = min(today(institution), period.replace(day=min(config.billing_day, last.day)))
    for enrollment in rows:
        student_id = enrollment.student_id
        if student_id in seen:
            continue
        seen.add(student_id)
        if values.get("academic_class") not in (None, enrollment.academic_class_id):
            continue
        if values.get("section") not in (None, enrollment.section_id):
            continue
        first = max(
            period,
            session.start_date,
            enrollment.enrollment_date,
            enrollment.student.admission_date,
        )
        end = (
            min(cutoff, enrollment.ended_on - timedelta(days=1)) if enrollment.ended_on else cutoff
        )
        if first > end:
            continue
        eligible += 1
        concessions = StudentConcession.objects.filter(
            institution=institution,
            status="approved",
            student_id=student_id,
            session=session,
            start_date__lte=end,
            end_date__gte=end,
        )
        existing = set(
            FeeInvoiceItem.objects.filter(student_id=student_id, session=session).values_list(
                "category_id", "identity"
            )
        )
        items = []
        for category, item in plans(institution, enrollment, end, values.get("structure")).items():
            key = identity(item, period, values.get("reference", ""))
            if not key or (
                values.get("reference") and item.recurrence not in {"one_time", "custom"}
            ):
                continue
            if (category, key) in existing:
                skipped += 1
                continue
            gross = item.amount
            if config.prorate and item.recurrence == "monthly":
                gross = round_money(gross * Decimal((end - first).days + 1) / Decimal(last.day))
            reduction = discount_for(gross, concessions, category, config.stack_discounts)
            items.append(
                {
                    "category_id": category,
                    "identity": key,
                    "description": item.category.name,
                    "amount": gross,
                    "discount": reduction,
                }
            )
        if late_category:
            before_grace = assessment - timedelta(days=config.grace_days)
            overdue = FeeInvoice.objects.filter(
                student_id=student_id,
                session=session,
                period__lt=period,
                due_date__lt=before_grace,
                voided=False,
            )
            for source in overdue:
                key = f"late:{source.pk}"
                if (late_category.pk, key) not in existing and amounts(source, assessment)[
                    "outstanding"
                ] > ZERO:
                    items.append(
                        {
                            "category_id": late_category.pk,
                            "identity": key,
                            "description": f"Late fee for {source.number}",
                            "amount": config.late_fee,
                            "discount": ZERO,
                        }
                    )
        if items:
            invoices.append((enrollment, items))
        elif not existing:
            errors.append(enrollment.student.admission_number)
    return session, config, invoices, eligible, skipped, errors


def run_billing(values, request, *, post=False):
    institution = school(lock=post)
    session, config, invoices, eligible, skipped, errors = calculate(values, institution)
    period = values["period"]
    gross = sum((item["amount"] for _, items in invoices for item in items), ZERO)
    discounts = sum((item["discount"] for _, items in invoices for item in items), ZERO)
    result = {
        "eligible": eligible,
        "invoices": len(invoices),
        "duplicate_lines": skipped,
        "subtotal": str(gross),
        "discount": str(discounts),
        "total": str(gross - discounts),
        "no_charge_students": errors,
    }
    fingerprint = sha256(
        json.dumps(
            {
                "currency": config.currency,
                "day": config.due_day,
                "rows": [(str(enrollment.pk), items) for enrollment, items in invoices],
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    result["preview_key"] = fingerprint
    if not post:
        return result
    if values.get("preview_key", fingerprint) != fingerprint and invoices:
        raise Conflict(
            "Billing changed after the preview. Review the updated amounts before issuing."
        )

    day = today(institution)
    due = max(
        day, period.replace(day=min(config.due_day, monthrange(period.year, period.month)[1]))
    )
    batch = FeeGenerationBatch.objects.create(
        institution=institution,
        session=session,
        period=period,
        created_by=request.user,
        criteria={key: str(value) for key, value in values.items() if key != "preview_key"},
        result=result,
    )
    for enrollment, items in invoices:
        subtotal = sum(item["amount"] for item in items)
        reduction = sum(item["discount"] for item in items)
        invoice = FeeInvoice.objects.create(
            institution=institution,
            session=session,
            student=enrollment.student,
            enrollment=enrollment,
            batch=batch,
            created_by=request.user,
            period=period,
            issue_date=day,
            due_date=due,
            number=identifier(config.invoice_prefix, day),
            currency=config.currency,
            subtotal=subtotal,
            discount=reduction,
            issued_total=subtotal - reduction,
            issued_details={
                "student": " ".join(
                    (enrollment.student.first_name, enrollment.student.last_name)
                ).strip(),
                "admission": enrollment.student.admission_number,
                "class": enrollment.academic_class.name,
                "section": enrollment.section.name if enrollment.section else "",
                "session": session.name,
                "institution": institution.name,
                "address": institution.address,
                "instructions": config.challan_instructions,
            },
        )
        FeeInvoiceItem.objects.bulk_create(
            [
                FeeInvoiceItem(invoice=invoice, student=invoice.student, session=session, **item)
                for item in items
            ]
        )
    audit(request, "FEE_BATCH_POSTED", "feegenerationbatch", batch, invoice_count=len(invoices))
    return result | {"batch": batch.pk}

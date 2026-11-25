from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from rest_framework.exceptions import ValidationError

from apps.academics.access import Conflict
from apps.accounts.authentication import audit

from . import models

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def rounded(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def evaluate(scheme, obtained, percentage):
    value = percentage if scheme.basis == "percentage" else obtained
    for band in scheme.bands.all():
        if value >= band.minimum:
            return band.label, band.points, band.passing
    raise ValidationError("A grade does not cover the calculation.")


def subject_result(subject, marks, scheme):
    maximum = obtained = ZERO
    fails = False
    blocked = set()
    for component, mark in marks:
        if mark.status == "withheld":
            blocked.add("withheld")
            continue
        if mark.status == "missing" and component.required:
            blocked.add("incomplete")
            continue
        if mark.status not in {"marked", "absent"}:
            continue
        value = mark.obtained if mark.obtained is not None else ZERO
        if component.minimum is not None and value < component.minimum:
            fails = True
        if subject.weighted:
            maximum += component.weight
            obtained += value / component.maximum * component.weight
        else:
            maximum += component.maximum
            obtained += value
    result = {"subject": subject.subject_name, "subject_id": str(subject.subject_id)}
    if blocked or not maximum:
        status = "withheld" if "withheld" in blocked else "incomplete" if blocked else "exempt"
        return result | {
            "status": status,
            "obtained": None,
            "maximum": None,
            "percentage": None,
            "grade": None,
            "points": None,
        }
    pct = rounded(obtained / maximum * HUNDRED)
    score = rounded(obtained)
    grade, points, passing = evaluate(subject.scheme or scheme, score, pct)
    return result | {
        "status": "pass" if passing and not fails and pct >= subject.passing_percentage else "fail",
        "obtained": str(score),
        "maximum": str(rounded(maximum)),
        "percentage": str(pct),
        "grade": grade,
        "points": str(points) if points is not None else None,
    }


def build(group):
    exam = group.exam
    subjects = list(group.subjects.select_related("scheme").prefetch_related("scheme__bands"))
    marks = defaultdict(list)
    for mark in models.StudentAssessmentMark.objects.filter(
        registration__group=group
    ).select_related("submission__component"):
        component = mark.submission.component
        marks[(mark.registration_id, component.subject_id)].append((component, mark))
    rows = []
    for entry in group.registrations.filter(excluded=False).prefetch_related("optional_subjects"):
        selected = {subject.pk for subject in entry.optional_subjects.all()}
        items = [
            subject_result(subject, marks[(entry.pk, subject.pk)], exam.scheme)
            for subject in subjects
            if not subject.optional or subject.pk in selected
        ]
        comparable = [item for item in items if item["status"] in {"pass", "fail"}]
        withdrawn = any(item["status"] == "withheld" for item in items)
        scores = {
            "obtained": None,
            "maximum": None,
            "percentage": None,
            "grade": None,
            "gpa": None,
            "status": "withheld" if withdrawn else "incomplete",
            "rank": None,
        }
        if not withdrawn and all(item["status"] != "incomplete" for item in items) and comparable:
            obtained = sum(Decimal(item["obtained"]) for item in comparable)
            maximum = sum(Decimal(item["maximum"]) for item in comparable)
            pct = rounded(obtained / maximum * HUNDRED)
            grade, _, passing = evaluate(exam.scheme, obtained, pct)
            passed = passing and all(item["status"] == "pass" for item in comparable)
            points = [item["points"] for item in comparable]
            gpa = (
                rounded(sum(Decimal(point) for point in points) / Decimal(len(points)))
                if all(point is not None for point in points)
                else None
            )
            scores.update(
                {
                    "obtained": str(rounded(obtained)),
                    "maximum": str(rounded(maximum)),
                    "percentage": str(pct),
                    "grade": grade,
                    "status": "pass" if passed else "fail",
                    "gpa": str(gpa) if gpa is not None else None,
                }
            )
        rows.append(
            (
                entry,
                scores
                | {
                    **entry.details,
                    "subjects": items,
                    "exam": exam.name,
                    "session": exam.session.name,
                    "scheme": f"{exam.scheme.name} v{exam.scheme.version}",
                },
            )
        )
    rank(rows, exam)
    return rows


def rank(rows, exam):
    if exam.ranking == "disabled":
        return
    sets = defaultdict(list)
    for entry, scores in rows:
        if scores["status"] != "pass":
            continue
        signature = tuple(
            sorted(
                (row["subject_id"], row["maximum"]) for row in scores["subjects"] if row["maximum"]
            )
        )
        sets[(entry.section_id if exam.rank_by_section else None, signature)].append(scores)
    for scores in sets.values():
        previous = None
        position = 0
        for index, item in enumerate(
            sorted(scores, key=lambda row: Decimal(row["percentage"]), reverse=True), 1
        ):
            value = item["percentage"]
            if value != previous:
                position = index if exam.ranking == "competition" else position + 1
            previous = value
            item["rank"] = position


def calculate(group, request):
    if group.exam.status not in {"open", "closed"}:
        raise ValidationError("Open marks entry before calculating results.")
    if models.ResultPublication.objects.filter(group=group, active=True).exists():
        raise Conflict("Withdraw the published results before calculating a new revision.")
    previous = group.calculations.order_by("-revision").first()
    revision = previous.revision + 1 if previous else 1
    rows = build(group)
    run = models.ResultCalculation.objects.create(
        group=group, revision=revision, created_by=request.user
    )
    group.calculations.exclude(pk=run.pk).update(superseded=True)
    models.StudentExamResult.objects.bulk_create(
        [
            models.StudentExamResult(
                calculation=run,
                registration=entry,
                status=scores["status"],
                percentage=scores["percentage"],
                snapshot=scores,
            )
            for entry, scores in rows
        ]
    )
    audit(request, "EXAM_RESULTS_CALCULATED", "resultcalculation", run, revision=revision)
    return run

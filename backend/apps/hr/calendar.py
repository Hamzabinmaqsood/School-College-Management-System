from calendar import monthrange
from datetime import date

from apps.attendance.models import AttendanceHoliday, AttendanceSettings

from . import models
from .schedule import elapsed, is_overnight, scheduled_day


def month_rows(employee, month, institution):
    end = month.replace(day=monthrange(month.year, month.month)[1])
    contracts = list(
        models.EmploymentContract.objects.filter(
            employee=employee,
            active=True,
            start_date__lte=end,
            end_date__gte=month,
        ).order_by("-start_date")
    )
    attendance = {
        row.date: row
        for row in models.EmployeeAttendance.objects.filter(
            employee=employee,
            date__range=(month, end),
        )
    }
    overtime = dict(
        models.StaffOvertime.objects.filter(
            attendance__employee=employee,
            attendance__date__range=(month, end),
            status="approved",
        ).values_list("attendance__date", "snapshot")
    )
    leaves = list(
        models.EmployeeLeave.objects.filter(
            employee=employee,
            status="approved",
            start_date__lte=end,
            end_date__gte=month,
        )
    )
    holidays = {
        row.date: row
        for row in AttendanceHoliday.objects.filter(
            institution=institution,
            date__range=(month, end),
        )
    }
    settings = AttendanceSettings.objects.filter(institution=institution).first()
    fallback = settings.non_teaching_weekdays if settings else []
    for number in range(1, end.day + 1):
        day = date(month.year, month.month, number)
        contract = next((c for c in contracts if c.start_date <= day <= c.end_date), None)
        record = attendance.get(day)
        holiday = holidays.get(day)
        if record:
            status = record.status
        elif day < employee.joined_on or (employee.ended_on and day > employee.ended_on):
            status = "outside_employment"
        elif holiday and holiday.kind != "working":
            status = "holiday"
        elif any(leave.start_date <= day <= leave.end_date for leave in leaves):
            status = "leave"
        elif not scheduled_day(day, contract, holiday, fallback):
            status = "non_working"
        else:
            status = "unrecorded"

        late = early = expected = None
        if contract and contract.shift_start and contract.shift_end:
            expected = (
                elapsed(
                    contract.shift_start,
                    contract.shift_end,
                    overnight=is_overnight(contract),
                ).total_seconds()
                / 60
                - contract.break_minutes
            )
        if record and expected is not None:
            if record.check_in:
                late = max(0, elapsed(contract.shift_start, record.check_in).total_seconds() / 60)
            if record.check_out:
                overnight = is_overnight(contract)
                scheduled = elapsed(contract.shift_start, contract.shift_end, overnight=overnight)
                actual = elapsed(contract.shift_start, record.check_out, overnight=overnight)
                early = max(0, (scheduled - actual).total_seconds() / 60)
        yield {
            "date": day,
            "status": status,
            "attendance": record.pk if record else None,
            "calendar_exception": holiday.name if holiday else None,
            "calendar_exception_kind": holiday.kind if holiday else None,
            "expected_minutes": expected,
            "overtime_hours": overtime.get(day, {}).get("hours"),
            "check_in": record.check_in if record else None,
            "check_out": record.check_out if record else None,
            "shift_start": contract.shift_start if contract else None,
            "shift_end": contract.shift_end if contract else None,
            "overnight": is_overnight(contract),
            "late_minutes": late,
            "early_minutes": early,
            "late": late > contract.late_tolerance_minutes if late is not None else None,
            "early": early > contract.early_tolerance_minutes if early is not None else None,
        }

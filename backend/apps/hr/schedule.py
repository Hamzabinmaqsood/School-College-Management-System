from datetime import date, datetime, timedelta


def elapsed(start, end, *, overnight=False):
    anchor = date.min
    delta = datetime.combine(anchor, end) - datetime.combine(anchor, start)
    if overnight and delta < timedelta():
        delta += timedelta(days=1)
    return delta


def is_overnight(contract):
    return bool(
        contract
        and contract.shift_start
        and contract.shift_end
        and contract.shift_end < contract.shift_start
    )


def scheduled_day(day, contract, holiday, fallback=()):
    if holiday:
        return holiday.kind == "working"
    weekdays = contract.weekdays if contract and contract.weekdays else None
    return day.weekday() in weekdays if weekdays else day.weekday() not in fallback

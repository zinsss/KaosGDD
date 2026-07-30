import calendar
import re
from datetime import date


WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]


def validate_month(value):
    month = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("invalid_caregiver_month")
    year, month_number = (int(part) for part in month.split("-", 1))
    if year < 2000 or year > 2200 or month_number < 1 or month_number > 12:
        raise ValueError("invalid_caregiver_month")
    return month


def validate_day(value):
    raw = str(value or "").strip()
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("invalid_caregiver_date") from exc
    if parsed.year < 2000 or parsed.year > 2200 or parsed.isoformat() != raw:
        raise ValueError("invalid_caregiver_date")
    return raw


def nonnegative_integer(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def time_minutes(value):
    raw = str(value or "")
    if not re.fullmatch(r"\d{2}:\d{2}", raw):
        return None
    hour, minute = (int(part) for part in raw.split(":", 1))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def normalized_sessions(sessions):
    if not isinstance(sessions, list):
        return []
    normalized = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        start = time_minutes(session.get("start"))
        end = time_minutes(session.get("end"))
        if start is not None and end is not None and end > start:
            normalized.append(
                {
                    "start": f"{start // 60:02d}:{start % 60:02d}",
                    "end": f"{end // 60:02d}:{end % 60:02d}",
                }
            )
    return normalized


def session_minutes(sessions):
    return sum(
        time_minutes(session["end"]) - time_minutes(session["start"])
        for session in normalized_sessions(sessions)
    )


def normalized_extras(extras):
    if not isinstance(extras, list):
        return []
    return [
        {
            "label": str(extra.get("label") or "").strip(),
            "amount": nonnegative_integer(extra.get("amount")),
        }
        for extra in extras
        if isinstance(extra, dict)
        and (str(extra.get("label") or "").strip() or nonnegative_integer(extra.get("amount")))
    ]


def settings_for_month(settings, month):
    candidates = []
    for setting in settings if isinstance(settings, list) else []:
        if not isinstance(setting, dict):
            continue
        setting_month = str(setting.get("month") or "")
        try:
            validate_month(setting_month)
        except ValueError:
            continue
        if setting_month <= month:
            candidates.append(setting)
    selected = max(candidates, key=lambda item: item["month"]) if candidates else {}
    return {
        "month": month,
        "sourceMonth": selected.get("month") or "",
        "hourlyWage": nonnegative_integer(selected.get("hourlyWage")),
        "transportFee": nonnegative_integer(selected.get("transportFee")),
    }


def compact_hours(minutes):
    return round(minutes / 60, 2)


def caregiver_base_pay(minutes, hourly_wage):
    return (minutes * hourly_wage + 30) // 60


def calculate_month(month, days, settings):
    selected_month = validate_month(month)
    year, month_number = (int(part) for part in selected_month.split("-", 1))
    setting = settings_for_month(settings, selected_month)
    records = {}
    for record in days if isinstance(days, list) else []:
        if not isinstance(record, dict):
            continue
        date_value = str(record.get("date") or "")
        if date_value.startswith(f"{selected_month}-"):
            records[date_value] = record

    daily = []
    total_minutes = 0
    total_extras = 0
    worked_days = 0
    for day_number in range(1, calendar.monthrange(year, month_number)[1] + 1):
        date_value = f"{selected_month}-{day_number:02d}"
        record = records.get(date_value, {})
        sessions = normalized_sessions(record.get("sessions"))
        minutes = session_minutes(sessions)
        extras = normalized_extras(record.get("extras"))
        extras_total = sum(extra["amount"] for extra in extras)
        if minutes > 0:
            worked_days += 1
            total_minutes += minutes
        total_extras += extras_total
        daily.append(
            {
                "date": date_value,
                "day": day_number,
                "weekday": WEEKDAY_LABELS[date(year, month_number, day_number).weekday()],
                "minutes": minutes,
                "hours": compact_hours(minutes),
                "basePay": caregiver_base_pay(minutes, setting["hourlyWage"]),
                "extras": extras_total,
                "sessions": sessions,
                "extraItems": extras,
                "notes": ", ".join(
                    f"{extra['label'] or '추가'} {extra['amount']:,}" for extra in extras
                ),
            }
        )

    base_pay = caregiver_base_pay(total_minutes, setting["hourlyWage"])
    total = base_pay + total_extras + setting["transportFee"]
    return {
        "ok": True,
        "live": True,
        "month": selected_month,
        "settings": setting,
        "summary": {
            "days": worked_days,
            "minutes": total_minutes,
            "hours": compact_hours(total_minutes),
            "hourlyWage": setting["hourlyWage"],
            "basePay": base_pay,
            "extras": total_extras,
            "transportFee": setting["transportFee"],
            "total": total,
        },
        "daily": daily,
    }

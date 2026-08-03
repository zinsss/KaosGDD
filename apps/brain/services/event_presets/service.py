import uuid
from datetime import datetime

from models.database import connect


PROFILE_OWNERS = {
    "main": ("zin", "family"),
    "family": ("wife", "family"),
}

SELECT_COLUMNS = """
    id, owner, name, title, all_day, start_time, end_time, alarm_time,
    memo, created_at, updated_at
"""


def clean_text(value):
    return str(value or "").strip()


def owners_for_profile(profile):
    if profile not in PROFILE_OWNERS:
        raise ValueError("invalid_profile")
    return PROFILE_OWNERS[profile]


def validate_time(value, field, optional=False):
    raw = clean_text(value)
    if optional and not raw:
        return None
    try:
        parsed = datetime.strptime(raw, "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"invalid_{field}") from exc
    if parsed.minute % 5:
        raise ValueError(f"invalid_{field}_step")
    return parsed


def validate_payload(payload, profile):
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    name = " ".join(clean_text(payload.get("name")).split())
    title = " ".join(clean_text(payload.get("title")).split())
    if not name:
        raise ValueError("name_required")
    if not title:
        raise ValueError("title_required")
    owner = "family" if payload.get("shareFamily") is True else ("wife" if profile == "family" else "zin")
    return {
        "owner": owner,
        "name": name,
        "title": title,
        "all_day": payload.get("allDay") is not False,
        "start_time": validate_time(payload.get("startTime") or "09:00", "startTime"),
        "end_time": validate_time(payload.get("endTime") or "10:00", "endTime"),
        "alarm_time": validate_time(payload.get("alarm"), "alarm", optional=True),
        "memo": clean_text(payload.get("memo")),
    }


def row_to_item(row):
    if not row:
        return None
    values = list(row)
    return {
        "id": values[0],
        "owner": values[1],
        "name": values[2],
        "title": values[3],
        "all_day": values[4],
        "start_time": values[5],
        "end_time": values[6],
        "alarm_time": values[7],
        "memo": values[8],
        "created_at": values[9],
        "updated_at": values[10],
    }


def iso_value(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else ""


def time_value(value):
    return str(value)[:5] if value is not None else ""


def public_item(item):
    return {
        "id": item["id"],
        "name": item["name"],
        "title": item["title"],
        "allDay": bool(item["all_day"]),
        "startTime": time_value(item["start_time"]),
        "endTime": time_value(item["end_time"]),
        "alarm": time_value(item["alarm_time"]),
        "memo": item["memo"],
        "shareFamily": item["owner"] == "family",
        "owner": item["owner"],
        "createdAt": iso_value(item["created_at"]),
        "updatedAt": iso_value(item["updated_at"]),
    }


def list_items(profile):
    owners = list(owners_for_profile(profile))
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM event_presets
            WHERE owner = ANY(%s)
            ORDER BY updated_at DESC, name, id
            """,
            (owners,),
        ).fetchall()
    return {"ok": True, "items": [public_item(row_to_item(row)) for row in rows]}


def get_item(item_id, profile):
    owners = list(owners_for_profile(profile))
    with connect() as connection:
        row = connection.execute(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM event_presets
            WHERE id = %s AND owner = ANY(%s)
            """,
            (clean_text(item_id), owners),
        ).fetchone()
    if not row:
        raise ValueError("event_preset_not_found")
    return row_to_item(row)


def create_item(payload, profile):
    item = validate_payload(payload, profile)
    item_id = str(uuid.uuid4())
    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO event_presets (
                id, owner, name, title, all_day, start_time, end_time,
                alarm_time, memo
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                item_id,
                item["owner"],
                item["name"],
                item["title"],
                item["all_day"],
                item["start_time"],
                item["end_time"],
                item["alarm_time"],
                item["memo"],
            ),
        ).fetchone()
    if not row:
        raise RuntimeError("event_preset_create_failed")
    return public_item(get_item(item_id, profile))


def update_item(item_id, payload, profile):
    current = get_item(item_id, profile)
    item = validate_payload(payload, profile)
    with connect() as connection:
        row = connection.execute(
            """
            UPDATE event_presets
            SET owner = %s,
                name = %s,
                title = %s,
                all_day = %s,
                start_time = %s,
                end_time = %s,
                alarm_time = %s,
                memo = %s,
                updated_at = now()
            WHERE id = %s
            RETURNING id
            """,
            (
                item["owner"],
                item["name"],
                item["title"],
                item["all_day"],
                item["start_time"],
                item["end_time"],
                item["alarm_time"],
                item["memo"],
                current["id"],
            ),
        ).fetchone()
    if not row:
        raise ValueError("event_preset_not_found")
    return public_item(get_item(current["id"], profile))


def delete_item(item_id, profile):
    current = get_item(item_id, profile)
    with connect() as connection:
        connection.execute("DELETE FROM event_presets WHERE id = %s", (current["id"],))
    return {"ok": True, "id": current["id"]}

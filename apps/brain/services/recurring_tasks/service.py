import calendar
import json
import os
import threading
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from models.database import connect
from services.calendar.upstream import request_upstream


FREQUENCIES = {"daily", "weekly", "monthly", "yearly"}
PRIORITIES = {"", "1", "5", "9"}
PROFILE_HOSTS = {
    "main": "kaosgdd.net",
    "family": "family.kaosgdd.net",
}
PROFILE_OWNERS = {
    "main": ("zin", "family"),
    "family": ("wife", "family"),
}
DEFAULT_TIME = "10:00"
LOCAL_ZONE = ZoneInfo(os.environ.get("KAOSGDD_LOCAL_TZID", "Asia/Seoul"))
SCHEDULER_LOCK_KEY = "kaosgdd-recurring-tasks-v1"
SCHEDULER_INTERVAL_SECONDS = max(10, int(os.environ.get("BRAIN_RECURRING_TASK_INTERVAL_SECONDS", "60")))

SELECT_COLUMNS = """
    id, owner, adapter_profile, collection_id, title, memo,
    first_due_date, due_time, priority, frequency, enabled,
    active_uid, active_collection_id, active_due_date, next_due_date,
    last_completed_uid, last_completed_at, last_error, created_at, updated_at
"""

_scheduler_thread = None
_scheduler_wake = threading.Event()


def profile_for_host(host):
    return "family" if str(host or "").split(":", 1)[0].lower() == PROFILE_HOSTS["family"] else "main"


def owners_for_profile(profile):
    if profile not in PROFILE_OWNERS:
        raise ValueError("invalid_profile")
    return PROFILE_OWNERS[profile]


def clean_text(value):
    return str(value or "").strip()


def validate_date(value, field="firstDueDate"):
    try:
        return date.fromisoformat(clean_text(value))
    except ValueError as exc:
        raise ValueError(f"invalid_{field}") from exc


def validate_time(value):
    raw = clean_text(value) or DEFAULT_TIME
    try:
        parsed = datetime.strptime(raw, "%H:%M").time()
    except ValueError as exc:
        raise ValueError("invalid_dueTime") from exc
    if parsed.minute % 5:
        raise ValueError("invalid_dueTime_step")
    return parsed


def validate_payload(payload, profile):
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    title = " ".join(clean_text(payload.get("title")).split())
    if not title:
        raise ValueError("title_required")
    frequency = clean_text(payload.get("frequency")).lower()
    if frequency not in FREQUENCIES:
        raise ValueError("invalid_frequency")
    priority = clean_text(payload.get("priority"))
    if priority not in PRIORITIES:
        raise ValueError("invalid_priority")
    owner = "family" if payload.get("shareFamily") is True else ("wife" if profile == "family" else "zin")
    return {
        "owner": owner,
        "adapter_profile": profile,
        "title": title,
        "memo": clean_text(payload.get("memo")),
        "first_due_date": validate_date(payload.get("firstDueDate")),
        "due_time": validate_time(payload.get("dueTime")),
        "priority": priority,
        "frequency": frequency,
        "enabled": payload.get("enabled") is not False,
    }


def add_months(value, months, preferred_day=None):
    target_month = value.month - 1 + months
    year = value.year + target_month // 12
    month = target_month % 12 + 1
    day = min(preferred_day or value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def next_scheduled_date(value, frequency, anchor=None):
    anchor_date = anchor or value
    if frequency == "daily":
        return value + timedelta(days=1)
    if frequency == "weekly":
        return value + timedelta(days=7)
    if frequency == "monthly":
        return add_months(value, 1, anchor_date.day)
    if frequency == "yearly":
        target_year = value.year + 1
        target_day = min(anchor_date.day, calendar.monthrange(target_year, anchor_date.month)[1])
        return date(target_year, anchor_date.month, target_day)
    raise ValueError("invalid_frequency")


def date_on_or_after(value, frequency, today=None, anchor=None):
    current = today or datetime.now(LOCAL_ZONE).date()
    candidate = value
    while candidate < current:
        candidate = next_scheduled_date(candidate, frequency, anchor=anchor)
    return candidate


def next_current_date(value, frequency, today=None, anchor=None):
    return date_on_or_after(
        next_scheduled_date(value, frequency, anchor=anchor),
        frequency,
        today=today,
        anchor=anchor,
    )


def decode_upstream_json(status, body):
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("calendar_adapter_invalid_response") from exc
    if status < 200 or status >= 300:
        raise RuntimeError(str(payload.get("error") or f"calendar_adapter_http_{status}"))
    return payload


def adapter_json(profile, method, path, payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status, _, response_body = request_upstream(
        method,
        path,
        PROFILE_HOSTS[profile],
        body=body,
        content_type="application/json",
    )
    return decode_upstream_json(status, response_body)


def resolve_collection(profile, owner):
    bootstrap = adapter_json(profile, "GET", "/api/calendar/bootstrap")
    if not bootstrap.get("live"):
        raise RuntimeError("calendar_adapter_unavailable")
    candidates = [
        item
        for item in bootstrap.get("collections", [])
        if item.get("owner") == owner and "VTODO" in (item.get("components") or [])
    ]
    if not candidates:
        raise ValueError("task_collection_not_found")
    named = next((item for item in candidates if "task" in str(item.get("name") or "").lower()), None)
    return str((named or candidates[0]).get("id") or "")


def row_to_definition(row):
    if not row:
        return None
    values = list(row)
    return {
        "id": values[0],
        "owner": values[1],
        "adapter_profile": values[2],
        "collection_id": values[3],
        "title": values[4],
        "memo": values[5],
        "first_due_date": values[6],
        "due_time": values[7],
        "priority": values[8],
        "frequency": values[9],
        "enabled": values[10],
        "active_uid": values[11],
        "active_collection_id": values[12],
        "active_due_date": values[13],
        "next_due_date": values[14],
        "last_completed_uid": values[15],
        "last_completed_at": values[16],
        "last_error": values[17],
        "created_at": values[18],
        "updated_at": values[19],
    }


def iso_value(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else (str(value) if value else "")


def public_definition(item):
    active_due = item.get("active_due_date")
    next_due = active_due or item.get("next_due_date")
    return {
        "id": item["id"],
        "title": item["title"],
        "memo": item["memo"],
        "shareFamily": item["owner"] == "family",
        "owner": item["owner"],
        "firstDueDate": iso_value(item["first_due_date"]),
        "dueTime": str(item["due_time"])[:5],
        "priority": item["priority"],
        "frequency": item["frequency"],
        "enabled": bool(item["enabled"]),
        "activeUid": item.get("active_uid") or "",
        "activeDueDate": iso_value(active_due),
        "nextDueDate": iso_value(next_due),
        "lastCompletedAt": iso_value(item.get("last_completed_at")),
        "error": item.get("last_error") or "",
        "createdAt": iso_value(item.get("created_at")),
        "updatedAt": iso_value(item.get("updated_at")),
    }


def list_definitions(profile):
    owners = list(owners_for_profile(profile))
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM recurring_task_definitions
            WHERE owner = ANY(%s)
            ORDER BY enabled DESC, updated_at DESC, title
            """,
            (owners,),
        ).fetchall()
    return {"ok": True, "items": [public_definition(row_to_definition(row)) for row in rows]}


def get_definition(definition_id, profile):
    owners = list(owners_for_profile(profile))
    with connect() as connection:
        row = connection.execute(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM recurring_task_definitions
            WHERE id = %s AND owner = ANY(%s)
            """,
            (clean_text(definition_id), owners),
        ).fetchone()
    if not row:
        raise ValueError("recurring_task_not_found")
    return row_to_definition(row)


def create_definition(payload, profile):
    item = validate_payload(payload, profile)
    item["collection_id"] = resolve_collection(profile, item["owner"])
    item["id"] = str(uuid.uuid4())
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO recurring_task_definitions (
                id, owner, adapter_profile, collection_id, title, memo,
                first_due_date, due_time, priority, frequency, enabled, next_due_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                item["id"],
                item["owner"],
                item["adapter_profile"],
                item["collection_id"],
                item["title"],
                item["memo"],
                item["first_due_date"],
                item["due_time"],
                item["priority"],
                item["frequency"],
                item["enabled"],
                item["first_due_date"],
            ),
        )
    request_scheduler_run()
    return public_definition(get_definition(item["id"], profile))


def update_definition(definition_id, payload, profile):
    current = get_definition(definition_id, profile)
    item = validate_payload(payload, profile)
    item["collection_id"] = resolve_collection(profile, item["owner"])
    pending_due = current["next_due_date"] if current.get("active_uid") else item["first_due_date"]
    with connect() as connection:
        row = connection.execute(
            """
            UPDATE recurring_task_definitions
            SET owner = %s,
                adapter_profile = %s,
                collection_id = %s,
                title = %s,
                memo = %s,
                first_due_date = %s,
                due_time = %s,
                priority = %s,
                frequency = %s,
                enabled = %s,
                next_due_date = %s,
                last_error = '',
                updated_at = now()
            WHERE id = %s
            RETURNING id
            """,
            (
                item["owner"],
                item["adapter_profile"],
                item["collection_id"],
                item["title"],
                item["memo"],
                item["first_due_date"],
                item["due_time"],
                item["priority"],
                item["frequency"],
                item["enabled"],
                pending_due,
                current["id"],
            ),
        ).fetchone()
    if not row:
        raise ValueError("recurring_task_not_found")
    request_scheduler_run()
    return public_definition(get_definition(current["id"], profile))


def delete_definition(definition_id, profile):
    current = get_definition(definition_id, profile)
    with connect() as connection:
        connection.execute("DELETE FROM recurring_task_definitions WHERE id = %s", (current["id"],))
    return {"ok": True, "id": current["id"]}


def enabled_definitions():
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM recurring_task_definitions
            WHERE enabled = true
            ORDER BY created_at, id
            """
        ).fetchall()
    return [row_to_definition(row) for row in rows]


def store_error(definition_id, error):
    with connect() as connection:
        connection.execute(
            """
            UPDATE recurring_task_definitions
            SET last_error = %s, updated_at = now()
            WHERE id = %s
            """,
            (clean_text(error)[:500], definition_id),
        )


def clear_active_occurrence(item, completed, next_due):
    with connect() as connection:
        connection.execute(
            """
            UPDATE recurring_task_definitions
            SET active_uid = NULL,
                active_collection_id = NULL,
                active_due_date = NULL,
                next_due_date = %s,
                last_completed_uid = CASE WHEN %s THEN %s ELSE last_completed_uid END,
                last_completed_at = CASE WHEN %s THEN now() ELSE last_completed_at END,
                last_error = '',
                updated_at = now()
            WHERE id = %s AND active_uid = %s
            """,
            (next_due, completed, item["active_uid"], completed, item["id"], item["active_uid"]),
        )


def assign_active_occurrence(item, due_date, result):
    with connect() as connection:
        connection.execute(
            """
            UPDATE recurring_task_definitions
            SET active_uid = %s,
                active_collection_id = %s,
                active_due_date = %s,
                next_due_date = NULL,
                last_error = '',
                updated_at = now()
            WHERE id = %s AND active_uid IS NULL
            """,
            (result["uid"], result.get("collection") or item["collection_id"], due_date, item["id"]),
        )


def occurrence_uid(item, due_date):
    definition_id = "".join(character for character in clean_text(item["id"]).upper() if character.isalnum())
    return f"KAOSGDD-REPEAT-{definition_id}-{due_date.strftime('%Y%m%d')}"


def create_occurrence(item, due_date):
    return adapter_json(
        item["adapter_profile"],
        "POST",
        "/api/calendar/tasks",
        {
            "uid": occurrence_uid(item, due_date),
            "collectionId": item["collection_id"],
            "title": item["title"],
            "memo": item["memo"],
            "dueDate": due_date.isoformat(),
            "dueTime": str(item["due_time"])[:5],
            "priority": item["priority"],
        },
    )


def synchronize_definition(item, bootstrap, today=None):
    current_date = today or datetime.now(LOCAL_ZONE).date()
    active_uid = item.get("active_uid")
    if active_uid:
        active = next(
            (
                task
                for task in bootstrap.get("tasks", [])
                if task.get("uid") == active_uid
                and (not item.get("active_collection_id") or task.get("collection") == item["active_collection_id"])
            ),
            None,
        )
        if active and str(active.get("status") or "NEEDS-ACTION").upper() != "COMPLETED":
            return
        next_due = next_current_date(
            item["active_due_date"],
            item["frequency"],
            current_date,
            anchor=item["first_due_date"],
        )
        clear_active_occurrence(item, bool(active), next_due)
        item = {**item, "active_uid": None, "active_collection_id": None, "active_due_date": None, "next_due_date": next_due}

    due_date = date_on_or_after(
        item.get("next_due_date") or item["first_due_date"],
        item["frequency"],
        current_date,
        anchor=item["first_due_date"],
    )
    expected_uid = occurrence_uid(item, due_date)
    existing = next(
        (
            task
            for task in bootstrap.get("tasks", [])
            if task.get("uid") == expected_uid and task.get("collection") == item["collection_id"]
        ),
        None,
    )
    if existing:
        assign_active_occurrence(
            item,
            due_date,
            {"uid": expected_uid, "collection": item["collection_id"]},
        )
        return
    result = create_occurrence(item, due_date)
    if not result.get("uid"):
        raise RuntimeError("calendar_adapter_missing_uid")
    assign_active_occurrence(item, due_date, result)


def run_scheduler_cycle(today=None):
    with connect() as lock_connection:
        locked = lock_connection.execute(
            "SELECT pg_try_advisory_lock(hashtext(%s))",
            (SCHEDULER_LOCK_KEY,),
        ).fetchone()[0]
        if not locked:
            return False
        try:
            bootstraps = {}
            for item in enabled_definitions():
                try:
                    profile = item["adapter_profile"]
                    if profile not in bootstraps:
                        bootstrap = adapter_json(profile, "GET", "/api/calendar/bootstrap")
                        if not bootstrap.get("live"):
                            raise RuntimeError("calendar_adapter_unavailable")
                        bootstraps[profile] = bootstrap
                    synchronize_definition(item, bootstraps[profile], today=today)
                except Exception as exc:
                    store_error(item["id"], str(exc) or type(exc).__name__)
            return True
        finally:
            lock_connection.execute("SELECT pg_advisory_unlock(hashtext(%s))", (SCHEDULER_LOCK_KEY,))


def request_scheduler_run():
    _scheduler_wake.set()


def scheduler_loop():
    while True:
        try:
            run_scheduler_cycle()
        except Exception as exc:
            print(f"Recurring task scheduler failed: {type(exc).__name__}: {exc}", flush=True)
        _scheduler_wake.wait(SCHEDULER_INTERVAL_SECONDS)
        _scheduler_wake.clear()


def start_scheduler():
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return _scheduler_thread
    _scheduler_thread = threading.Thread(target=scheduler_loop, name="recurring-task-scheduler", daemon=True)
    _scheduler_thread.start()
    return _scheduler_thread

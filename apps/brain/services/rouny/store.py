import json
import re

from models.database import connect


MAX_TEMPLATES = 100
MAX_ITEMS = 1_000
MAX_SLOTS = 2_000
MAX_ID_LENGTH = 128
MAX_NAME_LENGTH = 200
MAX_TITLE_LENGTH = 500
MAX_MEMO_LENGTH = 10_000
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class RounyConflict(Exception):
    def __init__(self, document):
        super().__init__("rouny_revision_conflict")
        self.document = document


def required_text(value, field, maximum):
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"invalid_rouny_{field}")
    return normalized


def optional_text(value, field, maximum):
    normalized = str(value or "")
    if len(normalized) > maximum:
        raise ValueError(f"invalid_rouny_{field}")
    return normalized


def validate_time(value):
    normalized = str(value or "")
    if not TIME_PATTERN.fullmatch(normalized):
        raise ValueError("invalid_rouny_time")
    return normalized


def time_minutes(value):
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def validate_slot(slot):
    if not isinstance(slot, dict):
        raise ValueError("invalid_rouny_slot")
    day = str(slot.get("dayOfWeek") or "")
    if day not in {"0", "1", "2", "3", "4", "5", "6"}:
        raise ValueError("invalid_rouny_day")
    start = validate_time(slot.get("startTime"))
    end = validate_time(slot.get("endTime"))
    if time_minutes(end) <= time_minutes(start):
        raise ValueError("invalid_rouny_time_range")
    return {
        "id": required_text(slot.get("id"), "slot_id", MAX_ID_LENGTH),
        "dayOfWeek": day,
        "startTime": start,
        "endTime": end,
    }


def validate_item(item):
    if not isinstance(item, dict):
        raise ValueError("invalid_rouny_item")
    slots = item.get("slots")
    if not isinstance(slots, list) or not slots:
        raise ValueError("invalid_rouny_slots")
    normalized_slots = [validate_slot(slot) for slot in slots]
    first_slot = normalized_slots[0]
    color = str(item.get("color") or "")
    if not COLOR_PATTERN.fullmatch(color):
        raise ValueError("invalid_rouny_color")
    return {
        "id": required_text(item.get("id"), "item_id", MAX_ID_LENGTH),
        "title": optional_text(item.get("title"), "title", MAX_TITLE_LENGTH),
        "dayOfWeek": first_slot["dayOfWeek"],
        "startTime": first_slot["startTime"],
        "endTime": first_slot["endTime"],
        "slots": normalized_slots,
        "memo": optional_text(item.get("memo"), "memo", MAX_MEMO_LENGTH),
        "color": color.lower(),
    }


def validate_templates(templates):
    if not isinstance(templates, list) or len(templates) > MAX_TEMPLATES:
        raise ValueError("invalid_rouny_templates")

    normalized = []
    template_ids = set()
    item_count = 0
    slot_count = 0
    for template in templates:
        if not isinstance(template, dict):
            raise ValueError("invalid_rouny_template")
        template_id = required_text(template.get("id"), "template_id", MAX_ID_LENGTH)
        if template_id in template_ids:
            raise ValueError("duplicate_rouny_template_id")
        template_ids.add(template_id)
        items = template.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("invalid_rouny_items")
        normalized_items = [validate_item(item) for item in items]
        item_count += len(normalized_items)
        slot_count += sum(len(item["slots"]) for item in normalized_items)
        if item_count > MAX_ITEMS or slot_count > MAX_SLOTS:
            raise ValueError("rouny_document_too_large")
        normalized.append(
            {
                "id": template_id,
                "name": required_text(template.get("name"), "template_name", MAX_NAME_LENGTH),
                "items": normalized_items,
                "createdAt": optional_text(template.get("createdAt"), "created_at", 64),
                "updatedAt": optional_text(template.get("updatedAt"), "updated_at", 64),
            }
        )
    return normalized


def document_from_row(scope, row):
    if not row:
        return {
            "ok": True,
            "scope": scope,
            "revision": 0,
            "templates": [],
            "updatedAt": "",
        }
    return {
        "ok": True,
        "scope": scope,
        "revision": int(row[0]),
        "templates": row[1] if isinstance(row[1], list) else json.loads(row[1]),
        "updatedAt": row[2].isoformat() if hasattr(row[2], "isoformat") else str(row[2]),
    }


def get_rouny_document(scope="family"):
    with connect() as connection:
        row = connection.execute(
            "SELECT revision, templates, updated_at FROM rouny_documents WHERE scope = %s",
            (scope,),
        ).fetchone()
    return document_from_row(scope, row)


def put_rouny_document(templates, base_revision, scope="family"):
    if isinstance(base_revision, bool) or not isinstance(base_revision, int) or base_revision < 0:
        raise ValueError("invalid_rouny_revision")
    normalized = validate_templates(templates)
    encoded = json.dumps(normalized, ensure_ascii=False)

    with connect() as connection:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"rouny:{scope}",))
            current_row = connection.execute(
                "SELECT revision, templates, updated_at FROM rouny_documents WHERE scope = %s FOR UPDATE",
                (scope,),
            ).fetchone()
            current = document_from_row(scope, current_row)
            if current["revision"] != base_revision:
                raise RounyConflict(current)
            next_revision = base_revision + 1
            row = connection.execute(
                """
                INSERT INTO rouny_documents (scope, revision, templates)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (scope) DO UPDATE
                SET revision = EXCLUDED.revision,
                    templates = EXCLUDED.templates,
                    updated_at = now()
                RETURNING revision, templates, updated_at
                """,
                (scope, next_revision, encoded),
            ).fetchone()
    return document_from_row(scope, row)

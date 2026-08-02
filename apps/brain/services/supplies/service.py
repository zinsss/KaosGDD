import base64
import json
import os
import re
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from models.database import connect


RADICALE_URL = os.environ.get("RADICALE_INTERNAL_URL", "http://100.94.208.16:5232").rstrip("/")
RADICALE_SUPPLIES_USERNAME = os.environ.get("RADICALE_SUPPLIES_USERNAME", "")
RADICALE_SUPPLIES_PASSWORD = os.environ.get("RADICALE_SUPPLIES_PASSWORD", "")
RADICALE_SUPPLIES_TASK_COLLECTION_NAME = os.environ.get("RADICALE_SUPPLIES_TASK_COLLECTION_NAME", "Kaos_Supplies")
TIMEOUT = float(os.environ.get("BRAIN_UPSTREAM_TIMEOUT_SECONDS", "30"))
LOCAL_TIMEZONE = timezone(timedelta(hours=int(os.environ.get("KAOSGDD_LOCAL_UTC_OFFSET_HOURS", "9"))))
LOCAL_TZID = os.environ.get("KAOSGDD_LOCAL_TZID", "Asia/Seoul")

SEOUL_VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Asia/Seoul
BEGIN:STANDARD
DTSTART:19881009T030000
TZNAME:GMT+9
TZOFFSETFROM:+1000
TZOFFSETTO:+0900
END:STANDARD
END:VTIMEZONE"""

TITLE_REQUIRED = "title is required"
NOT_FOUND = "not found"


def configured():
    return bool(RADICALE_URL and RADICALE_SUPPLIES_USERNAME and RADICALE_SUPPLIES_PASSWORD)


def account():
    return {
        "key": "supplies",
        "username": RADICALE_SUPPLIES_USERNAME,
        "password": RADICALE_SUPPLIES_PASSWORD,
        "label": "Supplies",
    }


def clean_title(title):
    return " ".join(str(title or "").strip().split())


def normalize_title(title):
    return " ".join(str(title or "").strip().lower().split())


def utc_stamp(value):
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_ics_datetime(value):
    raw = str(value or "")
    is_utc = raw.endswith("Z")
    clean = re.sub(r"Z$", "", raw)
    if "T" in clean:
        if is_utc:
            local = datetime.strptime(clean[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).astimezone(LOCAL_TIMEZONE)
            iso = local.strftime("%Y-%m-%dT%H:%M:%S")
            return {"date": iso[:10], "time": iso[11:16], "iso": iso}
        return {
            "date": f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}",
            "time": f"{clean[9:11]}:{clean[11:13]}",
            "iso": f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}T{clean[9:11]}:{clean[11:13]}:00",
        }
    if len(clean) >= 8:
        return {"date": f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}", "time": "", "iso": f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}"}
    return {"date": "", "time": "", "iso": ""}


def done_date_key_for_ui(done_at):
    parsed = parse_ics_datetime(done_at)
    return parsed["date"]


def format_dt_for_ui(value):
    parsed = parse_ics_datetime(value)
    if not parsed["date"]:
        return ""
    return f"{parsed['date']} {parsed['time']}".strip()


def escape_ics(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def unescape_ics(value):
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def fold_ics_line(line):
    if len(line.encode("utf-8")) <= 75:
        return line
    folded = []
    current = ""
    for char in line:
        candidate = current + char
        if len(candidate.encode("utf-8")) > 75:
            folded.append(current)
            current = f" {char}"
        else:
            current = candidate
    folded.append(current)
    return "\r\n".join(folded)


def calendar_body(lines):
    return "\r\n".join(fold_ics_line(line) for line in lines) + "\r\n"


def radicale_request(method, path, body="", headers=None):
    item_account = account()
    url = urllib.parse.urljoin(f"{RADICALE_URL}/", path.lstrip("/"))
    request = urllib.request.Request(url, data=body.encode("utf-8"), method=method)
    token = base64.b64encode(f"{item_account['username']}:{item_account['password']}".encode("utf-8")).decode("ascii")
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("User-Agent", "KaosGDD-Brain/0.4 Supplies")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def text_of(element, selector, namespace):
    item = element.find(selector, namespace)
    if item is None or item.text is None:
        return ""
    return item.text.strip()


def parse_property(line):
    if ":" not in line:
        return "", ""
    name, value = line.split(":", 1)
    return name.split(";", 1)[0].upper(), unescape_ics(value)


def unfold_ics(data):
    unfolded = []
    for raw in data.splitlines():
        if raw.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += raw[1:]
        else:
            unfolded.append(raw.rstrip("\r"))
    return unfolded


def parse_ics(data, href="", etag=""):
    lines = unfold_ics(data)
    items = []
    current = None
    for line in lines:
        if line == "BEGIN:VTODO":
            current = {"component": "VTODO", "href": href, "etag": etag, "_raw_properties": []}
        elif line == "END:VTODO":
            if current:
                items.append(current)
            current = None
        elif current is not None:
            current["_raw_properties"].append(line)
            name, value = parse_property(line)
            if name:
                current[name] = value
    return items


def parse_collection_report(xml):
    root = ET.fromstring(xml)
    namespace = {"d": "DAV:", "cal": "urn:ietf:params:xml:ns:caldav"}
    items = []
    for response in root.findall("d:response", namespace):
        href = text_of(response, "d:href", namespace)
        etag = text_of(response, ".//d:getetag", namespace)
        calendar_data = text_of(response, ".//cal:calendar-data", namespace)
        if calendar_data:
            items.extend(parse_ics(calendar_data, href, etag))
    return items


def parse_collections(xml):
    root = ET.fromstring(xml)
    namespace = {"d": "DAV:", "cal": "urn:ietf:params:xml:ns:caldav"}
    collections = []
    for response in root.findall("d:response", namespace):
        href = text_of(response, "d:href", namespace)
        if not href or href.rstrip("/") == f"/{RADICALE_SUPPLIES_USERNAME}":
            continue
        resourcetype = response.find(".//d:resourcetype", namespace)
        if resourcetype is None:
            continue
        display_name = text_of(response, ".//d:displayname", namespace) or href.strip("/").split("/")[-1]
        components = [
            (item.attrib.get("name") or "").upper()
            for item in response.findall(".//cal:supported-calendar-component-set/cal:comp", namespace)
            if item.attrib.get("name")
        ]
        collections.append({"name": display_name, "href": href, "components": components})
    return collections


def supplies_collection():
    if not configured():
        raise ValueError("supplies_not_configured")
    body = """<?xml version="1.0" encoding="utf-8" ?>
<propfind xmlns="DAV:" xmlns:cs="http://calendarserver.org/ns/" xmlns:cal="urn:ietf:params:xml:ns:caldav">
  <prop>
    <displayname />
    <resourcetype />
    <cal:supported-calendar-component-set />
  </prop>
</propfind>"""
    _, xml = radicale_request(
        "PROPFIND",
        f"/{RADICALE_SUPPLIES_USERNAME}/",
        body,
        {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    for collection in parse_collections(xml):
        if collection["name"] == RADICALE_SUPPLIES_TASK_COLLECTION_NAME and "VTODO" in collection.get("components", []):
            return collection
    raise ValueError("supplies_collection_not_found")


def report_supplies(collection):
    body = """<?xml version="1.0" encoding="utf-8" ?>
<calendar-query xmlns="urn:ietf:params:xml:ns:caldav" xmlns:d="DAV:">
  <d:prop>
    <d:getetag />
    <calendar-data />
  </d:prop>
  <filter>
    <comp-filter name="VCALENDAR">
      <comp-filter name="VTODO" />
    </comp-filter>
  </filter>
</calendar-query>"""
    _, xml = radicale_request(
        "REPORT",
        collection["href"],
        body,
        {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    return parse_collection_report(xml)


def normalize_supply(item):
    done_at = item.get("COMPLETED", "") if item.get("STATUS", "NEEDS-ACTION").upper() == "COMPLETED" else ""
    return {
        "id": item.get("UID") or item.get("href"),
        "title": item.get("SUMMARY", "Untitled supply"),
        "created_at": parse_ics_datetime(item.get("CREATED", ""))["iso"],
        "updated_at": parse_ics_datetime(item.get("LAST-MODIFIED", ""))["iso"],
        "done_at": parse_ics_datetime(done_at)["iso"] if done_at else None,
        "done_at_display": format_dt_for_ui(done_at),
        "done_date_key": done_date_key_for_ui(done_at),
        "status": "done" if done_at else "active",
        "_href": item.get("href", ""),
        "_etag": item.get("etag", ""),
        "_normalized_title": normalize_title(item.get("SUMMARY", "")),
    }


def public_supply(item):
    return {key: value for key, value in item.items() if not key.startswith("_")}


def list_all_supplies():
    collection = supplies_collection()
    return [normalize_supply(item) for item in report_supplies(collection) if item.get("component") == "VTODO"]


def list_supplies(mode="active"):
    normalized_mode = str(mode or "active").strip().lower()
    items = list_all_supplies()
    if normalized_mode == "done":
        done = [item for item in items if item["status"] == "done"]
        done.sort(key=lambda item: (item.get("done_at") or "", item.get("updated_at") or ""), reverse=True)
        return {"items": [public_supply(item) for item in done]}
    active = [item for item in items if item["status"] == "active"]
    active.sort(key=lambda item: item.get("created_at") or "")
    return {"items": [public_supply(item) for item in active]}


def touch_preset(name, normalized_name):
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO supply_presets (normalized_name, name, last_used_at)
            VALUES (%s, %s, now())
            ON CONFLICT (normalized_name) DO UPDATE SET
                name = excluded.name,
                last_used_at = excluded.last_used_at
            """,
            (normalized_name, name),
        )
        connection.execute(
            """
            DELETE FROM supply_presets
            WHERE normalized_name IN (
                SELECT normalized_name
                FROM (
                    SELECT normalized_name,
                           row_number() OVER (ORDER BY last_used_at DESC) AS preset_rank
                    FROM supply_presets
                ) ranked
                WHERE preset_rank > 15
            )
            """,
        )


def list_presets():
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT name, normalized_name, last_used_at
            FROM supply_presets
            ORDER BY last_used_at DESC
            LIMIT 15
            """
        ).fetchall()
    return {
        "items": [
            {
                "name": row[0],
                "normalized_name": row[1],
                "last_used_at": row[2].isoformat() if hasattr(row[2], "isoformat") else str(row[2]),
            }
            for row in rows
        ]
    }


def build_supply_vtodo(title, existing=None, done=False):
    existing = existing or {}
    uid = str(existing.get("UID") or uuid.uuid4()).upper()
    now = utc_stamp(datetime.now(timezone.utc))
    created = existing.get("CREATED") or now
    status = "COMPLETED" if done else "NEEDS-ACTION"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "PRODID:-//KaosGDD//Supplies//EN",
        *SEOUL_VTIMEZONE.splitlines(),
        "BEGIN:VTODO",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        f"CREATED:{created}",
        f"LAST-MODIFIED:{now}",
        f"SUMMARY:{escape_ics(title)}",
        f"STATUS:{status}",
        "CATEGORIES:SUPPLY",
    ]
    if done:
        lines.extend([f"COMPLETED:{existing.get('COMPLETED') or now}", "PERCENT-COMPLETE:100"])
    lines.extend(["END:VTODO", "END:VCALENDAR"])
    return uid, calendar_body(lines)


def create_supply(title):
    display_title = clean_title(title)
    if not display_title:
        return {"ok": False, "error": TITLE_REQUIRED}
    normalized = normalize_title(display_title)
    touch_preset(display_title, normalized)
    collection = supplies_collection()
    active = [item for item in list_all_supplies() if item["status"] == "active"]
    for item in active:
        if item["_normalized_title"] == normalized:
            return {"ok": True, "id": item["id"], "created": False}
    uid, body = build_supply_vtodo(display_title)
    href = urllib.parse.urljoin(collection["href"], f"{uid}.ics")
    radicale_request(
        "PUT",
        href,
        body,
        {"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"},
    )
    return {"ok": True, "id": uid, "created": True}


def find_supply(supply_id):
    target = str(supply_id or "").strip()
    if not target:
        raise ValueError(NOT_FOUND)
    collection = supplies_collection()
    for item in report_supplies(collection):
        if item.get("UID") == target:
            return collection, item
    raise ValueError(NOT_FOUND)


def set_supply_done_state(supply_id, done):
    collection, existing = find_supply(supply_id)
    current = normalize_supply(existing)
    if done and current["status"] == "done":
        return {"ok": False, "error": NOT_FOUND}
    if not done and current["status"] == "active":
        return {"ok": False, "error": NOT_FOUND}
    if not done:
        normalized = current["_normalized_title"]
        active = [item for item in list_all_supplies() if item["status"] == "active"]
        if any(item["id"] != current["id"] and item["_normalized_title"] == normalized for item in active):
            return {"ok": False, "error": NOT_FOUND}
    _, body = build_supply_vtodo(current["title"], existing=existing, done=done)
    headers = {"Content-Type": "text/calendar; charset=utf-8"}
    if existing.get("etag"):
        headers["If-Match"] = existing["etag"]
    radicale_request("PUT", existing["href"], body, headers)
    return {"ok": True, "id": current["id"], "collection": collection["name"]}


def mark_supply_done(supply_id):
    return set_supply_done_state(supply_id, True)


def mark_supply_active(supply_id):
    return set_supply_done_state(supply_id, False)


def delete_supply(supply_id):
    _, existing = find_supply(supply_id)
    headers = {}
    if existing.get("etag"):
        headers["If-Match"] = existing["etag"]
    radicale_request("DELETE", existing["href"], "", headers)
    return {"ok": True}


def use_preset(name):
    return create_supply(name)


def capture_supply(raw):
    text = str(raw or "").replace("\r\n", "\n").strip()
    first = next((line.strip() for line in text.split("\n") if line.strip()), "")
    if first == "$$":
        return {"ok": False, "error": TITLE_REQUIRED}
    if not first.startswith("$$"):
        return {"ok": False, "error": "unsupported prefix"}
    if len(first) > 2 and not first[2].isspace():
        return {"ok": False, "error": "supply line must start with $$ "}
    extra_lines = [line for line in text.split("\n")[1:] if line.strip()]
    if extra_lines:
        return {"ok": False, "error": "extra unrecognized lines"}
    result = create_supply(first[2:].strip())
    if not result.get("ok"):
        return result
    return {
        "ok": True,
        "kind": "supply",
        "id": result["id"],
        "created": result["created"],
        "created_types": ["supply"],
    }

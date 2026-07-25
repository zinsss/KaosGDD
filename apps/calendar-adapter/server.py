#!/usr/bin/env python3
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PORT = int(os.environ.get("PORT", "8091"))
RADICALE_URL = os.environ.get("RADICALE_INTERNAL_URL", "http://100.94.208.16:5232").rstrip("/")
RADICALE_USERNAME = os.environ.get("RADICALE_USERNAME", "")
RADICALE_PASSWORD = os.environ.get("RADICALE_PASSWORD", "")
RADICALE_FAMILY_USERNAME = os.environ.get("RADICALE_FAMILY_USERNAME", "")
RADICALE_FAMILY_PASSWORD = os.environ.get("RADICALE_FAMILY_PASSWORD", "")
RADICALE_WIFE_USERNAME = os.environ.get("RADICALE_WIFE_USERNAME", "")
RADICALE_WIFE_PASSWORD = os.environ.get("RADICALE_WIFE_PASSWORD", "")
RADICALE_SYSTEM_USERNAME = os.environ.get("RADICALE_SYSTEM_USERNAME", "")
RADICALE_SYSTEM_PASSWORD = os.environ.get("RADICALE_SYSTEM_PASSWORD", "")
TIMEOUT = float(os.environ.get("KAOSGDD_ADAPTER_TIMEOUT_SECONDS", "30"))
LOCAL_TIMEZONE = timezone(timedelta(hours=int(os.environ.get("KAOSGDD_LOCAL_UTC_OFFSET_HOURS", "9"))))
LOCAL_TZID = os.environ.get("KAOSGDD_LOCAL_TZID", "Asia/Seoul")
MAX_POST_BYTES = 20000

SEOUL_VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Asia/Seoul
BEGIN:STANDARD
DTSTART:19881009T030000
TZNAME:GMT+9
TZOFFSETFROM:+1000
TZOFFSETTO:+0900
END:STANDARD
END:VTIMEZONE"""


def account(key, username, password, label):
    return {
        "key": key,
        "username": username,
        "password": password,
        "label": label,
        "configured": bool(RADICALE_URL and username and password),
    }


ACCOUNTS = {
    "zin": account("zin", RADICALE_USERNAME, RADICALE_PASSWORD, "GDD_ZiN"),
    "family": account("family", RADICALE_FAMILY_USERNAME, RADICALE_FAMILY_PASSWORD, "Family"),
    "wife": account("wife", RADICALE_WIFE_USERNAME, RADICALE_WIFE_PASSWORD, "Wife"),
    "system": account("system", RADICALE_SYSTEM_USERNAME, RADICALE_SYSTEM_PASSWORD, "Kaos"),
}


def configured(profile="main"):
    return any(item["configured"] for item in profile_accounts(profile))


def profile_from_headers(headers):
    host = (headers.get("X-Forwarded-Host") or headers.get("Host") or "").split(":", 1)[0].lower()
    if host == "family.kaosgdd.net":
        return "family"
    return "main"


def profile_accounts(profile):
    keys = ["wife", "family"] if profile == "family" else ["zin", "family"]
    return [ACCOUNTS[key] for key in keys if ACCOUNTS[key]["configured"]]


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_request(handler):
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0 or length > MAX_POST_BYTES:
        raise ValueError("invalid_body_length")
    body = handler.rfile.read(length).decode("utf-8")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("invalid_json_payload")
    return payload


def radicale_request(account, method, path, body="", headers=None):
    url = urllib.parse.urljoin(f"{RADICALE_URL}/", path.lstrip("/"))
    request = urllib.request.Request(url, data=body.encode("utf-8"), method=method)
    token = base64.b64encode(f"{account['username']}:{account['password']}".encode("utf-8")).decode("ascii")
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("User-Agent", "KaosGDD-CalendarAdapter/0.1")
    for key, value in (headers or {}).items():
        request.add_header(key, value)

    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def propfind_collections(account):
    body = """<?xml version="1.0" encoding="utf-8" ?>
<propfind xmlns="DAV:" xmlns:cs="http://calendarserver.org/ns/" xmlns:cal="urn:ietf:params:xml:ns:caldav">
  <prop>
    <displayname />
    <resourcetype />
    <cs:getctag />
    <cal:supported-calendar-component-set />
  </prop>
</propfind>"""
    _, xml = radicale_request(
        account,
        "PROPFIND",
        f"/{account['username']}/",
        body,
        {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    return parse_collections(xml, account)


def parse_collections(xml, account):
    root = ET.fromstring(xml)
    namespace = {"d": "DAV:", "cal": "urn:ietf:params:xml:ns:caldav", "cs": "http://calendarserver.org/ns/"}
    collections = []

    for response in root.findall("d:response", namespace):
        href = text_of(response, "d:href", namespace)
        if not href or href.rstrip("/") == f"/{account['username']}":
            continue

        resourcetype = response.find(".//d:resourcetype", namespace)
        if resourcetype is None:
            continue

        is_calendar = resourcetype.find("cal:calendar", namespace) is not None or resourcetype.find("d:collection", namespace) is not None
        if not is_calendar:
            continue

        collection_id = href.strip("/").split("/")[-1] or href.strip("/")
        display_name = text_of(response, ".//d:displayname", namespace) or collection_id
        components = [
            (item.attrib.get("name") or "").upper()
            for item in response.findall(".//cal:supported-calendar-component-set/cal:comp", namespace)
            if item.attrib.get("name")
        ]
        collections.append(
            {
                "id": f"{account['key']}:{collection_id}",
                "rawId": collection_id,
                "name": display_name,
                "owner": account["key"],
                "ownerLabel": account["label"],
                "href": href,
                "components": components,
            }
        )

    return collections


def text_of(element, selector, namespace):
    item = element.find(selector, namespace)
    if item is None or item.text is None:
        return ""
    return item.text.strip()


def report_collection(account, href):
    body = """<?xml version="1.0" encoding="utf-8" ?>
<calendar-query xmlns="urn:ietf:params:xml:ns:caldav" xmlns:d="DAV:">
  <d:prop>
    <d:getetag />
    <calendar-data />
  </d:prop>
  <filter>
    <comp-filter name="VCALENDAR" />
  </filter>
</calendar-query>"""
    _, xml = radicale_request(
        account,
        "REPORT",
        href,
        body,
        {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    return parse_calendar_data(xml)


def parse_calendar_data(xml):
    root = ET.fromstring(xml)
    namespace = {"d": "DAV:", "cal": "urn:ietf:params:xml:ns:caldav"}
    calendars = []
    for response in root.findall("d:response", namespace):
        href = text_of(response, "d:href", namespace)
        calendar_data = text_of(response, ".//cal:calendar-data", namespace)
        if calendar_data:
            calendars.extend(parse_ics(calendar_data, href))
    return calendars


def parse_ics(data, href):
    lines = unfold_ics(data)
    items = []
    current = None
    alarm_depth = 0

    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {"component": "VEVENT", "href": href}
        elif line == "BEGIN:VTODO":
            current = {"component": "VTODO", "href": href}
        elif current is not None and line == "BEGIN:VALARM":
            alarm_depth += 1
        elif current is not None and line == "END:VALARM":
            alarm_depth = max(0, alarm_depth - 1)
        elif alarm_depth:
            continue
        elif line in {"END:VEVENT", "END:VTODO"}:
            if current:
                items.append(current)
            current = None
        elif current is not None:
            name, value = parse_property(line)
            if name:
                current[name] = value

    return items


def unfold_ics(data):
    unfolded = []
    for raw in data.splitlines():
        if raw.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += raw[1:]
        else:
            unfolded.append(raw.rstrip("\r"))
    return unfolded


def parse_property(line):
    if ":" not in line:
        return "", ""
    name, value = line.split(":", 1)
    name = name.split(";", 1)[0].upper()
    return name, unescape_ics(value)


def unescape_ics(value):
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


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


def fold_ics_line(line):
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
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


def normalize_event(item, collection):
    start = item.get("DTSTART", "")
    parsed = parse_ics_datetime(start)
    return {
        "uid": item.get("UID") or item.get("href"),
        "collection": collection["id"],
        "summary": item.get("SUMMARY", "Untitled event"),
        "description": item.get("DESCRIPTION", ""),
        "dtstart": parsed["iso"] or start,
        "dtend": parse_ics_datetime(item.get("DTEND", ""))["iso"],
        "location": item.get("LOCATION", ""),
        "status": item.get("STATUS", ""),
        "created": parse_ics_datetime(item.get("CREATED", ""))["iso"],
        "lastModified": parse_ics_datetime(item.get("LAST-MODIFIED", ""))["iso"],
    }


def normalize_task(item, collection):
    categories = [part.strip() for part in item.get("CATEGORIES", "").split(",") if part.strip()]
    due = parse_ics_datetime(item.get("DUE", ""))
    return {
        "uid": item.get("UID") or item.get("href"),
        "collection": collection["id"],
        "summary": item.get("SUMMARY", "Untitled task"),
        "description": item.get("DESCRIPTION", ""),
        "due": due["date"],
        "dueTime": due["time"],
        "priority": item.get("PRIORITY", ""),
        "status": item.get("STATUS", "NEEDS-ACTION"),
        "completed": parse_ics_datetime(item.get("COMPLETED", ""))["iso"],
        "created": parse_ics_datetime(item.get("CREATED", ""))["iso"],
        "lastModified": parse_ics_datetime(item.get("LAST-MODIFIED", ""))["iso"],
        "categories": categories,
    }


def parse_ics_datetime(value):
    raw = value or ""
    is_utc = raw.endswith("Z")
    clean = re.sub(r"Z$", "", raw)
    if "T" in clean:
        if is_utc:
            local = datetime.strptime(clean[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).astimezone(LOCAL_TIMEZONE)
            iso = local.strftime("%Y-%m-%dT%H:%M:%S")
            return {"date": iso[:10], "time": iso[11:16], "iso": iso}
        return {"date": f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}", "time": f"{clean[9:11]}:{clean[11:13]}", "iso": f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}T{clean[9:11]}:{clean[11:13]}:00"}
    if len(clean) >= 8:
        return {"date": f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}", "time": "", "iso": f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}"}
    return {"date": "", "time": "", "iso": ""}


def bootstrap_payload(profile="main"):
    accounts = profile_accounts(profile)
    if not accounts:
        return {
            "configured": False,
            "live": False,
            "profile": profile,
            "collections": [],
            "events": [],
            "tasks": [],
            "message": "Radicale credentials are not configured.",
        }

    collections = []
    events = []
    tasks = []

    for item_account in accounts:
        account_collections = propfind_collections(item_account)
        collections.extend(account_collections)
        for collection in account_collections:
            for item in report_collection(item_account, collection["href"]):
                if item.get("component") == "VEVENT":
                    events.append(normalize_event(item, collection))
                elif item.get("component") == "VTODO":
                    tasks.append(normalize_task(item, collection))

    return {
        "configured": True,
        "live": True,
        "profile": profile,
        "collections": collections,
        "events": events,
        "tasks": tasks,
    }


def collections_for_profile(profile):
    collections = []
    for item_account in profile_accounts(profile):
        collections.extend(propfind_collections(item_account))
    return collections


def account_for_collection(collection):
    owner = collection.get("owner")
    account_item = ACCOUNTS.get(owner)
    if not account_item or not account_item["configured"]:
        raise ValueError("collection_account_not_configured")
    return account_item


def validate_date(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError("invalid_due_date")
    datetime.strptime(raw, "%Y-%m-%d")
    return raw


def validate_time(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not re.fullmatch(r"\d{2}:\d{2}", raw):
        raise ValueError("invalid_due_time")
    datetime.strptime(raw, "%H:%M")
    return raw


def validate_priority(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw not in {"1", "5", "9"}:
        raise ValueError("invalid_priority")
    return raw


def select_collection(collections, collection_id, component):
    if collection_id:
        for collection in collections:
            if collection["id"] == collection_id:
                if collection.get("components") and component not in collection["components"]:
                    raise ValueError("collection_component_mismatch")
                return collection
        raise ValueError("collection_not_found")

    for collection in collections:
        if component in collection.get("components", []):
            return collection

    lowered = component.lower().replace("v", "")
    for collection in collections:
        if lowered in collection.get("name", "").lower():
            return collection

    raise ValueError("no_writable_collection")


def utc_stamp(value):
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def local_due_stamp(date_value, time_value):
    local = datetime.strptime(f"{date_value}T{time_value}:00", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=LOCAL_TIMEZONE)
    return local.strftime("%Y%m%dT%H%M%S"), utc_stamp(local)


def local_datetime(date_value, time_value):
    return datetime.strptime(f"{date_value}T{time_value}:00", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=LOCAL_TIMEZONE)


def local_datetime_stamp(date_value, time_value):
    return local_datetime(date_value, time_value).strftime("%Y%m%dT%H%M%S")


def compact_date(date_value):
    return date_value.replace("-", "")


def build_vtodo(payload, existing=None):
    existing = existing or {}
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("title_required")

    due_date = validate_date(payload.get("dueDate") or "")
    due_time = validate_time(payload.get("dueTime") or "")
    if due_time and not due_date:
        raise ValueError("due_time_without_date")

    priority = validate_priority(payload.get("priority") or "")
    description = str(payload.get("memo") or "").strip()
    uid = str(payload.get("uid") or existing.get("UID") or uuid.uuid4()).upper()
    alarm_uid = str(uuid.uuid4()).upper()
    now = utc_stamp(datetime.now(timezone.utc))
    created = existing.get("CREATED") or now
    status = existing.get("STATUS") or "NEEDS-ACTION"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "PRODID:-//KaosGDD//Calendar Adapter//EN",
        *SEOUL_VTIMEZONE.splitlines(),
        "BEGIN:VTODO",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        f"CREATED:{created}",
        f"LAST-MODIFIED:{now}",
        f"SUMMARY:{escape_ics(title)}",
        f"STATUS:{escape_ics(status)}",
    ]
    if status == "COMPLETED":
        completed = existing.get("COMPLETED") or now
        lines.extend([f"COMPLETED:{completed}", "PERCENT-COMPLETE:100"])
    if description:
        lines.append(f"DESCRIPTION:{escape_ics(description)}")
    if priority:
        lines.append(f"PRIORITY:{priority}")
    if due_date and due_time:
        local_due, utc_due = local_due_stamp(due_date, due_time)
        lines.extend(
            [
                f"DTSTART;TZID={LOCAL_TZID}:{local_due}",
                f"DUE;TZID={LOCAL_TZID}:{local_due}",
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                "DESCRIPTION:Reminder",
                f"TRIGGER;VALUE=DATE-TIME:{utc_due}",
                f"UID:{alarm_uid}",
                f"X-WR-ALARMUID:{alarm_uid}",
                "END:VALARM",
            ]
        )
    elif due_date:
        compact = due_date.replace("-", "")
        lines.append(f"DUE;VALUE=DATE:{compact}")

    lines.extend(["END:VTODO", "END:VCALENDAR"])
    return uid, calendar_body(lines)


def create_task(payload, profile="main"):
    if not configured(profile):
        raise ValueError("adapter_not_configured")
    collections = collections_for_profile(profile)
    collection = select_collection(collections, str(payload.get("collectionId") or "").strip(), "VTODO")
    item_account = account_for_collection(collection)
    uid, body = build_vtodo(payload)
    href = urllib.parse.urljoin(collection["href"], f"{uid}.ics")
    radicale_request(
        item_account,
        "PUT",
        href,
        body,
        {"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"},
    )
    return {"ok": True, "uid": uid, "collection": collection["id"]}


def validate_repeat(value):
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw not in {"weekly", "monthly", "yearly"}:
        raise ValueError("invalid_repeat")
    return raw


def rrule_for_repeat(repeat):
    return {
        "weekly": "FREQ=WEEKLY",
        "monthly": "FREQ=MONTHLY",
        "yearly": "FREQ=YEARLY",
    }.get(repeat, "")


def build_vevent(payload):
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("title_required")

    start_date = validate_date(payload.get("startDate") or "")
    if not start_date:
        raise ValueError("start_date_required")
    end_date = validate_date(payload.get("endDate") or start_date)
    all_day = bool(payload.get("allDay"))
    start_time = validate_time(payload.get("startTime") or "")
    end_time = validate_time(payload.get("endTime") or "")
    alarm_time = validate_time(payload.get("alarmTime") or "")
    repeat = validate_repeat(payload.get("repeat") or "")
    description = str(payload.get("memo") or "").strip()

    uid = str(uuid.uuid4()).upper()
    alarm_uid = str(uuid.uuid4()).upper()
    now = utc_stamp(datetime.now(timezone.utc))

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "PRODID:-//KaosGDD//Calendar Adapter//EN",
        *SEOUL_VTIMEZONE.splitlines(),
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        f"CREATED:{now}",
        f"LAST-MODIFIED:{now}",
        f"SUMMARY:{escape_ics(title)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{escape_ics(description)}")

    if all_day:
        start_compact = compact_date(start_date)
        end_exclusive = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        lines.extend([f"DTSTART;VALUE=DATE:{start_compact}", f"DTEND;VALUE=DATE:{end_exclusive.strftime('%Y%m%d')}"])
    else:
        start_time = start_time or "09:00"
        end_time = end_time or "10:00"
        start_dt = local_datetime(start_date, start_time)
        end_dt = local_datetime(end_date, end_time)
        if end_dt <= start_dt:
            raise ValueError("end_before_start")
        lines.extend(
            [
                f"DTSTART;TZID={LOCAL_TZID}:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND;TZID={LOCAL_TZID}:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            ]
        )

    rrule = rrule_for_repeat(repeat)
    if rrule:
        lines.append(f"RRULE:{rrule}")

    if alarm_time:
        alarm_dt = local_datetime(start_date, alarm_time)
        lines.extend(
            [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{escape_ics(title)}",
                f"TRIGGER;VALUE=DATE-TIME:{utc_stamp(alarm_dt)}",
                f"UID:{alarm_uid}",
                f"X-WR-ALARMUID:{alarm_uid}",
                "END:VALARM",
            ]
        )

    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return uid, calendar_body(lines)


def create_event(payload, profile="main"):
    if not configured(profile):
        raise ValueError("adapter_not_configured")
    collections = collections_for_profile(profile)
    collection = select_collection(collections, str(payload.get("collectionId") or "").strip(), "VEVENT")
    item_account = account_for_collection(collection)
    uid, body = build_vevent(payload)
    href = urllib.parse.urljoin(collection["href"], f"{uid}.ics")
    radicale_request(
        item_account,
        "PUT",
        href,
        body,
        {"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"},
    )
    return {"ok": True, "uid": uid, "collection": collection["id"]}


def find_task(collections, uid, collection_id=""):
    if not uid:
        raise ValueError("uid_required")
    targets = [collection for collection in collections if not collection_id or collection["id"] == collection_id]
    if collection_id and not targets:
        raise ValueError("collection_not_found")

    for collection in targets:
        if collection.get("components") and "VTODO" not in collection["components"]:
            continue
        item_account = account_for_collection(collection)
        for item in report_collection(item_account, collection["href"]):
            if item.get("component") == "VTODO" and item.get("UID") == uid:
                return collection, item

    raise ValueError("task_not_found")


def update_task(payload, profile="main"):
    if not configured(profile):
        raise ValueError("adapter_not_configured")
    uid = str(payload.get("uid") or "").strip()
    collections = collections_for_profile(profile)
    collection, existing = find_task(collections, uid, str(payload.get("collectionId") or "").strip())
    item_account = account_for_collection(collection)
    _, body = build_vtodo(payload, existing)
    radicale_request(
        item_account,
        "PUT",
        existing["href"],
        body,
        {"Content-Type": "text/calendar; charset=utf-8"},
    )
    return {"ok": True, "uid": uid, "collection": collection["id"]}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        profile = profile_from_headers(self.headers)
        if path == "/health":
            json_response(self, 200, {"ok": True, "configured": configured(profile), "provider": "radicale", "profile": profile})
            return
        if path == "/api/calendar/bootstrap":
            try:
                json_response(self, 200, bootstrap_payload(profile))
            except (ET.ParseError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"configured": configured(profile), "live": False, "profile": profile, "error": type(exc).__name__})
            return
        json_response(self, 404, {"error": "not_found"})

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        profile = profile_from_headers(self.headers)
        if path == "/api/calendar/tasks":
            try:
                json_response(self, 200, update_task(read_json_request(self), profile))
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
            except (ET.ParseError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"configured": configured(profile), "live": False, "profile": profile, "error": type(exc).__name__})
            return
        json_response(self, 404, {"error": "not_found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        profile = profile_from_headers(self.headers)
        if path == "/api/calendar/events":
            try:
                json_response(self, 201, create_event(read_json_request(self), profile))
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
            except (ET.ParseError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"configured": configured(profile), "live": False, "profile": profile, "error": type(exc).__name__})
            return
        if path == "/api/calendar/tasks":
            try:
                json_response(self, 201, create_task(read_json_request(self), profile))
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
            except (ET.ParseError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"configured": configured(profile), "live": False, "profile": profile, "error": type(exc).__name__})
            return
        json_response(self, 404, {"error": "not_found"})

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"KaosGDD calendar adapter listening on {PORT}", flush=True)
    server.serve_forever()

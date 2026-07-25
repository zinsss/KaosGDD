#!/usr/bin/env python3
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PORT = int(os.environ.get("PORT", "8091"))
RADICALE_URL = os.environ.get("RADICALE_INTERNAL_URL", "http://100.94.208.16:5232").rstrip("/")
RADICALE_USERNAME = os.environ.get("RADICALE_USERNAME", "")
RADICALE_PASSWORD = os.environ.get("RADICALE_PASSWORD", "")
TIMEOUT = float(os.environ.get("KAOSGDD_ADAPTER_TIMEOUT_SECONDS", "30"))
LOCAL_TIMEZONE = timezone(timedelta(hours=int(os.environ.get("KAOSGDD_LOCAL_UTC_OFFSET_HOURS", "9"))))


def configured():
    return bool(RADICALE_URL and RADICALE_USERNAME and RADICALE_PASSWORD)


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def radicale_request(method, path, body="", headers=None):
    url = urllib.parse.urljoin(f"{RADICALE_URL}/", path.lstrip("/"))
    request = urllib.request.Request(url, data=body.encode("utf-8"), method=method)
    token = base64.b64encode(f"{RADICALE_USERNAME}:{RADICALE_PASSWORD}".encode("utf-8")).decode("ascii")
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("User-Agent", "KaosGDD-CalendarAdapter/0.1")
    for key, value in (headers or {}).items():
        request.add_header(key, value)

    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def propfind_collections():
    body = """<?xml version="1.0" encoding="utf-8" ?>
<propfind xmlns="DAV:" xmlns:cs="http://calendarserver.org/ns/">
  <prop>
    <displayname />
    <resourcetype />
    <cs:getctag />
  </prop>
</propfind>"""
    _, xml = radicale_request(
        "PROPFIND",
        f"/{RADICALE_USERNAME}/",
        body,
        {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    return parse_collections(xml)


def parse_collections(xml):
    root = ET.fromstring(xml)
    namespace = {"d": "DAV:", "cal": "urn:ietf:params:xml:ns:caldav", "cs": "http://calendarserver.org/ns/"}
    collections = []

    for response in root.findall("d:response", namespace):
        href = text_of(response, "d:href", namespace)
        if not href or href.rstrip("/") == f"/{RADICALE_USERNAME}":
            continue

        resourcetype = response.find(".//d:resourcetype", namespace)
        if resourcetype is None:
            continue

        is_calendar = resourcetype.find("cal:calendar", namespace) is not None or resourcetype.find("d:collection", namespace) is not None
        if not is_calendar:
            continue

        collection_id = href.strip("/").split("/")[-1] or href.strip("/")
        display_name = text_of(response, ".//d:displayname", namespace) or collection_id
        collections.append({"id": collection_id, "name": display_name, "owner": RADICALE_USERNAME, "href": href})

    return collections


def text_of(element, selector, namespace):
    item = element.find(selector, namespace)
    if item is None or item.text is None:
        return ""
    return item.text.strip()


def report_collection(href):
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

    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {"component": "VEVENT", "href": href}
        elif line == "BEGIN:VTODO":
            current = {"component": "VTODO", "href": href}
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


def bootstrap_payload():
    if not configured():
        return {
            "configured": False,
            "live": False,
            "collections": [],
            "events": [],
            "tasks": [],
            "message": "Radicale credentials are not configured.",
        }

    collections = propfind_collections()
    events = []
    tasks = []

    for collection in collections:
        for item in report_collection(collection["href"]):
            if item.get("component") == "VEVENT":
                events.append(normalize_event(item, collection))
            elif item.get("component") == "VTODO":
                tasks.append(normalize_task(item, collection))

    return {
        "configured": True,
        "live": True,
        "collections": collections,
        "events": events,
        "tasks": tasks,
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            json_response(self, 200, {"ok": True, "configured": configured(), "provider": "radicale"})
            return
        if path == "/api/calendar/bootstrap":
            try:
                json_response(self, 200, bootstrap_payload())
            except (ET.ParseError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"configured": configured(), "live": False, "error": type(exc).__name__})
            return
        json_response(self, 404, {"error": "not_found"})

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"KaosGDD calendar adapter listening on {PORT}", flush=True)
    server.serve_forever()

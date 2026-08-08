import hashlib
import json
import os
import threading
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta


GOOGLE_KOREA_HOLIDAY_URL = os.environ.get(
    "GOOGLE_KOREA_HOLIDAY_ICAL_URL",
    "https://calendar.google.com/calendar/ical/ko.south_korea%23holiday%40group.v.calendar.google.com/public/basic.ics",
).strip()
SYNC_ENABLED = os.environ.get("HOLIDAY_SYNC_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
SYNC_INTERVAL_SECONDS = max(3600, int(os.environ.get("HOLIDAY_SYNC_INTERVAL_SECONDS", "86400")))
ADAPTER_URL = os.environ.get("CALENDAR_ADAPTER_INTERNAL_URL", "http://100.94.208.16:8091").rstrip("/")
TIMEOUT_SECONDS = float(os.environ.get("BRAIN_UPSTREAM_TIMEOUT_SECONDS", "30"))

SYSTEM_CATEGORY = "KAOS-SYSTEM"
SOURCE_CATEGORY = "KAOS-GOOGLE-HOLIDAY"
PUBLIC_CATEGORY = "KAOS-PUBLIC-HOLIDAY"
OBSERVANCE_CATEGORY = "KAOS-OBSERVANCE"
PUBLIC_HOLIDAY_TITLES = {
    "새해첫날",
    "설날",
    "설날 연휴",
    "삼일절",
    "어린이날",
    "부처님오신날",
    "지방선거일",
    "현충일",
    "광복절",
    "추석",
    "추석 연휴",
    "개천절",
    "한글날",
    "크리스마스",
}

_state_lock = threading.Lock()
_sync_lock = threading.Lock()
_scheduler_thread = None
_scheduler_wake = threading.Event()
_after_change_callback = None
_state = {
    "running": False,
    "lastAttemptAt": "",
    "lastSuccessAt": "",
    "lastError": "",
    "lastResult": {},
}


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def set_after_change_callback(callback):
    global _after_change_callback
    _after_change_callback = callback


def _notify_after_change():
    if not _after_change_callback:
        return
    try:
        _after_change_callback()
    except Exception as exc:
        print(f"Post-holiday calendar sync failed: {type(exc).__name__}: {exc}", flush=True)


def _unfold_ics(data):
    lines = []
    for raw in str(data or "").splitlines():
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw.rstrip("\r"))
    return lines


def _unescape_ics(value):
    return (
        str(value or "")
        .replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _property(line):
    if ":" not in line:
        return "", ""
    name, value = line.split(":", 1)
    return name.split(";", 1)[0].upper(), _unescape_ics(value)


def _ical_date(value):
    compact = str(value or "").strip()[:8]
    try:
        return datetime.strptime(compact, "%Y%m%d").date()
    except ValueError:
        return None


def parse_google_calendar(data, today=None):
    today = today or date.today()
    start_year = today.year
    end_year = today.year + 1
    items = []
    current = None
    for line in _unfold_ics(data):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current:
                start = _ical_date(current.get("DTSTART"))
                if start and start_year <= start.year <= end_year and current.get("SUMMARY"):
                    raw_end = _ical_date(current.get("DTEND"))
                    end = raw_end - timedelta(days=1) if raw_end and raw_end > start else start
                    external_uid = current.get("UID") or f"{start.isoformat()}:{current['SUMMARY']}"
                    items.append(
                        {
                            "externalUid": external_uid,
                            "uid": holiday_uid(external_uid),
                            "title": current["SUMMARY"].strip(),
                            "startDate": start.isoformat(),
                            "endDate": end.isoformat(),
                        }
                    )
            current = None
            continue
        if current is not None:
            name, value = _property(line)
            if name in {"UID", "SUMMARY", "DTSTART", "DTEND"} and name not in current:
                current[name] = value
    unique = {item["uid"]: item for item in items}
    return sorted(unique.values(), key=lambda item: (item["startDate"], item["title"], item["uid"]))


def holiday_uid(external_uid):
    digest = hashlib.sha256(str(external_uid or "").encode("utf-8")).hexdigest()[:24].upper()
    return f"KAOS-HOLIDAY-{digest}"


def fetch_google_calendar(today=None):
    if not GOOGLE_KOREA_HOLIDAY_URL:
        raise RuntimeError("holiday_source_not_configured")
    request = urllib.request.Request(
        GOOGLE_KOREA_HOLIDAY_URL,
        headers={"Accept": "text/calendar", "User-Agent": "KaosGDD-Brain/holiday-sync"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = response.read().decode("utf-8", errors="replace")
    items = parse_google_calendar(data, today=today)
    if not items:
        raise RuntimeError("holiday_source_empty")
    return items


def _adapter_request(method, payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{ADAPTER_URL}/internal/family/holidays",
        data=body,
        method=method,
        headers={"Accept": "application/json", "User-Agent": "KaosGDD-Brain/holiday-sync"},
    )
    if body is not None:
        request.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            result = json.loads(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            result = {"error": f"calendar_adapter_http_{status}"}
    if status >= 400 or not result.get("ok"):
        raise RuntimeError(result.get("error") or f"calendar_adapter_http_{status}")
    return result


def _categories(public_holiday):
    return [
        SYSTEM_CATEGORY,
        SOURCE_CATEGORY,
        PUBLIC_CATEGORY if public_holiday else OBSERVANCE_CATEGORY,
    ]


def default_public_holiday(title):
    normalized = str(title or "").strip()
    return normalized.startswith("쉬는 날 ") or normalized in PUBLIC_HOLIDAY_TITLES


def _public_item(item):
    categories = {str(value).upper() for value in item.get("categories", [])}
    return {
        "uid": item.get("uid", ""),
        "title": item.get("summary", item.get("title", "")),
        "startDate": item.get("startDate", ""),
        "endDate": item.get("endDate", item.get("startDate", "")),
        "publicHoliday": PUBLIC_CATEGORY in categories,
        "categories": sorted(categories),
    }


def list_holidays():
    result = _adapter_request("GET")
    return {
        "ok": True,
        "collection": result.get("collection", {}),
        "items": [_public_item(item) for item in result.get("items", [])],
        "sync": status(),
    }


def sync_holidays(today=None):
    with _sync_lock:
        with _state_lock:
            _state["running"] = True
            _state["lastAttemptAt"] = _now_iso()
            _state["lastError"] = ""
        try:
            source_items = fetch_google_calendar(today=today)
            existing_result = _adapter_request("GET")
            existing = {str(item.get("uid") or "").upper(): item for item in existing_result.get("items", [])}
            source_uids = {item["uid"] for item in source_items}
            created = 0
            updated = 0
            deleted = 0
            for source in source_items:
                current = existing.get(source["uid"])
                public_holiday = (
                    bool(current.get("publicHoliday"))
                    if current is not None
                    else default_public_holiday(source["title"])
                )
                result = _adapter_request(
                    "PUT",
                    {
                        **source,
                        "memo": "Google Korea Holidays",
                        "categories": _categories(public_holiday),
                    },
                )
                created += int(bool(result.get("created")))
                updated += int(not result.get("created"))

            years = {item["startDate"][:4] for item in source_items}
            for uid, current in existing.items():
                if uid in source_uids or str(current.get("startDate") or "")[:4] not in years:
                    continue
                result = _adapter_request("DELETE", {"uid": uid})
                deleted += int(bool(result.get("deleted")))

            result = {"created": created, "updated": updated, "deleted": deleted, "total": len(source_items)}
            with _state_lock:
                _state["lastSuccessAt"] = _now_iso()
                _state["lastResult"] = result
            _notify_after_change()
            return {"ok": True, **result}
        except Exception as exc:
            with _state_lock:
                _state["lastError"] = str(exc) or type(exc).__name__
            raise
        finally:
            with _state_lock:
                _state["running"] = False


def set_public_holiday(uid, public_holiday):
    with _sync_lock:
        uid = str(uid or "").strip().upper()
        result = _adapter_request("GET")
        current = next((item for item in result.get("items", []) if str(item.get("uid") or "").upper() == uid), None)
        if current is None:
            raise ValueError("holiday_not_found")
        _adapter_request(
            "PUT",
            {
                "uid": uid,
                "title": current.get("summary") or current.get("title"),
                "memo": current.get("description") or "Google Korea Holidays",
                "startDate": current.get("startDate"),
                "endDate": current.get("endDate") or current.get("startDate"),
                "categories": _categories(bool(public_holiday)),
            },
        )
        response = {"ok": True, "item": {**_public_item(current), "publicHoliday": bool(public_holiday)}}
        _notify_after_change()
        return response


def status():
    with _state_lock:
        return {
            "configured": bool(GOOGLE_KOREA_HOLIDAY_URL),
            "enabled": SYNC_ENABLED,
            **_state,
        }


def scheduler_loop():
    while True:
        try:
            sync_holidays()
        except Exception as exc:
            print(f"Holiday sync failed: {type(exc).__name__}: {exc}", flush=True)
        _scheduler_wake.wait(SYNC_INTERVAL_SECONDS)
        _scheduler_wake.clear()


def start_scheduler():
    global _scheduler_thread
    if not SYNC_ENABLED:
        return None
    if _scheduler_thread and _scheduler_thread.is_alive():
        return _scheduler_thread
    _scheduler_thread = threading.Thread(target=scheduler_loop, name="holiday-sync", daemon=True)
    _scheduler_thread.start()
    return _scheduler_thread

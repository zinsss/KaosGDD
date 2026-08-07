#!/usr/bin/env python3
import json
import os
import re
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from models.database import database_status, wait_for_database_and_migrate
from services.caregiver.summary import calculate_month, validate_day, validate_month
from services.caregiver.upstream import (
    CaregiverAdapterError,
    delete_caregiver_day,
    fetch_caregiver_journals,
    put_caregiver_day,
    put_caregiver_settings,
)
from services.calendar.upstream import adapter_status, portal_host, request_upstream, route_allowed
from services.event_presets import service as event_preset_service
from services.faxmail import notifier as faxmail_notifier
from services.rouny.store import RounyConflict, get_rouny_document, put_rouny_document
from services.recurring_tasks import service as recurring_task_service
from services.supplies import service as supplies_service


PORT = int(os.environ.get("BRAIN_PORT", "8092"))
VERSION = os.environ.get("BRAIN_VERSION", "0.5.1")
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
MAX_REQUEST_BYTES = 500_000


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def brain_status(headers):
    host = portal_host(headers)
    database = database_status()
    calendar_adapter = adapter_status(host)
    return {
        "ok": bool(database.get("ok") and calendar_adapter.get("ok")),
        "service": "kaosgdd-brain",
        "version": VERSION,
        "mode": "shadow",
        "profile": "family" if host == "family.kaosgdd.net" else "main",
        "database": database,
        "upstreams": {
            "calendarAdapter": calendar_adapter,
            "faxmailNotifications": faxmail_notifier.status(),
        },
    }


def request_body(handler):
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except ValueError as exc:
        raise ValueError("invalid_body_length") from exc
    if length <= 0 or length > MAX_REQUEST_BYTES:
        raise ValueError("invalid_body_length")
    return handler.rfile.read(length)


def json_request(handler):
    try:
        payload = json.loads(request_body(handler).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_json_payload") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_json_payload")
    return payload


def require_family_profile(headers):
    if portal_host(headers) != "family.kaosgdd.net":
        raise ValueError("family_profile_required")


def caregiver_month_payload(month):
    selected_month = validate_month(month)
    journals = fetch_caregiver_journals(selected_month)
    return calculate_month(selected_month, journals.get("days"), journals.get("settings"))


def supplies_status_for_error(exc):
    message = str(exc)
    if message in {"supplies_not_configured", "supplies_collection_not_found"}:
        return 503
    if message == "not found":
        return 404
    return 400


def re_match_supply_action(path):
    match = re.fullmatch(r"/api/supplies/([^/]+)(?:/(done|active))?", path)
    if not match:
        return None
    return urllib.parse.unquote(match.group(1)), match.group(2) or ""


def re_match_recurring_task(path):
    match = re.fullmatch(r"/api/recurring-tasks/([^/]+)", path)
    return urllib.parse.unquote(match.group(1)) if match else ""


def recurring_task_status_for_error(exc):
    message = str(exc)
    if message == "recurring_task_not_found":
        return 404
    if message in {"calendar_adapter_unavailable", "calendar_adapter_invalid_response"}:
        return 502
    return 400


def re_match_event_preset(path):
    match = re.fullmatch(r"/api/event-presets/([^/]+)", path)
    return urllib.parse.unquote(match.group(1)) if match else ""


def event_preset_status_for_error(exc):
    return 404 if str(exc) == "event_preset_not_found" else 400


def proxy_request(handler, method):
    if not route_allowed(method, handler.path):
        raise ValueError("upstream_route_not_allowed")
    body = request_body(handler) if method != "GET" else None
    status, content_type, response_body = request_upstream(
        method,
        handler.path,
        portal_host(handler.headers),
        body=body,
        content_type=handler.headers.get("Content-Type", "application/json"),
    )
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(response_body)))
    handler.end_headers()
    handler.wfile.write(response_body)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/event-presets":
            try:
                profile = recurring_task_service.profile_for_host(portal_host(self.headers))
                json_response(self, 200, event_preset_service.list_items(profile))
            except ValueError as exc:
                json_response(self, event_preset_status_for_error(exc), {"ok": False, "error": str(exc)})
            except Exception as exc:
                print(f"Event preset read failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "event_preset_storage_unavailable"})
            return

        if parsed.path == "/api/recurring-tasks":
            try:
                profile = recurring_task_service.profile_for_host(portal_host(self.headers))
                json_response(self, 200, recurring_task_service.list_definitions(profile))
            except ValueError as exc:
                json_response(self, recurring_task_status_for_error(exc), {"ok": False, "error": str(exc)})
            except Exception as exc:
                print(f"Recurring task read failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "recurring_task_storage_unavailable"})
            return

        if parsed.path == "/api/rouny/templates":
            try:
                require_family_profile(self.headers)
                json_response(self, 200, get_rouny_document())
            except ValueError as exc:
                json_response(self, 404 if str(exc) == "family_profile_required" else 400, {"error": str(exc)})
            except Exception as exc:
                print(f"Rouny read failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "rouny_storage_unavailable"})
            return

        if parsed.path == "/api/caregiver/month":
            try:
                require_family_profile(self.headers)
                query = urllib.parse.parse_qs(parsed.query)
                json_response(self, 200, caregiver_month_payload((query.get("month") or [""])[0]))
            except ValueError as exc:
                status = 404 if str(exc) == "family_profile_required" else 400
                json_response(self, status, {"error": str(exc)})
            except CaregiverAdapterError as exc:
                json_response(self, 502 if exc.status >= 500 else exc.status, exc.payload)
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return

        if parsed.path == "/api/supplies":
            try:
                query = urllib.parse.parse_qs(parsed.query)
                json_response(self, 200, supplies_service.list_supplies((query.get("mode") or ["active"])[0]))
            except ValueError as exc:
                json_response(self, supplies_status_for_error(exc), {"ok": False, "error": str(exc)})
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return

        if parsed.path == "/api/supplies/presets":
            try:
                json_response(self, 200, supplies_service.list_presets())
            except Exception as exc:
                print(f"Supplies presets read failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "supplies_presets_unavailable"})
            return

        if self.path == "/health":
            payload = brain_status(self.headers)
            json_response(self, 200 if payload["ok"] else 503, payload)
            return

        if self.path == "/api/brain/status":
            json_response(self, 200, brain_status(self.headers))
            return

        if (
            self.path == "/api/calendar/bootstrap"
            or self.path == "/api/weather/month"
            or self.path.startswith("/api/weather/month?")
        ):
            try:
                proxy_request(self, "GET")
            except ValueError as exc:
                json_response(self, 404, {"error": str(exc)})
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return

        json_response(self, 404, {"error": "not_found"})

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/event-presets":
            try:
                profile = recurring_task_service.profile_for_host(portal_host(self.headers))
                json_response(self, 201, event_preset_service.create_item(json_request(self), profile))
            except ValueError as exc:
                json_response(self, event_preset_status_for_error(exc), {"ok": False, "error": str(exc)})
            except Exception as exc:
                print(f"Event preset create failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "event_preset_storage_unavailable"})
            return

        if path == "/api/recurring-tasks":
            try:
                profile = recurring_task_service.profile_for_host(portal_host(self.headers))
                payload = json_request(self)
                json_response(self, 201, recurring_task_service.create_definition(payload, profile))
            except ValueError as exc:
                json_response(self, recurring_task_status_for_error(exc), {"ok": False, "error": str(exc)})
            except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                json_response(self, 502, {"ok": False, "error": str(exc) or type(exc).__name__})
            except Exception as exc:
                print(f"Recurring task create failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "recurring_task_storage_unavailable"})
            return

        if path == "/api/supplies":
            try:
                payload = json_request(self)
                json_response(self, 200, supplies_service.create_supply(payload.get("title")))
            except ValueError as exc:
                json_response(self, supplies_status_for_error(exc), {"ok": False, "error": str(exc)})
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return
        if path == "/api/supplies/presets/use":
            try:
                payload = json_request(self)
                json_response(self, 200, supplies_service.use_preset(payload.get("name")))
            except ValueError as exc:
                json_response(self, supplies_status_for_error(exc), {"ok": False, "error": str(exc)})
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return
        supply_action = re_match_supply_action(path)
        if supply_action and supply_action[1] in {"done", "active"}:
            try:
                result = (
                    supplies_service.mark_supply_done(supply_action[0])
                    if supply_action[1] == "done"
                    else supplies_service.mark_supply_active(supply_action[0])
                )
                json_response(self, 200, result)
            except ValueError as exc:
                json_response(self, supplies_status_for_error(exc), {"ok": False, "error": str(exc)})
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return
        if path in {"/api/capture", "/capture"}:
            try:
                payload = json_request(self)
                raw = payload.get("raw")
                if raw is None:
                    raw = payload.get("text")
                json_response(self, 200, supplies_service.capture_supply(raw))
            except ValueError as exc:
                json_response(self, 400, {"ok": False, "error": str(exc)})
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return
        self._proxy_write("POST")

    def do_PUT(self):
        path = urllib.parse.urlsplit(self.path).path
        event_preset_id = re_match_event_preset(path)
        if event_preset_id:
            try:
                profile = recurring_task_service.profile_for_host(portal_host(self.headers))
                json_response(
                    self,
                    200,
                    event_preset_service.update_item(event_preset_id, json_request(self), profile),
                )
            except ValueError as exc:
                json_response(self, event_preset_status_for_error(exc), {"ok": False, "error": str(exc)})
            except Exception as exc:
                print(f"Event preset update failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "event_preset_storage_unavailable"})
            return

        recurring_task_id = re_match_recurring_task(path)
        if recurring_task_id:
            try:
                profile = recurring_task_service.profile_for_host(portal_host(self.headers))
                payload = json_request(self)
                json_response(
                    self,
                    200,
                    recurring_task_service.update_definition(recurring_task_id, payload, profile),
                )
            except ValueError as exc:
                json_response(self, recurring_task_status_for_error(exc), {"ok": False, "error": str(exc)})
            except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                json_response(self, 502, {"ok": False, "error": str(exc) or type(exc).__name__})
            except Exception as exc:
                print(f"Recurring task update failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "recurring_task_storage_unavailable"})
            return

        if path == "/api/rouny/templates":
            try:
                require_family_profile(self.headers)
                payload = json_request(self)
                json_response(
                    self,
                    200,
                    put_rouny_document(payload.get("templates"), payload.get("baseRevision")),
                )
            except RounyConflict as exc:
                json_response(
                    self,
                    409,
                    {
                        "ok": False,
                        "error": "rouny_revision_conflict",
                        "document": exc.document,
                    },
                )
            except ValueError as exc:
                json_response(self, 404 if str(exc) == "family_profile_required" else 400, {"error": str(exc)})
            except Exception as exc:
                print(f"Rouny write failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "rouny_storage_unavailable"})
            return
        if path == "/api/caregiver/settings":
            try:
                require_family_profile(self.headers)
                payload = json_request(self)
                month = validate_month(payload.get("month"))
                put_caregiver_settings(
                    {
                        "month": month,
                        "hourlyWage": payload.get("hourlyWage"),
                        "transportFee": payload.get("transportFee"),
                    }
                )
                json_response(self, 200, caregiver_month_payload(month))
            except ValueError as exc:
                status = 404 if str(exc) == "family_profile_required" else 400
                json_response(self, status, {"error": str(exc)})
            except CaregiverAdapterError as exc:
                json_response(self, 502 if exc.status >= 500 else exc.status, exc.payload)
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return
        if path == "/api/caregiver/day":
            try:
                require_family_profile(self.headers)
                payload = json_request(self)
                date_value = validate_day(payload.get("date"))
                put_caregiver_day(
                    {
                        "date": date_value,
                        "sessions": payload.get("sessions"),
                        "extras": payload.get("extras"),
                    }
                )
                json_response(self, 200, caregiver_month_payload(date_value[:7]))
            except ValueError as exc:
                status = 404 if str(exc) == "family_profile_required" else 400
                json_response(self, status, {"error": str(exc)})
            except CaregiverAdapterError as exc:
                json_response(self, 502 if exc.status >= 500 else exc.status, exc.payload)
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return
        self._proxy_write("PUT")

    def do_DELETE(self):
        path = urllib.parse.urlsplit(self.path).path
        event_preset_id = re_match_event_preset(path)
        if event_preset_id:
            try:
                profile = recurring_task_service.profile_for_host(portal_host(self.headers))
                json_response(self, 200, event_preset_service.delete_item(event_preset_id, profile))
            except ValueError as exc:
                json_response(self, event_preset_status_for_error(exc), {"ok": False, "error": str(exc)})
            except Exception as exc:
                print(f"Event preset delete failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "event_preset_storage_unavailable"})
            return

        recurring_task_id = re_match_recurring_task(path)
        if recurring_task_id:
            try:
                profile = recurring_task_service.profile_for_host(portal_host(self.headers))
                json_response(
                    self,
                    200,
                    recurring_task_service.delete_definition(recurring_task_id, profile),
                )
            except ValueError as exc:
                json_response(self, recurring_task_status_for_error(exc), {"ok": False, "error": str(exc)})
            except Exception as exc:
                print(f"Recurring task delete failed: {type(exc).__name__}", flush=True)
                json_response(self, 503, {"ok": False, "error": "recurring_task_storage_unavailable"})
            return

        if path == "/api/caregiver/day":
            try:
                require_family_profile(self.headers)
                payload = json_request(self)
                date_value = validate_day(payload.get("date"))
                delete_caregiver_day({"date": date_value})
                json_response(self, 200, caregiver_month_payload(date_value[:7]))
            except ValueError as exc:
                status = 404 if str(exc) == "family_profile_required" else 400
                json_response(self, status, {"error": str(exc)})
            except CaregiverAdapterError as exc:
                json_response(self, 502 if exc.status >= 500 else exc.status, exc.payload)
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return
        supply_action = re_match_supply_action(path)
        if supply_action and supply_action[1] == "":
            try:
                json_response(self, 200, supplies_service.delete_supply(supply_action[0]))
            except ValueError as exc:
                json_response(self, supplies_status_for_error(exc), {"ok": False, "error": str(exc)})
            except (urllib.error.URLError, TimeoutError) as exc:
                json_response(self, 502, {"ok": False, "error": type(exc).__name__})
            return
        self._proxy_write("DELETE")

    def _proxy_write(self, method):
        try:
            proxy_request(self, method)
        except ValueError as exc:
            status = 400 if str(exc) == "invalid_body_length" else 404
            json_response(self, status, {"error": str(exc)})
        except (urllib.error.URLError, TimeoutError) as exc:
            json_response(self, 502, {"ok": False, "error": type(exc).__name__})

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}", flush=True)


def main():
    wait_for_database_and_migrate(MIGRATIONS)
    recurring_task_service.start_scheduler()
    faxmail_notifier.start_scheduler()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"KaosGDD Brain {VERSION} listening on {PORT} in shadow mode", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

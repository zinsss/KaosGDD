#!/usr/bin/env python3
import json
import os
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from models.database import database_status, wait_for_database_and_migrate
from services.calendar.upstream import adapter_status, portal_host, request_upstream, route_allowed


PORT = int(os.environ.get("BRAIN_PORT", "8092"))
VERSION = os.environ.get("BRAIN_VERSION", "0.2.0-shadow")
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
MAX_REQUEST_BYTES = 20_000


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
        self._proxy_write("POST")

    def do_PUT(self):
        self._proxy_write("PUT")

    def do_DELETE(self):
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
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"KaosGDD Brain {VERSION} listening on {PORT} in shadow mode", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from models.database import database_status, wait_for_database_and_migrate
from services.calendar.upstream import adapter_status, portal_host, request_upstream


PORT = int(os.environ.get("BRAIN_PORT", "8092"))
VERSION = os.environ.get("BRAIN_VERSION", "0.1.0-shadow")
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


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
                status, content_type, body = request_upstream(self.path, portal_host(self.headers))
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except ValueError as exc:
                json_response(self, 404, {"error": str(exc)})
            return

        json_response(self, 404, {"error": "not_found"})

    def do_POST(self):
        json_response(self, 405, {"error": "brain_shadow_read_only"})

    def do_PUT(self):
        json_response(self, 405, {"error": "brain_shadow_read_only"})

    def do_DELETE(self):
        json_response(self, 405, {"error": "brain_shadow_read_only"})

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}", flush=True)


def main():
    wait_for_database_and_migrate(MIGRATIONS)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"KaosGDD Brain {VERSION} listening on {PORT} in shadow mode", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

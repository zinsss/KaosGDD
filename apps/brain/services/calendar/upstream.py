import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


ALLOWED_PORTAL_HOSTS = {"kaosgdd.net", "family.kaosgdd.net"}
ALLOWED_ROUTES = {
    "GET": {"/api/calendar/bootstrap", "/api/weather/month"},
    "POST": {"/api/calendar/events", "/api/calendar/tasks"},
    "PUT": {"/api/calendar/events", "/api/calendar/tasks"},
    "DELETE": {"/api/calendar/events", "/api/calendar/tasks"},
}


def portal_host(headers):
    raw = headers.get("X-Forwarded-Host") or headers.get("Host") or "kaosgdd.net"
    host = raw.split(":", 1)[0].lower()
    return host if host in ALLOWED_PORTAL_HOSTS else "kaosgdd.net"


def route_allowed(method, path_and_query):
    parsed = urllib.parse.urlsplit(path_and_query)
    return parsed.path in ALLOWED_ROUTES.get(method.upper(), set())


def upstream_url(method, path_and_query):
    base = os.environ.get("CALENDAR_ADAPTER_INTERNAL_URL", "http://100.94.208.16:8091").rstrip("/")
    parsed = urllib.parse.urlsplit(path_and_query)
    normalized_method = method.upper()
    if not route_allowed(normalized_method, path_and_query):
        raise ValueError("upstream_route_not_allowed")
    return f"{base}{parsed.path}{'?' + parsed.query if parsed.query else ''}"


def request_upstream(method, path_and_query, host, body=None, content_type="application/json"):
    normalized_method = method.upper()
    request = urllib.request.Request(
        upstream_url(normalized_method, path_and_query),
        data=body,
        method=normalized_method,
        headers={
            "Accept": "application/json",
            "Host": host,
            "X-Forwarded-Host": host,
            "User-Agent": "KaosGDD-Brain/0.2",
        },
    )
    if body is not None:
        request.add_header("Content-Type", content_type or "application/json")
    timeout = float(os.environ.get("BRAIN_UPSTREAM_TIMEOUT_SECONDS", "30"))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers.get("Content-Type", "application/json"), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", "application/json"), exc.read()


def adapter_status(host):
    base = os.environ.get("CALENDAR_ADAPTER_INTERNAL_URL", "http://100.94.208.16:8091").rstrip("/")
    request = urllib.request.Request(
        f"{base}/health",
        headers={
            "Accept": "application/json",
            "Host": host,
            "X-Forwarded-Host": host,
            "User-Agent": "KaosGDD-Brain/0.2",
        },
    )
    started = time.monotonic()
    timeout = float(os.environ.get("BRAIN_UPSTREAM_TIMEOUT_SECONDS", "30"))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "ok": response.status == 200 and bool(payload.get("ok")),
            "status": response.status,
            "profile": payload.get("profile", ""),
            "configured": bool(payload.get("configured")),
            "latencyMs": round((time.monotonic() - started) * 1000, 1),
        }
    except (json.JSONDecodeError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        return {
            "ok": False,
            "error": type(exc).__name__,
            "latencyMs": round((time.monotonic() - started) * 1000, 1),
        }

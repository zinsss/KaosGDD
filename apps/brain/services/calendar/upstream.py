import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


ALLOWED_PORTAL_HOSTS = {"kaosgdd.net", "family.kaosgdd.net"}
ALLOWED_READ_PATHS = {"/api/calendar/bootstrap", "/api/weather/month"}


def portal_host(headers):
    raw = headers.get("X-Forwarded-Host") or headers.get("Host") or "kaosgdd.net"
    host = raw.split(":", 1)[0].lower()
    return host if host in ALLOWED_PORTAL_HOSTS else "kaosgdd.net"


def upstream_url(path_and_query):
    base = os.environ.get("CALENDAR_ADAPTER_INTERNAL_URL", "http://100.94.208.16:8091").rstrip("/")
    parsed = urllib.parse.urlsplit(path_and_query)
    if parsed.path not in ALLOWED_READ_PATHS:
        raise ValueError("upstream_path_not_allowed")
    return f"{base}{parsed.path}{'?' + parsed.query if parsed.query else ''}"


def request_upstream(path_and_query, host):
    request = urllib.request.Request(
        upstream_url(path_and_query),
        headers={
            "Accept": "application/json",
            "Host": host,
            "X-Forwarded-Host": host,
            "User-Agent": "KaosGDD-Brain/0.1",
        },
    )
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
            "User-Agent": "KaosGDD-Brain/0.1",
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

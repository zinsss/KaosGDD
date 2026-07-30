import json
import os
import urllib.error
import urllib.parse
import urllib.request


class CaregiverAdapterError(Exception):
    def __init__(self, status, payload):
        super().__init__(payload.get("error") or f"caregiver_adapter_{status}")
        self.status = status
        self.payload = payload


def adapter_request(method, path, payload=None):
    base = os.environ.get("CALENDAR_ADAPTER_INTERNAL_URL", "http://100.94.208.16:8091").rstrip("/")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base}{path}",
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Host": "kaosgdd.net",
            "X-Forwarded-Host": "kaosgdd.net",
            "User-Agent": "KaosGDD-Brain/0.3",
        },
    )
    timeout = float(os.environ.get("BRAIN_UPSTREAM_TIMEOUT_SECONDS", "30"))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
        except json.JSONDecodeError:
            error_payload = {"error": f"caregiver_adapter_{exc.code}"}
        raise CaregiverAdapterError(exc.code, error_payload) from exc


def fetch_caregiver_journals(month):
    query = urllib.parse.urlencode({"month": month})
    return adapter_request("GET", f"/internal/system/caregiver?{query}")


def put_caregiver_settings(payload):
    return adapter_request("PUT", "/internal/system/caregiver/settings", payload)


def put_caregiver_day(payload):
    return adapter_request("PUT", "/internal/system/caregiver/day", payload)


def delete_caregiver_day(payload):
    return adapter_request("DELETE", "/internal/system/caregiver/day", payload)

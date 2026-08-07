import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


STATE_LOCK = threading.Lock()
WORKER_THREAD = None
WORKER_STATE = {
    "started": False,
    "lastScanAt": "",
    "lastNotifyAt": "",
    "lastError": "",
    "knownCount": 0,
    "notifiedCount": 0,
    "failureCount": 0,
}


@dataclass(frozen=True)
class FaxEvent:
    key: str
    filename: str
    path: str
    commid: str
    remote: str
    pages: str
    received_at: str


@dataclass(frozen=True)
class DeliveryFailure:
    key: str
    delivery_key: str
    filename: str
    attempts: int
    error_type: str


def enabled():
    return os.environ.get("FAX_NOTIFY_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def recvq_root():
    return Path(os.environ.get("FAX_NOTIFY_RECVQ", "/integrations/hylafax/recvq"))


def xferfaxlog_path():
    return Path(os.environ.get("FAX_NOTIFY_XFERFAXLOG", "/integrations/hylafax/log/xferfaxlog"))


def state_path():
    return Path(os.environ.get("FAX_NOTIFY_STATE_PATH", "/data/faxmail/notified-recvq.json"))


def poll_seconds():
    return max(5, int(os.environ.get("FAX_NOTIFY_POLL_SECONDS", "20")))


def min_file_age_seconds():
    return max(0, int(os.environ.get("FAX_NOTIFY_MIN_FILE_AGE_SECONDS", "60")))


def delivery_failure_root():
    return Path(
        os.environ.get(
            "FAX_NOTIFY_DELIVERY_FAILURE_ROOT",
            "/integrations/hylafax/status/kaosgdd-faxmail/failed",
        )
    )


def mark_existing_on_first_run():
    return os.environ.get("FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def ntfy_url():
    raw_url = os.environ.get("NTFY_URL", "").strip().rstrip("/")
    topic = os.environ.get("NTFY_TOPIC", "").strip().strip("/")
    if not raw_url:
        return ""
    if topic:
        return f"{raw_url}/{urllib.parse.quote(topic)}"
    return raw_url


def load_state(path=None):
    path = Path(path or state_path())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"known": [], "knownFailures": []}
    known = payload.get("known") if isinstance(payload, dict) else []
    known_failures = payload.get("knownFailures") if isinstance(payload, dict) else []
    if not isinstance(known, list):
        known = []
    if not isinstance(known_failures, list):
        known_failures = []
    return {
        "known": [str(value) for value in known],
        "knownFailures": [str(value) for value in known_failures],
    }


def save_state(state, path=None):
    path = Path(path or state_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    known = sorted(set(str(value) for value in state.get("known", [])))
    known_failures = sorted(set(str(value) for value in state.get("knownFailures", [])))
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(
        json.dumps(
            {"known": known, "knownFailures": known_failures},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def commid_from_filename(filename):
    match = re.fullmatch(r"fax0*([0-9]+)\.tif", filename)
    if not match:
        return ""
    return match.group(1).zfill(9)


def parse_xferfaxlog(path=None):
    path = Path(path or xferfaxlog_path())
    events = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return events
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 10 or parts[1] != "RECV":
            continue
        commid = parts[2].strip()
        filename = parts[4].strip()
        if not commid or not filename:
            continue
        events[filename] = {
            "received_at": parts[0].strip(),
            "remote": parts[8].strip().strip('"'),
            "pages": parts[10].strip() if len(parts) > 10 else "",
            "commid": commid,
        }
    return events


def scan_received_faxes(recvq=None, xferlog=None, *, minimum_age=None, now=None):
    recvq = Path(recvq or recvq_root())
    details = parse_xferfaxlog(xferlog)
    minimum_age = min_file_age_seconds() if minimum_age is None else max(0, int(minimum_age))
    now = time.time() if now is None else float(now)
    if not recvq.is_dir():
        return []
    events = []
    for path in sorted(recvq.glob("fax*.tif")):
        stat = path.stat()
        if now - stat.st_mtime < minimum_age:
            continue
        info = details.get(f"recvq/{path.name}") or details.get(str(path)) or {}
        commid = str(info.get("commid") or commid_from_filename(path.name))
        events.append(
            FaxEvent(
                key=f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}",
                filename=path.name,
                path=str(path),
                commid=commid,
                remote=str(info.get("remote") or "unknown"),
                pages=str(info.get("pages") or ""),
                received_at=str(info.get("received_at") or ""),
            )
        )
    return events


def scan_delivery_failures(root=None):
    root = Path(root or delivery_failure_root())
    if not root.is_dir():
        return []
    failures = []
    try:
        paths = sorted(root.glob("*.json"))
    except OSError:
        return []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        delivery_key = str(payload.get("deliveryKey") or path.stem)
        source = Path(str(payload.get("source") or ""))
        failures.append(
            DeliveryFailure(
                key=delivery_key,
                delivery_key=delivery_key,
                filename=source.name or "unknown fax",
                attempts=int(payload.get("attempts") or 0),
                error_type=str(payload.get("lastErrorType") or "delivery error"),
            )
        )
    return failures


def notify_ntfy(event, opener=None):
    url = ntfy_url()
    if not url:
        raise RuntimeError("ntfy_not_configured")
    title = os.environ.get("FAX_NOTIFY_TITLE", "Incoming fax").strip() or "Incoming fax"
    topic_click = os.environ.get("FAX_NOTIFY_CLICK_URL", "").strip()
    body_lines = [
        f"Received {event.filename}",
        f"From: {event.remote or 'unknown'}",
    ]
    if event.pages:
        body_lines.append(f"Pages: {event.pages}")
    if event.commid:
        body_lines.append(f"CommID: {event.commid}")
    request = urllib.request.Request(
        url,
        data="\n".join(body_lines).encode("utf-8"),
        method="POST",
        headers={
            "Title": title,
            "Priority": os.environ.get("FAX_NOTIFY_PRIORITY", "high"),
            "Tags": os.environ.get("FAX_NOTIFY_TAGS", "fax,inbox"),
        },
    )
    if topic_click:
        request.add_header("Click", topic_click)
    token = os.environ.get("NTFY_TOKEN", "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    timeout = float(os.environ.get("NTFY_TIMEOUT_SECONDS", "10"))
    opener = opener or urllib.request.urlopen
    with opener(request, timeout=timeout) as response:
        response.read()


def notify_delivery_failure(failure, opener=None):
    url = ntfy_url()
    if not url:
        raise RuntimeError("ntfy_not_configured")
    body = "\n".join(
        [
            f"Mailbox delivery failed for {failure.filename}",
            f"Attempts: {failure.attempts}",
            f"Error: {failure.error_type}",
            "Automatic retry remains enabled.",
        ]
    )
    request = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Title": os.environ.get("FAX_NOTIFY_FAILURE_TITLE", "Fax mailbox delivery failed"),
            "Priority": "urgent",
            "Tags": "warning,fax,inbox",
        },
    )
    click_url = os.environ.get("FAX_NOTIFY_CLICK_URL", "").strip()
    if click_url:
        request.add_header("Click", click_url)
    token = os.environ.get("NTFY_TOKEN", "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    opener = opener or urllib.request.urlopen
    timeout = float(os.environ.get("NTFY_TIMEOUT_SECONDS", "10"))
    with opener(request, timeout=timeout) as response:
        response.read()


def scan_and_notify(*, opener=None):
    state_file = state_path()
    state = load_state(state_file)
    known = set(state.get("known", []))
    known_failures = set(state.get("knownFailures", []))
    events = scan_received_faxes()
    if not known and mark_existing_on_first_run():
        state["known"] = [event.key for event in events]
        known = set(state["known"])
        state["knownFailures"] = sorted(known_failures)
        save_state(state, state_file)
    sent = 0
    for event in events:
        if event.key in known:
            continue
        notify_ntfy(event, opener=opener)
        known.add(event.key)
        sent += 1
        state["known"] = sorted(known)
        state["knownFailures"] = sorted(known_failures)
        save_state(state, state_file)

    failures = scan_delivery_failures()
    for failure in failures:
        if failure.key in known_failures:
            continue
        notify_delivery_failure(failure, opener=opener)
        known_failures.add(failure.key)
        sent += 1
        state["known"] = sorted(known)
        state["knownFailures"] = sorted(known_failures)
        save_state(state, state_file)

    state["known"] = sorted(known)
    state["knownFailures"] = sorted(known_failures)
    save_state(state, state_file)
    update_status(
        last_error="",
        known_count=len(known),
        failure_count=len(failures),
        notified_delta=sent,
    )
    return sent


def update_status(*, last_error=None, known_count=None, failure_count=None, notified_delta=0):
    with STATE_LOCK:
        WORKER_STATE["lastScanAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if last_error is not None:
            WORKER_STATE["lastError"] = last_error
        if known_count is not None:
            WORKER_STATE["knownCount"] = known_count
        if failure_count is not None:
            WORKER_STATE["failureCount"] = failure_count
        if notified_delta:
            WORKER_STATE["lastNotifyAt"] = WORKER_STATE["lastScanAt"]
            WORKER_STATE["notifiedCount"] = int(WORKER_STATE["notifiedCount"]) + notified_delta


def status():
    with STATE_LOCK:
        worker = dict(WORKER_STATE)
    return {
        "ok": (not enabled()) or (bool(ntfy_url()) and int(worker["failureCount"]) == 0),
        "enabled": enabled(),
        "configured": bool(ntfy_url()),
        "recvq": str(recvq_root()),
        "xferfaxlog": str(xferfaxlog_path()),
        "statePath": str(state_path()),
        "deliveryFailureRoot": str(delivery_failure_root()),
        "minimumFileAgeSeconds": min_file_age_seconds(),
        **worker,
    }


def start_scheduler():
    global WORKER_THREAD
    if not enabled():
        return None
    if WORKER_THREAD and WORKER_THREAD.is_alive():
        return WORKER_THREAD

    def run():
        with STATE_LOCK:
            WORKER_STATE["started"] = True
        while True:
            try:
                scan_and_notify()
            except (OSError, RuntimeError, urllib.error.URLError, TimeoutError) as exc:
                update_status(last_error=type(exc).__name__)
                print(f"Fax notification worker failed: {type(exc).__name__}", flush=True)
            time.sleep(poll_seconds())

    WORKER_THREAD = threading.Thread(target=run, name="faxmail-notifier", daemon=True)
    WORKER_THREAD.start()
    return WORKER_THREAD

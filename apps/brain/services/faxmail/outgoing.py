import hashlib
import imaplib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr
from pathlib import Path

from services.mail.notifier import encode_modified_utf7, quoted_mailbox, selected_uidvalidity
from services.notifications import actions as notification_actions
from services.notifications import ntfy


STATE_LOCK = threading.Lock()
WORKER_THREAD = None
WORKER_STATE = {
    "started": False,
    "lastScanAt": "",
    "lastError": "",
    "lastAcceptedAt": "",
    "lastCompletedAt": "",
    "acceptedCount": 0,
    "rejectedCount": 0,
    "sentCount": 0,
    "failedCount": 0,
}
SUBJECT_PATTERN = re.compile(r"^\s*fax\s*:\s*([+0-9][0-9\s().-]*)\s*$", re.IGNORECASE)
DOMESTIC_NUMBER_PATTERN = re.compile(r"^0\d{8,10}$")
JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
HYLAFAX_REQUEST_PATTERN = re.compile(r"request id is\s+(\d+)", re.IGNORECASE)


class OutgoingFaxError(ValueError):
    pass


def ensure_shared_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o2770)
    except PermissionError:
        # The bind-mount root is provisioned by the host and may not be owned by Brain.
        pass
    return path


@dataclass(frozen=True)
class OutgoingRequest:
    destination: str
    sender: str
    subject: str
    message_id: str
    filename: str
    pdf: bytes
    pdf_sha256: str


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def enabled():
    return env_bool("FAX_OUTGOING_ENABLED")


def mode():
    value = os.environ.get("FAX_OUTGOING_MODE", "shadow").strip().lower()
    return value if value in {"shadow", "dry-run", "live"} else "shadow"


def queue_root():
    return Path(os.environ.get("FAX_OUTGOING_QUEUE_ROOT", "/data/fax-outgoing"))


def state_path():
    return Path(os.environ.get("FAX_OUTGOING_STATE_PATH", "/data/fax-outgoing/state.json"))


def doneq_root():
    return Path(os.environ.get("FAX_OUTGOING_DONEQ_ROOT", "/integrations/hylafax/doneq"))


def poll_seconds():
    return max(30, int(os.environ.get("FAX_OUTGOING_POLL_SECONDS", "60")))


def max_pdf_bytes():
    return max(1, int(os.environ.get("FAX_OUTGOING_MAX_PDF_MB", "20"))) * 1024 * 1024


def outgoing_aliases():
    return {
        item.strip().lower()
        for item in os.environ.get("FAX_OUTGOING_RECIPIENTS", "fax-send@kaosgdd.net").split(",")
        if item.strip()
    }


def allowed_senders():
    return {
        item.strip().lower()
        for item in os.environ.get("FAX_OUTGOING_ALLOWED_SENDERS", "").split(",")
        if item.strip()
    }


def imap_settings():
    return {
        "host": os.environ.get("FAX_OUTGOING_IMAP_HOST", os.environ.get("MAIL_NOTIFY_GMAIL_HOST", "imap.gmail.com")).strip(),
        "port": int(os.environ.get("FAX_OUTGOING_IMAP_PORT", os.environ.get("MAIL_NOTIFY_GMAIL_PORT", "993"))),
        "username": os.environ.get("FAX_OUTGOING_IMAP_USERNAME", os.environ.get("MAIL_NOTIFY_GMAIL_USERNAME", "")).strip(),
        "password": os.environ.get("FAX_OUTGOING_IMAP_PASSWORD", os.environ.get("MAIL_NOTIFY_GMAIL_PASSWORD", "")),
        "folder": os.environ.get("FAX_OUTGOING_IMAP_FOLDER", "INBOX").strip(),
    }


def configured():
    settings = imap_settings()
    return bool(settings["host"] and settings["username"] and settings["password"] and allowed_senders())


def normalize_destination(raw):
    value = str(raw or "").strip()
    compact = re.sub(r"[\s().-]+", "", value)
    if compact.startswith("+82"):
        compact = f"0{compact[3:]}"
    if not compact.isdigit() or not DOMESTIC_NUMBER_PATTERN.fullmatch(compact):
        raise OutgoingFaxError("invalid_domestic_fax_number")
    return compact


def message_addresses(message, names):
    values = []
    for name in names:
        values.extend(str(value) for value in message.get_all(name, []))
    return {address.lower() for _label, address in getaddresses(values) if address}


def sender_authenticated(message):
    if not env_bool("FAX_OUTGOING_REQUIRE_AUTH_RESULTS", True):
        return True
    results = " ".join(str(value) for value in message.get_all("Authentication-Results", [])).lower()
    return "dkim=pass" in results or "dmarc=pass" in results


def extract_pdf(message):
    attachments = [part for part in message.iter_attachments()]
    if len(attachments) != 1:
        raise OutgoingFaxError("exactly_one_pdf_required")
    attachment = attachments[0]
    filename = str(attachment.get_filename() or "fax.pdf").strip()
    content_type = attachment.get_content_type().lower()
    if content_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise OutgoingFaxError("pdf_attachment_required")
    payload = attachment.get_payload(decode=True) or b""
    if not payload.startswith(b"%PDF-"):
        raise OutgoingFaxError("invalid_pdf_signature")
    if not payload or len(payload) > max_pdf_bytes():
        raise OutgoingFaxError("pdf_size_invalid")
    return filename, payload


def parse_request(raw_message):
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    recipients = message_addresses(
        message,
        ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To", "X-Envelope-To"),
    )
    if not outgoing_aliases().intersection(recipients):
        return None
    sender = parseaddr(str(message.get("From", "")))[1].lower()
    if not sender or sender not in allowed_senders():
        raise OutgoingFaxError("sender_not_authorized")
    if not sender_authenticated(message):
        raise OutgoingFaxError("sender_authentication_failed")
    subject = str(message.get("Subject", "")).strip()
    match = SUBJECT_PATTERN.fullmatch(subject)
    if not match:
        raise OutgoingFaxError("subject_must_be_fax_colon_number")
    destination = normalize_destination(match.group(1))
    filename, pdf = extract_pdf(message)
    message_id = str(message.get("Message-ID", "")).strip()
    if not message_id:
        raise OutgoingFaxError("message_id_required")
    return OutgoingRequest(
        destination=destination,
        sender=sender,
        subject=subject,
        message_id=message_id,
        filename=filename,
        pdf=pdf,
        pdf_sha256=hashlib.sha256(pdf).hexdigest(),
    )


def request_job_id(request):
    value = "\0".join((request.message_id, request.destination, request.pdf_sha256)).encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:32]


def load_state(path=None):
    path = Path(path or state_path())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"jobs": {}}
    if not isinstance(payload, dict):
        return {"jobs": {}}
    payload["jobs"] = payload.get("jobs") if isinstance(payload.get("jobs"), dict) else {}
    return payload


def save_state(state, path=None):
    path = Path(path or state_path())
    ensure_shared_directory(path.parent)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o660)
    os.replace(tmp, path)


def atomic_bytes(path, value):
    ensure_shared_directory(path.parent)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_bytes(value)
    os.chmod(tmp, 0o660)
    os.replace(tmp, path)


def atomic_json(path, value):
    atomic_bytes(path, json.dumps(value, indent=2, sort_keys=True).encode("utf-8"))


def queue_request(request, *, root=None, now=None):
    root = Path(root or queue_root())
    job_id = request_job_id(request)
    job_dir = ensure_shared_directory(root / "jobs" / job_id)
    pdf_path = job_dir / "document.pdf"
    manifest_path = root / "pending" / f"{job_id}.json"
    if not pdf_path.exists():
        atomic_bytes(pdf_path, request.pdf)
    manifest = {
        "version": 1,
        "jobId": job_id,
        "destination": request.destination,
        "sender": request.sender,
        "messageId": request.message_id,
        "filename": request.filename,
        "pdfPath": f"jobs/{job_id}/document.pdf",
        "pdfSha256": request.pdf_sha256,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now)),
    }
    if not manifest_path.exists() and not (root / "processed" / manifest_path.name).exists():
        atomic_json(manifest_path, manifest)
    return manifest


def parse_doneq(path):
    values = {}
    current_key = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if current_key and raw_line.endswith("\\"):
            values[current_key] = f"{values[current_key]}\n{raw_line[:-1]}"
            continue
        current_key = None
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip().lower()] = value[:-1] if value.endswith("\\") else value.strip()
        if value.endswith("\\"):
            current_key = key.strip().lower()
    status = str(values.get("status") or "").strip()
    statuscode = str(values.get("statuscode") or "").strip()
    state = str(values.get("state") or "").strip()
    returned = str(values.get("returned") or "").strip()
    return {
        **values,
        "sent": statuscode == "0" or (state == "7" and returned == "2" and not status),
    }


def notification_for_stage(job, stage):
    click_url = os.environ.get("FAX_NOTIFY_CLICK_URL", "https://mail.kaosgdd.net/").strip()
    definitions = {
        "queued": ("normal", "Fax queued", "default", "fax,outbox_tray"),
        "sending": ("normal", "Fax sending", "high", "fax,telephone_receiver"),
        "sent": ("normal", "Fax sent", "default", "fax,white_check_mark"),
        "failed": ("system", "Fax failed", "urgent", "warning,fax"),
    }
    channel, title, priority, tags = definitions[stage]
    details = [f"To: {job.get('destination', 'unknown')}"]
    if job.get("hylafaxJobId"):
        details.append(f"Job: {job['hylafaxJobId']}")
    if stage == "failed":
        details.append(f"Reason: {job.get('error', 'transmission failed')}")
    notification = {
        "channel": channel,
        "title": title,
        "message": "\n".join(details),
        "priority": priority,
        "tags": tags,
        "click_url": click_url,
    }
    try:
        ntfy.publish(
            **notification,
            actions=notification_actions.action_header(notification),
            user_agent="KaosGDD-Brain-Outgoing-Fax/1.0",
        )
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def notify_stage_once(job, stage):
    notified = job.setdefault("notifiedStages", [])
    if stage in notified:
        return False
    if not notification_for_stage(job, stage):
        return False
    notified.append(stage)
    return True


def bridge_result(root, job_id):
    path = Path(root) / "results" / f"{job_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def reconcile_jobs(state, *, root=None, doneq=None, notify=True):
    root = Path(root or queue_root())
    doneq = Path(doneq or doneq_root())
    changed = False
    for job_id, job in state.get("jobs", {}).items():
        if job.get("status") in {"sent", "failed", "rejected", "shadow_valid", "shadow_rejected"}:
            continue
        result = bridge_result(root, job_id)
        if result and job.get("status") == "queued":
            result_status = str(result.get("status") or "")
            if result_status == "dry_run":
                job["status"] = "dry_run"
                job["bridgeResult"] = result
                changed = True
            elif result_status == "submitted" and str(result.get("hylafaxJobId") or "").isdigit():
                job["status"] = "submitted"
                job["hylafaxJobId"] = str(result["hylafaxJobId"])
                job["bridgeResult"] = result
                if notify:
                    notify_stage_once(job, "sending")
                changed = True
            elif result_status == "failed":
                job["status"] = "failed"
                job["error"] = str(result.get("error") or "submission_failed")
                job["completedAt"] = result.get("completedAt") or ""
                if notify:
                    notify_stage_once(job, "failed")
                changed = True
        hylafax_job_id = str(job.get("hylafaxJobId") or "")
        if job.get("status") != "submitted" or not hylafax_job_id:
            continue
        done_path = doneq / f"q{hylafax_job_id}"
        if not done_path.is_file():
            continue
        result = parse_doneq(done_path)
        success = bool(result.get("sent"))
        job["status"] = "sent" if success else "failed"
        job["error"] = "" if success else str(result.get("status") or "transmission_failed")
        job["doneq"] = result
        job["completedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(done_path.stat().st_mtime))
        if notify:
            notify_stage_once(job, "sent" if success else "failed")
        changed = True
    return changed


def fetch_raw_message(client, uid):
    status, rows = client.uid("fetch", str(uid), "(BODY.PEEK[])")
    if status != "OK":
        raise RuntimeError("imap_fetch_failed")
    return b"".join(
        row[1]
        for row in rows or []
        if isinstance(row, tuple) and len(row) > 1 and isinstance(row[1], bytes)
    )


def search_uids(client):
    status, rows = client.uid("search", None, "ALL")
    if status != "OK":
        raise RuntimeError("imap_search_failed")
    raw = b" ".join(row for row in (rows or []) if isinstance(row, bytes))
    return sorted(int(value) for value in raw.split() if value.isdigit())


def scan_mailbox(*, imap_factory=None):
    settings = imap_settings()
    state = load_state()
    imap_factory = imap_factory or imaplib.IMAP4_SSL
    client = imap_factory(settings["host"], settings["port"], timeout=20)
    accepted = 0
    rejected = 0
    try:
        status, _data = client.login(settings["username"], settings["password"])
        if status != "OK":
            raise RuntimeError("imap_login_failed")
        status, _data = client.select(quoted_mailbox(encode_modified_utf7(settings["folder"])), readonly=True)
        if status != "OK":
            raise RuntimeError("imap_select_failed")
        uidvalidity = selected_uidvalidity(client)
        uids = search_uids(client)
        if state.get("uidValidity") != uidvalidity:
            state["uidValidity"] = uidvalidity
            state["lastUid"] = max(uids, default=0) if env_bool("FAX_OUTGOING_MARK_EXISTING_ON_FIRST_RUN", True) else 0
            save_state(state)
            return 0, 0
        last_uid = int(state.get("lastUid") or 0)
        for uid in (value for value in uids if value > last_uid):
            raw_message = fetch_raw_message(client, uid)
            try:
                request = parse_request(raw_message)
                if request is None:
                    state["lastUid"] = uid
                    save_state(state)
                    continue
                job_id = request_job_id(request)
                if job_id in state["jobs"]:
                    state["lastUid"] = uid
                    save_state(state)
                    continue
                job = {
                    "jobId": job_id,
                    "destination": request.destination,
                    "sender": request.sender,
                    "messageId": request.message_id,
                    "filename": request.filename,
                    "pdfSha256": request.pdf_sha256,
                    "sourceUid": uid,
                    "status": "shadow_valid" if mode() == "shadow" else "queued",
                    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                if mode() != "shadow":
                    queue_request(request)
                state["jobs"][job_id] = job
                if mode() == "live":
                    notify_stage_once(job, "queued")
                accepted += 1
            except OutgoingFaxError as exc:
                key = hashlib.sha256(f"{uid}\0{uidvalidity}".encode("utf-8")).hexdigest()[:32]
                state["jobs"][key] = {
                    "jobId": key,
                    "sourceUid": uid,
                    "status": "shadow_rejected" if mode() == "shadow" else "rejected",
                    "error": str(exc),
                    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                rejected += 1
            state["lastUid"] = uid
            save_state(state)
        if reconcile_jobs(state):
            save_state(state)
    finally:
        try:
            client.close()
        except (imaplib.IMAP4.error, OSError):
            pass
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
    return accepted, rejected


def update_status(*, accepted=0, rejected=0, last_error=None):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with STATE_LOCK:
        WORKER_STATE["lastScanAt"] = timestamp
        if last_error is not None:
            WORKER_STATE["lastError"] = last_error
        if accepted:
            WORKER_STATE["lastAcceptedAt"] = timestamp
            WORKER_STATE["acceptedCount"] += accepted
        if rejected:
            WORKER_STATE["rejectedCount"] += rejected


def scan_and_process(*, imap_factory=None):
    try:
        accepted, rejected = scan_mailbox(imap_factory=imap_factory)
        update_status(accepted=accepted, rejected=rejected, last_error="")
        return accepted, rejected
    except (imaplib.IMAP4.error, OSError, RuntimeError, UnicodeError, ValueError) as exc:
        update_status(last_error=type(exc).__name__)
        print(f"Outgoing fax scan failed: {type(exc).__name__}", flush=True)
        return 0, 0


def status():
    settings = imap_settings()
    with STATE_LOCK:
        runtime = dict(WORKER_STATE)
    state = load_state()
    jobs = list(state.get("jobs", {}).values())
    counts = {}
    for job in jobs:
        value = str(job.get("status") or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return {
        "ok": (not enabled()) or (configured() and not runtime["lastError"]),
        "enabled": enabled(),
        "configured": configured(),
        "mode": mode(),
        "started": bool(runtime["started"]),
        "host": settings["host"],
        "folder": settings["folder"],
        "allowedSenderCount": len(allowed_senders()),
        "queueRoot": str(queue_root()),
        "statePath": str(state_path()),
        "lastScanAt": runtime["lastScanAt"],
        "lastError": runtime["lastError"],
        "acceptedCount": runtime["acceptedCount"],
        "rejectedCount": runtime["rejectedCount"],
        "jobCounts": counts,
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
            scan_and_process()
            time.sleep(poll_seconds())

    WORKER_THREAD = threading.Thread(target=run, name="outgoing-fax", daemon=True)
    WORKER_THREAD.start()
    return WORKER_THREAD

import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from services.notifications import router as notifications
from services.telegram import client as telegram


STATE_LOCK = threading.Lock()
STATE_FILE_LOCK = threading.Lock()
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


def delete_telegram_source_on_success():
    return env_bool("TELEGRAM_FAX_DELETE_SOURCE_ON_SUCCESS")


def configured():
    return bool(str(queue_root()) and str(state_path()) and str(doneq_root()))


def normalize_destination(raw):
    value = str(raw or "").strip()
    compact = re.sub(r"[\s().-]+", "", value)
    if compact.startswith("+82"):
        compact = f"0{compact[3:]}"
    if not compact.isdigit() or not DOMESTIC_NUMBER_PATTERN.fullmatch(compact):
        raise OutgoingFaxError("invalid_domestic_fax_number")
    return compact


def request_from_pdf(*, destination, sender, message_id, filename, pdf):
    destination = normalize_destination(destination)
    sender = str(sender or "").strip()
    message_id = str(message_id or "").strip()
    filename = Path(str(filename or "fax.pdf")).name.strip() or "fax.pdf"
    if not sender or not message_id:
        raise OutgoingFaxError("source_identity_required")
    if not filename.lower().endswith(".pdf"):
        raise OutgoingFaxError("pdf_attachment_required")
    if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-"):
        raise OutgoingFaxError("invalid_pdf_signature")
    if len(pdf) > max_pdf_bytes():
        raise OutgoingFaxError("pdf_size_invalid")
    return OutgoingRequest(
        destination=destination,
        sender=sender,
        subject=f"fax:{destination}",
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


def submit_request(request, *, source="telegram", source_metadata=None, now=None):
    with STATE_FILE_LOCK:
        state = load_state()
        job_id = request_job_id(request)
        if job_id in state["jobs"]:
            return state["jobs"][job_id], False
        timestamp = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() if now is None else now),
        )
        job = {
            "jobId": job_id,
            "destination": request.destination,
            "sender": request.sender,
            "messageId": request.message_id,
            "filename": request.filename,
            "pdfSha256": request.pdf_sha256,
            "source": source,
            "sourceMetadata": dict(source_metadata or {}),
            "status": "shadow_valid" if mode() == "shadow" else "queued",
            "createdAt": timestamp,
        }
        if mode() != "shadow":
            queue_request(request, now=now)
        state["jobs"][job_id] = job
        if mode() == "live":
            notify_stage_once(job, "queued")
        save_state(state)
        return job, True


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
    definitions = {
        "queued": ("normal", "Fax queued to send."),
        "sending": ("normal", ""),
        "sent": ("normal", "Fax successfully sent."),
        "failed": ("system", "Fax failed"),
    }
    channel, title = definitions[stage]
    destination = str(job.get("destination") or "unknown")
    filename = unicodedata.normalize("NFC", str(job.get("filename") or "fax.pdf"))
    if stage == "sending":
        title = f"Sending fax to {destination}."
        details = [f": {filename}"]
    elif stage == "sent":
        details = [f": to {destination}"]
    else:
        details = [f": to {destination}", f": {filename}"]
        if stage == "failed":
            details.append(f": {job.get('error', 'transmission failed')}")
    notification = {
        "channel": channel,
        "title": title,
        "message": "\n".join(details),
    }
    try:
        notifications.publish(
            **notification,
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


def telegram_source_message_ids(job):
    if str(job.get("source") or "") != "telegram":
        return []
    metadata = job.get("sourceMetadata")
    if not isinstance(metadata, dict):
        return []
    message_ids = set()
    for key in ("messageId", "commandMessageId", "instructionMessageId"):
        try:
            message_id = int(metadata.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if message_id > 0:
            message_ids.add(message_id)
    return sorted(message_ids)


def delete_telegram_source_messages(job, *, api_call=None, now=None):
    if not delete_telegram_source_on_success() or job.get("status") != "sent":
        return False
    message_ids = telegram_source_message_ids(job)
    if not message_ids:
        return False
    metadata = job.get("sourceMetadata") or {}
    chat_id = str(metadata.get("chatId") or "").strip()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    cleanup = job.setdefault("sourceMessageCleanup", {})
    deleted_ids = {
        int(value)
        for value in cleanup.get("deletedMessageIds", [])
        if str(value).isdigit() and int(value) > 0
    }
    pending_ids = [message_id for message_id in message_ids if message_id not in deleted_ids]
    if not pending_ids:
        return False

    cleanup["attemptCount"] = int(cleanup.get("attemptCount") or 0) + 1
    cleanup["lastAttemptAt"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(time.time() if now is None else now),
    )
    cleanup["status"] = "pending"
    cleanup["lastError"] = ""
    if not token or not chat_id:
        cleanup["status"] = "failed"
        cleanup["lastError"] = "telegram_cleanup_not_configured"
        return True

    call = api_call or telegram.call
    for message_id in pending_ids:
        try:
            call(
                token,
                "deleteMessage",
                {"chat_id": chat_id, "message_id": message_id},
            )
        except telegram.TelegramError as exc:
            cleanup["status"] = "failed"
            cleanup["lastError"] = str(exc)
            break
        deleted_ids.add(message_id)
        cleanup["deletedMessageIds"] = sorted(deleted_ids)

    if all(message_id in deleted_ids for message_id in message_ids):
        cleanup["status"] = "deleted"
        cleanup["completedAt"] = cleanup["lastAttemptAt"]
        cleanup["lastError"] = ""
    return True


def bridge_result(root, job_id):
    path = Path(root) / "results" / f"{job_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def reconcile_jobs(state, *, root=None, doneq=None, notify=True, telegram_api_call=None):
    root = Path(root or queue_root())
    doneq = Path(doneq or doneq_root())
    changed = False
    for job_id, job in state.get("jobs", {}).items():
        if job.get("status") == "sent":
            changed = delete_telegram_source_messages(
                job,
                api_call=telegram_api_call,
            ) or changed
            continue
        if job.get("status") in {"failed", "rejected", "shadow_valid", "shadow_rejected"}:
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
        if success:
            delete_telegram_source_messages(job, api_call=telegram_api_call)
        changed = True
    return changed


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


def scan_and_process():
    try:
        with STATE_FILE_LOCK:
            state = load_state()
            if reconcile_jobs(state):
                save_state(state)
        update_status(last_error="")
        return 0, 0
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        update_status(last_error=type(exc).__name__)
        print(f"Outgoing fax reconciliation failed: {type(exc).__name__}", flush=True)
        return 0, 0


def status():
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
        "intake": "telegram",
        "mode": mode(),
        "started": bool(runtime["started"]),
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

    WORKER_THREAD = threading.Thread(target=run, name="outgoing-fax-reconcile", daemon=True)
    WORKER_THREAD.start()
    return WORKER_THREAD

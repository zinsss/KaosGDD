"""Archive confirmed fax documents to one private Telegram chat."""

import json
import mimetypes
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from services.faxmail import notifier
from services.telegram import access as telegram_access


STATE_LOCK = threading.Lock()
WORKER_THREAD = None
WORKER_STATE = {
    "started": False,
    "lastScanAt": "",
    "lastArchiveAt": "",
    "lastError": "",
    "eligibleCount": 0,
    "archivedCount": 0,
}
FAX_FILENAME = re.compile(r"fax[0-9]+\.tif", re.IGNORECASE)
KST = ZoneInfo("Asia/Seoul")


class TelegramArchiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArchiveItem:
    key: str
    direction: str
    path: Path
    filename: str
    caption: str


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def enabled():
    return env_bool("FAX_TELEGRAM_ARCHIVE_ENABLED")


def configured():
    return bool(bot_token() and chat_id())


def bot_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def chat_id():
    return (
        os.environ.get("FAX_TELEGRAM_ARCHIVE_CHAT_ID", "").strip()
        or os.environ.get("TELEGRAM_SUPERGROUP_CHAT_ID", "").strip()
    )


def topic_id():
    return (
        os.environ.get("FAX_TELEGRAM_ARCHIVE_TOPIC_ID", "").strip()
        or os.environ.get("TELEGRAM_TOPIC_FAX_ID", "").strip()
    )


def api_base_url():
    return os.environ.get("TELEGRAM_API_BASE_URL", "https://api.telegram.org").strip().rstrip("/")


def state_path():
    return Path(os.environ.get("FAX_TELEGRAM_ARCHIVE_STATE_PATH", "/data/faxmail/telegram-archive.json"))


def incoming_recvq_root():
    return Path(
        os.environ.get(
            "FAX_TELEGRAM_ARCHIVE_RECVQ",
            os.environ.get("FAX_NOTIFY_RECVQ", "/integrations/hylafax/recvq"),
        )
    )


def incoming_xferfaxlog_path():
    return Path(
        os.environ.get(
            "FAX_TELEGRAM_ARCHIVE_XFERFAXLOG",
            os.environ.get("FAX_NOTIFY_XFERFAXLOG", "/integrations/hylafax/log/xferfaxlog"),
        )
    )


def incoming_minimum_age_seconds():
    return max(
        0,
        int(
            os.environ.get(
                "FAX_TELEGRAM_ARCHIVE_MIN_FILE_AGE_SECONDS",
                os.environ.get("FAX_NOTIFY_MIN_FILE_AGE_SECONDS", "60"),
            )
        ),
    )


def outgoing_state_path():
    return Path(
        os.environ.get(
            "FAX_TELEGRAM_ARCHIVE_OUTGOING_STATE_PATH",
            "/data/fax-outgoing/state.json",
        )
    )


def poll_seconds():
    return max(10, int(os.environ.get("FAX_TELEGRAM_ARCHIVE_POLL_SECONDS", "30")))


def max_document_bytes():
    configured_mb = max(1, int(os.environ.get("FAX_TELEGRAM_ARCHIVE_MAX_MB", "45")))
    return min(configured_mb, 50) * 1024 * 1024


def mark_existing_on_first_run():
    return env_bool("FAX_TELEGRAM_ARCHIVE_MARK_EXISTING_ON_FIRST_RUN", True)


def load_json(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_state(path=None):
    payload = load_json(path or state_path())
    archived = payload.get("archived") if isinstance(payload.get("archived"), dict) else {}
    try:
        update_offset = max(0, int(payload.get("updateOffset") or 0))
    except (TypeError, ValueError):
        update_offset = 0
    return {"archived": archived, "updateOffset": update_offset}


def save_state(state, path=None):
    path = Path(path or state_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def safe_relative_file(root, relative):
    root = Path(root).resolve()
    candidate = (root / str(relative)).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


def normalized_remote_number(value):
    raw = str(value or "").strip()
    digits = re.sub(r"\D+", "", raw)
    if digits.startswith("82") and len(digits) >= 10:
        digits = f"0{digits[2:]}"
    return digits or "unknown"


def received_datetime(value, path):
    raw = str(value or "").strip()
    for pattern in ("%m/%d/%y %H:%M", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(raw, pattern).replace(tzinfo=KST)
        except ValueError:
            continue
    return datetime.fromtimestamp(Path(path).stat().st_mtime, tz=KST)


def incoming_archive_filename(event):
    received = received_datetime(event.received_at, event.path)
    remote = normalized_remote_number(event.remote)
    return f"{received:%Y-%m-%d-%H:%M}_FROM_{remote}.pdf"


def sent_timestamp(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed.astimezone(KST).strftime("%Y-%m-%d %H:%M")


def scan_incoming(recvq=None, xferfaxlog=None):
    events = notifier.scan_received_faxes(
        recvq or incoming_recvq_root(),
        xferfaxlog or incoming_xferfaxlog_path(),
        minimum_age=incoming_minimum_age_seconds(),
    )
    items = []
    for event in events:
        path = Path(event.path)
        if not FAX_FILENAME.fullmatch(path.name):
            continue
        delivery_key = event.commid or path.stem
        items.append(
            ArchiveItem(
                key=f"received:{delivery_key}",
                direction="received",
                path=path,
                filename=incoming_archive_filename(event),
                caption="",
            )
        )
    return items


def scan_outgoing(path=None):
    path = Path(path or outgoing_state_path())
    payload = load_json(path)
    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), dict) else {}
    root = path.parent
    items = []
    for job_id, job in sorted(jobs.items()):
        if not isinstance(job, dict) or job.get("status") != "sent":
            continue
        document = safe_relative_file(root, f"jobs/{job_id}/document.pdf")
        if not document:
            continue
        destination = str(job.get("destination") or "unknown")
        filename = str(job.get("filename") or document.name)
        completed_at = sent_timestamp(job.get("completedAt"))
        caption = "\n".join(
            value
            for value in (
                "Sent fax.",
                f": to {destination}",
                f": {completed_at}" if completed_at else "",
            )
            if value
        )
        items.append(
            ArchiveItem(
                key=f"sent:{job_id}",
                direction="sent",
                path=document,
                filename=filename,
                caption=caption,
            )
        )
    return items


def multipart_body(fields, *, file_field, file_path, filename):
    boundary = f"----KaosGDD{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    safe_name = re.sub(r"[\x00-\x1f\x7f\"\\/]+", "-", Path(filename).name).strip(" .-") or "fax-document"
    encoded_name = urllib.parse.quote(safe_name, safe="")
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body.extend(f"--{boundary}\r\n".encode("ascii"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{safe_name}"; filename*=UTF-8\'\'{encoded_name}\r\n'
        ).encode("utf-8")
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("ascii"))
    body.extend(Path(file_path).read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("ascii"))
    return bytes(body), boundary


def convert_tiff_to_pdf(source, output):
    result = subprocess.run(
        ["tiff2pdf", "-o", str(output), str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        reason = (result.stderr or result.stdout or "").strip()
        raise TelegramArchiveError(reason or "tiff2pdf_failed")
    if not output.is_file() or output.stat().st_size <= 0:
        raise TelegramArchiveError("tiff2pdf_output_missing")


def send_document(item, *, opener=None, converter=None):
    if not configured():
        raise TelegramArchiveError("telegram_not_configured")
    temporary = None
    document_path = item.path
    try:
        if item.path.suffix.lower() in {".tif", ".tiff"}:
            temporary = tempfile.TemporaryDirectory(prefix="kaosgdd-telegram-fax-")
            document_path = Path(temporary.name) / item.filename
            (converter or convert_tiff_to_pdf)(item.path, document_path)
        size = document_path.stat().st_size
        if size <= 0 or size > max_document_bytes():
            raise TelegramArchiveError("telegram_document_size_invalid")
        fields = {
            "chat_id": chat_id(),
            "disable_notification": "true",
            "protect_content": "true" if env_bool("FAX_TELEGRAM_ARCHIVE_PROTECT_CONTENT") else "false",
        }
        if item.caption:
            fields["caption"] = item.caption[:1024]
        if topic_id():
            fields["message_thread_id"] = topic_id()
        body, boundary = multipart_body(
            fields,
            file_field="document",
            file_path=document_path,
            filename=item.filename,
        )
    finally:
        if temporary is not None:
            temporary.cleanup()
    request = urllib.request.Request(
        f"{api_base_url()}/bot{bot_token()}/sendDocument",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "KaosGDD-Brain-Telegram-Fax-Archive/1.0",
        },
        method="POST",
    )
    open_request = opener or urllib.request.urlopen
    try:
        response = open_request(request, timeout=30)
        raw = response.read()
    except urllib.error.HTTPError as exc:
        raise TelegramArchiveError(f"telegram_http_{exc.code}") from exc
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise TelegramArchiveError("telegram_request_failed") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelegramArchiveError("telegram_invalid_response") from exc
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise TelegramArchiveError("telegram_api_rejected")
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return {"messageId": result.get("message_id")}


def telegram_api(method, fields, *, opener=None):
    if not configured():
        raise TelegramArchiveError("telegram_not_configured")
    request = urllib.request.Request(
        f"{api_base_url()}/bot{bot_token()}/{method}",
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "KaosGDD-Brain-Telegram-Archive/1.0",
        },
        method="POST",
    )
    open_request = opener or urllib.request.urlopen
    try:
        response = open_request(request, timeout=30)
        raw = response.read()
    except urllib.error.HTTPError as exc:
        raise TelegramArchiveError(f"telegram_http_{exc.code}") from exc
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise TelegramArchiveError("telegram_request_failed") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelegramArchiveError("telegram_invalid_response") from exc
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise TelegramArchiveError("telegram_api_rejected")
    return payload.get("result")


def scan_and_archive(*, uploader=None):
    state_file = state_path()
    first_run = not state_file.is_file()
    state = load_state(state_file)
    archived = state["archived"]
    items = scan_incoming() + scan_outgoing()
    if first_run and mark_existing_on_first_run():
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for item in items:
            archived[item.key] = {"status": "baselined", "at": timestamp}
        save_state(state, state_file)
        update_status(last_error="", eligible_count=len(items))
        return 0

    upload = uploader or send_document
    uploaded = 0
    for item in items:
        if item.key in archived:
            continue
        result = upload(item) or {}
        archived[item.key] = {
            "status": "uploaded",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "direction": item.direction,
            "messageId": result.get("messageId"),
        }
        save_state(state, state_file)
        uploaded += 1
    update_status(last_error="", eligible_count=len(items), archived_delta=uploaded)
    return uploaded


def update_status(*, last_error=None, eligible_count=None, archived_delta=0):
    with STATE_LOCK:
        WORKER_STATE["lastScanAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if last_error is not None:
            WORKER_STATE["lastError"] = last_error
        if eligible_count is not None:
            WORKER_STATE["eligibleCount"] = eligible_count
        if archived_delta:
            WORKER_STATE["lastArchiveAt"] = WORKER_STATE["lastScanAt"]
            WORKER_STATE["archivedCount"] += archived_delta


def status():
    with STATE_LOCK:
        runtime = dict(WORKER_STATE)
    return {
        "ok": (not enabled()) or (configured() and not runtime["lastError"]),
        "enabled": enabled(),
        "configured": configured(),
        "groupOnly": True,
        "supergroupConfigured": bool(telegram_access.configured_supergroup_id()),
        "incomingSource": "hylafax-recvq",
        "incomingRecvq": str(incoming_recvq_root()),
        "incomingXferfaxlog": str(incoming_xferfaxlog_path()),
        "incomingMinimumFileAgeSeconds": incoming_minimum_age_seconds(),
        "outgoingStatePath": str(outgoing_state_path()),
        "statePath": str(state_path()),
        "maximumDocumentBytes": max_document_bytes(),
        **runtime,
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
                scan_and_archive()
            except (OSError, TelegramArchiveError, ValueError) as exc:
                update_status(last_error=type(exc).__name__)
                print(f"Telegram fax archive failed: {type(exc).__name__}", flush=True)
            time.sleep(poll_seconds())

    WORKER_THREAD = threading.Thread(target=run, name="telegram-fax-archive", daemon=True)
    WORKER_THREAD.start()
    return WORKER_THREAD

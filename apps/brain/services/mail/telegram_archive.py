"""Archive new Naver mail bodies and attachments to Telegram."""

import html
import imaplib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path

from services.mail import notifier
from services.telegram import client as telegram


STATE_LOCK = threading.Lock()
WORKER_THREAD = None
WORKER_STATE = {
    "started": False,
    "lastScanAt": "",
    "lastArchiveAt": "",
    "lastError": "",
    "archivedCount": 0,
    "mailboxCount": 0,
}


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class ArchiveMail:
    mailbox: str
    uid: int
    sender: str
    subject: str
    preview: str
    attachments: tuple[Attachment, ...]


class TextExtractor(HTMLParser):
    BLOCKS = {"address", "article", "blockquote", "br", "div", "h1", "h2", "h3", "h4", "li", "p", "pre", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(data)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def enabled():
    return env_bool("MAIL_TELEGRAM_ARCHIVE_ENABLED")


def bot_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def chat_id():
    return (
        os.environ.get("MAIL_TELEGRAM_ARCHIVE_CHAT_ID", "").strip()
        or os.environ.get("TELEGRAM_SUPERGROUP_CHAT_ID", "").strip()
        or os.environ.get("FAX_TELEGRAM_ARCHIVE_CHAT_ID", "").strip()
    )


def topic_id():
    return (
        os.environ.get("MAIL_TELEGRAM_ARCHIVE_TOPIC_ID", "").strip()
        or os.environ.get("TELEGRAM_TOPIC_MAIL_ID", "").strip()
    )


def configured():
    config = naver_config()
    return bool(config and config.configured and bot_token() and chat_id())


def state_path():
    return Path(os.environ.get("MAIL_TELEGRAM_ARCHIVE_STATE_PATH", "/data/mail/telegram-archive.json"))


def poll_seconds():
    return max(30, int(os.environ.get("MAIL_TELEGRAM_ARCHIVE_POLL_SECONDS", "60")))


def max_attachment_bytes():
    return max(1, int(os.environ.get("MAIL_TELEGRAM_ARCHIVE_MAX_ATTACHMENT_MB", "20"))) * 1024 * 1024


def preview_characters():
    return max(200, min(3000, int(os.environ.get("MAIL_TELEGRAM_ARCHIVE_PREVIEW_CHARS", "2200"))))


def mark_existing_on_first_run():
    return env_bool("MAIL_TELEGRAM_ARCHIVE_MARK_EXISTING_ON_FIRST_RUN", True)


def protect_content():
    return env_bool("MAIL_TELEGRAM_ARCHIVE_PROTECT_CONTENT")


def naver_config():
    return next((config for config in notifier.account_configs() if config.key == "naver"), None)


def load_state(path=None):
    try:
        payload = json.loads(Path(path or state_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"mailboxes": {}}
    mailboxes = payload.get("mailboxes") if isinstance(payload, dict) else None
    return {"mailboxes": mailboxes if isinstance(mailboxes, dict) else {}}


def save_state(state, path=None):
    path = Path(path or state_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def normalize_text(value):
    lines = []
    blank = False
    for raw_line in html.unescape(value).replace("\r", "").split("\n"):
        line = re.sub(r"[\t ]+", " ", raw_line).strip()
        if line:
            lines.append(line)
            blank = False
        elif lines and not blank:
            lines.append("")
            blank = True
    return "\n".join(lines).strip()


def html_to_text(value):
    parser = TextExtractor()
    parser.feed(value)
    parser.close()
    return normalize_text("".join(parser.parts))


def parse_message(raw, mailbox, uid):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    plain_parts = []
    html_parts = []
    attachments = []
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = str(part.get_filename() or "").strip()
        disposition = part.get_content_disposition()
        payload = part.get_payload(decode=True) or b""
        if filename or disposition == "attachment":
            attachments.append(
                Attachment(
                    filename=filename or "attachment",
                    content_type=part.get_content_type(),
                    content=payload,
                )
            )
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):
            content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if not isinstance(content, str):
            continue
        if part.get_content_type() == "text/plain":
            plain_parts.append(content)
        elif part.get_content_type() == "text/html":
            html_parts.append(content)
    body = normalize_text("\n\n".join(plain_parts))
    if not body and html_parts:
        body = html_to_text("\n".join(html_parts))
    return ArchiveMail(
        mailbox=mailbox,
        uid=uid,
        sender=str(message.get("from", "")).strip() or "Unknown sender",
        subject=str(message.get("subject", "")).strip() or "(No subject)",
        preview=body[:preview_characters()],
        attachments=tuple(attachments),
    )


def fetch_message(client, mailbox, uid):
    status, rows = client.uid("fetch", str(uid), "(BODY.PEEK[])")
    if status != "OK":
        raise RuntimeError("imap_fetch_message_failed")
    raw = b"".join(
        row[1]
        for row in rows or []
        if isinstance(row, tuple) and len(row) > 1 and isinstance(row[1], bytes)
    )
    if not raw:
        raise RuntimeError("imap_message_empty")
    return parse_message(raw, mailbox.display_name, uid)


def attachment_label(attachment):
    if not attachment.content:
        return f"{attachment.filename} (empty)"
    if len(attachment.content) > max_attachment_bytes():
        return f"{attachment.filename} (over size limit)"
    return attachment.filename


def format_summary(mail):
    sections = [
        f"Naver Mail >> {mail.mailbox}\nFrom: {mail.sender}",
        mail.subject,
    ]
    if mail.attachments:
        attachments = "\n".join(
            f"{index}. {attachment_label(item)}"
            for index, item in enumerate(mail.attachments, start=1)
        )
        sections.append(f"Attachments\n{attachments}")
    preview = "\n".join((mail.preview or "").splitlines()[:15]).strip()
    sections.append(preview or "(No preview text)")
    return "\n\n".join(sections)[:4096]


def send_summary(mail, *, opener=None):
    return telegram.send_message(
        bot_token(),
        chat_id(),
        format_summary(mail),
        thread_id=topic_id(),
        silent=True,
        protect_content=protect_content(),
        opener=opener,
    )


def send_attachment(attachment, *, opener=None):
    return telegram.send_document(
        bot_token(),
        chat_id(),
        attachment.filename,
        attachment.content,
        caption=f"Attachment: {attachment.filename}",
        content_type=attachment.content_type,
        thread_id=topic_id(),
        silent=True,
        protect_content=protect_content(),
        opener=opener,
    )


def archive_mail(mail, progress, *, summary_sender=None, attachment_sender=None, persist=None):
    summary_sender = summary_sender or send_summary
    attachment_sender = attachment_sender or send_attachment
    uploaded = set(progress.get("uploadedAttachments") or [])
    if not progress.get("summaryMessageId"):
        result = summary_sender(mail)
        progress["summaryMessageId"] = (result or {}).get("message_id") or (result or {}).get("messageId")
        if persist:
            persist()
    for index, attachment in enumerate(mail.attachments):
        key = f"{index}:{attachment.filename}:{len(attachment.content)}"
        if key in uploaded or not attachment.content or len(attachment.content) > max_attachment_bytes():
            continue
        attachment_sender(attachment)
        uploaded.add(key)
        progress["uploadedAttachments"] = sorted(uploaded)
        if persist:
            persist()


def poll_naver(
    state,
    *,
    imap_factory=None,
    summary_sender=None,
    attachment_sender=None,
    persist=None,
):
    config = naver_config()
    if not config or not config.configured:
        raise RuntimeError("naver_not_configured")
    imap_factory = imap_factory or imaplib.IMAP4_SSL
    timeout = float(os.environ.get("MAIL_NOTIFY_IMAP_TIMEOUT_SECONDS", "20"))
    client = imap_factory(config.host, config.port, timeout=timeout)
    archived = 0
    mailbox_count = 0
    try:
        status, _data = client.login(config.username, config.password)
        if status != "OK":
            raise RuntimeError("imap_login_failed")
        mailboxes = notifier.discover_mailboxes(client, config)
        mailbox_count = len(mailboxes)
        states = state.setdefault("mailboxes", {})
        for mailbox in mailboxes:
            status, _data = client.select(notifier.quoted_mailbox(mailbox.raw_name), readonly=True)
            if status != "OK":
                raise RuntimeError("imap_select_failed")
            uidvalidity = notifier.selected_uidvalidity(client)
            uids = notifier.search_uids(client)
            current = states.get(mailbox.raw_name)
            if not isinstance(current, dict) or current.get("uidValidity") != uidvalidity:
                states[mailbox.raw_name] = {
                    "displayName": mailbox.display_name,
                    "uidValidity": uidvalidity,
                    "lastUid": max(uids, default=0) if mark_existing_on_first_run() else 0,
                    "pending": {},
                }
                if persist:
                    persist()
                client.close()
                continue
            pending = current.setdefault("pending", {})
            last_uid = int(current.get("lastUid") or 0)
            for uid in (value for value in uids if value > last_uid):
                mail = fetch_message(client, mailbox, uid)
                progress = pending.setdefault(str(uid), {})
                archive_mail(
                    mail,
                    progress,
                    summary_sender=summary_sender,
                    attachment_sender=attachment_sender,
                    persist=persist,
                )
                current["lastUid"] = uid
                pending.pop(str(uid), None)
                archived += 1
                if persist:
                    persist()
            current["displayName"] = mailbox.display_name
            current["uidValidity"] = uidvalidity
            client.close()
    finally:
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
    return archived, mailbox_count


def scan_and_archive(*, imap_factory=None, summary_sender=None, attachment_sender=None):
    state = load_state()

    def persist():
        save_state(state)

    try:
        archived, mailbox_count = poll_naver(
            state,
            imap_factory=imap_factory,
            summary_sender=summary_sender,
            attachment_sender=attachment_sender,
            persist=persist,
        )
        save_state(state)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with STATE_LOCK:
            WORKER_STATE["lastScanAt"] = timestamp
            WORKER_STATE["lastError"] = ""
            WORKER_STATE["mailboxCount"] = mailbox_count
            WORKER_STATE["archivedCount"] += archived
            if archived:
                WORKER_STATE["lastArchiveAt"] = timestamp
        return archived
    except (imaplib.IMAP4.error, OSError, RuntimeError, UnicodeError, telegram.TelegramError) as exc:
        with STATE_LOCK:
            WORKER_STATE["lastScanAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            WORKER_STATE["lastError"] = type(exc).__name__
        print(f"Telegram mail archive scan failed: {type(exc).__name__}", flush=True)
        return 0


def status():
    with STATE_LOCK:
        worker = dict(WORKER_STATE)
    return {
        "ok": (not enabled()) or (configured() and not worker["lastError"]),
        "enabled": enabled(),
        "configured": configured(),
        "started": bool(worker["started"]),
        "statePath": str(state_path()),
        "pollSeconds": poll_seconds(),
        "maxAttachmentMb": max_attachment_bytes() // (1024 * 1024),
        **{key: worker[key] for key in ("lastScanAt", "lastArchiveAt", "lastError", "archivedCount", "mailboxCount")},
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
            scan_and_archive()
            time.sleep(poll_seconds())

    WORKER_THREAD = threading.Thread(target=run, name="telegram-mail-archive", daemon=True)
    WORKER_THREAD.start()
    return WORKER_THREAD

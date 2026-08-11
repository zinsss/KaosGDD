"""Scheduled Naver unread-mail organizer for the Telegram Mail topic."""

import imaplib
import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from models.database import connect
from services.mail import notifier
from services.mail import telegram_archive
from services.telegram import access
from services.telegram import client as telegram


KST = timezone(timedelta(hours=9), "KST")
INBOX = notifier.Mailbox(raw_name="INBOX", display_name="INBOX")
CALLBACK_PREFIX = "mail"
STATE_LOCK = threading.RLock()
WORKER_THREAD = None
WORKER_STATE = {
    "started": False,
    "lastCheckAt": "",
    "lastDigestAt": "",
    "lastError": "",
    "digestCount": 0,
}


class MailOrganizerError(RuntimeError):
    pass


@dataclass(frozen=True)
class UnreadMail:
    uid: int
    sender: str
    subject: str
    mailbox_raw: str
    mailbox_name: str
    uidvalidity: str
    received_epoch: float


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def enabled():
    return env_bool("MAIL_ORGANIZER_ENABLED")


def bot_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def topic_id():
    return os.environ.get("TELEGRAM_TOPIC_MAIL_ID", "").strip()


def allowed_user_ids():
    values = os.environ.get("MAIL_ORGANIZER_ALLOWED_USER_IDS", "")
    return {
        int(value.strip())
        for value in values.split(",")
        if value.strip().isdigit() and int(value.strip()) > 0
    }


def configured():
    config = telegram_archive.naver_config()
    return bool(
        (not enabled())
        or (
            config
            and config.configured
            and bot_token()
            and access.configured_supergroup_id()
            and topic_id()
            and allowed_user_ids()
        )
    )


def state_path():
    return Path(os.environ.get("MAIL_ORGANIZER_STATE_PATH", "/data/mail/telegram-organizer.json"))


def max_items():
    return max(5, min(50, int(os.environ.get("MAIL_ORGANIZER_MAX_ITEMS", "30"))))


def scheduler_poll_seconds():
    return max(30, int(os.environ.get("MAIL_ORGANIZER_SCHEDULER_POLL_SECONDS", "60")))


def trash_folder():
    return os.environ.get("MAIL_ORGANIZER_TRASH_FOLDER", "Deleted Messages").strip() or "Deleted Messages"


def load_state(path=None):
    try:
        payload = json.loads(Path(path or state_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "lastSentSlots": {}, "digests": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "lastSentSlots": {}, "digests": {}}
    slots = payload.get("lastSentSlots")
    digests = payload.get("digests")
    return {
        "version": 1,
        "lastSentSlots": slots if isinstance(slots, dict) else {},
        "digests": digests if isinstance(digests, dict) else {},
    }


def save_state(state, path=None):
    path = Path(path or state_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _time_value(value):
    return str(value)[:5]


def get_settings():
    with connect() as connection:
        row = connection.execute(
            """
            SELECT runs_per_day, first_time, second_time, updated_at
            FROM mail_organizer_settings
            WHERE id = 1
            """
        ).fetchone()
    if not row:
        raise RuntimeError("mail_organizer_settings_missing")
    return {
        "runsPerDay": int(row[0]),
        "firstTime": _time_value(row[1]),
        "secondTime": _time_value(row[2]),
        "updatedAt": row[3].isoformat() if row[3] else "",
    }


def validate_time(value, field):
    try:
        parsed = datetime.strptime(str(value or ""), "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"invalid_{field}") from exc
    if parsed.minute % 5:
        raise ValueError(f"invalid_{field}_step")
    return parsed


def update_settings(payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    try:
        runs = int(payload.get("runsPerDay"))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_runs_per_day") from exc
    if runs not in {1, 2}:
        raise ValueError("invalid_runs_per_day")
    first = validate_time(payload.get("firstTime"), "first_time")
    second = validate_time(payload.get("secondTime") or "17:00", "second_time")
    if runs == 2 and first >= second:
        raise ValueError("mail_organizer_times_out_of_order")
    with connect() as connection:
        row = connection.execute(
            """
            UPDATE mail_organizer_settings
            SET runs_per_day = %s,
                first_time = %s,
                second_time = %s,
                updated_at = now()
            WHERE id = 1
            RETURNING runs_per_day, first_time, second_time, updated_at
            """,
            (runs, first, second),
        ).fetchone()
    return {
        "runsPerDay": int(row[0]),
        "firstTime": _time_value(row[1]),
        "secondTime": _time_value(row[2]),
        "updatedAt": row[3].isoformat() if row[3] else "",
    }


def settings_payload():
    return {"ok": True, "enabled": enabled(), "configured": configured(), "settings": get_settings()}


@contextmanager
def naver_client(*, imap_factory=None):
    config = telegram_archive.naver_config()
    if not config or not config.configured:
        raise MailOrganizerError("naver_not_configured")
    factory = imap_factory or imaplib.IMAP4_SSL
    timeout = float(os.environ.get("MAIL_NOTIFY_IMAP_TIMEOUT_SECONDS", "20"))
    client = factory(config.host, config.port, timeout=timeout)
    try:
        status, _data = client.login(config.username, config.password)
        if status != "OK":
            raise MailOrganizerError("imap_login_failed")
        yield client
    finally:
        try:
            if hasattr(client, "unselect"):
                client.unselect()
        except (imaplib.IMAP4.error, OSError):
            pass
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


def select_mailbox(client, mailbox, *, readonly):
    status, _data = client.select(notifier.quoted_mailbox(mailbox.raw_name), readonly=readonly)
    if status != "OK":
        raise MailOrganizerError("imap_select_failed")
    return notifier.selected_uidvalidity(client)


def organizer_mailboxes(client):
    status, rows = client.list()
    if status != "OK":
        raise MailOrganizerError("imap_list_failed")
    excluded_flags = {rb"\bsent\b", rb"\bdrafts\b", rb"\btrash\b", rb"\bjunk\b"}
    excluded_names = {trash_folder().casefold()}
    mailboxes = []
    for row in rows or []:
        parsed = notifier.parse_list_line(row)
        if not parsed:
            continue
        _delimiter, mailbox = parsed
        flags = row.split(b")", 1)[0].lower()
        if b"\\noselect" in flags or any(re.search(pattern, flags) for pattern in excluded_flags):
            continue
        if mailbox.display_name.casefold() in excluded_names:
            continue
        mailboxes.append(mailbox)
    if not any(mailbox.raw_name.upper() == "INBOX" for mailbox in mailboxes):
        mailboxes.insert(0, INBOX)
    return mailboxes


def unread_uids(client):
    status, rows = client.uid("search", None, "UNSEEN")
    if status != "OK":
        raise MailOrganizerError("imap_search_unread_failed")
    raw = b" ".join(row for row in (rows or []) if isinstance(row, bytes))
    return sorted((int(value) for value in raw.split() if value.isdigit()), reverse=True)


def fetch_unread_header(client, mailbox, uid, uidvalidity):
    status, rows = client.uid(
        "fetch",
        str(uid),
        "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])",
    )
    if status != "OK":
        raise MailOrganizerError("imap_fetch_header_failed")
    raw = b"".join(
        row[1]
        for row in rows or []
        if isinstance(row, tuple) and len(row) > 1 and isinstance(row[1], bytes)
    )
    if not raw:
        raise MailOrganizerError("imap_message_missing")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    try:
        received_at = parsedate_to_datetime(str(message.get("date", "")))
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)
        received_epoch = received_at.timestamp()
    except (AttributeError, TypeError, ValueError, OverflowError):
        received_epoch = 0.0
    return UnreadMail(
        uid=uid,
        sender=str(message.get("from", "")).strip() or "Unknown sender",
        subject=" ".join(str(message.get("subject", "")).split()) or "(No subject)",
        mailbox_raw=mailbox.raw_name,
        mailbox_name=mailbox.display_name,
        uidvalidity=str(uidvalidity or ""),
        received_epoch=received_epoch,
    )


def list_unread(*, imap_factory=None):
    entries = []
    total = 0
    with naver_client(imap_factory=imap_factory) as client:
        for mailbox in organizer_mailboxes(client):
            uidvalidity = select_mailbox(client, mailbox, readonly=True)
            uids = unread_uids(client)
            total += len(uids)
            entries.extend(
                fetch_unread_header(client, mailbox, uid, uidvalidity)
                for uid in uids[: max_items()]
            )
    entries.sort(key=lambda entry: (entry.received_epoch, entry.uid), reverse=True)
    return entries[: max_items()], total


def _button_text(subject):
    subject = " ".join(str(subject or "").split()) or "(No subject)"
    return subject if len(subject) <= 52 else f"{subject[:49]}..."


def digest_keyboard(digest_id, digest):
    items = digest.get("items", {})
    ordered_ids = [item_id for item_id in digest.get("order", []) if item_id in items]
    ordered_ids.extend(item_id for item_id in items if item_id not in ordered_ids)
    rows = [
        [{"text": _button_text(items[item_id].get("subject")), "callback_data": f"mail:o:{digest_id}:{item_id}"}]
        for item_id in ordered_ids
    ]
    rows.append([{"text": "Menu", "callback_data": f"mail:m:{digest_id}"}])
    return {"inline_keyboard": rows}


def detail_keyboard(digest_id, item_id, *, imported=False):
    row = [{"text": "Mark Read", "callback_data": f"mail:r:{digest_id}:{item_id}"}]
    if not imported:
        row.append({"text": "Import", "callback_data": f"mail:i:{digest_id}:{item_id}"})
    row.append({"text": "Delete", "callback_data": f"mail:d:{digest_id}:{item_id}"})
    return {"inline_keyboard": [row]}


def menu_keyboard(digest_id):
    return {
        "inline_keyboard": [
            [
                {"text": "Mark Read All", "callback_data": f"mail:ra:{digest_id}"},
                {"text": "Delete All", "callback_data": f"mail:da:{digest_id}"},
            ],
            [{"text": "Close", "callback_data": f"mail:cl:{digest_id}"}],
        ]
    }


def _timestamp(now=None):
    return (now or datetime.now(KST)).astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def _send(text, reply_markup, *, reply_to_message_id=None, sender=None):
    sender = sender or telegram.send_message
    return sender(
        bot_token(),
        access.configured_supergroup_id(),
        text,
        thread_id=topic_id(),
        silent=True,
        reply_markup=reply_markup,
        reply_to_message_id=reply_to_message_id,
    )


def _prune_digests(state, now_epoch):
    cutoff = now_epoch - 14 * 86400
    for digest_id, digest in list(state.get("digests", {}).items()):
        if not isinstance(digest, dict) or float(digest.get("createdEpoch") or 0) < cutoff:
            state["digests"].pop(digest_id, None)


def send_digest(*, imap_factory=None, sender=None, now=None):
    if not enabled():
        raise MailOrganizerError("mail_organizer_disabled")
    if not configured():
        raise MailOrganizerError("mail_organizer_not_configured")
    now = now or datetime.now(KST)
    entries, total = list_unread(imap_factory=imap_factory)
    if not entries:
        return {"ok": True, "sent": False, "unreadCount": 0, "shownCount": 0}
    digest_id = secrets.token_hex(4)
    items = {}
    order = []
    for entry in entries:
        item_id = secrets.token_hex(4)
        order.append(item_id)
        items[item_id] = {
            "uid": entry.uid,
            "subject": entry.subject,
            "sender": entry.sender,
            "mailboxRaw": entry.mailbox_raw,
            "mailboxName": entry.mailbox_name,
            "uidValidity": entry.uidvalidity,
            "imported": False,
            "archiveProgress": {},
        }
    digest = {
        "createdAt": now.astimezone(KST).isoformat(timespec="seconds"),
        "createdEpoch": now.timestamp(),
        "totalUnread": total,
        "items": items,
        "order": order,
    }
    text = f"Naver Mail\nUpdated: {_timestamp(now)}"
    if total > len(entries):
        text += f"\n\nShowing {len(entries)} of {total} unread messages"
    result = _send(text, digest_keyboard(digest_id, digest), sender=sender)
    digest["messageId"] = int((result or {}).get("message_id") or 0)
    with STATE_LOCK:
        state = load_state()
        _prune_digests(state, now.timestamp())
        state["digests"][digest_id] = digest
        save_state(state)
        WORKER_STATE["lastDigestAt"] = now.astimezone(KST).isoformat(timespec="seconds")
        WORKER_STATE["digestCount"] += 1
    return {
        "ok": True,
        "sent": True,
        "digestId": digest_id,
        "unreadCount": total,
        "shownCount": len(entries),
    }


def callback_in_topic(callback):
    message = callback.get("message") if isinstance(callback, dict) else None
    return bool(
        isinstance(message, dict)
        and access.message_is_allowed(message)
        and str(message.get("message_thread_id") or "") == topic_id()
        and str(callback.get("data") or "").startswith(f"{CALLBACK_PREFIX}:")
    )


def _authorized(callback):
    sender = callback.get("from") if isinstance(callback.get("from"), dict) else {}
    try:
        return int(sender.get("id") or 0) in allowed_user_ids()
    except (TypeError, ValueError):
        return False


def _parse_callback(data):
    parts = str(data or "").split(":")
    if len(parts) not in {3, 4} or parts[0] != CALLBACK_PREFIX:
        raise MailOrganizerError("mail_action_invalid")
    action = parts[1]
    if action not in {"o", "r", "i", "d", "m", "ra", "da", "cd", "cda", "cl", "x"}:
        raise MailOrganizerError("mail_action_invalid")
    return action, parts[2], parts[3] if len(parts) == 4 else ""


def _digest_and_item(state, digest_id, item_id=""):
    digest = state.get("digests", {}).get(digest_id)
    if not isinstance(digest, dict):
        raise MailOrganizerError("mail_digest_expired")
    item = None
    if item_id:
        item = digest.get("items", {}).get(item_id)
        if not isinstance(item, dict):
            raise MailOrganizerError("mail_item_unavailable")
    return digest, item


def _item_mailbox(digest, item):
    return notifier.Mailbox(
        raw_name=str(item.get("mailboxRaw") or INBOX.raw_name),
        display_name=str(item.get("mailboxName") or INBOX.display_name),
    )


def _item_uidvalidity(digest, item):
    return str(item.get("uidValidity") or digest.get("uidValidity") or "")


def _fetch_live_mail(digest, item, *, imap_factory=None):
    mailbox = _item_mailbox(digest, item)
    with naver_client(imap_factory=imap_factory) as client:
        uidvalidity = select_mailbox(client, mailbox, readonly=True)
        if uidvalidity != _item_uidvalidity(digest, item):
            raise MailOrganizerError("mailbox_generation_changed")
        return telegram_archive.fetch_message(client, mailbox, int(item["uid"]))


def _mutate(digest, items, operation, *, imap_factory=None):
    if not items:
        return
    grouped = {}
    for item in items:
        mailbox = _item_mailbox(digest, item)
        key = (mailbox.raw_name, mailbox.display_name, _item_uidvalidity(digest, item))
        grouped.setdefault(key, []).append(int(item["uid"]))
    with naver_client(imap_factory=imap_factory) as client:
        for (raw_name, display_name, expected_uidvalidity), uids in grouped.items():
            mailbox = notifier.Mailbox(raw_name=raw_name, display_name=display_name)
            uidvalidity = select_mailbox(client, mailbox, readonly=False)
            if uidvalidity != expected_uidvalidity:
                raise MailOrganizerError("mailbox_generation_changed")
            sequence = ",".join(str(uid) for uid in uids)
            if operation == "read":
                status, _data = client.uid("store", sequence, "+FLAGS.SILENT", "(\\Seen)")
            elif operation == "delete":
                status, _data = client.uid("MOVE", sequence, notifier.quoted_mailbox(trash_folder()))
            else:
                raise MailOrganizerError("mail_action_invalid")
            if status != "OK":
                raise MailOrganizerError(f"imap_{operation}_failed")


def _edit_digest(digest_id, digest, *, markup_editor=None):
    message_id = int(digest.get("messageId") or 0)
    if message_id <= 0:
        return
    editor = markup_editor or telegram.edit_message_reply_markup
    editor(
        bot_token(),
        access.configured_supergroup_id(),
        message_id,
        digest_keyboard(digest_id, digest),
    )


def _delete_telegram_message(message_id, *, message_deleter=None):
    message_id = int(message_id or 0)
    if message_id <= 0:
        return
    (message_deleter or telegram.delete_message)(
        bot_token(), access.configured_supergroup_id(), message_id
    )


def _refresh_or_close_digest(digest_id, digest, *, markup_editor=None, message_deleter=None):
    if digest.get("items"):
        _edit_digest(digest_id, digest, markup_editor=markup_editor)
        return False
    _delete_telegram_message(digest.get("messageId"), message_deleter=message_deleter)
    digest["messageId"] = 0
    return True


def _detail_text(mail):
    attachments = ""
    if mail.attachments:
        attachments = "\n\nAttachments\n" + "\n".join(
            f"{index}. {telegram_archive.attachment_label(item)}"
            for index, item in enumerate(mail.attachments, start=1)
        )
    preview = "\n".join((mail.preview or "").splitlines()[:15]).strip() or "(No preview text)"
    return f"Naver Mail >> {mail.mailbox}\nFrom: {mail.sender}\n\n{mail.subject}{attachments}\n\n{preview}"[:4096]


def _confirmation_fresh(message):
    try:
        return 0 <= time.time() - int(message.get("date") or 0) <= 60
    except (TypeError, ValueError):
        return False


def process_callback(
    callback,
    *,
    imap_factory=None,
    sender=None,
    callback_answerer=None,
    markup_editor=None,
    message_deleter=None,
):
    if not callback_in_topic(callback):
        return "ignored"
    answerer = callback_answerer or telegram.answer_callback_query
    callback_id = str(callback.get("id") or "")
    if not _authorized(callback):
        answerer(bot_token(), callback_id, "Not authorized")
        return "unauthorized"
    action, digest_id, item_id = _parse_callback(callback.get("data"))
    message = callback["message"]
    with STATE_LOCK:
        state = load_state()
        digest, item = _digest_and_item(state, digest_id, item_id)
        if action == "o":
            mail = _fetch_live_mail(digest, item, imap_factory=imap_factory)
            _send(
                _detail_text(mail),
                detail_keyboard(digest_id, item_id, imported=bool(item.get("imported"))),
                reply_to_message_id=int(message.get("message_id") or 0),
                sender=sender,
            )
            answerer(bot_token(), callback_id)
            return "opened"
        if action == "m":
            _send(
                "Naver Mail Menu",
                menu_keyboard(digest_id),
                reply_to_message_id=int(message.get("message_id") or 0),
                sender=sender,
            )
            answerer(bot_token(), callback_id)
            return "menu"
        if action == "cl":
            digest_message_id = int(digest.get("messageId") or 0)
            _delete_telegram_message(digest_message_id, message_deleter=message_deleter)
            digest["messageId"] = 0
            save_state(state)
            if int(message.get("message_id") or 0) != digest_message_id:
                _delete_telegram_message(message.get("message_id"), message_deleter=message_deleter)
            answerer(bot_token(), callback_id, "Closed")
            return "closed"
        if action in {"d", "da"}:
            data = f"mail:cd:{digest_id}:{item_id}" if action == "d" else f"mail:cda:{digest_id}"
            label = "Delete this mail?" if action == "d" else "Delete all mail in this digest?"
            _send(
                label,
                {"inline_keyboard": [[
                    {"text": "Confirm Delete", "callback_data": data},
                    {"text": "Cancel", "callback_data": f"mail:x:{digest_id}"},
                ]]},
                reply_to_message_id=int(message.get("message_id") or 0),
                sender=sender,
            )
            _delete_telegram_message(message.get("message_id"), message_deleter=message_deleter)
            answerer(bot_token(), callback_id)
            return "confirmation"
        if action == "x":
            (message_deleter or telegram.delete_message)(
                bot_token(), access.configured_supergroup_id(), int(message.get("message_id") or 0)
            )
            answerer(bot_token(), callback_id, "Cancelled")
            return "cancelled"
        if action in {"cd", "cda"} and not _confirmation_fresh(message):
            answerer(bot_token(), callback_id, "Confirmation expired")
            (markup_editor or telegram.edit_message_reply_markup)(
                bot_token(), access.configured_supergroup_id(), int(message.get("message_id") or 0), {"inline_keyboard": []}
            )
            return "expired"
        if action == "i":
            if item.get("imported"):
                answerer(bot_token(), callback_id, "Already imported")
                return "imported"
            mail = _fetch_live_mail(digest, item, imap_factory=imap_factory)
            progress = item.setdefault("archiveProgress", {})
            telegram_archive.archive_mail(mail, progress, persist=lambda: save_state(state))
            item["imported"] = True
            digest.get("items", {}).pop(item_id, None)
            digest["order"] = [key for key in digest.get("order", []) if key != item_id]
            save_state(state)
            _refresh_or_close_digest(
                digest_id,
                digest,
                markup_editor=markup_editor,
                message_deleter=message_deleter,
            )
            save_state(state)
            _delete_telegram_message(message.get("message_id"), message_deleter=message_deleter)
            answerer(bot_token(), callback_id, "Imported")
            return "imported"
        items = digest.get("items", {})
        if action in {"r", "cd"}:
            operation = "read" if action == "r" else "delete"
            _mutate(digest, [item], operation, imap_factory=imap_factory)
            items.pop(item_id, None)
            digest["order"] = [key for key in digest.get("order", []) if key != item_id]
        elif action in {"ra", "cda"}:
            operation = "read" if action == "ra" else "delete"
            _mutate(digest, list(items.values()), operation, imap_factory=imap_factory)
            items.clear()
            digest["order"] = []
        save_state(state)
        _refresh_or_close_digest(
            digest_id,
            digest,
            markup_editor=markup_editor,
            message_deleter=message_deleter,
        )
        save_state(state)
        _delete_telegram_message(message.get("message_id"), message_deleter=message_deleter)
        answerer(bot_token(), callback_id, "Done")
        return operation


def schedule_slots(settings):
    values = [settings["firstTime"]]
    if int(settings["runsPerDay"]) == 2:
        values.append(settings["secondTime"])
    return values


def send_due_digest(*, now=None, settings_getter=None, digest_sender=None):
    if not enabled() or not configured():
        return None
    now = (now or datetime.now(KST)).astimezone(KST)
    settings = (settings_getter or get_settings)()
    slots = schedule_slots(settings)
    today = now.date().isoformat()
    current = now.strftime("%H:%M")
    due = [slot for slot in slots if slot <= current]
    if not due:
        return None
    with STATE_LOCK:
        state = load_state()
        if state["lastSentSlots"].get(due[-1]) == today:
            return None
    result = (digest_sender or send_digest)(now=now)
    with STATE_LOCK:
        state = load_state()
        for slot in due:
            state["lastSentSlots"][slot] = today
        save_state(state)
    return result


def send_now():
    result = send_digest()
    now = datetime.now(KST)
    settings = get_settings()
    with STATE_LOCK:
        state = load_state()
        for slot in schedule_slots(settings):
            if slot <= now.strftime("%H:%M"):
                state["lastSentSlots"][slot] = now.date().isoformat()
        save_state(state)
    return result


def scan_schedule_once():
    try:
        result = send_due_digest()
        with STATE_LOCK:
            WORKER_STATE["lastCheckAt"] = datetime.now(KST).isoformat(timespec="seconds")
            WORKER_STATE["lastError"] = ""
        return result
    except (imaplib.IMAP4.error, OSError, RuntimeError, ValueError, telegram.TelegramError) as exc:
        with STATE_LOCK:
            WORKER_STATE["lastCheckAt"] = datetime.now(KST).isoformat(timespec="seconds")
            WORKER_STATE["lastError"] = type(exc).__name__
        print(f"Telegram mail organizer failed: {type(exc).__name__}", flush=True)
        return None


def status():
    with STATE_LOCK:
        runtime = dict(WORKER_STATE)
    return {
        "ok": (not enabled()) or (configured() and not runtime["lastError"]),
        "enabled": enabled(),
        "configured": configured(),
        "started": bool(runtime["started"]),
        "statePath": str(state_path()),
        "maxItems": max_items(),
        **{key: runtime[key] for key in ("lastCheckAt", "lastDigestAt", "lastError", "digestCount")},
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
            scan_schedule_once()
            time.sleep(scheduler_poll_seconds())

    WORKER_THREAD = threading.Thread(target=run, name="telegram-mail-organizer", daemon=True)
    WORKER_THREAD.start()
    return WORKER_THREAD

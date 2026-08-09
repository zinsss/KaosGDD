import base64
import imaplib
import json
import os
import re
import threading
import time
import urllib.error
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path

from services.notifications import actions as notification_actions
from services.notifications import router as notifications


STATE_LOCK = threading.Lock()
WORKER_THREAD = None
WORKER_STATE = {
    "started": False,
    "lastScanAt": "",
    "lastNotifyAt": "",
    "notifiedCount": 0,
    "accounts": {
        "naver": {"lastError": "", "mailboxCount": 0},
        "gmailFax": {"lastError": "", "mailboxCount": 0},
    },
}
LIST_PATTERN = re.compile(
    rb"^\((?P<flags>.*?)\)\s+(?P<delimiter>NIL|\"(?:\\.|[^\"])*\")\s+(?P<name>.+)$"
)


@dataclass(frozen=True)
class AccountConfig:
    key: str
    label: str
    enabled: bool
    host: str
    port: int
    username: str
    password: str
    folder_root: str
    include_descendants: bool
    match_addresses: tuple[str, ...]

    @property
    def configured(self):
        return bool(self.host and self.username and self.password and self.folder_roots)

    @property
    def folder_roots(self):
        return tuple(
            value.strip()
            for value in self.folder_root.split(",")
            if value.strip()
        )


@dataclass(frozen=True)
class Mailbox:
    raw_name: str
    display_name: str


@dataclass(frozen=True)
class MailEvent:
    account_key: str
    account_label: str
    mailbox: str
    uid: int
    subject: str
    sender: str
    recipients: tuple[str, ...]
    message_id: str


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def account_configs():
    fax_addresses = tuple(
        address.strip().lower()
        for address in os.environ.get(
            "MAIL_NOTIFY_GMAIL_MATCH_ADDRESSES",
            "fax@kaosgdd.net,fax-in@kaosgdd.net,fax-send@kaosgdd.net,fax-failed@kaosgdd.net",
        ).split(",")
        if address.strip()
    )
    return (
        AccountConfig(
            key="naver",
            label="Naver",
            enabled=env_bool("MAIL_NOTIFY_NAVER_ENABLED"),
            host=os.environ.get("MAIL_NOTIFY_NAVER_HOST", "imap.naver.com").strip(),
            port=int(os.environ.get("MAIL_NOTIFY_NAVER_PORT", "993")),
            username=os.environ.get("MAIL_NOTIFY_NAVER_USERNAME", "").strip(),
            password=os.environ.get("MAIL_NOTIFY_NAVER_PASSWORD", ""),
            folder_root=os.environ.get(
                "MAIL_NOTIFY_NAVER_FOLDERS",
                os.environ.get("MAIL_NOTIFY_NAVER_FOLDER", "각종공문"),
            ).strip(),
            include_descendants=True,
            match_addresses=(),
        ),
        AccountConfig(
            key="gmailFax",
            label="Fax mail",
            enabled=env_bool("MAIL_NOTIFY_GMAIL_ENABLED"),
            host=os.environ.get("MAIL_NOTIFY_GMAIL_HOST", "imap.gmail.com").strip(),
            port=int(os.environ.get("MAIL_NOTIFY_GMAIL_PORT", "993")),
            username=os.environ.get("MAIL_NOTIFY_GMAIL_USERNAME", "").strip(),
            password=os.environ.get("MAIL_NOTIFY_GMAIL_PASSWORD", ""),
            folder_root=os.environ.get("MAIL_NOTIFY_GMAIL_FOLDER", "INBOX").strip(),
            include_descendants=False,
            match_addresses=fax_addresses,
        ),
    )


def enabled():
    return any(config.enabled for config in account_configs())


def state_path():
    return Path(os.environ.get("MAIL_NOTIFY_STATE_PATH", "/data/mail/notified-imap.json"))


def poll_seconds():
    return max(30, int(os.environ.get("MAIL_NOTIFY_POLL_SECONDS", "60")))


def load_state(path=None):
    path = Path(path or state_path())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"accounts": {}}
    accounts = payload.get("accounts") if isinstance(payload, dict) else None
    return {"accounts": accounts if isinstance(accounts, dict) else {}}


def save_state(state, path=None):
    path = Path(path or state_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def encode_modified_utf7(value):
    result = []
    buffered = []

    def flush():
        if not buffered:
            return
        encoded = base64.b64encode("".join(buffered).encode("utf-16be")).decode("ascii")
        result.append("&" + encoded.rstrip("=").replace("/", ",") + "-")
        buffered.clear()

    for character in value:
        codepoint = ord(character)
        if 0x20 <= codepoint <= 0x7E:
            flush()
            result.append("&-" if character == "&" else character)
        else:
            buffered.append(character)
    flush()
    return "".join(result)


def decode_modified_utf7(value):
    result = []
    index = 0
    while index < len(value):
        if value[index] != "&":
            next_ampersand = value.find("&", index)
            if next_ampersand < 0:
                next_ampersand = len(value)
            result.append(value[index:next_ampersand])
            index = next_ampersand
            continue
        end = value.find("-", index)
        if end < 0:
            result.append(value[index:])
            break
        encoded = value[index + 1 : end]
        if not encoded:
            result.append("&")
        else:
            encoded = encoded.replace(",", "/")
            encoded += "=" * ((4 - len(encoded) % 4) % 4)
            result.append(base64.b64decode(encoded).decode("utf-16be"))
        index = end + 1
    return "".join(result)


def unquote_imap(value):
    value = value.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace(r"\"", '"').replace(r"\\", "\\")
    return value


def parse_list_line(line):
    if not isinstance(line, bytes):
        line = str(line).encode("ascii", errors="replace")
    match = LIST_PATTERN.match(line)
    if not match:
        return None
    delimiter = unquote_imap(match.group("delimiter").decode("ascii", errors="replace"))
    if delimiter == "NIL":
        delimiter = ""
    raw_name = unquote_imap(match.group("name").decode("ascii", errors="replace"))
    return delimiter, Mailbox(raw_name=raw_name, display_name=decode_modified_utf7(raw_name))


def discover_mailboxes(client, config):
    if not config.include_descendants:
        return [
            Mailbox(encode_modified_utf7(folder), folder)
            for folder in config.folder_roots
        ]
    status, rows = client.list()
    if status != "OK":
        raise RuntimeError("imap_list_failed")
    mailboxes = []
    for row in rows or []:
        parsed = parse_list_line(row)
        if not parsed:
            continue
        delimiter, mailbox = parsed
        if any(
            mailbox.display_name == root
            or (delimiter and mailbox.display_name.startswith(f"{root}{delimiter}"))
            for root in config.folder_roots
        ):
            mailboxes.append(mailbox)
    return sorted(mailboxes, key=lambda mailbox: mailbox.display_name)


def quoted_mailbox(raw_name):
    return '"' + raw_name.replace("\\", "\\\\").replace('"', r'\"') + '"'


def selected_uidvalidity(client):
    _code, values = client.response("UIDVALIDITY")
    if not values:
        return ""
    value = values[-1]
    if isinstance(value, bytes):
        value = value.decode("ascii", errors="replace")
    return str(value).strip()


def search_uids(client):
    status, rows = client.uid("search", None, "ALL")
    if status != "OK":
        raise RuntimeError("imap_search_failed")
    raw = b" ".join(row for row in (rows or []) if isinstance(row, bytes))
    return sorted(int(value) for value in raw.split() if value.isdigit())


def fetch_event(client, config, mailbox, uid):
    status, rows = client.uid(
        "fetch",
        str(uid),
        "(BODY.PEEK[HEADER.FIELDS (FROM TO CC REPLY-TO SUBJECT DATE MESSAGE-ID)])",
    )
    if status != "OK":
        raise RuntimeError("imap_fetch_failed")
    header = b"".join(
        row[1]
        for row in rows or []
        if isinstance(row, tuple) and len(row) > 1 and isinstance(row[1], bytes)
    )
    message = BytesParser(policy=policy.default).parsebytes(header)
    address_headers = [str(message.get(name, "")) for name in ("from", "to", "cc", "reply-to")]
    addresses = tuple(address.lower() for _name, address in getaddresses(address_headers) if address)
    sender = str(message.get("from", "")).strip() or "Unknown sender"
    return MailEvent(
        account_key=config.key,
        account_label=config.label,
        mailbox=mailbox.display_name,
        uid=uid,
        subject=str(message.get("subject", "")).strip() or "(No subject)",
        sender=sender,
        recipients=addresses,
        message_id=str(message.get("message-id", "")).strip(),
    )


def event_matches(config, event):
    if not config.match_addresses:
        return True
    return bool(set(config.match_addresses).intersection(event.recipients))


def notify_event(event, opener=None):
    click_url = os.environ.get("MAIL_NOTIFY_CLICK_URL", "https://mail.kaosgdd.net/").strip()
    notification = {
        "channel": "normal",
        "title": f"New mail · {event.account_label}",
        "message": "\n".join(
            [
                event.subject,
                f"From: {event.sender}",
                f"Folder: {event.mailbox}",
            ]
        ),
        "priority": "default",
        "tags": "email,inbox",
        "click_url": click_url,
    }
    notifications.publish(
        **notification,
        actions=notification_actions.action_header(notification),
        user_agent="KaosGDD-Brain-Mail/1.0",
        opener=opener,
    )


def poll_account(config, account_state, *, imap_factory=None, opener=None):
    imap_factory = imap_factory or imaplib.IMAP4_SSL
    timeout = float(os.environ.get("MAIL_NOTIFY_IMAP_TIMEOUT_SECONDS", "20"))
    client = imap_factory(config.host, config.port, timeout=timeout)
    sent = 0
    mailbox_count = 0
    try:
        status, _data = client.login(config.username, config.password)
        if status != "OK":
            raise RuntimeError("imap_login_failed")
        mailboxes = discover_mailboxes(client, config)
        mailbox_count = len(mailboxes)
        mailbox_states = account_state.setdefault("mailboxes", {})
        for mailbox in mailboxes:
            status, _data = client.select(quoted_mailbox(mailbox.raw_name), readonly=True)
            if status != "OK":
                raise RuntimeError("imap_select_failed")
            uidvalidity = selected_uidvalidity(client)
            uids = search_uids(client)
            current = mailbox_states.get(mailbox.raw_name)
            if not isinstance(current, dict) or current.get("uidValidity") != uidvalidity:
                mailbox_states[mailbox.raw_name] = {
                    "displayName": mailbox.display_name,
                    "uidValidity": uidvalidity,
                    "lastUid": max(uids, default=0),
                }
                client.close()
                continue

            last_uid = int(current.get("lastUid") or 0)
            for uid in (value for value in uids if value > last_uid):
                event = fetch_event(client, config, mailbox, uid)
                if event_matches(config, event):
                    notify_event(event, opener=opener)
                    sent += 1
                current["lastUid"] = uid
            current["displayName"] = mailbox.display_name
            current["uidValidity"] = uidvalidity
            client.close()
    finally:
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
    return sent, mailbox_count


def update_account_status(key, *, last_error=None, mailbox_count=None, notified_delta=0):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with STATE_LOCK:
        WORKER_STATE["lastScanAt"] = timestamp
        account = WORKER_STATE["accounts"].setdefault(key, {})
        if last_error is not None:
            account["lastError"] = last_error
        if mailbox_count is not None:
            account["mailboxCount"] = mailbox_count
        if notified_delta:
            WORKER_STATE["lastNotifyAt"] = timestamp
            WORKER_STATE["notifiedCount"] += notified_delta


def scan_and_notify(*, imap_factories=None, opener=None):
    state = load_state()
    accounts = state.setdefault("accounts", {})
    sent = 0
    for config in account_configs():
        if not config.enabled:
            continue
        if not config.configured:
            update_account_status(config.key, last_error="not_configured", mailbox_count=0)
            continue
        account_state = accounts.setdefault(config.key, {})
        factory = (imap_factories or {}).get(config.key)
        try:
            account_sent, mailbox_count = poll_account(
                config,
                account_state,
                imap_factory=factory,
                opener=opener,
            )
            save_state(state)
            sent += account_sent
            update_account_status(
                config.key,
                last_error="",
                mailbox_count=mailbox_count,
                notified_delta=account_sent,
            )
        except (imaplib.IMAP4.error, OSError, RuntimeError, UnicodeError, urllib.error.URLError) as exc:
            update_account_status(config.key, last_error=type(exc).__name__)
            print(f"Mail notification scan failed for {config.key}: {type(exc).__name__}", flush=True)
    return sent


def status():
    configs = {config.key: config for config in account_configs()}
    with STATE_LOCK:
        worker = {
            **WORKER_STATE,
            "accounts": {key: dict(value) for key, value in WORKER_STATE["accounts"].items()},
        }
    accounts = {}
    for key, config in configs.items():
        runtime = worker["accounts"].get(key, {})
        accounts[key] = {
            "enabled": config.enabled,
            "configured": config.configured,
            "host": config.host,
            "folder": config.folder_root,
            "folders": list(config.folder_roots),
            "includeDescendants": config.include_descendants,
            "mailboxCount": int(runtime.get("mailboxCount") or 0),
            "lastError": str(runtime.get("lastError") or ""),
        }
    healthy = all(
        (not details["enabled"])
        or (details["configured"] and not details["lastError"])
        for details in accounts.values()
    )
    return {
        "ok": healthy,
        "enabled": any(details["enabled"] for details in accounts.values()),
        "configured": all(
            (not details["enabled"]) or details["configured"]
            for details in accounts.values()
        ),
        "started": bool(worker["started"]),
        "statePath": str(state_path()),
        "pollSeconds": poll_seconds(),
        "lastScanAt": worker["lastScanAt"],
        "lastNotifyAt": worker["lastNotifyAt"],
        "notifiedCount": int(worker["notifiedCount"]),
        "accounts": accounts,
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
            scan_and_notify()
            time.sleep(poll_seconds())

    WORKER_THREAD = threading.Thread(target=run, name="mail-notifier", daemon=True)
    WORKER_THREAD.start()
    return WORKER_THREAD

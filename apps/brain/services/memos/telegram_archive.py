"""Archive the personal Memos account into the Telegram Memos topic."""

import hashlib
import json
import os
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from services.memos import relay
from services.telegram import client as telegram


STATE_LOCK = threading.Lock()
WORKER_THREAD = None
WORKER_STATE = {
    "started": False,
    "lastScanAt": "",
    "lastArchiveAt": "",
    "lastError": "",
    "createdCount": 0,
    "updatedCount": 0,
    "deletedCount": 0,
    "memoCount": 0,
}
KST = ZoneInfo("Asia/Seoul")
MESSAGE_LIMIT = 3900


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def enabled():
    return env_bool("MEMOS_TELEGRAM_ARCHIVE_ENABLED")


def bot_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def chat_id():
    return os.environ.get("TELEGRAM_SUPERGROUP_CHAT_ID", "").strip()


def topic_id():
    return os.environ.get("TELEGRAM_TOPIC_MEMOS_ID", "").strip()


def configured():
    try:
        relay.load_token("personal")
    except Exception:
        return False
    return bool(bot_token() and chat_id() and topic_id() and personal_creator())


def personal_creator():
    username = os.environ.get("MEMOS_PERSONAL_USERNAME", "").strip()
    return f"users/{username}" if username else ""


def state_path():
    return Path(
        os.environ.get(
            "MEMOS_TELEGRAM_ARCHIVE_STATE_PATH",
            "/data/memos/telegram-archive.json",
        )
    )


def poll_seconds():
    return max(30, int(os.environ.get("MEMOS_TELEGRAM_ARCHIVE_POLL_SECONDS", "60")))


def protect_content():
    return env_bool("MEMOS_TELEGRAM_ARCHIVE_PROTECT_CONTENT")


def load_state(path=None):
    try:
        payload = json.loads(Path(path or state_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"memos": {}}
    memos = payload.get("memos") if isinstance(payload, dict) else None
    return {"memos": memos if isinstance(memos, dict) else {}}


def save_state(state, path=None):
    path = Path(path or state_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _json_response(status, body):
    if status != 200:
        raise RuntimeError(f"memos_list_http_{status}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("memos_list_invalid") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("memos", []), list):
        raise RuntimeError("memos_list_invalid")
    return payload


def list_personal_memos(*, requester=None):
    requester = requester or relay.upstream_request
    token = relay.load_token("personal")
    creator = personal_creator()
    page_token = ""
    result = []
    while True:
        query = {
            "pageSize": "100",
            "orderBy": "create_time asc",
            "filter": f'creator == "{creator}"',
        }
        if page_token:
            query["pageToken"] = page_token
        path = f"/api/v1/memos?{urllib.parse.urlencode(query)}"
        status, _content_type, body = requester("GET", path, access_token=token)
        payload = _json_response(status, body)
        for memo in payload.get("memos", []):
            if (
                isinstance(memo, dict)
                and memo.get("creator") == creator
                and memo.get("state") == "NORMAL"
                and memo.get("name")
            ):
                result.append(memo)
        next_token = str(payload.get("nextPageToken") or "")
        if not next_token:
            break
        if next_token == page_token:
            raise RuntimeError("memos_page_token_repeated")
        page_token = next_token
    return result


def local_time(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return str(value or "")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST).strftime("%Y-%m-%d %H:%M")


def attachment_names(memo):
    names = []
    for item in memo.get("attachments") or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("filename") or item.get("name") or "").strip()
        if value:
            names.append(Path(value).name)
    return names


def format_memo(memo, *, deleted_at=""):
    content = str(memo.get("content") or "").strip()
    sections = [content or "(Empty memo)"]
    names = attachment_names(memo)
    if names:
        sections.append("Attachments\n" + "\n".join(f"- {name}" for name in names))
    timestamps = [f"Created: {local_time(memo.get('createTime'))}"]
    if memo.get("updateTime") and memo.get("updateTime") != memo.get("createTime"):
        timestamps.append(f"Updated: {local_time(memo.get('updateTime'))}")
    sections.append("\n".join(timestamps))
    if deleted_at:
        sections.append(f"Deleted from Memos: {deleted_at}")
    return "\n\n".join(sections).strip()


def split_text(value, limit=MESSAGE_LIMIT):
    value = str(value or "")
    if len(value) <= limit:
        return [value]
    chunks = []
    remaining = value
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit + 1)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n ")
    total = len(chunks)
    if total > 1:
        return [f"Memo {index}/{total}\n\n{chunk}" for index, chunk in enumerate(chunks, 1)]
    return chunks


def content_hash(memo):
    normalized = {
        "content": memo.get("content") or "",
        "createTime": memo.get("createTime") or "",
        "updateTime": memo.get("updateTime") or "",
        "attachments": attachment_names(memo),
    }
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def send_chunk(text, *, sender=None):
    sender = sender or telegram.send_message
    return sender(
        bot_token(),
        chat_id(),
        text,
        thread_id=topic_id(),
        silent=True,
        protect_content=protect_content(),
    )


def edit_chunk(message_id, text, *, editor=None):
    editor = editor or telegram.edit_message_text
    return editor(bot_token(), chat_id(), message_id, text)


def delete_chunk(message_id, *, deleter=None):
    deleter = deleter or telegram.delete_message
    return deleter(bot_token(), chat_id(), message_id)


def _message_id(result):
    value = (result or {}).get("message_id") or (result or {}).get("messageId")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise telegram.TelegramError("telegram_message_id_missing")


def replace_messages(
    text,
    message_ids,
    *,
    sender=None,
    editor=None,
    deleter=None,
    persist_ids=None,
):
    chunks = split_text(text)
    current = [int(value) for value in message_ids or [] if int(value) > 0]
    retained = []
    for index, chunk in enumerate(chunks):
        if index < len(current):
            edit_chunk(current[index], chunk, editor=editor)
            retained.append(current[index])
        else:
            retained.append(_message_id(send_chunk(chunk, sender=sender)))
            if persist_ids:
                persist_ids(retained)
    for message_id in current[len(chunks):]:
        delete_chunk(message_id, deleter=deleter)
    return retained


def archive_memo(memo, record, *, sender=None, editor=None, deleter=None, persist=None):
    digest = content_hash(memo)
    if record.get("contentHash") == digest and not record.get("deleted"):
        return "unchanged"
    had_messages = bool(record.get("messageIds"))

    def persist_ids(message_ids):
        record["messageIds"] = list(message_ids)
        if persist:
            persist()

    message_ids = replace_messages(
        format_memo(memo),
        record.get("messageIds") or [],
        sender=sender,
        editor=editor,
        deleter=deleter,
        persist_ids=persist_ids,
    )
    deletion_message_id = record.pop("deletionMessageId", None)
    if deletion_message_id:
        delete_chunk(deletion_message_id, deleter=deleter)
        record.pop("deletedAt", None)
    action = "updated" if had_messages else "created"
    record.update(
        {
            "messageIds": message_ids,
            "contentHash": digest,
            "updateTime": str(memo.get("updateTime") or ""),
            "deleted": False,
        }
    )
    if persist:
        persist()
    return action


def mark_deleted(name, record, *, sender=None, persist=None):
    if record.get("deleted"):
        return False
    deleted_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    marker = f"Memo deleted from Memos.\n{name}\nDeleted: {deleted_at}"
    result = send_chunk(marker, sender=sender)
    record["deletionMessageId"] = _message_id(result)
    record["deleted"] = True
    record["deletedAt"] = deleted_at
    if persist:
        persist()
    return True


def scan_once(*, requester=None, sender=None, editor=None, deleter=None):
    state = load_state()

    def persist():
        save_state(state)

    memos = list_personal_memos(requester=requester)
    records = state.setdefault("memos", {})
    seen = set()
    created = updated = deleted = 0
    for memo in memos:
        name = str(memo["name"])
        seen.add(name)
        record = records.setdefault(name, {})
        action = archive_memo(
            memo,
            record,
            sender=sender,
            editor=editor,
            deleter=deleter,
            persist=persist,
        )
        created += int(action == "created")
        updated += int(action == "updated")
    for name, record in records.items():
        if name not in seen and not record.get("deleted"):
            deleted += int(mark_deleted(name, record, sender=sender, persist=persist))
    save_state(state)
    return created, updated, deleted, len(memos)


def scan_and_archive():
    try:
        created, updated, deleted, memo_count = scan_once()
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with STATE_LOCK:
            WORKER_STATE["lastScanAt"] = timestamp
            WORKER_STATE["lastError"] = ""
            WORKER_STATE["createdCount"] += created
            WORKER_STATE["updatedCount"] += updated
            WORKER_STATE["deletedCount"] += deleted
            WORKER_STATE["memoCount"] = memo_count
            if created or updated or deleted:
                WORKER_STATE["lastArchiveAt"] = timestamp
        return created, updated, deleted
    except (OSError, RuntimeError, ValueError, relay.MemosRelayError, telegram.TelegramError) as exc:
        with STATE_LOCK:
            WORKER_STATE["lastScanAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            WORKER_STATE["lastError"] = type(exc).__name__
        print(f"Telegram Memos archive scan failed: {type(exc).__name__}", flush=True)
        return 0, 0, 0


def status():
    with STATE_LOCK:
        worker = dict(WORKER_STATE)
    return {
        "ok": (not enabled()) or (configured() and not worker["lastError"]),
        "enabled": enabled(),
        "configured": configured(),
        "started": bool(worker["started"]),
        "profile": "personal",
        "topic": "Memos",
        "statePath": str(state_path()),
        "pollSeconds": poll_seconds(),
        **{key: worker[key] for key in (
            "lastScanAt",
            "lastArchiveAt",
            "lastError",
            "createdCount",
            "updatedCount",
            "deletedCount",
            "memoCount",
        )},
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

    WORKER_THREAD = threading.Thread(target=run, name="telegram-memos-archive", daemon=True)
    WORKER_THREAD.start()
    return WORKER_THREAD

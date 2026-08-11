"""Receive outgoing fax requests directly from the Telegram Fax topic."""

import json
import os
import re
import threading
import time
from pathlib import Path

from services.documents import telegram_intake as document_intake
from services.faxmail import outgoing
from services.mail import telegram_organizer as mail_organizer
from services.telegram import access
from services.telegram import client as telegram


STATE_LOCK = threading.Lock()
WORKER_THREAD = None
WORKER_STATE = {
    "started": False,
    "lastPollAt": "",
    "lastAcceptedAt": "",
    "lastError": "",
    "acceptedCount": 0,
    "rejectedCount": 0,
    "protectedDeletedCount": 0,
    "protectedDeleteFailedCount": 0,
}


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def enabled():
    return (
        env_bool("TELEGRAM_FAX_INTAKE_ENABLED")
        or memos_topic_read_only()
        or document_intake.enabled()
        or mail_organizer.enabled()
    )


def fax_intake_enabled():
    return env_bool("TELEGRAM_FAX_INTAKE_ENABLED")


def memos_topic_read_only():
    return env_bool("TELEGRAM_MEMOS_TOPIC_READ_ONLY")


def bot_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def topic_id():
    return os.environ.get("TELEGRAM_TOPIC_FAX_ID", "").strip()


def memos_topic_id():
    return os.environ.get("TELEGRAM_TOPIC_MEMOS_ID", "").strip()


def configured():
    base = bool(bot_token() and access.configured_supergroup_id())
    fax_ready = (not fax_intake_enabled()) or bool(topic_id() and outgoing.configured())
    memos_ready = (not memos_topic_read_only()) or bool(memos_topic_id())
    return (
        base
        and fax_ready
        and memos_ready
        and document_intake.configured()
        and mail_organizer.configured()
    )


def state_path():
    return Path(
        os.environ.get(
            "TELEGRAM_FAX_INTAKE_STATE_PATH",
            "/data/fax-outgoing/telegram-intake.json",
        )
    )


def poll_seconds():
    return max(5, min(25, int(os.environ.get("TELEGRAM_FAX_INTAKE_POLL_SECONDS", "20"))))


def mark_existing_on_first_run():
    return env_bool("TELEGRAM_FAX_INTAKE_MARK_EXISTING_ON_FIRST_RUN", True)


def load_state(path=None):
    try:
        payload = json.loads(Path(path or state_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"updateOffset": 0, "initialized": False}
    if not isinstance(payload, dict):
        return {"updateOffset": 0, "initialized": False}
    state = {
        "updateOffset": max(0, int(payload.get("updateOffset") or 0)),
        "initialized": bool(payload.get("initialized")),
    }
    prompt_ids = payload.get("promptMessageIds")
    if isinstance(prompt_ids, dict) and prompt_ids:
        state["promptMessageIds"] = {
            str(key): int(value)
            for key, value in prompt_ids.items()
            if str(value).isdigit() and int(value) > 0
        }
    return state


def save_state(state, path=None):
    outgoing.atomic_json(Path(path or state_path()), state)


def message_in_fax_topic(message):
    return (
        access.message_is_allowed(message)
        and str(message.get("message_thread_id") or "") == topic_id()
    )


def message_in_memos_topic(message):
    return (
        memos_topic_read_only()
        and access.message_is_allowed(message)
        and str(message.get("message_thread_id") or "") == memos_topic_id()
    )


def protect_memos_topic(message, *, message_deleter=None):
    if not message_in_memos_topic(message):
        return "ignored"
    source = message.get("from") if isinstance(message.get("from"), dict) else {}
    if source.get("is_bot"):
        return "ignored"
    try:
        message_id = int(message.get("message_id") or 0)
    except (TypeError, ValueError):
        message_id = 0
    if message_id <= 0:
        return "ignored"
    deleter = message_deleter or telegram.delete_message
    try:
        deleter(bot_token(), access.configured_supergroup_id(), message_id)
    except telegram.TelegramError:
        with STATE_LOCK:
            WORKER_STATE["protectedDeleteFailedCount"] += 1
        raise
    with STATE_LOCK:
        WORKER_STATE["protectedDeletedCount"] += 1
    return "protected"


def text_destination(value, *, error_code):
    match = outgoing.SUBJECT_PATTERN.fullmatch(str(value or "").strip())
    if not match:
        raise outgoing.OutgoingFaxError(error_code)
    return outgoing.normalize_destination(match.group(1))


def document_details(message):
    document = message.get("document") if isinstance(message.get("document"), dict) else None
    if not document:
        return None
    filename = Path(str(document.get("file_name") or "fax.pdf")).name
    mime_type = str(document.get("mime_type") or "").lower()
    if mime_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise outgoing.OutgoingFaxError("pdf_attachment_required")
    try:
        file_size = int(document.get("file_size") or 0)
    except (TypeError, ValueError) as exc:
        raise outgoing.OutgoingFaxError("pdf_size_invalid") from exc
    if file_size > outgoing.max_pdf_bytes():
        raise outgoing.OutgoingFaxError("pdf_size_invalid")
    file_id = str(document.get("file_id") or "").strip()
    if not file_id:
        raise outgoing.OutgoingFaxError("telegram_file_id_required")
    return {
        "filename": filename,
        "fileId": file_id,
        "fileUniqueId": str(document.get("file_unique_id") or file_id),
    }


def reply(text, *, api_sender=None):
    sender = api_sender or telegram.send_message
    return sender(
        bot_token(),
        access.configured_supergroup_id(),
        text,
        thread_id=topic_id(),
        silent=True,
    )


def rejection_message(error):
    labels = {
        "caption_must_be_fax_colon_number": "Use caption fax:<number> or reply to the PDF with fax:<number>.",
        "reply_to_pdf_required": "Reply directly to one PDF with fax:<number>.",
        "invalid_domestic_fax_number": "The fax number is invalid.",
        "pdf_attachment_required": "Only PDF documents can be faxed.",
        "pdf_size_invalid": "The PDF is empty or exceeds the configured size limit.",
        "invalid_pdf_signature": "The uploaded document is not a valid PDF.",
    }
    return f"Fax request rejected.\n{labels.get(str(error), str(error))}"


def prompt_key(chat_id, document_message_id):
    return f"{chat_id}:{document_message_id}"


def process_message(message, *, file_downloader=None, api_sender=None, intake_state=None):
    if not message_in_fax_topic(message):
        return "ignored"

    command_message = message
    document_message = message
    details = document_details(document_message)
    if details:
        caption = str(message.get("caption") or "").strip()
        if not caption:
            response = reply("Reply directly to this PDF with fax:<number>.", api_sender=api_sender)
            if isinstance(intake_state, dict):
                message_id = int(message.get("message_id") or 0)
                response_id = int((response or {}).get("message_id") or 0)
                if message_id > 0 and response_id > 0:
                    intake_state.setdefault("promptMessageIds", {})[
                        prompt_key(message["chat"]["id"], message_id)
                    ] = response_id
            return "waiting"
        destination = text_destination(
            caption,
            error_code="caption_must_be_fax_colon_number",
        )
    else:
        text = str(message.get("text") or "").strip()
        if not text.lower().startswith("fax"):
            return "ignored"
        destination = text_destination(text, error_code="reply_to_pdf_required")
        replied = message.get("reply_to_message")
        if not isinstance(replied, dict):
            raise outgoing.OutgoingFaxError("reply_to_pdf_required")
        if str(replied.get("message_thread_id") or "") != topic_id():
            raise outgoing.OutgoingFaxError("reply_to_pdf_required")
        document_message = replied
        details = document_details(document_message)
        if not details:
            raise outgoing.OutgoingFaxError("reply_to_pdf_required")

    if not details:
        return "ignored"
    downloader = file_downloader or telegram.download_file
    pdf = downloader(bot_token(), details["fileId"], max_bytes=outgoing.max_pdf_bytes())
    chat = command_message["chat"]
    source = command_message.get("from") if isinstance(command_message.get("from"), dict) else {}
    document_message_id = int(document_message.get("message_id") or 0)
    command_message_id = int(command_message.get("message_id") or 0)
    source_prompt_key = prompt_key(chat["id"], document_message_id)
    prompt_message_id = 0
    if isinstance(intake_state, dict):
        prompt_message_id = int(
            (intake_state.get("promptMessageIds") or {}).get(source_prompt_key) or 0
        )
    source_id = (
        f"telegram:{chat['id']}:{document_message_id}:"
        f"{details['fileUniqueId']}"
    )
    request = outgoing.request_from_pdf(
        destination=destination,
        sender=f"telegram:{source.get('id') or 'unknown'}",
        message_id=source_id,
        filename=details["filename"],
        pdf=pdf,
    )
    source_metadata = {
        "chatId": str(chat["id"]),
        "messageId": document_message_id,
        "commandMessageId": command_message_id,
        "threadId": int(command_message.get("message_thread_id") or 0),
        "userId": str(source.get("id") or ""),
        "fileUniqueId": details["fileUniqueId"],
    }
    if prompt_message_id > 0:
        source_metadata["instructionMessageId"] = prompt_message_id
    job, created = outgoing.submit_request(
        request,
        source="telegram",
        source_metadata=source_metadata,
    )
    if prompt_message_id > 0:
        prompts = intake_state.get("promptMessageIds") or {}
        prompts.pop(source_prompt_key, None)
        if not prompts:
            intake_state.pop("promptMessageIds", None)
    if created:
        return "accepted"
    return "duplicate"


def get_updates(state, *, api_call=None):
    call = api_call or telegram.call
    return call(
        bot_token(),
        "getUpdates",
        {
            "offset": state["updateOffset"],
            "limit": 100,
            "timeout": poll_seconds(),
            "allowed_updates": json.dumps(["message", "edited_message", "callback_query"]),
        },
    )


def scan_once(
    *,
    api_call=None,
    file_downloader=None,
    api_sender=None,
    message_deleter=None,
    callback_answerer=None,
    markup_editor=None,
):
    state = load_state()
    updates = get_updates(state, api_call=api_call)
    if not isinstance(updates, list):
        raise RuntimeError("telegram_updates_invalid")
    accepted = 0
    rejected = 0
    baseline = not state["initialized"] and mark_existing_on_first_run()
    for update in sorted(updates, key=lambda value: int(value.get("update_id") or 0)):
        update_id = int(update.get("update_id") or 0)
        if update_id < state["updateOffset"]:
            continue
        message = update.get("message") or update.get("edited_message") or {}
        callback = update.get("callback_query") or {}
        try:
            protected = protect_memos_topic(message, message_deleter=message_deleter)
            if not baseline and protected != "protected":
                document_result = document_intake.process_message(
                    message,
                    file_downloader=file_downloader,
                    api_sender=api_sender,
                )
                accepted += int(document_result == "accepted")
                if document_result == "ignored" and fax_intake_enabled():
                    result = process_message(
                        message,
                        file_downloader=file_downloader,
                        api_sender=api_sender,
                        intake_state=state,
                    )
                    accepted += int(result == "accepted")
                if callback:
                    callback_result = document_intake.process_callback(
                        callback,
                        callback_answerer=callback_answerer,
                        markup_editor=markup_editor,
                    )
                    if callback_result == "ignored":
                        mail_organizer.process_callback(
                            callback,
                            callback_answerer=callback_answerer,
                            markup_editor=markup_editor,
                            message_deleter=message_deleter,
                        )
        except (
            outgoing.OutgoingFaxError,
            document_intake.DocumentTelegramError,
            mail_organizer.MailOrganizerError,
            telegram.TelegramError,
        ) as exc:
            if document_intake.callback_in_topic(callback):
                answerer = callback_answerer or telegram.answer_callback_query
                try:
                    answerer(bot_token(), str(callback.get("id") or ""), "Document action failed")
                except telegram.TelegramError:
                    pass
                rejected += 1
            elif mail_organizer.callback_in_topic(callback):
                answerer = callback_answerer or telegram.answer_callback_query
                try:
                    answerer(bot_token(), str(callback.get("id") or ""), "Mail action failed")
                except telegram.TelegramError:
                    pass
                rejected += 1
            elif message_in_fax_topic(message):
                reply(rejection_message(exc), api_sender=api_sender)
                rejected += 1
            elif document_intake.message_in_topic(message):
                sender = api_sender or telegram.send_message
                sender(
                    bot_token(),
                    access.configured_supergroup_id(),
                    document_intake.rejection_message(exc),
                    thread_id=document_intake.topic_id(),
                    silent=True,
                    reply_to_message_id=int(message.get("message_id") or 0),
                )
                rejected += 1
        except (ValueError, RuntimeError) as exc:
            if document_intake.callback_in_topic(callback):
                answerer = callback_answerer or telegram.answer_callback_query
                answerer(bot_token(), str(callback.get("id") or ""), f"Action failed: {exc}")
                rejected += 1
            elif mail_organizer.callback_in_topic(callback):
                answerer = callback_answerer or telegram.answer_callback_query
                answerer(bot_token(), str(callback.get("id") or ""), "Mail action failed")
                rejected += 1
        state["updateOffset"] = update_id + 1
        save_state(state)
    # A full page can mean more old updates remain. Keep baselining until a
    # short page confirms that the complete pre-existing backlog was skipped.
    state["initialized"] = not baseline or len(updates) < 100
    save_state(state)
    return accepted, rejected


def update_status(*, accepted=0, rejected=0, last_error=None):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with STATE_LOCK:
        WORKER_STATE["lastPollAt"] = timestamp
        if last_error is not None:
            WORKER_STATE["lastError"] = last_error
        if accepted:
            WORKER_STATE["lastAcceptedAt"] = timestamp
            WORKER_STATE["acceptedCount"] += accepted
        if rejected:
            WORKER_STATE["rejectedCount"] += rejected


def scan_and_process():
    try:
        accepted, rejected = scan_once()
        update_status(accepted=accepted, rejected=rejected, last_error="")
        return accepted, rejected
    except (OSError, RuntimeError, ValueError, telegram.TelegramError) as exc:
        update_status(last_error=type(exc).__name__)
        print(f"Telegram fax intake failed: {type(exc).__name__}", flush=True)
        return 0, 0


def status():
    with STATE_LOCK:
        runtime = dict(WORKER_STATE)
    return {
        "ok": (not enabled()) or (configured() and not runtime["lastError"]),
        "enabled": enabled(),
        "configured": configured(),
        "started": bool(runtime["started"]),
        "groupOnly": True,
        "topics": {
            "faxIntake": fax_intake_enabled(),
            "memosReadOnly": memos_topic_read_only(),
            "documentIntake": document_intake.enabled(),
            "mailOrganizer": mail_organizer.enabled(),
        },
        "statePath": str(state_path()),
        "pollSeconds": poll_seconds(),
        **{key: runtime[key] for key in (
            "lastPollAt",
            "lastAcceptedAt",
            "lastError",
            "acceptedCount",
            "rejectedCount",
            "protectedDeletedCount",
            "protectedDeleteFailedCount",
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
            scan_and_process()
            time.sleep(1)

    WORKER_THREAD = threading.Thread(target=run, name="telegram-fax-intake", daemon=True)
    WORKER_THREAD.start()
    return WORKER_THREAD

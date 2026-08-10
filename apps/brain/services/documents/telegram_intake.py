"""Telegram Documents-topic intake and routing actions."""

import io
import os
import re
from pathlib import Path

from services.documents import store
from services.telegram import access
from services.telegram import client as telegram


CALLBACK_PATTERN = re.compile(
    r"^document:(paperless|delete):([0-9a-f]{8}-[0-9a-f-]{27})$",
    re.IGNORECASE,
)


class DocumentTelegramError(ValueError):
    pass


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def enabled():
    return env_bool("TELEGRAM_DOCUMENT_INTAKE_ENABLED")


def topic_id():
    return os.environ.get("TELEGRAM_TOPIC_DOCUMENTS_ID", "").strip()


def public_origin():
    return os.environ.get("TELEGRAM_DOCUMENT_PUBLIC_ORIGIN", "https://kaosgdd.net").strip().rstrip("/")


def max_pdf_bytes():
    return max(1, int(os.environ.get("TELEGRAM_DOCUMENT_MAX_MB", "20"))) * 1024 * 1024


def configured():
    return (not enabled()) or bool(
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        and access.configured_supergroup_id()
        and topic_id()
        and public_origin()
    )


def message_in_topic(message):
    return (
        enabled()
        and access.message_is_allowed(message)
        and str(message.get("message_thread_id") or "") == topic_id()
    )


def callback_in_topic(callback):
    message = callback.get("message") if isinstance(callback, dict) else None
    return message_in_topic(message)


def document_details(message):
    document = message.get("document") if isinstance(message.get("document"), dict) else None
    if not document:
        return None
    filename = Path(str(document.get("file_name") or "document.pdf")).name
    mime_type = str(document.get("mime_type") or "").lower()
    if mime_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise DocumentTelegramError("pdf_required")
    try:
        file_size = int(document.get("file_size") or 0)
    except (TypeError, ValueError) as exc:
        raise DocumentTelegramError("document_size_invalid") from exc
    if file_size <= 0 or file_size > max_pdf_bytes():
        raise DocumentTelegramError("document_size_invalid")
    file_id = str(document.get("file_id") or "").strip()
    if not file_id:
        raise DocumentTelegramError("telegram_file_id_required")
    return {
        "filename": filename,
        "fileId": file_id,
        "fileUniqueId": str(document.get("file_unique_id") or file_id),
        "fileSize": file_size,
    }


def action_keyboard(document_id):
    content_url = f"{public_origin()}/api/documents/{document_id}/content"
    return {
        "inline_keyboard": [[
            {"text": "Open", "url": content_url},
            {"text": "Paperless", "callback_data": f"document:paperless:{document_id}"},
            {"text": "Delete", "callback_data": f"document:delete:{document_id}"},
        ]]
    }


def process_message(message, *, file_downloader=None, api_sender=None):
    if not message_in_topic(message):
        return "ignored"
    details = document_details(message)
    if not details:
        return "ignored"
    downloader = file_downloader or telegram.download_file
    content = downloader(
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        details["fileId"],
        max_bytes=max_pdf_bytes(),
    )
    source_key = (
        f"telegram:{message['chat']['id']}:{int(message.get('message_id') or 0)}:"
        f"{details['fileUniqueId']}"
    )
    try:
        item = store.store_document(
            io.BytesIO(content),
            len(content),
            details["filename"],
            "telegram",
            "main",
            source_key=source_key,
        )
    except ValueError as exc:
        raise DocumentTelegramError(str(exc)) from exc
    sender = api_sender or telegram.send_message
    sender(
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        access.configured_supergroup_id(),
        f"Document ready\n{item['filename']}",
        thread_id=topic_id(),
        silent=True,
        reply_markup=action_keyboard(item["id"]),
        reply_to_message_id=int(message.get("message_id") or 0),
    )
    return "accepted"


def process_callback(
    callback,
    *,
    callback_answerer=None,
    markup_editor=None,
):
    if not callback_in_topic(callback):
        return "ignored"
    match = CALLBACK_PATTERN.fullmatch(str(callback.get("data") or ""))
    if not match:
        return "ignored"
    action, document_id = match.groups()
    if action == "paperless":
        store.submit_to_paperless(document_id, "main")
        answer = "Sent to Paperless"
    else:
        store.delete_document(document_id, "main")
        answer = "Temporary copy deleted"
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    answerer = callback_answerer or telegram.answer_callback_query
    answerer(token, str(callback.get("id") or ""), answer)
    message = callback["message"]
    editor = markup_editor or telegram.edit_message_reply_markup
    editor(
        token,
        access.configured_supergroup_id(),
        int(message.get("message_id") or 0),
        {"inline_keyboard": []},
    )
    return action


def rejection_message(error):
    labels = {
        "pdf_required": "Only PDF documents are supported in this topic for now.",
        "document_size_invalid": "The PDF is empty or exceeds the configured size limit.",
        "telegram_document_too_large": "The PDF exceeds the Telegram download limit.",
        "telegram_document_size_invalid": "The Telegram file download was incomplete.",
        "invalid_pdf_signature": "The uploaded file is not a valid PDF.",
    }
    return f"Document rejected.\n{labels.get(str(error), str(error))}"

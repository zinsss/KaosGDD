"""Small Telegram Bot API client used by Brain archive workers."""

import json
import mimetypes
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class TelegramError(RuntimeError):
    pass


def api_base_url():
    return os.environ.get("TELEGRAM_API_BASE_URL", "https://api.telegram.org").strip().rstrip("/")


def _decode_response(raw):
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelegramError("telegram_invalid_response") from exc
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise TelegramError("telegram_api_rejected")
    return payload.get("result")


def _open(request, *, opener=None, timeout=30):
    open_request = opener or urllib.request.urlopen
    try:
        return _decode_response(open_request(request, timeout=timeout).read())
    except urllib.error.HTTPError as exc:
        raise TelegramError(f"telegram_http_{exc.code}") from exc
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise TelegramError("telegram_request_failed") from exc


def call(token, method, fields, *, opener=None):
    if not token:
        raise TelegramError("telegram_token_missing")
    request = urllib.request.Request(
        f"{api_base_url()}/bot{token}/{method}",
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "KaosGDD-Brain-Telegram/1.0",
        },
        method="POST",
    )
    return _open(request, opener=opener)


def download_file(token, file_id, *, max_bytes, opener=None):
    metadata = call(token, "getFile", {"file_id": file_id}, opener=opener)
    if not isinstance(metadata, dict) or not metadata.get("file_path"):
        raise TelegramError("telegram_file_path_missing")
    try:
        declared_size = int(metadata.get("file_size") or 0)
    except (TypeError, ValueError):
        declared_size = 0
    if declared_size > max_bytes:
        raise TelegramError("telegram_document_too_large")
    local_root = os.environ.get("TELEGRAM_LOCAL_FILE_ROOT", "").strip()
    file_path = str(metadata["file_path"])
    if local_root and Path(file_path).is_absolute():
        root = Path(local_root).resolve()
        path = Path(file_path).resolve()
        if path != root and root not in path.parents:
            raise TelegramError("telegram_local_file_outside_root")
        try:
            with path.open("rb") as source:
                content = source.read(max_bytes + 1)
        except OSError as exc:
            raise TelegramError("telegram_file_download_failed") from exc
        if not content or len(content) > max_bytes:
            raise TelegramError("telegram_document_size_invalid")
        return content
    safe_path = urllib.parse.quote(file_path.lstrip("/"), safe="/")
    request = urllib.request.Request(
        f"{api_base_url()}/file/bot{token}/{safe_path}",
        headers={"User-Agent": "KaosGDD-Brain-Telegram/1.0"},
    )
    open_request = opener or urllib.request.urlopen
    try:
        response = open_request(request, timeout=30)
        content = response.read(max_bytes + 1)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise TelegramError("telegram_file_download_failed") from exc
    if not content or len(content) > max_bytes:
        raise TelegramError("telegram_document_size_invalid")
    return content


def send_message(
    token,
    chat_id,
    text,
    *,
    thread_id="",
    silent=True,
    protect_content=False,
    reply_markup=None,
    reply_to_message_id=None,
    opener=None,
):
    fields = {
        "chat_id": chat_id,
        "text": text[:4096],
        "disable_notification": "true" if silent else "false",
        "protect_content": "true" if protect_content else "false",
    }
    if thread_id:
        fields["message_thread_id"] = thread_id
    if reply_markup:
        fields["reply_markup"] = json.dumps(reply_markup, ensure_ascii=True)
    if reply_to_message_id:
        fields["reply_parameters"] = json.dumps(
            {"message_id": int(reply_to_message_id)},
            ensure_ascii=True,
        )
    result = call(token, "sendMessage", fields, opener=opener)
    return result if isinstance(result, dict) else {}


def edit_message_text(token, chat_id, message_id, text, *, opener=None):
    result = call(
        token,
        "editMessageText",
        {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "text": text[:4096],
        },
        opener=opener,
    )
    return result if isinstance(result, dict) else {}


def edit_message_reply_markup(token, chat_id, message_id, reply_markup=None, *, opener=None):
    result = call(
        token,
        "editMessageReplyMarkup",
        {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "reply_markup": json.dumps(reply_markup or {"inline_keyboard": []}),
        },
        opener=opener,
    )
    return result if isinstance(result, dict) else {}


def answer_callback_query(token, callback_query_id, text="", *, opener=None):
    fields = {"callback_query_id": callback_query_id}
    if text:
        fields["text"] = str(text)[:200]
    return bool(call(token, "answerCallbackQuery", fields, opener=opener))


def delete_message(token, chat_id, message_id, *, opener=None):
    return bool(
        call(
            token,
            "deleteMessage",
            {"chat_id": chat_id, "message_id": int(message_id)},
            opener=opener,
        )
    )


def _safe_filename(filename):
    value = re.sub(r"[\x00-\x1f\x7f\"\\/]+", "-", str(filename)).strip(" .-")
    return value or "attachment"


def _content_disposition_file_part(name, filename):
    safe_name = _safe_filename(filename)
    encoded_name = urllib.parse.quote(safe_name, safe="")
    return (
        f'Content-Disposition: form-data; name="{name}"; '
        f'filename="{safe_name}"; filename*=UTF-8\'\'{encoded_name}\r\n'
    )


def _multipart(fields, *, filename, content, content_type):
    boundary = f"----KaosGDD{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    safe_name = _safe_filename(filename)
    body.extend(f"--{boundary}\r\n".encode("ascii"))
    body.extend(_content_disposition_file_part("document", safe_name).encode("utf-8"))
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("ascii"))
    body.extend(content)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("ascii"))
    return bytes(body), boundary


def send_document(
    token,
    chat_id,
    filename,
    content,
    *,
    caption="",
    content_type="",
    thread_id="",
    silent=True,
    protect_content=False,
    opener=None,
):
    if not token or not chat_id:
        raise TelegramError("telegram_not_configured")
    if not isinstance(content, bytes) or not content:
        raise TelegramError("telegram_document_empty")
    fields = {
        "chat_id": chat_id,
        "caption": caption[:1024],
        "disable_notification": "true" if silent else "false",
        "protect_content": "true" if protect_content else "false",
    }
    if thread_id:
        fields["message_thread_id"] = thread_id
    body, boundary = _multipart(
        fields,
        filename=filename,
        content=content,
        content_type=content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
    )
    request = urllib.request.Request(
        f"{api_base_url()}/bot{token}/sendDocument",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "KaosGDD-Brain-Telegram/1.0",
        },
        method="POST",
    )
    result = _open(request, opener=opener)
    return result if isinstance(result, dict) else {}

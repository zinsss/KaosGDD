import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse

from services.notifications import router


class NotificationActionError(ValueError):
    pass


ALLOWED_CHANNELS = {"normal", "ios", "desktop", "system"}
MAX_TOKEN_BYTES = 12_000


def actions_enabled():
    return os.environ.get("NOTIFICATION_ACTIONS_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _secret():
    return os.environ.get("NOTIFICATION_LATER_SECRET", "").strip().encode("utf-8")


def _base64_encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64_decode(value):
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise NotificationActionError("invalid_later_token") from exc


def _ttl_seconds():
    try:
        return max(300, min(int(os.environ.get("NOTIFICATION_LATER_TOKEN_TTL_SECONDS", "604800")), 2_592_000))
    except ValueError as exc:
        raise NotificationActionError("invalid_later_token_ttl") from exc


def normalize_notification(notification):
    value = {
        "channel": str(notification.get("channel") or "normal").strip(),
        "title": str(notification.get("title") or "").strip()[:256],
        "message": str(notification.get("message") or "")[:4096],
        "priority": str(notification.get("priority") or "default").strip()[:32],
        "tags": str(notification.get("tags") or "").strip()[:256],
        "click_url": str(notification.get("click_url") or "").strip()[:2048],
    }
    if value["channel"] not in ALLOWED_CHANNELS or not value["title"] or not value["message"]:
        raise NotificationActionError("invalid_later_notification")
    if value["click_url"] and not value["click_url"].startswith("https://"):
        raise NotificationActionError("invalid_later_click_url")
    return value


def create_later_token(notification, now=None):
    secret = _secret()
    if not secret:
        return ""
    now = int(time.time() if now is None else now)
    envelope = {
        "v": 1,
        "exp": now + _ttl_seconds(),
        "notification": normalize_notification(notification),
    }
    payload = json.dumps(envelope, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret, payload, hashlib.sha256).digest()
    return f"{_base64_encode(payload)}.{_base64_encode(signature)}"


def decode_later_token(token, now=None):
    secret = _secret()
    if not secret:
        raise NotificationActionError("later_actions_not_configured")
    if not token or len(token) > MAX_TOKEN_BYTES or token.count(".") != 1:
        raise NotificationActionError("invalid_later_token")
    payload_value, signature_value = token.split(".", 1)
    payload = _base64_decode(payload_value)
    signature = _base64_decode(signature_value)
    expected = hmac.new(secret, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise NotificationActionError("invalid_later_token")
    try:
        envelope = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NotificationActionError("invalid_later_token") from exc
    now = int(time.time() if now is None else now)
    if envelope.get("v") != 1 or int(envelope.get("exp") or 0) < now:
        raise NotificationActionError("expired_later_token")
    return normalize_notification(envelope.get("notification") or {})


def action_header(notification, now=None):
    if not actions_enabled():
        return ""
    notification = normalize_notification(notification)
    actions = []
    if notification["click_url"]:
        actions.append(f"view, Open, {notification['click_url']}, clear=true")
    token = create_later_token(notification, now=now)
    base_url = os.environ.get(
        "NOTIFICATION_LATER_BASE_URL",
        "https://kaosgdd.net/api/notifications/later",
    ).strip()
    if token and base_url.startswith("https://"):
        separator = "&" if "?" in base_url else "?"
        later_url = f"{base_url}{separator}{urllib.parse.urlencode({'token': token})}"
        actions.append(f"view, Later, {later_url}, clear=true")
    return "; ".join(actions)


def schedule_later(token, *, opener=None, now=None):
    if not actions_enabled():
        raise NotificationActionError("notification_actions_disabled")
    notification = decode_later_token(token, now=now)
    actions = action_header(notification, now=now)
    sequence_id = f"later-{hashlib.sha256(token.encode('ascii')).hexdigest()[:24]}"
    router.publish(
        **notification,
        actions=actions,
        delay=os.environ.get("NOTIFICATION_LATER_DELAY", "1h").strip() or "1h",
        sequence_id=sequence_id,
        user_agent="KaosGDD-Brain-Later/1.0",
        opener=opener,
    )
    return notification

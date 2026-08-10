"""Inbound Telegram access policy for the private KaosGDD supergroup."""

import os


def configured_supergroup_id():
    return os.environ.get("TELEGRAM_SUPERGROUP_CHAT_ID", "").strip()


def is_configured_supergroup(chat):
    if not isinstance(chat, dict):
        return False
    return (
        bool(configured_supergroup_id())
        and str(chat.get("id") or "") == configured_supergroup_id()
        and str(chat.get("type") or "").lower() == "supergroup"
    )


def message_is_allowed(message):
    return isinstance(message, dict) and is_configured_supergroup(message.get("chat"))

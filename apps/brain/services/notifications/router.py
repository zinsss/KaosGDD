import os

from services.telegram import client as telegram


def transport_name():
    return "telegram"


def bot_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def chat_id():
    return os.environ.get("TELEGRAM_SUPERGROUP_CHAT_ID", "").strip()


def topic_id(channel="normal"):
    variable = (
        "TELEGRAM_TOPIC_SYSTEM_ALERTS_ID"
        if channel == "system"
        else "TELEGRAM_TOPIC_NOTIFICATIONS_ID"
    )
    return os.environ.get(variable, "").strip()


def configured(channel="normal"):
    return bool(bot_token() and chat_id() and topic_id(channel))


def publish(
    *,
    channel,
    title,
    message,
    priority="default",
    tags="",
    click_url="",
    actions="",
    delay="",
    sequence_id="",
    user_agent="KaosGDD-Brain/1.0",
    opener=None,
):
    del priority, tags, click_url, actions, delay, sequence_id, user_agent
    if not configured(channel):
        raise RuntimeError("telegram_notifications_not_configured")
    text = f"{str(title).strip()}\n{str(message).strip()}".strip()
    return telegram.send_message(
        bot_token(),
        chat_id(),
        text,
        thread_id=topic_id(channel),
        silent=False,
        opener=opener,
    )

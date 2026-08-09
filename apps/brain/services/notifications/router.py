import os

from services.notifications import ntfy, pushover


def transport_name():
    return os.environ.get("NOTIFICATION_TRANSPORT", "ntfy").strip().lower() or "ntfy"


def configured(channel="normal"):
    transport = transport_name()
    if transport == "pushover":
        return pushover.configured(channel)
    if transport == "ntfy":
        return bool(ntfy.topic_urls(channel))
    return False


def publish(**notification):
    transport = transport_name()
    if transport == "pushover":
        return pushover.publish(**notification)
    if transport == "ntfy":
        return ntfy.publish(**notification)
    raise RuntimeError("notification_transport_not_configured")

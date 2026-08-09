import json
import os
import urllib.parse
import urllib.request


PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"


def _enabled():
    return os.environ.get("PUSHOVER_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def destinations(channel="normal"):
    user_key = os.environ.get("PUSHOVER_USER_KEY", "").strip()
    if not _enabled() or not user_key:
        return []

    ios = (
        os.environ.get("PUSHOVER_IOS_TOKEN", "").strip(),
        os.environ.get("PUSHOVER_IOS_DEVICE", "").strip(),
    )
    desktop = (
        os.environ.get("PUSHOVER_DESKTOP_TOKEN", "").strip(),
        os.environ.get("PUSHOVER_DESKTOP_DEVICE", "").strip(),
    )
    if channel == "ios":
        selected = [ios]
    elif channel == "desktop":
        selected = [desktop]
    else:
        selected = [ios, desktop]

    targets = [
        {"token": token, "user": user_key, "device": device}
        for token, device in dict.fromkeys(selected)
        if token and device
    ]
    if channel not in {"ios", "desktop"} and len(targets) != 2:
        return []
    return targets


def configured(channel="normal"):
    return bool(destinations(channel))


def _priority(channel):
    # Priority 1 bypasses quiet hours without requiring acknowledgement.
    # Emergency priority 2 is intentionally not used by Brain.
    return 1 if channel == "system" else 0


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
    del priority, tags, click_url, actions, delay, sequence_id
    targets = destinations(channel)
    if not targets:
        raise RuntimeError("pushover_not_configured")

    timeout = float(os.environ.get("PUSHOVER_TIMEOUT_SECONDS", "10"))
    opener = opener or urllib.request.urlopen
    for target in targets:
        payload = {
            "token": target["token"],
            "user": target["user"],
            "title": str(title)[:250],
            "message": str(message)[:1024],
            "priority": str(_priority(channel)),
        }
        if target["device"]:
            payload["device"] = target["device"]
        request = urllib.request.Request(
            PUSHOVER_ENDPOINT,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": user_agent,
            },
        )
        with opener(request, timeout=timeout) as response:
            raw_response = response.read()
        if raw_response:
            result = json.loads(raw_response.decode("utf-8"))
            if int(result.get("status") or 0) != 1:
                raise RuntimeError("pushover_api_error")

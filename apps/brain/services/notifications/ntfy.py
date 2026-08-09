import os
import urllib.parse
import urllib.request


def topic_urls(channel="normal"):
    raw_url = os.environ.get("NTFY_URL", "").strip().rstrip("/")
    fallback_topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not raw_url:
        return []

    if channel == "ios":
        topics = [os.environ.get("NTFY_TOPIC_IOS", "").strip()]
    elif channel == "desktop":
        topics = [os.environ.get("NTFY_TOPIC_DESKTOP", "").strip()]
    else:
        # Normal and urgent system notifications fan out by device. Priority
        # remains part of the notification payload, not the topic hierarchy.
        topics = [
            os.environ.get("NTFY_TOPIC_IOS", "").strip(),
            os.environ.get("NTFY_TOPIC_DESKTOP", "").strip(),
        ]
        if not any(topics):
            topics = [os.environ.get("NTFY_TOPIC_NORMAL", "").strip()]

    topics = [topic.strip("/") for topic in topics if topic.strip("/")]
    if not topics and fallback_topic:
        topics = [fallback_topic.strip("/")]
    return [
        f"{raw_url}/{urllib.parse.quote(topic)}"
        for topic in dict.fromkeys(topics)
    ]


def topic_url(channel="normal"):
    urls = topic_urls(channel)
    return urls[0] if urls else ""


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
    urls = topic_urls(channel)
    if not urls:
        raise RuntimeError("ntfy_not_configured")

    token = os.environ.get("NTFY_TOKEN", "").strip()
    timeout = float(os.environ.get("NTFY_TIMEOUT_SECONDS", "10"))
    opener = opener or urllib.request.urlopen
    for url in urls:
        request = urllib.request.Request(
            url,
            data=str(message).encode("utf-8"),
            method="POST",
            headers={
                "Title": str(title),
                "Priority": str(priority),
                "User-Agent": user_agent,
            },
        )
        if tags:
            request.add_header("Tags", str(tags))
        if click_url:
            request.add_header("Click", str(click_url))
        if actions:
            request.add_header("Actions", str(actions))
        if delay:
            request.add_header("Delay", str(delay))
        if sequence_id:
            request.add_header("Sequence-ID", str(sequence_id))
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        with opener(request, timeout=timeout) as response:
            response.read()

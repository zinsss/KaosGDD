import json
import os
import pathlib
import sys
import urllib.parse
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.notifications import router


class Response:
    def read(self):
        return b'{"ok":true,"result":{"message_id":42}}'


class TelegramNotificationTests(unittest.TestCase):
    def environment(self, **overrides):
        values = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_SUPERGROUP_CHAT_ID": "-100123",
            "TELEGRAM_TOPIC_NOTIFICATIONS_ID": "10",
            "TELEGRAM_TOPIC_SYSTEM_ALERTS_ID": "20",
        }
        values.update(overrides)
        return mock.patch.dict(os.environ, values, clear=True)

    def publish(self, channel):
        captured = {}

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

        result = router.publish(
            channel=channel,
            title="Test title",
            message="Test message",
            opener=opener,
        )
        payload = urllib.parse.parse_qs(captured["request"].data.decode("utf-8"))
        return result, payload, captured["request"].full_url

    def test_normal_notification_is_pushed_to_notifications_topic(self):
        with self.environment():
            result, payload, url = self.publish("normal")

        self.assertEqual(result["message_id"], 42)
        self.assertEqual(payload["chat_id"], ["-100123"])
        self.assertEqual(payload["message_thread_id"], ["10"])
        self.assertEqual(payload["disable_notification"], ["false"])
        self.assertEqual(payload["text"], ["Test title\nTest message"])
        self.assertNotIn("test-token", urllib.parse.unquote("&".join(payload)))
        self.assertTrue(url.endswith("/sendMessage"))

    def test_system_notification_is_pushed_to_system_alerts_topic(self):
        with self.environment():
            _result, payload, _url = self.publish("system")

        self.assertEqual(payload["message_thread_id"], ["20"])
        self.assertEqual(payload["disable_notification"], ["false"])

    def test_legacy_audience_channels_share_notifications_topic(self):
        with self.environment():
            self.assertEqual(router.topic_id("ios"), "10")
            self.assertEqual(router.topic_id("desktop"), "10")
            self.assertEqual(router.transport_name(), "telegram")

    def test_missing_topic_is_not_configured(self):
        with self.environment(TELEGRAM_TOPIC_NOTIFICATIONS_ID=""):
            self.assertFalse(router.configured("normal"))
            with self.assertRaisesRegex(RuntimeError, "telegram_notifications_not_configured"):
                router.publish(channel="normal", title="Title", message="Message")


if __name__ == "__main__":
    unittest.main()

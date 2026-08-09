import os
import pathlib
import sys
import unittest
from unittest.mock import patch


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.notifications import actions


class Response:
    def read(self):
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class NotificationActionTests(unittest.TestCase):
    def notification(self):
        return {
            "channel": "normal",
            "title": "New mail",
            "message": "A message arrived",
            "priority": "default",
            "tags": "email,inbox",
            "click_url": "https://mail.kaosgdd.net/",
        }

    def environment(self):
        return patch.dict(
            os.environ,
            {
                "NOTIFICATION_LATER_SECRET": "a" * 64,
                "NOTIFICATION_LATER_BASE_URL": "https://kaosgdd.net/api/notifications/later",
                "NTFY_URL": "https://ntfy.example",
                "NTFY_TOPIC_IOS": "kaosgdd-ios",
                "NTFY_TOPIC_DESKTOP": "kaosgdd-desktop",
                "NTFY_TOKEN": "test-token",
            },
            clear=True,
        )

    def test_action_header_has_open_and_later(self):
        with self.environment():
            header = actions.action_header(self.notification(), now=1000)

        self.assertIn("view, Open, https://mail.kaosgdd.net/", header)
        self.assertIn("view, Later, https://kaosgdd.net/api/notifications/later?token=", header)

    def test_token_rejects_tampering_and_expiration(self):
        with self.environment():
            token = actions.create_later_token(self.notification(), now=1000)
            self.assertEqual(actions.decode_later_token(token, now=1001)["title"], "New mail")
            payload, signature = token.split(".", 1)
            replacement = "A" if signature[0] != "A" else "B"
            with self.assertRaises(actions.NotificationActionError):
                actions.decode_later_token(f"{payload}.{replacement}{signature[1:]}", now=1001)
            with self.assertRaises(actions.NotificationActionError):
                actions.decode_later_token(token, now=1_000_000)

    def test_schedule_later_republishes_to_both_topics(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return Response()

        with self.environment():
            token = actions.create_later_token(self.notification(), now=1000)
            actions.schedule_later(token, opener=opener, now=1001)

        self.assertEqual(
            [request.full_url for request in requests],
            ["https://ntfy.example/kaosgdd-ios", "https://ntfy.example/kaosgdd-desktop"],
        )
        for request in requests:
            self.assertEqual(request.get_header("Delay"), "1h")
            self.assertTrue(request.get_header("Actions").startswith("view, Open,"))
            self.assertTrue(request.get_header("Sequence-id").startswith("later-"))


if __name__ == "__main__":
    unittest.main()

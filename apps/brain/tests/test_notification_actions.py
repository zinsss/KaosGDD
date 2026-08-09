import os
import pathlib
import sys
import unittest
from unittest.mock import patch


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.notifications import actions


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
                "NOTIFICATION_ACTIONS_ENABLED": "true",
                "NOTIFICATION_LATER_BASE_URL": "https://kaosgdd.net/api/notifications/later",
            },
            clear=True,
        )

    def test_action_header_has_open_and_later(self):
        with self.environment():
            header = actions.action_header(self.notification(), now=1000)

        self.assertIn("view, Open, https://mail.kaosgdd.net/", header)
        self.assertIn("view, Later, https://kaosgdd.net/api/notifications/later?token=", header)

    def test_actions_are_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(actions.action_header(self.notification(), now=1000), "")
            with self.assertRaisesRegex(actions.NotificationActionError, "actions_disabled"):
                actions.schedule_later("unused", now=1001)

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

    def test_schedule_later_republishes_through_notification_router(self):
        with self.environment(), patch.object(actions.router, "publish") as publish:
            token = actions.create_later_token(self.notification(), now=1000)
            actions.schedule_later(token, now=1001)

        self.assertEqual(publish.call_count, 1)
        self.assertEqual(publish.call_args.kwargs["channel"], "normal")
        self.assertEqual(publish.call_args.kwargs["delay"], "1h")


if __name__ == "__main__":
    unittest.main()

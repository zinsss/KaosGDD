import os
import pathlib
import sys
import unittest
import urllib.parse
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.notifications import pushover, router


class Response:
    def read(self):
        return b'{"status":1,"request":"test"}'

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class PushoverNotificationTests(unittest.TestCase):
    def environment(self, **overrides):
        values = {
            "PUSHOVER_ENABLED": "true",
            "PUSHOVER_USER_KEY": "user-key",
            "PUSHOVER_IOS_TOKEN": "ios-token",
            "PUSHOVER_IOS_DEVICE": "iphone",
            "PUSHOVER_DESKTOP_TOKEN": "desktop-token",
            "PUSHOVER_DESKTOP_DEVICE": "desktop",
        }
        values.update(overrides)
        return mock.patch.dict(os.environ, values, clear=True)

    def test_normal_fans_out_to_each_application_and_device(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return Response()

        with self.environment():
            router.publish(
                channel="normal",
                title="Incoming fax",
                message="fax0001.tif",
                opener=opener,
            )

        payloads = [
            urllib.parse.parse_qs(request.data.decode("utf-8"))
            for request, _timeout in requests
        ]
        self.assertEqual([payload["token"][0] for payload in payloads], ["ios-token", "desktop-token"])
        self.assertEqual([payload["device"][0] for payload in payloads], ["iphone", "desktop"])
        self.assertEqual([payload["priority"][0] for payload in payloads], ["0", "0"])

    def test_desktop_channel_uses_only_desktop_application(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return Response()

        with self.environment():
            router.publish(channel="desktop", title="Task", message="Due today", opener=opener)

        payload = urllib.parse.parse_qs(requests[0].data.decode("utf-8"))
        self.assertEqual(len(requests), 1)
        self.assertEqual(payload["token"], ["desktop-token"])
        self.assertEqual(payload["device"], ["desktop"])

    def test_system_channel_is_high_priority_but_not_emergency(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return Response()

        with self.environment():
            router.publish(channel="system", title="Fax failed", message="No carrier", opener=opener)

        payloads = [urllib.parse.parse_qs(request.data.decode("utf-8")) for request in requests]
        self.assertEqual([payload["priority"][0] for payload in payloads], ["1", "1"])
        self.assertTrue(all("retry" not in payload and "expire" not in payload for payload in payloads))

    def test_disabled_or_missing_user_key_is_not_configured(self):
        with self.environment(PUSHOVER_ENABLED="false"):
            self.assertFalse(pushover.configured("normal"))
        with self.environment(PUSHOVER_USER_KEY=""):
            self.assertFalse(pushover.configured("normal"))

    def test_fanout_uses_available_audiences(self):
        with self.environment(PUSHOVER_DESKTOP_DEVICE=""):
            self.assertTrue(pushover.configured("ios"))
            self.assertFalse(pushover.configured("desktop"))
            self.assertTrue(pushover.configured("normal"))
            self.assertEqual(router.transport_name(), "pushover")


if __name__ == "__main__":
    unittest.main()

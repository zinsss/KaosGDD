import io
import pathlib
import sys
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from api import server


class BrainStatusTests(unittest.TestCase):
    @mock.patch.object(server, "adapter_status")
    @mock.patch.object(server, "database_status")
    def test_status_reports_shadow_dependencies(self, database_status, adapter_status):
        database_status.return_value = {
            "ok": True,
            "database": "kaosgdd_brain",
            "user": "kaosgdd_brain",
            "migration": "001",
        }
        adapter_status.return_value = {
            "ok": True,
            "status": 200,
            "profile": "family",
            "configured": True,
        }

        payload = server.brain_status({"Host": "family.kaosgdd.net"})

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "shadow")
        self.assertEqual(payload["profile"], "family")
        self.assertEqual(payload["database"]["migration"], "001")
        adapter_status.assert_called_once_with("family.kaosgdd.net")

    def test_caregiver_api_requires_family_profile(self):
        server.require_family_profile({"Host": "family.kaosgdd.net"})
        with self.assertRaisesRegex(ValueError, "family_profile_required"):
            server.require_family_profile({"Host": "kaosgdd.net"})


class RequestProxyTests(unittest.TestCase):
    def test_request_body_enforces_adapter_size_limit(self):
        valid = mock.Mock()
        valid.headers = {"Content-Length": "2"}
        valid.rfile = io.BytesIO(b"{}")
        self.assertEqual(server.request_body(valid), b"{}")

        missing = mock.Mock()
        missing.headers = {}
        with self.assertRaisesRegex(ValueError, "invalid_body_length"):
            server.request_body(missing)

        oversized = mock.Mock()
        oversized.headers = {"Content-Length": str(server.MAX_REQUEST_BYTES + 1)}
        with self.assertRaisesRegex(ValueError, "invalid_body_length"):
            server.request_body(oversized)

    @mock.patch.object(server, "request_upstream")
    def test_proxy_request_forwards_body_method_and_profile(self, request_upstream):
        request_upstream.return_value = (201, "application/json", b'{"ok":true}')
        body = b'{"title":"test"}'
        handler = mock.Mock()
        handler.path = "/api/calendar/tasks"
        handler.headers = {
            "Content-Length": str(len(body)),
            "Content-Type": "application/json",
            "Host": "family.kaosgdd.net",
        }
        handler.rfile = io.BytesIO(body)

        server.proxy_request(handler, "POST")

        request_upstream.assert_called_once_with(
            "POST",
            "/api/calendar/tasks",
            "family.kaosgdd.net",
            body=body,
            content_type="application/json",
        )
        handler.send_response.assert_called_once_with(201)
        handler.wfile.write.assert_called_once_with(b'{"ok":true}')

    @mock.patch.object(server, "request_body")
    def test_proxy_request_rejects_unknown_route_before_reading_body(self, request_body):
        handler = mock.Mock()
        handler.path = "/internal/system/weather"

        with self.assertRaisesRegex(ValueError, "upstream_route_not_allowed"):
            server.proxy_request(handler, "POST")

        request_body.assert_not_called()


if __name__ == "__main__":
    unittest.main()

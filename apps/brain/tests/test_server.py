import io
import json
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


class HolidayRequestTests(unittest.TestCase):
    @mock.patch.object(server.holiday_service, "list_holidays")
    def test_lists_holidays(self, list_holidays):
        list_holidays.return_value = {"ok": True, "items": []}
        handler = mock.Mock()
        handler.path = "/api/holidays"
        handler.headers = {"Host": "family.kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_GET(handler)

        list_holidays.assert_called_once_with()
        handler.send_response.assert_called_once_with(200)

    @mock.patch.object(server.holiday_service, "set_public_holiday")
    def test_updates_public_holiday_classification(self, set_public_holiday):
        uid = "KAOS-HOLIDAY-1234567890ABCDEF12345678"
        set_public_holiday.return_value = {"ok": True, "item": {"uid": uid, "publicHoliday": True}}
        body = json.dumps({"publicHoliday": True}).encode("utf-8")
        handler = mock.Mock()
        handler.path = f"/api/holidays/{uid}"
        handler.headers = {"Host": "family.kaosgdd.net", "Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()

        server.Handler.do_PUT(handler)

        set_public_holiday.assert_called_once_with(uid, True)
        handler.send_response.assert_called_once_with(200)


class CustomEventRequestTests(unittest.TestCase):
    @mock.patch.object(server.generated_calendar_service, "settings_payload")
    def test_settings_are_main_only(self, settings_payload):
        settings_payload.return_value = {"ok": True, "settings": {}}
        handler = mock.Mock()
        handler.path = "/api/custom-events"
        handler.headers = {"Host": "kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_GET(handler)

        settings_payload.assert_called_once_with()
        handler.send_response.assert_called_once_with(200)

    @mock.patch.object(server.generated_calendar_service, "sync_generated_calendar")
    @mock.patch.object(server.generated_calendar_service, "update_settings")
    def test_update_persists_then_synchronizes(self, update_settings, sync_generated_calendar):
        update_settings.return_value = {"marketDaysEnabled": False, "claimDayEnabled": True}
        sync_generated_calendar.return_value = {"ok": True, "total": 52}
        body = json.dumps({"marketDaysEnabled": False, "claimDayEnabled": True}).encode("utf-8")
        handler = mock.Mock()
        handler.path = "/api/custom-events"
        handler.headers = {"Host": "kaosgdd.net", "Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()

        server.Handler.do_PUT(handler)

        update_settings.assert_called_once_with({"marketDaysEnabled": False, "claimDayEnabled": True})
        sync_generated_calendar.assert_called_once_with()
        handler.send_response.assert_called_once_with(200)


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


class MemosRelayRequestTests(unittest.TestCase):
    @mock.patch.object(server.memos_relay, "relay")
    def test_get_memos_is_sent_through_trusted_relay(self, relay):
        relay.return_value = (200, "application/json", b'{"memos":[]}')
        handler = mock.Mock()
        handler.path = "/api/memos/api/v1/memos?pageSize=50"
        handler.headers = {"Host": "kaosgdd.net", "Cf-Access-Jwt-Assertion": "jwt"}
        handler.wfile = io.BytesIO()

        server.Handler.do_GET(handler)

        relay.assert_called_once_with("GET", handler.path, handler.headers, body=None)
        handler.send_response.assert_called_once_with(200)

    @mock.patch.object(server.memos_relay, "bootstrap")
    def test_bootstrap_uses_portal_headers(self, bootstrap):
        bootstrap.return_value = {"user": {"name": "users/zin"}}
        body = b"{}"
        handler = mock.Mock()
        handler.path = "/api/memos/bootstrap"
        handler.headers = {
            "Host": "kaosgdd.net",
            "Content-Length": str(len(body)),
            "Cf-Access-Jwt-Assertion": "jwt",
        }
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()

        server.Handler.do_POST(handler)

        bootstrap.assert_called_once_with(handler.headers, {})
        handler.send_response.assert_called_once_with(200)


class RounyRequestTests(unittest.TestCase):
    @mock.patch.object(server, "get_rouny_document")
    def test_get_rouny_document_is_family_only(self, get_rouny_document):
        get_rouny_document.return_value = {
            "ok": True,
            "scope": "family",
            "revision": 2,
            "templates": [],
            "updatedAt": "",
        }
        handler = mock.Mock()
        handler.path = "/api/rouny/templates"
        handler.headers = {"Host": "family.kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_GET(handler)

        handler.send_response.assert_called_once_with(200)
        get_rouny_document.assert_called_once_with()

        denied = mock.Mock()
        denied.path = "/api/rouny/templates"
        denied.headers = {"Host": "kaosgdd.net"}
        denied.wfile = io.BytesIO()
        server.Handler.do_GET(denied)
        denied.send_response.assert_called_once_with(404)

    @mock.patch.object(server, "put_rouny_document")
    @mock.patch.object(server, "json_request")
    def test_put_rouny_document_returns_conflict_copy(self, json_request, put_rouny_document):
        json_request.return_value = {"baseRevision": 2, "templates": []}
        put_rouny_document.side_effect = server.RounyConflict(
            {"ok": True, "scope": "family", "revision": 3, "templates": [], "updatedAt": ""}
        )
        handler = mock.Mock()
        handler.path = "/api/rouny/templates"
        handler.headers = {"Host": "family.kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_PUT(handler)

        handler.send_response.assert_called_once_with(409)
        payload = json.loads(handler.wfile.getvalue())
        self.assertEqual(payload["error"], "rouny_revision_conflict")
        self.assertEqual(payload["document"]["revision"], 3)


class RecurringTaskRequestTests(unittest.TestCase):
    @mock.patch.object(server.recurring_task_service, "list_definitions")
    def test_list_uses_host_profile(self, list_definitions):
        list_definitions.return_value = {"ok": True, "items": []}
        handler = mock.Mock()
        handler.path = "/api/recurring-tasks"
        handler.headers = {"Host": "family.kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_GET(handler)

        list_definitions.assert_called_once_with("family")
        handler.send_response.assert_called_once_with(200)

    @mock.patch.object(server.recurring_task_service, "create_definition")
    @mock.patch.object(server, "json_request")
    def test_create_uses_host_profile(self, json_request, create_definition):
        json_request.return_value = {"title": "Review"}
        create_definition.return_value = {"id": "repeat-1", "title": "Review"}
        handler = mock.Mock()
        handler.path = "/api/recurring-tasks"
        handler.headers = {"Host": "kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_POST(handler)

        create_definition.assert_called_once_with({"title": "Review"}, "main")
        handler.send_response.assert_called_once_with(201)

    @mock.patch.object(server.recurring_task_service, "delete_definition")
    def test_delete_definition(self, delete_definition):
        delete_definition.return_value = {"ok": True, "id": "repeat-1"}
        handler = mock.Mock()
        handler.path = "/api/recurring-tasks/repeat-1"
        handler.headers = {"Host": "kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_DELETE(handler)

        delete_definition.assert_called_once_with("repeat-1", "main")
        handler.send_response.assert_called_once_with(200)


class EventPresetRequestTests(unittest.TestCase):
    @mock.patch.object(server.event_preset_service, "list_items")
    def test_list_uses_family_host_profile(self, list_items):
        list_items.return_value = {"ok": True, "items": []}
        handler = mock.Mock()
        handler.path = "/api/event-presets"
        handler.headers = {"Host": "family.kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_GET(handler)

        list_items.assert_called_once_with("family")
        handler.send_response.assert_called_once_with(200)

    @mock.patch.object(server.event_preset_service, "create_item")
    @mock.patch.object(server, "json_request")
    def test_create_uses_main_host_profile(self, json_request, create_item):
        json_request.return_value = {"name": "Duty", "title": "Duty"}
        create_item.return_value = {"id": "preset-1", "name": "Duty", "title": "Duty"}
        handler = mock.Mock()
        handler.path = "/api/event-presets"
        handler.headers = {"Host": "kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_POST(handler)

        create_item.assert_called_once_with({"name": "Duty", "title": "Duty"}, "main")
        handler.send_response.assert_called_once_with(201)

    @mock.patch.object(server.event_preset_service, "delete_item")
    def test_delete_checks_portal_scope(self, delete_item):
        delete_item.return_value = {"ok": True, "id": "preset-1"}
        handler = mock.Mock()
        handler.path = "/api/event-presets/preset-1"
        handler.headers = {"Host": "family.kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_DELETE(handler)

        delete_item.assert_called_once_with("preset-1", "family")
        handler.send_response.assert_called_once_with(200)


if __name__ == "__main__":
    unittest.main()

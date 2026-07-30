import pathlib
import sys
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.calendar import upstream


class UpstreamBoundaryTests(unittest.TestCase):
    def test_portal_host_keeps_only_known_profiles(self):
        self.assertEqual(upstream.portal_host({"Host": "family.kaosgdd.net"}), "family.kaosgdd.net")
        self.assertEqual(upstream.portal_host({"X-Forwarded-Host": "kaosgdd.net"}), "kaosgdd.net")
        self.assertEqual(upstream.portal_host({"Host": "paperless.kaosgdd.net"}), "kaosgdd.net")

    def test_upstream_url_allows_only_calendar_routes_for_each_method(self):
        with mock.patch.dict(
            "os.environ",
            {"CALENDAR_ADAPTER_INTERNAL_URL": "http://adapter:8091"},
            clear=False,
        ):
            self.assertEqual(
                upstream.upstream_url("GET", "/api/calendar/bootstrap"),
                "http://adapter:8091/api/calendar/bootstrap",
            )
            self.assertEqual(
                upstream.upstream_url("GET", "/api/weather/month?city=pohang"),
                "http://adapter:8091/api/weather/month?city=pohang",
            )
            self.assertEqual(
                upstream.upstream_url("POST", "/api/calendar/events"),
                "http://adapter:8091/api/calendar/events",
            )
            self.assertEqual(
                upstream.upstream_url("DELETE", "/api/calendar/tasks"),
                "http://adapter:8091/api/calendar/tasks",
            )
            with self.assertRaisesRegex(ValueError, "upstream_route_not_allowed"):
                upstream.upstream_url("GET", "/api/calendar/events")
            with self.assertRaisesRegex(ValueError, "upstream_route_not_allowed"):
                upstream.upstream_url("POST", "/internal/system/weather")

    def test_route_allowed_matches_method_and_ignores_query(self):
        self.assertTrue(upstream.route_allowed("GET", "/api/weather/month?city=pohang"))
        self.assertTrue(upstream.route_allowed("PUT", "/api/calendar/tasks"))
        self.assertFalse(upstream.route_allowed("GET", "/api/calendar/tasks"))
        self.assertFalse(upstream.route_allowed("POST", "/internal/system/logs"))

    @mock.patch.object(upstream.urllib.request, "urlopen")
    def test_request_upstream_preserves_write_contract(self, urlopen):
        response = mock.MagicMock()
        response.status = 201
        response.headers.get.return_value = "application/json"
        response.read.return_value = b'{"ok":true}'
        response.__enter__.return_value = response
        urlopen.return_value = response

        result = upstream.request_upstream(
            "POST",
            "/api/calendar/tasks",
            "family.kaosgdd.net",
            body=b'{"title":"test"}',
            content_type="application/json",
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(result, (201, "application/json", b'{"ok":true}'))
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.data, b'{"title":"test"}')
        self.assertEqual(request.get_header("Host"), "family.kaosgdd.net")
        self.assertEqual(request.get_header("X-forwarded-host"), "family.kaosgdd.net")
        self.assertEqual(request.get_header("Content-type"), "application/json")


if __name__ == "__main__":
    unittest.main()

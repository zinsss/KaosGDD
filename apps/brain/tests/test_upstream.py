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

    def test_upstream_url_allows_only_shadow_read_routes(self):
        with mock.patch.dict(
            "os.environ",
            {"CALENDAR_ADAPTER_INTERNAL_URL": "http://adapter:8091"},
            clear=False,
        ):
            self.assertEqual(
                upstream.upstream_url("/api/calendar/bootstrap"),
                "http://adapter:8091/api/calendar/bootstrap",
            )
            self.assertEqual(
                upstream.upstream_url("/api/weather/month?city=pohang"),
                "http://adapter:8091/api/weather/month?city=pohang",
            )
            with self.assertRaisesRegex(ValueError, "upstream_path_not_allowed"):
                upstream.upstream_url("/api/calendar/events")


if __name__ == "__main__":
    unittest.main()

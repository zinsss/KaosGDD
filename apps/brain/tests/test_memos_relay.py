import json
import pathlib
import sys
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.memos import relay


class MemosRelayRouteTests(unittest.TestCase):
    def test_only_daily_memo_routes_are_allowed(self):
        self.assertTrue(relay.route_allowed("GET", "/api/memos/api/v1/auth/me"))
        self.assertTrue(relay.route_allowed("GET", "/api/memos/api/v1/memos?pageSize=50"))
        self.assertTrue(relay.route_allowed("PATCH", "/api/memos/api/v1/memos/abc?updateMask=content"))
        self.assertFalse(relay.route_allowed("POST", "/api/memos/api/v1/auth/signin"))
        self.assertFalse(relay.route_allowed("GET", "/api/memos/api/v1/users"))

    def test_unknown_host_has_no_profile(self):
        with self.assertRaisesRegex(relay.MemosRelayError, "memos_relay_profile_not_found"):
            relay.profile_for_headers({"Host": "memos.kaosgdd.net"})


class MemosRelayBootstrapTests(unittest.TestCase):
    @mock.patch.dict("os.environ", {"MEMOS_PERSONAL_USERNAME": "zin"}, clear=False)
    @mock.patch.object(relay, "store_token")
    @mock.patch.object(relay, "upstream_request")
    @mock.patch.object(relay, "load_token")
    @mock.patch.object(relay, "verify_cloudflare_access")
    def test_existing_refresh_cookie_is_converted_to_pat(
        self,
        verify_access,
        load_token,
        upstream_request,
        store_token,
    ):
        verify_access.return_value = ("personal", "owner@example.test")
        load_token.side_effect = relay.MemosRelayError(503, "memos_relay_profile_not_configured")
        current = {"user": {"name": "users/zin", "username": "zin"}}
        upstream_request.side_effect = [
            (200, "application/json", b'{"accessToken":"short-token"}'),
            (200, "application/json", json.dumps(current).encode()),
            (200, "application/json", b'{"token":"memos_pat_secret"}'),
        ]

        result = relay.bootstrap(
            {"Host": "kaosgdd.net", "Cookie": "memos.refresh_token=existing"},
            {},
        )

        self.assertEqual(result, current)
        store_token.assert_called_once_with("personal", "zin", "memos_pat_secret")
        self.assertEqual(upstream_request.call_args_list[0].kwargs["cookie"], "memos.refresh_token=existing")
        self.assertEqual(upstream_request.call_args_list[2].kwargs["access_token"], "short-token")

    @mock.patch.dict("os.environ", {"MEMOS_FAMILY_USERNAME": "my02"}, clear=False)
    @mock.patch.object(relay, "load_token")
    @mock.patch.object(relay, "verify_cloudflare_access")
    def test_password_fallback_cannot_provision_wrong_profile(self, verify_access, load_token):
        verify_access.return_value = ("family", "family@example.test")
        load_token.side_effect = relay.MemosRelayError(503, "memos_relay_profile_not_configured")

        with self.assertRaisesRegex(relay.MemosRelayError, "memos_bootstrap_profile_mismatch"):
            relay.bootstrap(
                {"Host": "family.kaosgdd.net"},
                {"username": "zin", "password": "secret"},
            )


class MemosRelayProxyTests(unittest.TestCase):
    @mock.patch.object(relay, "upstream_request")
    @mock.patch.object(relay, "load_token")
    @mock.patch.object(relay, "verify_cloudflare_access")
    def test_relay_uses_profile_pat(self, verify_access, load_token, upstream_request):
        verify_access.return_value = ("family", "family@example.test")
        load_token.return_value = "family-pat"
        upstream_request.return_value = (200, "application/json", b'{"memos":[]}')

        result = relay.relay(
            "GET",
            "/api/memos/api/v1/memos?pageSize=50",
            {"Host": "family.kaosgdd.net", "Authorization": "Bearer browser-token"},
        )

        self.assertEqual(result[0], 200)
        upstream_request.assert_called_once_with(
            "GET",
            "/api/v1/memos?pageSize=50",
            body=None,
            access_token="family-pat",
        )

    def test_access_assertion_is_mandatory(self):
        with self.assertRaisesRegex(relay.MemosRelayError, "cloudflare_access_required"):
            relay.verify_cloudflare_access({"Host": "kaosgdd.net"})

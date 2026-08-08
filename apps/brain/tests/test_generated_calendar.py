import pathlib
import sys
import unittest
from datetime import date
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.system_calendar import generated


class GeneratedCalendarDateTests(unittest.TestCase):
    def test_market_days_are_fixed_dates_on_every_weekday(self):
        values = generated.market_dates(2026)
        self.assertEqual({value.day for value in values}, {5, 10, 15, 20, 25, 30})
        self.assertTrue(any(value.weekday() == 5 for value in values))
        self.assertTrue(any(value.weekday() != 5 for value in values))

    def test_market_saturday_moves_claim_to_saturday(self):
        self.assertEqual(
            generated.claim_date_for_friday(date(2026, 1, 9)),
            date(2026, 1, 10),
        )

    def test_public_market_saturday_keeps_claim_on_friday(self):
        self.assertEqual(
            generated.claim_date_for_friday(date(2026, 1, 9), {date(2026, 1, 10)}),
            date(2026, 1, 9),
        )

    def test_public_friday_moves_claim_backward_repeatedly(self):
        public = {date(2026, 1, 1), date(2026, 1, 2)}
        self.assertEqual(generated.claim_date_for_friday(date(2026, 1, 2), public), date(2025, 12, 31))

    def test_market_display_setting_does_not_change_claim_rule(self):
        items = generated.desired_events(
            [2026],
            set(),
            {"marketDaysEnabled": False, "claimDayEnabled": True},
        )
        self.assertFalse(any(generated.MARKET_CATEGORY in item["categories"] for item in items))
        claim = next(item for item in items if item["uid"] == "KAOS-CLAIM-WEEK-2026-01-09")
        self.assertEqual(claim["startDate"], "2026-01-10")


class GeneratedCalendarSyncTests(unittest.TestCase):
    @mock.patch.object(generated.holidays, "list_holidays", return_value={"ok": True, "items": []})
    @mock.patch.object(generated, "get_settings")
    @mock.patch.object(generated, "_adapter_request")
    def test_sync_skips_unchanged_and_removes_only_stale_managed_years(
        self, adapter_request, get_settings, _list_holidays
    ):
        get_settings.return_value = {"marketDaysEnabled": True, "claimDayEnabled": False, "updatedAt": ""}
        current = generated.market_event(date(2026, 1, 5))
        adapter_request.return_value = {
            "ok": True,
            "items": [
                {**current, "summary": current["title"], "description": current["memo"]},
                {
                    "uid": "KAOS-MARKET-2026-01-06",
                    "summary": "Market Day",
                    "startDate": "2026-01-06",
                    "endDate": "2026-01-06",
                    "categories": [generated.SYSTEM_CATEGORY, generated.GENERATED_CATEGORY, generated.MARKET_CATEGORY],
                },
                {
                    "uid": "KAOS-MARKET-2025-12-30",
                    "summary": "Market Day",
                    "startDate": "2025-12-30",
                    "endDate": "2025-12-30",
                    "categories": [generated.SYSTEM_CATEGORY, generated.GENERATED_CATEGORY, generated.MARKET_CATEGORY],
                },
            ],
        }

        generated.sync_generated_calendar(today=date(2026, 8, 8))

        delete_payloads = [call.args[1] for call in adapter_request.call_args_list if call.args[0] == "DELETE"]
        self.assertEqual(delete_payloads, [{"uid": "KAOS-MARKET-2026-01-06"}])
        put_payloads = [call.args[1] for call in adapter_request.call_args_list if call.args[0] == "PUT"]
        self.assertNotIn(current, put_payloads)


if __name__ == "__main__":
    unittest.main()

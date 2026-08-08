import pathlib
import sys
import unittest
from datetime import date
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.system_calendar import holidays


GOOGLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260815
DTEND;VALUE=DATE:20260816
UID:holiday-1@google.com
SUMMARY:광복절
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261001
DTEND;VALUE=DATE:20261002
UID:observance-1@google.com
SUMMARY:국군의 날
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20280101
UID:outside-range@google.com
SUMMARY:Outside range
END:VEVENT
END:VCALENDAR
"""


class HolidayParsingTests(unittest.TestCase):
    def test_parses_current_and_next_year_google_events(self):
        items = holidays.parse_google_calendar(GOOGLE_ICS, today=date(2026, 8, 8))

        self.assertEqual([item["title"] for item in items], ["광복절", "국군의 날"])
        self.assertEqual(items[0]["startDate"], "2026-08-15")
        self.assertEqual(items[0]["endDate"], "2026-08-15")
        self.assertRegex(items[0]["uid"], r"^KAOS-HOLIDAY-[A-F0-9]{24}$")

    def test_default_classification_separates_holidays_from_observances(self):
        self.assertTrue(holidays.default_public_holiday("설날 연휴"))
        self.assertTrue(holidays.default_public_holiday("쉬는 날 광복절"))
        self.assertFalse(holidays.default_public_holiday("어버이날"))
        self.assertFalse(holidays.default_public_holiday("식목일"))


class HolidaySyncTests(unittest.TestCase):
    @mock.patch.object(holidays, "fetch_google_calendar")
    @mock.patch.object(holidays, "_adapter_request")
    def test_sync_preserves_manual_public_classification_and_deletes_stale(self, adapter_request, fetch_google):
        current_uid = holidays.holiday_uid("holiday-1@google.com")
        stale_uid = holidays.holiday_uid("stale@google.com")
        fetch_google.return_value = [
            {
                "uid": current_uid,
                "externalUid": "holiday-1@google.com",
                "title": "광복절",
                "startDate": "2026-08-15",
                "endDate": "2026-08-15",
            }
        ]

        def request(method, payload=None):
            if method == "GET":
                return {
                    "ok": True,
                    "items": [
                        {
                            "uid": current_uid,
                            "summary": "광복절",
                            "startDate": "2026-08-15",
                            "endDate": "2026-08-15",
                            "publicHoliday": True,
                            "categories": [holidays.PUBLIC_CATEGORY],
                        },
                        {
                            "uid": stale_uid,
                            "summary": "Old",
                            "startDate": "2026-09-01",
                            "endDate": "2026-09-01",
                            "publicHoliday": False,
                            "categories": [holidays.OBSERVANCE_CATEGORY],
                        },
                    ],
                }
            if method == "PUT":
                self.assertIn(holidays.PUBLIC_CATEGORY, payload["categories"])
                return {"ok": True, "created": False}
            if method == "DELETE":
                self.assertEqual(payload["uid"], stale_uid)
                return {"ok": True, "deleted": True}
            raise AssertionError(method)

        adapter_request.side_effect = request
        result = holidays.sync_holidays(today=date(2026, 8, 8))

        self.assertEqual(result, {"ok": True, "created": 0, "updated": 1, "deleted": 1, "total": 1})

    @mock.patch.object(holidays, "_adapter_request")
    def test_classification_toggle_updates_only_standard_categories(self, adapter_request):
        uid = holidays.holiday_uid("holiday-1@google.com")
        adapter_request.side_effect = [
            {
                "ok": True,
                "items": [
                    {
                        "uid": uid,
                        "summary": "광복절",
                        "description": "Google Korea Holidays",
                        "startDate": "2026-08-15",
                        "endDate": "2026-08-15",
                        "categories": [holidays.SYSTEM_CATEGORY, holidays.SOURCE_CATEGORY, holidays.OBSERVANCE_CATEGORY],
                    }
                ],
            },
            {"ok": True, "created": False},
        ]

        result = holidays.set_public_holiday(uid, True)

        self.assertTrue(result["item"]["publicHoliday"])
        payload = adapter_request.call_args_list[1].args[1]
        self.assertEqual(
            set(payload["categories"]),
            {holidays.SYSTEM_CATEGORY, holidays.SOURCE_CATEGORY, holidays.PUBLIC_CATEGORY},
        )


if __name__ == "__main__":
    unittest.main()

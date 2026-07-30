import pathlib
import sys
import unittest


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.caregiver.summary import calculate_month, settings_for_month, validate_day, validate_month


class CaregiverSummaryTests(unittest.TestCase):
    def test_validates_month(self):
        self.assertEqual(validate_month("2026-07"), "2026-07")
        for value in ("", "2026-7", "2026-13", "1999-12"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "invalid_caregiver_month"):
                    validate_month(value)

    def test_validates_day(self):
        self.assertEqual(validate_day("2026-07-30"), "2026-07-30")
        for value in ("", "2026-7-30", "2026-02-30", "1999-12-31"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "invalid_caregiver_date"):
                    validate_day(value)

    def test_uses_latest_monthly_setting_at_or_before_selected_month(self):
        setting = settings_for_month(
            [
                {"month": "2026-06", "hourlyWage": 12000, "transportFee": 100000},
                {"month": "2026-07", "hourlyWage": 13000, "transportFee": 120000},
                {"month": "2026-09", "hourlyWage": 14000, "transportFee": 130000},
            ],
            "2026-08",
        )

        self.assertEqual(
            setting,
            {
                "month": "2026-08",
                "sourceMonth": "2026-07",
                "hourlyWage": 13000,
                "transportFee": 120000,
            },
        )

    def test_calculates_legacy_monthly_review_fields_from_minutes(self):
        payload = calculate_month(
            "2026-07",
            [
                {
                    "date": "2026-07-01",
                    "sessions": [
                        {"start": "09:00", "end": "12:30"},
                        {"start": "14:00", "end": "16:00"},
                    ],
                    "extras": [{"label": "추가", "amount": 10000}],
                },
                {
                    "date": "2026-07-02",
                    "sessions": [{"start": "09:00", "end": "10:15"}],
                    "extras": [],
                },
                {
                    "date": "2026-08-01",
                    "sessions": [{"start": "09:00", "end": "18:00"}],
                    "extras": [],
                },
            ],
            [{"month": "2026-06", "hourlyWage": 12000, "transportFee": 100000}],
        )

        self.assertEqual(payload["summary"]["days"], 2)
        self.assertEqual(payload["summary"]["minutes"], 405)
        self.assertEqual(payload["summary"]["hours"], 6.75)
        self.assertEqual(payload["summary"]["hourlyWage"], 12000)
        self.assertEqual(payload["summary"]["basePay"], 81000)
        self.assertEqual(payload["summary"]["extras"], 10000)
        self.assertEqual(payload["summary"]["transportFee"], 100000)
        self.assertEqual(payload["summary"]["total"], 191000)
        self.assertEqual(payload["daily"][0]["notes"], "추가 10,000")
        self.assertEqual(
            payload["daily"][0]["sessions"],
            [
                {"start": "09:00", "end": "12:30"},
                {"start": "14:00", "end": "16:00"},
            ],
        )
        self.assertEqual(payload["daily"][0]["extraItems"], [{"label": "추가", "amount": 10000}])
        self.assertEqual(len(payload["daily"]), 31)

    def test_rounds_half_won_like_legacy_javascript(self):
        payload = calculate_month(
            "2026-07",
            [{"date": "2026-07-01", "sessions": [{"start": "09:00", "end": "09:01"}]}],
            [{"month": "2026-07", "hourlyWage": 30, "transportFee": 0}],
        )

        self.assertEqual(payload["daily"][0]["basePay"], 1)
        self.assertEqual(payload["summary"]["basePay"], 1)


if __name__ == "__main__":
    unittest.main()

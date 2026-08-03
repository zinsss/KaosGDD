import pathlib
import sys
import unittest
from datetime import time


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.event_presets import service


class EventPresetValidationTests(unittest.TestCase):
    def payload(self, **overrides):
        payload = {
            "name": "Clinic duty",
            "title": "Duty",
            "allDay": True,
            "startTime": "09:00",
            "endTime": "10:00",
            "alarm": "",
            "memo": "",
            "shareFamily": False,
        }
        payload.update(overrides)
        return payload

    def test_personal_owner_follows_portal_profile(self):
        self.assertEqual(service.validate_payload(self.payload(), "main")["owner"], "zin")
        self.assertEqual(service.validate_payload(self.payload(), "family")["owner"], "wife")

    def test_shared_owner_is_visible_to_both_profiles(self):
        self.assertEqual(service.validate_payload(self.payload(shareFamily=True), "main")["owner"], "family")
        self.assertIn("family", service.owners_for_profile("main"))
        self.assertIn("family", service.owners_for_profile("family"))

    def test_times_use_five_minute_steps(self):
        item = service.validate_payload(self.payload(startTime="09:05", alarm="08:55"), "main")
        self.assertEqual(item["start_time"], time(9, 5))
        self.assertEqual(item["alarm_time"], time(8, 55))
        with self.assertRaisesRegex(ValueError, "invalid_endTime_step"):
            service.validate_payload(self.payload(endTime="10:03"), "main")

    def test_name_and_title_are_required(self):
        with self.assertRaisesRegex(ValueError, "name_required"):
            service.validate_payload(self.payload(name=""), "main")
        with self.assertRaisesRegex(ValueError, "title_required"):
            service.validate_payload(self.payload(title=""), "main")


if __name__ == "__main__":
    unittest.main()

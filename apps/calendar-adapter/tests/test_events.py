import importlib.util
import pathlib
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("calendar_adapter_server", MODULE_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


TIMED_EVENT = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:EVENT-1
DTSTAMP:20260729T010000Z
CREATED:20260728T010000Z
LAST-MODIFIED:20260729T010000Z
SEQUENCE:3
SUMMARY:Old title
DESCRIPTION:Old memo
LOCATION:Clinic
DTSTART;TZID=Asia/Seoul:20260730T090000
DTEND;TZID=Asia/Seoul:20260730T100000
RRULE:FREQ=WEEKLY
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER;VALUE=DATE-TIME:20260729T234500Z
DESCRIPTION:Old title
END:VALARM
END:VEVENT
END:VCALENDAR
"""


class EventParsingTests(unittest.TestCase):
    def test_normalizes_timed_event_edit_fields(self):
        item = SERVER.parse_ics(TIMED_EVENT, "/zin/calendar/EVENT-1.ics", '"etag-1"')[0]
        normalized = SERVER.normalize_event(item, {"id": "zin:calendar"})

        self.assertEqual(normalized["startDate"], "2026-07-30")
        self.assertEqual(normalized["startTime"], "09:00")
        self.assertEqual(normalized["endDate"], "2026-07-30")
        self.assertEqual(normalized["endTime"], "10:00")
        self.assertEqual(normalized["repeat"], "weekly")
        self.assertEqual(normalized["alarmTime"], "08:45")
        self.assertTrue(normalized["editable"])
        self.assertEqual(item["etag"], '"etag-1"')

    def test_normalizes_all_day_end_as_inclusive(self):
        body = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:ALL-DAY
SUMMARY:Holiday
DTSTART;VALUE=DATE:20260730
DTEND;VALUE=DATE:20260801
END:VEVENT
END:VCALENDAR
"""
        item = SERVER.parse_ics(body, "/family/calendar/ALL-DAY.ics")[0]
        normalized = SERVER.normalize_event(item, {"id": "family:calendar"})

        self.assertTrue(normalized["allDay"])
        self.assertEqual(normalized["startDate"], "2026-07-30")
        self.assertEqual(normalized["endDate"], "2026-07-31")

    def test_marks_multi_component_resource_unsafe_to_edit(self):
        item = SERVER.parse_ics(TIMED_EVENT, "/zin/calendar/EVENT-1.ics")[0]
        item["_unsafe_multiple"] = True

        normalized = SERVER.normalize_event(item, {"id": "zin:calendar"})

        self.assertFalse(normalized["editable"])
        self.assertEqual(normalized["editReason"], "event_requires_native_client")

    def test_marks_recurrence_exceptions_unsafe_to_edit(self):
        body = TIMED_EVENT.replace("RRULE:FREQ=WEEKLY", "RRULE:FREQ=WEEKLY\nEXDATE;TZID=Asia/Seoul:20260806T090000")
        item = SERVER.parse_ics(body, "/zin/calendar/EVENT-1.ics")[0]

        normalized = SERVER.normalize_event(item, {"id": "zin:calendar"})

        self.assertFalse(normalized["editable"])
        self.assertEqual(normalized["repeat"], "custom")
        self.assertTrue(normalized["preserveRepeat"])


class EventWritingTests(unittest.TestCase):
    def test_update_preserves_standard_properties_and_increments_sequence(self):
        existing = SERVER.parse_ics(TIMED_EVENT, "/zin/calendar/EVENT-1.ics", '"etag-1"')[0]
        _, body = SERVER.build_vevent(
            {
                "uid": "EVENT-1",
                "title": "New title",
                "memo": "New memo",
                "startDate": "2026-07-31",
                "startTime": "11:00",
                "endDate": "2026-07-31",
                "endTime": "12:00",
                "repeat": "monthly",
                "alarmTime": "10:30",
            },
            existing,
        )

        self.assertIn("UID:EVENT-1", body)
        self.assertIn("CREATED:20260728T010000Z", body)
        self.assertIn("SEQUENCE:4", body)
        self.assertIn("LOCATION:Clinic", body)
        self.assertIn("SUMMARY:New title", body)
        self.assertIn("DESCRIPTION:New memo", body)
        self.assertIn("RRULE:FREQ=MONTHLY", body)
        self.assertNotIn("SUMMARY:Old title", body)

    def test_update_can_preserve_custom_recurrence_and_relative_alarm(self):
        body = TIMED_EVENT.replace("RRULE:FREQ=WEEKLY", "RRULE:FREQ=WEEKLY;BYDAY=MO,WE").replace(
            "TRIGGER;VALUE=DATE-TIME:20260729T234500Z",
            "TRIGGER:-PT30M",
        )
        existing = SERVER.parse_ics(body, "/zin/calendar/EVENT-1.ics")[0]
        normalized = SERVER.normalize_event(existing, {"id": "zin:calendar"})
        _, updated = SERVER.build_vevent(
            {
                "uid": "EVENT-1",
                "title": "Preserved",
                "startDate": "2026-07-30",
                "startTime": "09:00",
                "endDate": "2026-07-30",
                "endTime": "10:00",
                "preserveRepeat": normalized["preserveRepeat"],
                "preserveAlarm": normalized["preserveAlarm"],
            },
            existing,
        )

        self.assertEqual(normalized["repeat"], "custom")
        self.assertTrue(normalized["preserveRepeat"])
        self.assertTrue(normalized["preserveAlarm"])
        self.assertIn("RRULE:FREQ=WEEKLY;BYDAY=MO,WE", updated)
        self.assertIn("TRIGGER:-PT30M", updated)

    @mock.patch.object(SERVER, "configured", return_value=True)
    @mock.patch.object(SERVER, "collections_for_profile")
    @mock.patch.object(SERVER, "account_for_collection", return_value={"username": "zin"})
    @mock.patch.object(SERVER, "report_collection")
    @mock.patch.object(SERVER, "radicale_request")
    def test_update_uses_etag_guard(
        self,
        radicale_request,
        report_collection,
        _account_for_collection,
        collections_for_profile,
        _configured,
    ):
        collection = {
            "id": "zin:calendar",
            "owner": "zin",
            "href": "/zin/calendar/",
            "components": ["VEVENT"],
        }
        collections_for_profile.return_value = [collection]
        report_collection.return_value = [
            SERVER.parse_ics(TIMED_EVENT, "/zin/calendar/EVENT-1.ics", '"etag-1"')[0]
        ]

        SERVER.update_event(
            {
                "uid": "EVENT-1",
                "collectionId": "zin:calendar",
                "title": "Updated",
                "startDate": "2026-07-30",
                "startTime": "09:00",
                "endDate": "2026-07-30",
                "endTime": "10:00",
            }
        )

        self.assertEqual(radicale_request.call_args.args[1], "PUT")
        self.assertEqual(radicale_request.call_args.args[2], "/zin/calendar/EVENT-1.ics")
        self.assertEqual(radicale_request.call_args.args[4]["If-Match"], '"etag-1"')

    @mock.patch.object(SERVER, "configured", return_value=True)
    @mock.patch.object(SERVER, "collections_for_profile")
    @mock.patch.object(SERVER, "account_for_collection", return_value={"username": "zin"})
    @mock.patch.object(SERVER, "report_collection")
    @mock.patch.object(SERVER, "radicale_request")
    def test_delete_uses_etag_guard(
        self,
        radicale_request,
        report_collection,
        _account_for_collection,
        collections_for_profile,
        _configured,
    ):
        collection = {
            "id": "zin:calendar",
            "owner": "zin",
            "href": "/zin/calendar/",
            "components": ["VEVENT"],
        }
        collections_for_profile.return_value = [collection]
        report_collection.return_value = [
            SERVER.parse_ics(TIMED_EVENT, "/zin/calendar/EVENT-1.ics", '"etag-1"')[0]
        ]

        SERVER.delete_event({"uid": "EVENT-1", "collectionId": "zin:calendar"})

        self.assertEqual(
            radicale_request.call_args.args,
            (
                {"username": "zin"},
                "DELETE",
                "/zin/calendar/EVENT-1.ics",
                "",
                {"If-Match": '"etag-1"'},
            ),
        )


class PortalProfileTests(unittest.TestCase):
    def test_family_profile_only_exposes_shared_account(self):
        configured = {key: value["configured"] for key, value in SERVER.ACCOUNTS.items()}
        try:
            SERVER.ACCOUNTS["wife"]["configured"] = True
            SERVER.ACCOUNTS["family"]["configured"] = True
            self.assertEqual(
                [account["key"] for account in SERVER.profile_accounts("family")],
                ["family"],
            )
        finally:
            for key, value in configured.items():
                SERVER.ACCOUNTS[key]["configured"] = value


class CaregiverJournalTests(unittest.TestCase):
    def test_builds_deterministic_daily_journal(self):
        uid, body = SERVER.build_caregiver_day_vjournal(
            {
                "date": "2026-07-30",
                "sessions": [
                    {"start": "09:00", "end": "12:30"},
                    {"start": "14:00", "end": "16:00"},
                ],
                "extras": [{"label": "추가", "amount": 10000}],
            }
        )
        item = SERVER.parse_ics(body, f"/kaos/caregiver/{uid}.ics")[0]
        record = SERVER.parse_caregiver_journal(item, {"id": "system:caregiver"})

        self.assertEqual(uid, "KAOS-CAREGIVER-DAY-20260730")
        self.assertEqual(record["type"], "caregiver.day")
        self.assertEqual(record["date"], "2026-07-30")
        self.assertEqual(record["sessions"][0], {"start": "09:00", "end": "12:30"})
        self.assertEqual(record["extras"], [{"label": "추가", "amount": 10000}])

    def test_rejects_invalid_daily_session(self):
        with self.assertRaisesRegex(ValueError, "caregiver_end_before_start"):
            SERVER.build_caregiver_day_vjournal(
                {
                    "date": "2026-07-30",
                    "sessions": [{"start": "12:00", "end": "09:00"}],
                }
            )

    def test_builds_monthly_settings_journal(self):
        uid, body = SERVER.build_caregiver_settings_vjournal(
            {"month": "2026-07", "hourlyWage": 13000, "transportFee": 120000}
        )
        item = SERVER.parse_ics(body, f"/kaos/caregiver/{uid}.ics")[0]
        record = SERVER.parse_caregiver_journal(item, {"id": "system:caregiver"})

        self.assertEqual(uid, "KAOS-CAREGIVER-SETTINGS-202607")
        self.assertEqual(record["month"], "2026-07")
        self.assertEqual(record["hourlyWage"], 13000)
        self.assertEqual(record["transportFee"], 120000)

    @mock.patch.object(SERVER, "radicale_request")
    @mock.patch.object(SERVER, "system_collection")
    def test_deletes_deterministic_daily_journal(self, system_collection, radicale_request):
        system_collection.return_value = {
            "id": "system:caregiver",
            "href": "/kaos/caregiver/",
        }

        result = SERVER.delete_caregiver_day({"date": "2026-07-30"})

        self.assertEqual(result["uid"], "KAOS-CAREGIVER-DAY-20260730")
        radicale_request.assert_called_once_with(
            SERVER.ACCOUNTS["system"],
            "DELETE",
            "/kaos/caregiver/KAOS-CAREGIVER-DAY-20260730.ics",
        )

    @mock.patch.object(SERVER, "system_collection")
    @mock.patch.object(SERVER, "report_collection")
    def test_lists_selected_month_and_all_settings(self, report_collection, system_collection):
        collection = {"id": "system:caregiver", "href": "/kaos/caregiver/"}
        system_collection.return_value = collection
        day_uid, day_body = SERVER.build_caregiver_day_vjournal(
            {
                "date": "2026-07-30",
                "sessions": [{"start": "09:00", "end": "12:30"}],
            }
        )
        other_uid, other_body = SERVER.build_caregiver_day_vjournal(
            {
                "date": "2026-08-01",
                "sessions": [{"start": "09:00", "end": "10:00"}],
            }
        )
        settings_uid, settings_body = SERVER.build_caregiver_settings_vjournal(
            {"month": "2026-06", "hourlyWage": 12000, "transportFee": 100000}
        )
        report_collection.return_value = [
            SERVER.parse_ics(day_body, f"/kaos/caregiver/{day_uid}.ics")[0],
            SERVER.parse_ics(other_body, f"/kaos/caregiver/{other_uid}.ics")[0],
            SERVER.parse_ics(settings_body, f"/kaos/caregiver/{settings_uid}.ics")[0],
        ]

        payload = SERVER.list_caregiver_journals("2026-07")

        self.assertEqual([item["date"] for item in payload["days"]], ["2026-07-30"])
        self.assertEqual([item["month"] for item in payload["settings"]], ["2026-06"])


if __name__ == "__main__":
    unittest.main()

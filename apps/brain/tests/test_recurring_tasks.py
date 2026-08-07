import pathlib
import sys
import unittest
from datetime import date, time
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.recurring_tasks import service


class RecurringTaskValidationTests(unittest.TestCase):
    def test_profile_owners_are_isolated_except_family(self):
        self.assertEqual(service.owners_for_profile("main"), ("zin", "family"))
        self.assertEqual(service.owners_for_profile("family"), ("family",))

    def test_payload_uses_portal_personal_owner(self):
        payload = {
            "title": "Medication review",
            "firstDueDate": "2026-08-03",
            "dueTime": "10:00",
            "priority": "5",
            "frequency": "weekly",
        }
        self.assertEqual(service.validate_payload(payload, "main")["owner"], "zin")
        self.assertEqual(service.validate_payload(payload, "family")["owner"], "family")
        payload["shareFamily"] = True
        self.assertEqual(service.validate_payload(payload, "main")["owner"], "family")

    def test_due_time_requires_five_minute_step(self):
        with self.assertRaisesRegex(ValueError, "invalid_dueTime_step"):
            service.validate_time("10:03")
        self.assertEqual(service.validate_time("10:05"), time(10, 5))


class RecurringTaskDateTests(unittest.TestCase):
    def test_monthly_schedule_preserves_original_day(self):
        anchor = date(2027, 1, 31)
        february = service.next_scheduled_date(anchor, "monthly", anchor=anchor)
        march = service.next_scheduled_date(february, "monthly", anchor=anchor)
        self.assertEqual(february, date(2027, 2, 28))
        self.assertEqual(march, date(2027, 3, 31))

    def test_yearly_schedule_recovers_after_leap_day(self):
        anchor = date(2028, 2, 29)
        following = service.next_scheduled_date(anchor, "yearly", anchor=anchor)
        recovered = service.next_scheduled_date(following, "yearly", anchor=anchor)
        self.assertEqual(following, date(2029, 2, 28))
        self.assertEqual(recovered, date(2030, 2, 28))

    def test_missed_dates_fast_forward_to_current_schedule(self):
        self.assertEqual(
            service.date_on_or_after(date(2026, 7, 1), "weekly", today=date(2026, 8, 3)),
            date(2026, 8, 5),
        )

    def test_occurrence_uid_is_stable_for_definition_and_date(self):
        item = {"id": "45a6ad4c-bef1-4322"}
        self.assertEqual(
            service.occurrence_uid(item, date(2026, 8, 3)),
            "KAOSGDD-REPEAT-45A6AD4CBEF14322-20260803",
        )


class RecurringTaskSynchronizationTests(unittest.TestCase):
    def definition(self, **overrides):
        item = {
            "id": "repeat-1",
            "owner": "zin",
            "adapter_profile": "main",
            "collection_id": "zin:tasks",
            "title": "Weekly review",
            "memo": "",
            "first_due_date": date(2026, 8, 3),
            "due_time": time(10, 0),
            "priority": "",
            "frequency": "weekly",
            "active_uid": None,
            "active_collection_id": None,
            "active_due_date": None,
            "next_due_date": date(2026, 8, 3),
        }
        item.update(overrides)
        return item

    @mock.patch.object(service, "assign_active_occurrence")
    @mock.patch.object(service, "create_occurrence")
    def test_new_definition_creates_one_current_occurrence(self, create_occurrence, assign_active):
        create_occurrence.return_value = {"uid": "generated-1", "collection": "zin:tasks"}
        item = self.definition(first_due_date=date(2026, 7, 6), next_due_date=date(2026, 7, 6))

        service.synchronize_definition(item, {"tasks": []}, today=date(2026, 8, 3))

        create_occurrence.assert_called_once_with(item, date(2026, 8, 3))
        assign_active.assert_called_once_with(item, date(2026, 8, 3), create_occurrence.return_value)

    @mock.patch.object(service, "assign_active_occurrence")
    @mock.patch.object(service, "create_occurrence")
    @mock.patch.object(service, "clear_active_occurrence")
    def test_completed_occurrence_advances_fixed_schedule(self, clear_active, create_occurrence, assign_active):
        create_occurrence.return_value = {"uid": "generated-2", "collection": "zin:tasks"}
        item = self.definition(
            active_uid="generated-1",
            active_collection_id="zin:tasks",
            active_due_date=date(2026, 8, 3),
            next_due_date=None,
        )
        bootstrap = {"tasks": [{"uid": "generated-1", "collection": "zin:tasks", "status": "COMPLETED"}]}

        service.synchronize_definition(item, bootstrap, today=date(2026, 8, 3))

        clear_active.assert_called_once_with(item, True, date(2026, 8, 10))
        create_occurrence.assert_called_once()
        self.assertEqual(create_occurrence.call_args.args[1], date(2026, 8, 10))
        assign_active.assert_called_once()

    @mock.patch.object(service, "assign_active_occurrence")
    @mock.patch.object(service, "create_occurrence")
    @mock.patch.object(service, "clear_active_occurrence")
    def test_deleted_occurrence_also_advances(self, clear_active, create_occurrence, assign_active):
        create_occurrence.return_value = {"uid": "generated-2", "collection": "zin:tasks"}
        item = self.definition(
            active_uid="generated-1",
            active_collection_id="zin:tasks",
            active_due_date=date(2026, 8, 3),
            next_due_date=None,
        )

        service.synchronize_definition(item, {"tasks": []}, today=date(2026, 8, 3))

        clear_active.assert_called_once_with(item, False, date(2026, 8, 10))
        create_occurrence.assert_called_once()
        assign_active.assert_called_once()

    @mock.patch.object(service, "assign_active_occurrence")
    @mock.patch.object(service, "create_occurrence")
    def test_active_occurrence_is_not_duplicated(self, create_occurrence, assign_active):
        item = self.definition(
            active_uid="generated-1",
            active_collection_id="zin:tasks",
            active_due_date=date(2026, 8, 3),
            next_due_date=None,
        )
        bootstrap = {"tasks": [{"uid": "generated-1", "collection": "zin:tasks", "status": "NEEDS-ACTION"}]}

        service.synchronize_definition(item, bootstrap, today=date(2026, 8, 3))

        create_occurrence.assert_not_called()
        assign_active.assert_not_called()

    @mock.patch.object(service, "assign_active_occurrence")
    @mock.patch.object(service, "create_occurrence")
    def test_existing_deterministic_occurrence_is_adopted_after_restart(self, create_occurrence, assign_active):
        item = self.definition()
        uid = service.occurrence_uid(item, date(2026, 8, 3))
        bootstrap = {"tasks": [{"uid": uid, "collection": "zin:tasks", "status": "NEEDS-ACTION"}]}

        service.synchronize_definition(item, bootstrap, today=date(2026, 8, 3))

        create_occurrence.assert_not_called()
        assign_active.assert_called_once_with(
            item,
            date(2026, 8, 3),
            {"uid": uid, "collection": "zin:tasks"},
        )


if __name__ == "__main__":
    unittest.main()

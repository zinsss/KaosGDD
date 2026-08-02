import pathlib
import sys
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.supplies import service


class SuppliesBehaviorTests(unittest.TestCase):
    def test_title_cleanup_and_normalization_match_kaossupplies(self):
        self.assertEqual(service.clean_title(" Tongue   Depressor "), "Tongue Depressor")
        self.assertEqual(service.normalize_title(" Tongue   Depressor "), "tongue depressor")

    @mock.patch.object(service, "radicale_request")
    @mock.patch.object(service, "list_all_supplies")
    @mock.patch.object(service, "supplies_collection")
    @mock.patch.object(service, "touch_preset")
    def test_duplicate_active_supply_returns_existing_id(self, touch_preset, supplies_collection, list_all_supplies, radicale_request):
        supplies_collection.return_value = {"name": "Kaos_Supplies", "href": "/supplies/Kaos_Supplies/"}
        list_all_supplies.return_value = [
            {
                "id": "existing",
                "title": "tongue depressor",
                "status": "active",
                "_normalized_title": "tongue depressor",
            }
        ]

        result = service.create_supply(" Tongue   Depressor ")

        self.assertEqual(result, {"ok": True, "id": "existing", "created": False})
        touch_preset.assert_called_once_with("Tongue Depressor", "tongue depressor")
        radicale_request.assert_not_called()

    @mock.patch.object(service, "radicale_request")
    @mock.patch.object(service, "list_all_supplies")
    @mock.patch.object(service, "supplies_collection")
    @mock.patch.object(service, "touch_preset")
    def test_done_supply_does_not_block_new_active_create(self, touch_preset, supplies_collection, list_all_supplies, radicale_request):
        supplies_collection.return_value = {"name": "Kaos_Supplies", "href": "/supplies/Kaos_Supplies/"}
        list_all_supplies.return_value = [
            {
                "id": "done-one",
                "title": "gauze",
                "status": "done",
                "_normalized_title": "gauze",
            }
        ]
        radicale_request.return_value = (201, "")

        result = service.create_supply("gauze")

        self.assertTrue(result["ok"])
        self.assertTrue(result["created"])
        radicale_request.assert_called_once()

    def test_lists_active_by_created_and_done_by_completed(self):
        with mock.patch.object(
            service,
            "list_all_supplies",
            return_value=[
                {"id": "b", "status": "active", "created_at": "2026-07-02T09:00:00"},
                {"id": "a", "status": "active", "created_at": "2026-07-01T09:00:00"},
                {
                    "id": "d1",
                    "status": "done",
                    "done_at": "2026-07-01T09:00:00",
                    "updated_at": "2026-07-01T09:00:00",
                },
                {
                    "id": "d2",
                    "status": "done",
                    "done_at": "2026-07-02T09:00:00",
                    "updated_at": "2026-07-02T09:00:00",
                },
            ],
        ):
            self.assertEqual([item["id"] for item in service.list_supplies("active")["items"]], ["a", "b"])
            self.assertEqual([item["id"] for item in service.list_supplies("done")["items"]], ["d2", "d1"])

    @mock.patch.object(service, "create_supply")
    def test_capture_supply_contract(self, create_supply):
        create_supply.return_value = {"ok": True, "id": "abc", "created": True}

        result = service.capture_supply("$$ gauze")

        self.assertEqual(
            result,
            {
                "ok": True,
                "kind": "supply",
                "id": "abc",
                "created": True,
                "created_types": ["supply"],
            },
        )

    def test_capture_rejects_no_space_prefix(self):
        self.assertEqual(
            service.capture_supply("$$gauze"),
            {"ok": False, "error": "supply line must start with $$ "},
        )


if __name__ == "__main__":
    unittest.main()

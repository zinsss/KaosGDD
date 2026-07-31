import datetime
import pathlib
import sys
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.rouny import store


def valid_templates():
    return [
        {
            "id": "template-1",
            "name": "기본",
            "createdAt": "2026-07-31T01:00:00.000Z",
            "updatedAt": "2026-07-31T01:00:00.000Z",
            "items": [
                {
                    "id": "item-1",
                    "title": "수업",
                    "memo": "메모",
                    "color": "#F4C7DF",
                    "slots": [
                        {
                            "id": "slot-1",
                            "dayOfWeek": "1",
                            "startTime": "09:00",
                            "endTime": "09:40",
                        }
                    ],
                }
            ],
        }
    ]


class RounyValidationTests(unittest.TestCase):
    def test_normalizes_known_document_fields(self):
        result = store.validate_templates(valid_templates())

        self.assertEqual(result[0]["name"], "기본")
        self.assertEqual(result[0]["items"][0]["dayOfWeek"], "1")
        self.assertEqual(result[0]["items"][0]["color"], "#f4c7df")

    def test_allows_empty_server_document(self):
        self.assertEqual(store.validate_templates([]), [])

    def test_rejects_duplicate_template_ids(self):
        templates = valid_templates() * 2
        with self.assertRaisesRegex(ValueError, "duplicate_rouny_template_id"):
            store.validate_templates(templates)

    def test_rejects_invalid_time(self):
        templates = valid_templates()
        templates[0]["items"][0]["slots"][0]["startTime"] = "25:00"
        with self.assertRaisesRegex(ValueError, "invalid_rouny_time"):
            store.validate_templates(templates)


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self, current_row=None):
        self.current_row = current_row
        self.written_row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def transaction(self):
        return FakeTransaction()

    def execute(self, query, parameters=None):
        if "pg_advisory_xact_lock" in query:
            return FakeResult(None)
        if "FOR UPDATE" in query:
            return FakeResult(self.current_row)
        if "INSERT INTO rouny_documents" in query:
            revision = parameters[1]
            self.written_row = (revision, store.validate_templates(json_loads(parameters[2])), datetime.datetime(2026, 7, 31))
            return FakeResult(self.written_row)
        raise AssertionError(query)


def json_loads(value):
    import json

    return json.loads(value)


class RounyStoreTests(unittest.TestCase):
    @mock.patch.object(store, "connect")
    def test_creates_next_revision(self, connect):
        connection = FakeConnection()
        connect.return_value = connection

        result = store.put_rouny_document(valid_templates(), 0)

        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["templates"][0]["name"], "기본")

    @mock.patch.object(store, "connect")
    def test_rejects_stale_revision_with_current_document(self, connect):
        current = (3, valid_templates(), datetime.datetime(2026, 7, 31))
        connect.return_value = FakeConnection(current)

        with self.assertRaises(store.RounyConflict) as caught:
            store.put_rouny_document(valid_templates(), 2)

        self.assertEqual(caught.exception.document["revision"], 3)


if __name__ == "__main__":
    unittest.main()

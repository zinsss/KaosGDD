import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("calendar_adapter_task_server", MODULE_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


TASK = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VTODO
UID:TASK-1
DTSTAMP:20260729T010000Z
CREATED:20260728T010000Z
LAST-MODIFIED:20260729T010000Z
SUMMARY:Old task
DESCRIPTION:Old memo
STATUS:NEEDS-ACTION
DUE;TZID=Asia/Seoul:20260730T100000
END:VTODO
END:VCALENDAR
"""


class TaskWritingTests(unittest.TestCase):
    def test_update_can_mark_task_completed(self):
        existing = SERVER.parse_ics(TASK, "/zin/tasks/TASK-1.ics", '"etag-1"')[0]

        _, body = SERVER.build_vtodo(
            {
                "uid": "TASK-1",
                "title": "Old task",
                "memo": "Old memo",
                "dueDate": "2026-07-30",
                "dueTime": "10:00",
                "status": "COMPLETED",
            },
            existing,
        )

        self.assertIn("UID:TASK-1", body)
        self.assertIn("CREATED:20260728T010000Z", body)
        self.assertIn("STATUS:COMPLETED", body)
        self.assertIn("COMPLETED:", body)
        self.assertIn("PERCENT-COMPLETE:100", body)

    def test_update_can_mark_task_active_again(self):
        existing = SERVER.parse_ics(
            TASK.replace("STATUS:NEEDS-ACTION", "STATUS:COMPLETED\nCOMPLETED:20260730T010000Z\nPERCENT-COMPLETE:100"),
            "/zin/tasks/TASK-1.ics",
            '"etag-1"',
        )[0]

        _, body = SERVER.build_vtodo(
            {
                "uid": "TASK-1",
                "title": "Old task",
                "memo": "Old memo",
                "dueDate": "2026-07-30",
                "dueTime": "10:00",
                "status": "NEEDS-ACTION",
            },
            existing,
        )

        self.assertIn("STATUS:NEEDS-ACTION", body)
        self.assertNotIn("COMPLETED:", body)
        self.assertNotIn("PERCENT-COMPLETE:100", body)


if __name__ == "__main__":
    unittest.main()

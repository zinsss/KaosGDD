import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.faxmail import notifier


class FaxmailNotifierTests(unittest.TestCase):
    def test_scan_received_faxes_uses_xferfaxlog_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            recvq = root / "recvq"
            log = root / "log" / "xferfaxlog"
            recvq.mkdir()
            log.parent.mkdir()
            fax = recvq / "fax000000123.tif"
            fax.write_bytes(b"fax")
            log.write_text(
                '08/07/26 17:09\tRECV\t000000123\tttyACM0\trecvq/fax000000123.tif\t""\tfax\t"+82 54"\t"07079664986"\t2908201\t1\n',
                encoding="utf-8",
            )

            events = notifier.scan_received_faxes(recvq, log, minimum_age=0)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].commid, "000000123")
        self.assertEqual(events[0].remote, "07079664986")
        self.assertEqual(events[0].pages, "1")

    def test_first_run_marks_existing_without_notifying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            recvq = root / "recvq"
            recvq.mkdir()
            (recvq / "fax000000001.tif").write_bytes(b"fax")
            state = root / "state.json"
            with mock.patch.dict(
                os.environ,
                {
                    "FAX_NOTIFY_RECVQ": str(recvq),
                    "FAX_NOTIFY_XFERFAXLOG": str(root / "missing.log"),
                    "FAX_NOTIFY_STATE_PATH": str(state),
                    "FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN": "true",
                    "FAX_NOTIFY_MIN_FILE_AGE_SECONDS": "0",
                },
                clear=False,
            ):
                sent = notifier.scan_and_notify(opener=mock.Mock())

            payload = json.loads(state.read_text(encoding="utf-8"))

        self.assertEqual(sent, 0)
        self.assertEqual(len(payload["known"]), 1)

    def test_unreadable_xferfaxlog_does_not_block_recvq_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            recvq = pathlib.Path(tmp) / "recvq"
            recvq.mkdir()
            (recvq / "fax000000007.tif").write_bytes(b"fax")
            with mock.patch.object(pathlib.Path, "read_text", side_effect=PermissionError):
                events = notifier.scan_received_faxes(
                    recvq,
                    pathlib.Path(tmp) / "xferfaxlog",
                    minimum_age=0,
                )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].commid, "000000007")
        self.assertEqual(events[0].remote, "unknown")

    def test_new_fax_publishes_and_updates_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            recvq = root / "recvq"
            recvq.mkdir()
            state = root / "state.json"
            notifier.save_state({"known": []}, state)
            (recvq / "fax000000002.tif").write_bytes(b"fax")
            with mock.patch.dict(
                os.environ,
                {
                    "FAX_NOTIFY_RECVQ": str(recvq),
                    "FAX_NOTIFY_XFERFAXLOG": str(root / "missing.log"),
                    "FAX_NOTIFY_STATE_PATH": str(state),
                    "FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN": "false",
                    "FAX_NOTIFY_MIN_FILE_AGE_SECONDS": "0",
                },
                clear=False,
            ), mock.patch.object(notifier.notifications, "publish") as publish:
                sent = notifier.scan_and_notify()

            payload = json.loads(state.read_text(encoding="utf-8"))

        self.assertEqual(sent, 1)
        self.assertEqual(len(payload["known"]), 1)
        self.assertEqual(publish.call_count, 1)
        self.assertIn("fax000000002.tif", publish.call_args.kwargs["message"])

    def test_recent_fax_waits_until_stable_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            recvq = pathlib.Path(tmp) / "recvq"
            recvq.mkdir()
            fax = recvq / "fax000000009.tif"
            fax.write_bytes(b"partial")
            modified = fax.stat().st_mtime

            recent = notifier.scan_received_faxes(
                recvq,
                pathlib.Path(tmp) / "missing.log",
                minimum_age=60,
                now=modified + 10,
            )
            stable = notifier.scan_received_faxes(
                recvq,
                pathlib.Path(tmp) / "missing.log",
                minimum_age=60,
                now=modified + 61,
            )

        self.assertEqual(recent, [])
        self.assertEqual(len(stable), 1)

if __name__ == "__main__":
    unittest.main()

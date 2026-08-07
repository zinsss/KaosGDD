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


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b"ok"


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

            events = notifier.scan_received_faxes(recvq, log)

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
                    "NTFY_URL": "http://ntfy",
                    "NTFY_TOPIC": "kaosgdd-fax",
                },
                clear=False,
            ):
                sent = notifier.scan_and_notify(opener=mock.Mock())

            payload = json.loads(state.read_text(encoding="utf-8"))

        self.assertEqual(sent, 0)
        self.assertEqual(len(payload["known"]), 1)

    def test_new_fax_posts_to_ntfy_and_updates_state(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeResponse()

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
                    "NTFY_URL": "http://ntfy",
                    "NTFY_TOPIC": "kaosgdd-fax",
                },
                clear=False,
            ):
                sent = notifier.scan_and_notify(opener=opener)

            payload = json.loads(state.read_text(encoding="utf-8"))

        self.assertEqual(sent, 1)
        self.assertEqual(len(payload["known"]), 1)
        self.assertEqual(requests[0][0].full_url, "http://ntfy/kaosgdd-fax")
        self.assertIn(b"fax000000002.tif", requests[0][0].data)


if __name__ == "__main__":
    unittest.main()

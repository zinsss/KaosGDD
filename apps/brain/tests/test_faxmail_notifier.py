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
                    "FAX_NOTIFY_DELIVERY_FAILURE_ROOT": str(root / "missing-failures"),
                    "NTFY_URL": "http://ntfy",
                    "NTFY_TOPIC_IOS": "kaosgdd-ios",
                    "NTFY_TOPIC_DESKTOP": "kaosgdd-desktop",
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
                    "NTFY_TOPIC_IOS": "kaosgdd-ios",
                    "NTFY_TOPIC_DESKTOP": "kaosgdd-desktop",
                    "FAX_NOTIFY_MIN_FILE_AGE_SECONDS": "0",
                    "FAX_NOTIFY_DELIVERY_FAILURE_ROOT": str(root / "missing-failures"),
                },
                clear=False,
            ):
                sent = notifier.scan_and_notify(opener=opener)

            payload = json.loads(state.read_text(encoding="utf-8"))

        self.assertEqual(sent, 1)
        self.assertEqual(len(payload["known"]), 1)
        self.assertEqual(
            [request.full_url for request, _timeout in requests],
            ["http://ntfy/kaosgdd-ios", "http://ntfy/kaosgdd-desktop"],
        )
        self.assertIn(b"fax000000002.tif", requests[0][0].data)

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

    def test_delivery_failure_posts_urgent_ntfy_once(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            recvq = root / "recvq"
            failures = root / "failed"
            recvq.mkdir()
            failures.mkdir()
            state = root / "state.json"
            notifier.save_state({"known": [], "knownFailures": []}, state)
            (failures / "000000010.json").write_text(
                json.dumps(
                    {
                        "deliveryKey": "000000010",
                        "source": "/integrations/hylafax/recvq/fax000000010.tif",
                        "attempts": 1,
                        "lastErrorType": "SMTPConnectError",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "FAX_NOTIFY_RECVQ": str(recvq),
                    "FAX_NOTIFY_XFERFAXLOG": str(root / "missing.log"),
                    "FAX_NOTIFY_STATE_PATH": str(state),
                    "FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN": "false",
                    "FAX_NOTIFY_MIN_FILE_AGE_SECONDS": "0",
                    "FAX_NOTIFY_DELIVERY_FAILURE_ROOT": str(failures),
                    "NTFY_URL": "http://ntfy",
                    "NTFY_TOPIC_IOS": "kaosgdd-ios",
                    "NTFY_TOPIC_DESKTOP": "kaosgdd-desktop",
                },
                clear=False,
            ):
                sent = notifier.scan_and_notify(opener=opener)
                sent_again = notifier.scan_and_notify(opener=opener)

            payload = json.loads(state.read_text(encoding="utf-8"))

        self.assertEqual(sent, 1)
        self.assertEqual(sent_again, 0)
        self.assertEqual(payload["knownFailures"], ["000000010"])
        self.assertEqual(
            [request.full_url for request, _timeout in requests],
            ["http://ntfy/kaosgdd-ios", "http://ntfy/kaosgdd-desktop"],
        )
        self.assertTrue(all(request.get_header("Priority") == "urgent" for request, _timeout in requests))

    def test_single_topic_variable_remains_a_compatibility_fallback(self):
        with mock.patch.dict(
            os.environ,
            {
                "NTFY_URL": "http://ntfy",
                "NTFY_TOPIC": "legacy-topic",
                "NTFY_TOPIC_IOS": "",
                "NTFY_TOPIC_DESKTOP": "",
                "NTFY_TOPIC_NORMAL": "",
            },
            clear=False,
        ):
            self.assertEqual(notifier.ntfy_url("normal"), "http://ntfy/legacy-topic")
            self.assertEqual(notifier.ntfy_url("system"), "http://ntfy/legacy-topic")

    def test_duplicate_audience_topic_is_published_once(self):
        with mock.patch.dict(
            os.environ,
            {
                "NTFY_URL": "http://ntfy",
                "NTFY_TOPIC_IOS": "kaosgdd-shared",
                "NTFY_TOPIC_DESKTOP": "kaosgdd-shared",
            },
            clear=False,
        ):
            self.assertEqual(notifier.ntfy_urls("normal"), ["http://ntfy/kaosgdd-shared"])

    def test_unreadable_delivery_failure_directory_does_not_stop_scan(self):
        with mock.patch.object(pathlib.Path, "is_dir", return_value=True), mock.patch.object(
            pathlib.Path, "glob", side_effect=PermissionError
        ):
            failures = notifier.scan_delivery_failures("/unreadable")

        self.assertEqual(failures, [])

    def test_inaccessible_delivery_failure_directory_does_not_stop_scan(self):
        with mock.patch.object(pathlib.Path, "is_dir", side_effect=PermissionError):
            failures = notifier.scan_delivery_failures("/inaccessible")

        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()

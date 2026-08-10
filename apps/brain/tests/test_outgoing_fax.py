import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.faxmail import outgoing


class OutgoingFaxTests(unittest.TestCase):
    def env(self, **overrides):
        values = {}
        values.update(overrides)
        return mock.patch.dict(os.environ, values, clear=False)

    def test_normalizes_korean_international_number(self):
        self.assertEqual(outgoing.normalize_destination("+82 2-2848-302"), "022848302")

    def test_builds_source_agnostic_request_from_pdf(self):
        with self.env():
            request = outgoing.request_from_pdf(
                destination="02-2848-302",
                sender="telegram:777",
                message_id="telegram:-100123:55:unique",
                filename="notice.pdf",
                pdf=b"%PDF-1.4\n%%EOF",
            )

        self.assertEqual(request.destination, "022848302")
        self.assertEqual(request.sender, "telegram:777")
        self.assertEqual(request.subject, "fax:022848302")

    def test_rejects_plain_number_and_twelve_digit_mobile_number(self):
        with self.assertRaisesRegex(outgoing.OutgoingFaxError, "invalid_domestic"):
            outgoing.normalize_destination("010304949393")

    def test_rejects_invalid_pdf_source(self):
        with self.assertRaisesRegex(outgoing.OutgoingFaxError, "invalid_pdf_signature"):
            outgoing.request_from_pdf(
                destination="022848302",
                sender="telegram:777",
                message_id="telegram-message",
                filename="fax.pdf",
                pdf=b"not-pdf",
            )

    def test_queue_is_deterministic_and_does_not_duplicate_manifest(self):
        with tempfile.TemporaryDirectory() as tmp, self.env():
            request = outgoing.request_from_pdf(
                destination="022848302",
                sender="telegram:777",
                message_id="telegram-message",
                filename="fax.pdf",
                pdf=b"%PDF-1.4\n%%EOF",
            )
            first = outgoing.queue_request(request, root=tmp, now=1)
            second = outgoing.queue_request(request, root=tmp, now=2)
            manifests = list((pathlib.Path(tmp) / "pending").glob("*.json"))
            job_mode = stat.S_IMODE((pathlib.Path(tmp) / "jobs" / first["jobId"]).stat().st_mode)

        self.assertEqual(first["jobId"], second["jobId"])
        self.assertEqual(len(manifests), 1)
        self.assertEqual(job_mode, 0o2770)

    def test_legacy_doneq_success_and_failure_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            success = root / "q1"
            failure = root / "q2"
            success.write_text("state:7\nreturned:2\nstatus:\n", encoding="utf-8")
            failure.write_text("state:8\nstatus:No carrier\nstatuscode:40\n", encoding="utf-8")

            self.assertTrue(outgoing.parse_doneq(success)["sent"])
            self.assertFalse(outgoing.parse_doneq(failure)["sent"])

    def test_reconcile_records_dry_run_without_notification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            job_id = "a" * 32
            (root / "results").mkdir()
            (root / "results" / f"{job_id}.json").write_text(
                json.dumps({"status": "dry_run", "jobId": job_id}), encoding="utf-8"
            )
            state = {"jobs": {job_id: {"status": "queued"}}}

            changed = outgoing.reconcile_jobs(state, root=root, doneq=root / "doneq")

        self.assertTrue(changed)
        self.assertEqual(state["jobs"][job_id]["status"], "dry_run")

    def test_live_stage_notifications_are_idempotent(self):
        job = {"destination": "022848302", "filename": "sample.pdf", "hylafaxJobId": "419"}
        with mock.patch.object(outgoing.notifications, "publish") as publish:
            first = outgoing.notify_stage_once(job, "queued")
            duplicate = outgoing.notify_stage_once(job, "queued")
            outgoing.notify_stage_once(job, "sending")
            outgoing.notify_stage_once(job, "sent")

        self.assertTrue(first)
        self.assertFalse(duplicate)
        self.assertEqual([call.kwargs["title"] for call in publish.call_args_list], [
            "Fax queued to send.",
            "Sending fax to 022848302.",
            "Fax successfully sent.",
        ])
        self.assertEqual([call.kwargs["message"] for call in publish.call_args_list], [
            ": to 022848302\n: sample.pdf",
            ": sample.pdf",
            ": to 022848302",
        ])
        self.assertTrue(all("actions" not in call.kwargs for call in publish.call_args_list))
        self.assertEqual(job["notifiedStages"], ["queued", "sending", "sent"])

    def test_success_deletes_telegram_source_messages_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            doneq = root / "doneq"
            doneq.mkdir()
            (doneq / "q419").write_text(
                "state:7\nreturned:2\nstatus:\n",
                encoding="utf-8",
            )
            job = {
                "status": "submitted",
                "hylafaxJobId": "419",
                "source": "telegram",
                "sourceMetadata": {
                    "chatId": "-100123",
                    "messageId": 55,
                    "commandMessageId": 56,
                    "instructionMessageId": 88,
                },
            }
            state = {"jobs": {"a" * 32: job}}
            calls = []

            def api_call(token, method, fields):
                calls.append((token, method, fields))
                return True

            with self.env(
                TELEGRAM_FAX_DELETE_SOURCE_ON_SUCCESS="true",
                TELEGRAM_BOT_TOKEN="token",
            ):
                first = outgoing.reconcile_jobs(
                    state,
                    root=root,
                    doneq=doneq,
                    notify=False,
                    telegram_api_call=api_call,
                )
                second = outgoing.reconcile_jobs(
                    state,
                    root=root,
                    doneq=doneq,
                    notify=False,
                    telegram_api_call=api_call,
                )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(
            [call[1] for call in calls],
            ["deleteMessage", "deleteMessage", "deleteMessage"],
        )
        self.assertEqual([call[2]["message_id"] for call in calls], [55, 56, 88])
        self.assertEqual(job["sourceMessageCleanup"]["status"], "deleted")

    def test_failed_fax_keeps_telegram_source_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            doneq = root / "doneq"
            doneq.mkdir()
            (doneq / "q420").write_text(
                "state:8\nstatus:No carrier\nstatuscode:40\n",
                encoding="utf-8",
            )
            job = {
                "status": "submitted",
                "hylafaxJobId": "420",
                "source": "telegram",
                "sourceMetadata": {
                    "chatId": "-100123",
                    "messageId": 55,
                    "commandMessageId": 56,
                },
            }
            state = {"jobs": {"b" * 32: job}}
            api_call = mock.Mock()

            with self.env(
                TELEGRAM_FAX_DELETE_SOURCE_ON_SUCCESS="true",
                TELEGRAM_BOT_TOKEN="token",
            ):
                outgoing.reconcile_jobs(
                    state,
                    root=root,
                    doneq=doneq,
                    notify=False,
                    telegram_api_call=api_call,
                )

        self.assertEqual(job["status"], "failed")
        api_call.assert_not_called()

if __name__ == "__main__":
    unittest.main()

import json
import os
import pathlib
import sys
import tempfile
import unittest
from email.message import EmailMessage
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.faxmail import outgoing


def fax_message(subject="fax:022848302", *, sender="zin@example.test", attachment=b"%PDF-1.4\n%%EOF"):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "fax-send@kaosgdd.net"
    message["Subject"] = subject
    message["Message-ID"] = "<fax-request@example.test>"
    message["Authentication-Results"] = "mx.example; dkim=pass header.d=example.test"
    message.set_content("Send attached fax")
    message.add_attachment(attachment, maintype="application", subtype="pdf", filename="fax.pdf")
    return message.as_bytes()


class OutgoingFaxTests(unittest.TestCase):
    def env(self, **overrides):
        values = {
            "FAX_OUTGOING_RECIPIENTS": "fax-send@kaosgdd.net",
            "FAX_OUTGOING_ALLOWED_SENDERS": "zin@example.test",
            "FAX_OUTGOING_REQUIRE_AUTH_RESULTS": "true",
        }
        values.update(overrides)
        return mock.patch.dict(os.environ, values, clear=False)

    def test_parses_strict_authenticated_pdf_request(self):
        with self.env():
            request = outgoing.parse_request(fax_message())

        self.assertEqual(request.destination, "022848302")
        self.assertEqual(request.sender, "zin@example.test")

    def test_normalizes_korean_international_number(self):
        with self.env():
            request = outgoing.parse_request(fax_message("fax:+82 2-2848-302"))

        self.assertEqual(request.destination, "022848302")

    def test_rejects_plain_number_and_twelve_digit_mobile_number(self):
        with self.env():
            with self.assertRaisesRegex(outgoing.OutgoingFaxError, "subject_must"):
                outgoing.parse_request(fax_message("022848302"))
            with self.assertRaisesRegex(outgoing.OutgoingFaxError, "invalid_domestic"):
                outgoing.parse_request(fax_message("fax:010304949393"))

    def test_rejects_unapproved_or_unauthenticated_sender(self):
        with self.env():
            with self.assertRaisesRegex(outgoing.OutgoingFaxError, "sender_not_authorized"):
                outgoing.parse_request(fax_message(sender="other@example.test"))
        raw = fax_message().replace(b"dkim=pass", b"dkim=fail")
        with self.env():
            with self.assertRaisesRegex(outgoing.OutgoingFaxError, "sender_authentication_failed"):
                outgoing.parse_request(raw)

    def test_queue_is_deterministic_and_does_not_duplicate_manifest(self):
        with tempfile.TemporaryDirectory() as tmp, self.env():
            request = outgoing.parse_request(fax_message())
            first = outgoing.queue_request(request, root=tmp, now=1)
            second = outgoing.queue_request(request, root=tmp, now=2)
            manifests = list((pathlib.Path(tmp) / "pending").glob("*.json"))

        self.assertEqual(first["jobId"], second["jobId"])
        self.assertEqual(len(manifests), 1)

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

    def test_irrelevant_mail_advances_persisted_uid_cursor(self):
        class FakeIMAP:
            def login(self, _username, _password):
                return "OK", [b"logged in"]

            def select(self, _mailbox, readonly=False):
                self.readonly = readonly
                return "OK", [b"1"]

            def response(self, _code):
                return "UIDVALIDITY", [b"7"]

            def uid(self, command, *args):
                if command == "search":
                    return "OK", [b"12"]
                if command == "fetch":
                    message = EmailMessage()
                    message["From"] = "sender@example.test"
                    message["To"] = "fax@kaosgdd.net"
                    message["Subject"] = "ordinary inbox mail"
                    return "OK", [(b"message", message.as_bytes())]
                raise AssertionError((command, args))

            def close(self):
                return "OK", [b"closed"]

            def logout(self):
                return "BYE", [b"logout"]

        with tempfile.TemporaryDirectory() as tmp, self.env(
            FAX_OUTGOING_STATE_PATH=str(pathlib.Path(tmp) / "state.json"),
            FAX_OUTGOING_IMAP_USERNAME="fax@example.test",
            FAX_OUTGOING_IMAP_PASSWORD="password",
        ):
            outgoing.save_state({"uidValidity": "7", "lastUid": 11, "jobs": {}})
            outgoing.scan_mailbox(imap_factory=lambda *_args, **_kwargs: FakeIMAP())
            state = outgoing.load_state()

        self.assertEqual(state["lastUid"], 12)
        self.assertEqual(state["jobs"], {})


if __name__ == "__main__":
    unittest.main()

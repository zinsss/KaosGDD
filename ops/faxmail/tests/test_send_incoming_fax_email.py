import importlib.util
import os
import pathlib
import smtplib
import tempfile
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "send-incoming-fax-email.py"
SPEC = importlib.util.spec_from_file_location("faxmail_sender", MODULE_PATH)
sender = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sender)


class FaxmailSenderTests(unittest.TestCase):
    def config(self, state_dir):
        return mock.patch.dict(
            os.environ,
            {
                "FAXMAIL_STATE_DIR": str(state_dir),
                "FAXMAIL_SMTP_HOST": "smtp.example.test",
                "FAXMAIL_SMTP_PORT": "587",
                "FAXMAIL_SMTP_STARTTLS": "true",
                "FAXMAIL_SMTP_SSL": "false",
                "FAXMAIL_FROM": "fax@example.test",
                "FAXMAIL_TO": "inbox@example.test",
            },
            clear=False,
        )

    @staticmethod
    def fake_convert(_source, output):
        output.write_bytes(b"%PDF-test")

    def test_success_writes_marker_and_duplicate_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "fax000000001.tif"
            source.write_bytes(b"fax")
            with self.config(root / "state"), mock.patch.object(
                sender, "convert_tiff_to_pdf", side_effect=self.fake_convert
            ), mock.patch.object(sender, "send_message") as send_message:
                first = sender.main(["sender", str(source), "--commid", "000000001"])
                second = sender.main(["sender", str(source), "--commid", "000000001"])

            marker = root / "state" / "sent" / "000000001.json"
            marker_exists = marker.is_file()

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        self.assertTrue(marker_exists)
        self.assertEqual(send_message.call_count, 1)

    def test_smtp_failure_is_persisted_for_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "fax000000002.tif"
            source.write_bytes(b"fax")
            with self.config(root / "state"), mock.patch.object(
                sender, "convert_tiff_to_pdf", side_effect=self.fake_convert
            ), mock.patch.object(
                sender,
                "send_message",
                side_effect=smtplib.SMTPConnectError(421, "unavailable"),
            ):
                result = sender.main(["sender", str(source), "--commid", "000000002"])

            marker = root / "state" / "failed" / "000000002.json"
            payload = sender.read_json(marker)

        self.assertEqual(result, 1)
        self.assertEqual(payload["attempts"], 1)
        self.assertEqual(payload["lastErrorType"], "SMTPConnectError")

    def test_retry_delivers_due_failure_and_clears_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            state = root / "state"
            source = root / "fax000000003.tif"
            source.write_bytes(b"fax")
            with self.config(state):
                sender.record_failure(
                    "000000003",
                    source=source,
                    remote_number="unknown",
                    device="ttyACM0",
                    commid="000000003",
                    error=smtplib.SMTPConnectError(421, "unavailable"),
                )
                marker = state / "failed" / "000000003.json"
                payload = sender.read_json(marker)
                payload["nextAttemptAt"] = 0
                sender.write_json(marker, payload)
                with mock.patch.object(
                    sender, "convert_tiff_to_pdf", side_effect=self.fake_convert
                ), mock.patch.object(sender, "send_message"):
                    result = sender.main(["sender", "--retry-failures"])

            sent = state / "sent" / "000000003.json"
            sent_exists = sent.is_file()
            failure_exists = marker.exists()

        self.assertEqual(result, 0)
        self.assertTrue(sent_exists)
        self.assertFalse(failure_exists)

    def test_mark_sent_does_not_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "fax000000004.tif"
            source.write_bytes(b"fax")
            with self.config(root / "state"), mock.patch.object(sender, "send_message") as send_message:
                result = sender.main(
                    ["sender", str(source), "--commid", "000000004", "--mark-sent"]
                )

            marker = root / "state" / "sent" / "000000004.json"
            marker_exists = marker.is_file()

        self.assertEqual(result, 0)
        self.assertTrue(marker_exists)
        send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()

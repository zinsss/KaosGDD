import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.mail import notifier
from services.mail import telegram_archive


class FakeMailboxServer:
    def __init__(self):
        root = notifier.encode_modified_utf7("각종공문")
        self.mailboxes = {
            root: {"uidvalidity": "10", "messages": {1: self.message("Existing")}},
        }

    @staticmethod
    def message(subject, *, html_only=False, attachment=False):
        body = (
            "From: Sender <sender@example.test>\r\n"
            "To: clinic@example.test\r\n"
            f"Subject: {subject}\r\n"
            "MIME-Version: 1.0\r\n"
        )
        if attachment:
            body += (
                'Content-Type: multipart/mixed; boundary="boundary"\r\n\r\n'
                "--boundary\r\n"
                "Content-Type: text/plain; charset=utf-8\r\n\r\n"
                "Preview body\r\n"
                "--boundary\r\n"
                "Content-Type: application/pdf\r\n"
                "Content-Disposition: attachment; filename=notice.pdf\r\n"
                "Content-Transfer-Encoding: base64\r\n\r\n"
                "JVBERi0xLjQ=\r\n"
                "--boundary--\r\n"
            )
        elif html_only:
            body += "Content-Type: text/html; charset=utf-8\r\n\r\n<p>Hello <b>there</b></p><script>bad()</script>"
        else:
            body += "Content-Type: text/plain; charset=utf-8\r\n\r\nPreview body"
        return body.encode("utf-8")

    def factory(self, _host, _port, timeout):
        self.timeout = timeout
        return FakeIMAP(self)


class FakeIMAP:
    def __init__(self, server):
        self.server = server
        self.selected = ""
        self.readonly_values = []
        server.last_client = self

    def login(self, _username, _password):
        return "OK", [b"logged in"]

    def list(self):
        return "OK", [f'(\\HasNoChildren) "/" "{name}"'.encode() for name in self.server.mailboxes]

    def select(self, mailbox, readonly=False):
        self.readonly_values.append(readonly)
        self.selected = notifier.unquote_imap(mailbox)
        return "OK", [b"1"]

    def response(self, code):
        return code, [self.server.mailboxes[self.selected]["uidvalidity"].encode()]

    def uid(self, command, *args):
        mailbox = self.server.mailboxes[self.selected]
        if command == "search":
            values = " ".join(str(uid) for uid in sorted(mailbox["messages"]))
            return "OK", [values.encode()]
        if command == "fetch":
            uid = int(args[0])
            self.last_fetch_spec = args[1]
            return "OK", [(b"message", mailbox["messages"][uid])]
        raise AssertionError(command)

    def close(self):
        return "OK", [b"closed"]

    def logout(self):
        return "BYE", [b"logout"]


class MailTelegramArchiveTests(unittest.TestCase):
    def environment(self, root, **overrides):
        values = {
            "MAIL_NOTIFY_NAVER_ENABLED": "true",
            "MAIL_NOTIFY_NAVER_USERNAME": "user",
            "MAIL_NOTIFY_NAVER_PASSWORD": "password",
            "MAIL_NOTIFY_NAVER_FOLDERS": "각종공문",
            "MAIL_TELEGRAM_ARCHIVE_ENABLED": "true",
            "MAIL_TELEGRAM_ARCHIVE_CHAT_ID": "123",
            "MAIL_TELEGRAM_ARCHIVE_STATE_PATH": str(root / "state.json"),
            "MAIL_TELEGRAM_ARCHIVE_MARK_EXISTING_ON_FIRST_RUN": "true",
            "TELEGRAM_BOT_TOKEN": "token",
        }
        values.update(overrides)
        return mock.patch.dict(os.environ, values, clear=False)

    def test_parses_plain_html_and_attachment(self):
        plain = telegram_archive.parse_message(FakeMailboxServer.message("Plain", attachment=True), "각종공문", 2)
        html_mail = telegram_archive.parse_message(FakeMailboxServer.message("HTML", html_only=True), "각종공문", 3)

        self.assertEqual(plain.preview, "Preview body")
        self.assertEqual(plain.attachments[0].filename, "notice.pdf")
        self.assertEqual(plain.attachments[0].content, b"%PDF-1.4")
        self.assertEqual(html_mail.preview, "Hello there")
        self.assertNotIn("bad", html_mail.preview)
        self.assertEqual(
            telegram_archive.format_summary(plain),
            "\n".join(
                (
                    "Naver Mail >> 각종공문",
                    "From: Sender <sender@example.test>",
                    "",
                    "Plain",
                    "",
                    "Attachments",
                    "1. notice.pdf",
                    "",
                    "Preview body",
                )
            ),
        )

    def test_summary_omits_empty_attachments_and_limits_preview_to_fifteen_lines(self):
        mail = telegram_archive.ArchiveMail(
            mailbox="세무사",
            uid=4,
            sender="sender@example.test",
            subject="Tax notice",
            preview="\n".join(f"Line {number}" for number in range(1, 18)),
            attachments=(),
        )

        summary = telegram_archive.format_summary(mail)

        self.assertEqual(
            summary,
            "Naver Mail >> 세무사\n"
            "From: sender@example.test\n\n"
            "Tax notice\n\n"
            + "\n".join(f"Line {number}" for number in range(1, 16)),
        )
        self.assertNotIn("Attachments", summary)
        self.assertNotIn("Line 16", summary)

    def test_shared_supergroup_and_named_mail_topic_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with self.environment(
                root,
                MAIL_TELEGRAM_ARCHIVE_CHAT_ID="",
                MAIL_TELEGRAM_ARCHIVE_TOPIC_ID="",
                TELEGRAM_SUPERGROUP_CHAT_ID="-100123",
                TELEGRAM_TOPIC_MAIL_ID="99",
            ):
                self.assertEqual(telegram_archive.chat_id(), "-100123")
                self.assertEqual(telegram_archive.topic_id(), "99")

    def test_baselines_then_archives_new_mail_without_marking_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            server = FakeMailboxServer()
            summaries = []
            attachments = []
            with self.environment(root):
                first = telegram_archive.scan_and_archive(
                    imap_factory=server.factory,
                    summary_sender=lambda mail: summaries.append(mail) or {"message_id": 1},
                    attachment_sender=lambda item: attachments.append(item) or {"message_id": 2},
                )
                mailbox = notifier.encode_modified_utf7("각종공문")
                server.mailboxes[mailbox]["messages"][2] = server.message("New", attachment=True)
                second = telegram_archive.scan_and_archive(
                    imap_factory=server.factory,
                    summary_sender=lambda mail: summaries.append(mail) or {"message_id": 1},
                    attachment_sender=lambda item: attachments.append(item) or {"message_id": 2},
                )
                state = telegram_archive.load_state()

        self.assertEqual(first, 0)
        self.assertEqual(second, 1)
        self.assertEqual([mail.subject for mail in summaries], ["New"])
        self.assertEqual([item.filename for item in attachments], ["notice.pdf"])
        self.assertTrue(all(server.last_client.readonly_values))
        self.assertEqual(server.last_client.last_fetch_spec, "(BODY.PEEK[])")
        self.assertEqual(state["mailboxes"][mailbox]["lastUid"], 2)

    def test_saved_progress_prevents_duplicate_summary_after_attachment_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            mail = telegram_archive.parse_message(
                FakeMailboxServer.message("Retry", attachment=True), "각종공문", 2
            )
            progress = {}
            summaries = []
            attempts = []
            saves = []

            def fail_attachment(item):
                attempts.append(item.filename)
                raise RuntimeError("upload_failed")

            with self.environment(root):
                with self.assertRaises(RuntimeError):
                    telegram_archive.archive_mail(
                        mail,
                        progress,
                        summary_sender=lambda item: summaries.append(item.subject) or {"message_id": 9},
                        attachment_sender=fail_attachment,
                        persist=lambda: saves.append(dict(progress)),
                    )
                telegram_archive.archive_mail(
                    mail,
                    progress,
                    summary_sender=lambda item: summaries.append(item.subject) or {"message_id": 10},
                    attachment_sender=lambda item: attempts.append(item.filename) or {"message_id": 11},
                )

        self.assertEqual(summaries, ["Retry"])
        self.assertEqual(attempts, ["notice.pdf", "notice.pdf"])
        self.assertEqual(progress["summaryMessageId"], 9)
        self.assertTrue(saves)


if __name__ == "__main__":
    unittest.main()

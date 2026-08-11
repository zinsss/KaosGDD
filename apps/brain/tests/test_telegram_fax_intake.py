import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.faxmail import outgoing
from services.faxmail import telegram_intake
from services.telegram import client as telegram


class TelegramFaxIntakeTests(unittest.TestCase):
    def env(self, root, **overrides):
        values = {
            "TELEGRAM_FAX_INTAKE_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_SUPERGROUP_CHAT_ID": "-100123",
            "TELEGRAM_TOPIC_FAX_ID": "77",
            "TELEGRAM_TOPIC_MEMOS_ID": "88",
            "TELEGRAM_MEMOS_TOPIC_READ_ONLY": "true",
            "TELEGRAM_DOCUMENT_INTAKE_ENABLED": "false",
            "TELEGRAM_FAX_INTAKE_STATE_PATH": str(root / "telegram-intake.json"),
            "TELEGRAM_FAX_INTAKE_MARK_EXISTING_ON_FIRST_RUN": "true",
            "FAX_OUTGOING_ENABLED": "true",
            "FAX_OUTGOING_MODE": "dry-run",
            "FAX_OUTGOING_QUEUE_ROOT": str(root / "queue"),
            "FAX_OUTGOING_STATE_PATH": str(root / "queue" / "state.json"),
            "FAX_OUTGOING_DONEQ_ROOT": str(root / "doneq"),
        }
        values.update(overrides)
        return mock.patch.dict(os.environ, values, clear=False)

    @staticmethod
    def message(*, caption="fax:022848302", chat_id=-100123, chat_type="supergroup", topic=77):
        return {
            "message_id": 55,
            "message_thread_id": topic,
            "from": {"id": 777},
            "chat": {"id": chat_id, "type": chat_type},
            "caption": caption,
            "document": {
                "file_id": "telegram-file",
                "file_unique_id": "unique-file",
                "file_name": "notice.pdf",
                "mime_type": "application/pdf",
                "file_size": 16,
            },
        }

    def test_first_run_baselines_pending_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)

            def api_call(_token, method, _fields):
                self.assertEqual(method, "getUpdates")
                return [{"update_id": 9, "message": self.message()}]

            with self.env(root):
                accepted, rejected = telegram_intake.scan_once(api_call=api_call)
                state = telegram_intake.load_state()
                outgoing_state = outgoing.load_state()

        self.assertEqual((accepted, rejected), (0, 0))
        self.assertEqual(state, {"updateOffset": 10, "initialized": True})
        self.assertEqual(outgoing_state["jobs"], {})

    def test_first_run_keeps_baselining_when_update_page_is_full(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            updates = [{"update_id": value, "message": self.message()} for value in range(100)]

            with self.env(root):
                accepted, rejected = telegram_intake.scan_once(
                    api_call=lambda _token, _method, _fields: updates
                )
                state = telegram_intake.load_state()

        self.assertEqual((accepted, rejected), (0, 0))
        self.assertEqual(state, {"updateOffset": 100, "initialized": False})

    @mock.patch.object(telegram_intake.mail_organizer, "process_callback")
    @mock.patch.object(telegram_intake.document_intake, "process_callback", return_value="ignored")
    def test_mail_callbacks_share_the_single_update_consumer(self, document_callback, mail_callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            update = {
                "update_id": 14,
                "callback_query": {
                    "id": "mail-callback",
                    "data": "mail:m:digest1",
                    "from": {"id": 777},
                    "message": {
                        "message_id": 90,
                        "message_thread_id": 99,
                        "chat": {"id": -100123, "type": "supergroup"},
                    },
                },
            }
            with self.env(root):
                telegram_intake.save_state({"updateOffset": 0, "initialized": True})
                telegram_intake.scan_once(api_call=lambda *_args: [update])

        document_callback.assert_called_once()
        mail_callback.assert_called_once()

    def test_valid_group_topic_pdf_is_queued_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            replies = []

            def sender(_token, _chat_id, text, **kwargs):
                replies.append((text, kwargs))
                return {"message_id": 88}

            with self.env(root):
                telegram_intake.save_state({"updateOffset": 0, "initialized": True})
                first = telegram_intake.process_message(
                    self.message(),
                    file_downloader=lambda *_args, **_kwargs: b"%PDF-1.4\n%%EOF",
                    api_sender=sender,
                )
                second = telegram_intake.process_message(
                    self.message(),
                    file_downloader=lambda *_args, **_kwargs: b"%PDF-1.4\n%%EOF",
                    api_sender=sender,
                )
                jobs = list(outgoing.load_state()["jobs"].values())

        self.assertEqual(first, "accepted")
        self.assertEqual(second, "duplicate")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["destination"], "022848302")
        self.assertEqual(jobs[0]["source"], "telegram")
        self.assertEqual(jobs[0]["sourceMetadata"]["threadId"], 77)
        self.assertEqual(replies, [])

    def test_mobile_reply_to_pdf_is_queued(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            document = self.message(caption="")
            command = {
                "message_id": 56,
                "message_thread_id": 77,
                "from": {"id": 777},
                "chat": {"id": -100123, "type": "supergroup"},
                "text": "fax:022848302",
                "reply_to_message": document,
            }
            replies = []
            intake_state = {"promptMessageIds": {"-100123:55": 88}}

            with self.env(root):
                result = telegram_intake.process_message(
                    command,
                    file_downloader=lambda *_args, **_kwargs: b"%PDF-1.4\n%%EOF",
                    api_sender=lambda _token, _chat, text, **kwargs: replies.append((text, kwargs)),
                    intake_state=intake_state,
                )
                jobs = list(outgoing.load_state()["jobs"].values())

        self.assertEqual(result, "accepted")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["destination"], "022848302")
        self.assertEqual(jobs[0]["sourceMetadata"]["messageId"], 55)
        self.assertEqual(jobs[0]["sourceMetadata"]["commandMessageId"], 56)
        self.assertEqual(jobs[0]["sourceMetadata"]["instructionMessageId"], 88)
        self.assertNotIn("promptMessageIds", intake_state)
        self.assertEqual(replies, [])

    def test_uncaptioned_pdf_waits_for_mobile_reply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            downloader = mock.Mock()
            replies = []
            intake_state = {}
            with self.env(root):
                result = telegram_intake.process_message(
                    self.message(caption=""),
                    file_downloader=downloader,
                    api_sender=lambda _token, _chat, text, **kwargs: (
                        replies.append((text, kwargs)) or {"message_id": 88}
                    ),
                    intake_state=intake_state,
                )

        self.assertEqual(result, "waiting")
        downloader.assert_not_called()
        self.assertIn("Reply directly", replies[0][0])
        self.assertEqual(intake_state["promptMessageIds"], {"-100123:55": 88})

    def test_fax_number_without_pdf_reply_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            command = {
                "message_id": 56,
                "message_thread_id": 77,
                "from": {"id": 777},
                "chat": {"id": -100123, "type": "supergroup"},
                "text": "fax:022848302",
            }
            with self.env(root):
                with self.assertRaisesRegex(outgoing.OutgoingFaxError, "reply_to_pdf_required"):
                    telegram_intake.process_message(command)

    def test_private_other_group_and_other_topic_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with self.env(root):
                results = [
                    telegram_intake.process_message(self.message(chat_type="private")),
                    telegram_intake.process_message(self.message(chat_id=-100999)),
                    telegram_intake.process_message(self.message(topic=99)),
                ]

        self.assertEqual(results, ["ignored", "ignored", "ignored"])

    def test_user_message_in_memos_topic_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            deleted = []
            message = {
                "message_id": 91,
                "message_thread_id": 88,
                "from": {"id": 777, "is_bot": False},
                "chat": {"id": -100123, "type": "supergroup"},
                "text": "do not keep this",
            }
            with self.env(root):
                result = telegram_intake.protect_memos_topic(
                    message,
                    message_deleter=lambda token, chat, message_id: deleted.append(
                        (token, chat, message_id)
                    ),
                )

        self.assertEqual(result, "protected")
        self.assertEqual(deleted, [("token", "-100123", 91)])

    def test_bot_messages_in_memos_topic_are_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            message = {
                "message_id": 91,
                "message_thread_id": 88,
                "from": {"id": 1, "is_bot": True},
                "chat": {"id": -100123, "type": "supergroup"},
                "text": "archive",
            }
            with self.env(root):
                result = telegram_intake.protect_memos_topic(
                    message,
                    message_deleter=mock.Mock(),
                )

        self.assertEqual(result, "ignored")

    def test_invalid_caption_is_rejected_without_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            downloader = mock.Mock()
            with self.env(root):
                with self.assertRaisesRegex(outgoing.OutgoingFaxError, "caption_must"):
                    telegram_intake.process_message(
                        self.message(caption="022848302"),
                        file_downloader=downloader,
                    )

        downloader.assert_not_called()

    def test_bot_api_file_download_is_bounded(self):
        class Response:
            def __init__(self, body):
                self.body = body

            def read(self, limit=-1):
                return self.body if limit < 0 else self.body[:limit]

        def opener(request, timeout):
            self.assertEqual(timeout, 30)
            if request.full_url.endswith("/getFile"):
                return Response(
                    b'{"ok":true,"result":{"file_path":"documents/fax.pdf","file_size":14}}'
                )
            self.assertIn("/file/bottoken/documents/fax.pdf", request.full_url)
            return Response(b"%PDF-1.4\n%%EOF")

        content = telegram.download_file("token", "file-id", max_bytes=100, opener=opener)

        self.assertEqual(content, b"%PDF-1.4\n%%EOF")

    def test_local_bot_api_file_download_reads_shared_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            document = root / "documents" / "fax.pdf"
            document.parent.mkdir()
            document.write_bytes(b"%PDF-1.4\n%%EOF")

            def api_call(_token, method, _fields, *, opener=None):
                self.assertEqual(method, "getFile")
                return {"file_path": str(document), "file_size": document.stat().st_size}

            with mock.patch.dict(os.environ, {"TELEGRAM_LOCAL_FILE_ROOT": str(root)}), mock.patch.object(
                telegram, "call", side_effect=api_call
            ):
                content = telegram.download_file("token", "file-id", max_bytes=100)

        self.assertEqual(content, b"%PDF-1.4\n%%EOF")

    def test_local_bot_api_file_path_cannot_escape_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            outside = root.parent / "outside.pdf"
            with mock.patch.dict(os.environ, {"TELEGRAM_LOCAL_FILE_ROOT": str(root)}), mock.patch.object(
                telegram,
                "call",
                return_value={"file_path": str(outside), "file_size": 10},
            ):
                with self.assertRaisesRegex(telegram.TelegramError, "outside_root"):
                    telegram.download_file("token", "file-id", max_bytes=100)


if __name__ == "__main__":
    unittest.main()

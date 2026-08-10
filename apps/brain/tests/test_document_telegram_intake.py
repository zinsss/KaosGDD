import os
import pathlib
import sys
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.documents import telegram_intake


class DocumentTelegramIntakeTests(unittest.TestCase):
    def env(self):
        return mock.patch.dict(
            os.environ,
            {
                "TELEGRAM_DOCUMENT_INTAKE_ENABLED": "true",
                "TELEGRAM_BOT_TOKEN": "token",
                "TELEGRAM_SUPERGROUP_CHAT_ID": "-100123",
                "TELEGRAM_TOPIC_DOCUMENTS_ID": "99",
                "TELEGRAM_DOCUMENT_PUBLIC_ORIGIN": "https://kaosgdd.net",
                "TELEGRAM_DOCUMENT_MAX_MB": "20",
            },
            clear=False,
        )

    @staticmethod
    def message(topic=99):
        return {
            "message_id": 55,
            "message_thread_id": topic,
            "from": {"id": 777},
            "chat": {"id": -100123, "type": "supergroup"},
            "document": {
                "file_id": "telegram-file",
                "file_unique_id": "unique-file",
                "file_name": "report.pdf",
                "mime_type": "application/pdf",
                "file_size": 16,
            },
        }

    @mock.patch.object(telegram_intake.store, "store_document")
    def test_pdf_uses_queue_and_returns_actions(self, store_document):
        store_document.return_value = {
            "id": "12345678-1234-1234-1234-123456789012",
            "filename": "report.pdf",
        }
        sent = []
        with self.env():
            result = telegram_intake.process_message(
                self.message(),
                file_downloader=lambda *_args, **_kwargs: b"%PDF-1.4\n%%EOF",
                api_sender=lambda *args, **kwargs: sent.append((args, kwargs)),
            )

        self.assertEqual(result, "accepted")
        store_document.assert_called_once()
        self.assertEqual(store_document.call_args.args[3:5], ("telegram", "main"))
        self.assertEqual(
            store_document.call_args.kwargs["source_key"],
            "telegram:-100123:55:unique-file",
        )
        buttons = sent[0][1]["reply_markup"]["inline_keyboard"][0]
        self.assertEqual([button["text"] for button in buttons], ["Open", "Paperless", "Delete"])
        self.assertEqual(sent[0][1]["reply_to_message_id"], 55)

    def test_non_pdf_is_rejected_before_download(self):
        message = self.message()
        message["document"]["file_name"] = "photo.jpg"
        message["document"]["mime_type"] = "image/jpeg"
        downloader = mock.Mock()
        with self.env():
            with self.assertRaisesRegex(telegram_intake.DocumentTelegramError, "pdf_required"):
                telegram_intake.process_message(message, file_downloader=downloader)
        downloader.assert_not_called()

    @mock.patch.object(telegram_intake.store, "submit_to_paperless")
    def test_paperless_callback_submits_and_removes_actions(self, submit):
        answered = []
        edited = []
        callback = {
            "id": "callback-1",
            "data": "document:paperless:12345678-1234-1234-1234-123456789012",
            "message": {
                "message_id": 90,
                "message_thread_id": 99,
                "chat": {"id": -100123, "type": "supergroup"},
            },
        }
        with self.env():
            result = telegram_intake.process_callback(
                callback,
                callback_answerer=lambda *args: answered.append(args),
                markup_editor=lambda *args: edited.append(args),
            )

        self.assertEqual(result, "paperless")
        submit.assert_called_once_with("12345678-1234-1234-1234-123456789012", "main")
        self.assertEqual(answered[0][2], "Sent to Paperless")
        self.assertEqual(edited[0][3], {"inline_keyboard": []})

    def test_other_topic_is_ignored(self):
        with self.env():
            self.assertEqual(telegram_intake.process_message(self.message(topic=77)), "ignored")


if __name__ == "__main__":
    unittest.main()

import json
import os
import pathlib
import sys
import tempfile
import urllib.parse
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.faxmail import telegram_archive


class TelegramFaxArchiveTests(unittest.TestCase):
    def env(self, root, **overrides):
        values = {
            "FAX_TELEGRAM_ARCHIVE_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_SUPERGROUP_CHAT_ID": "123456",
            "FAX_TELEGRAM_ARCHIVE_CHAT_ID": "123456",
            "FAX_TELEGRAM_ARCHIVE_TOPIC_ID": "77",
            "FAX_TELEGRAM_ARCHIVE_STATE_PATH": str(root / "telegram-state.json"),
            "FAX_TELEGRAM_ARCHIVE_RECVQ": str(root / "hylafax" / "recvq"),
            "FAX_TELEGRAM_ARCHIVE_XFERFAXLOG": str(root / "hylafax" / "log" / "xferfaxlog"),
            "FAX_TELEGRAM_ARCHIVE_MIN_FILE_AGE_SECONDS": "0",
            "FAX_TELEGRAM_ARCHIVE_OUTGOING_STATE_PATH": str(root / "fax-outgoing" / "state.json"),
            "FAX_TELEGRAM_ARCHIVE_MARK_EXISTING_ON_FIRST_RUN": "false",
        }
        values.update(overrides)
        return mock.patch.dict(os.environ, values, clear=False)

    def create_incoming(self, root):
        recvq = root / "hylafax" / "recvq"
        log = root / "hylafax" / "log" / "xferfaxlog"
        recvq.mkdir(parents=True)
        log.parent.mkdir(parents=True)
        (recvq / "fax000000007.tif").write_bytes(b"TIFF-incoming")
        log.write_text(
            '07/26/26 13:55\tRECV\t000000007\tttyACM0\trecvq/fax000000007.tif\t""\tfax\t""\t"0547337787"\t9600\t1\n',
            encoding="utf-8",
        )

    def create_outgoing(self, root):
        queue = root / "fax-outgoing"
        job_id = "a" * 32
        document = queue / "jobs" / job_id / "document.pdf"
        document.parent.mkdir(parents=True)
        document.write_bytes(b"%PDF-outgoing")
        (queue / "state.json").write_text(
            json.dumps(
                {
                    "jobs": {
                        job_id: {
                            "status": "sent",
                            "destination": "022848302",
                            "filename": "request.pdf",
                            "completedAt": "2026-08-09T12:00:00Z",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def test_scans_only_confirmed_incoming_and_outgoing_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.create_incoming(root)
            self.create_outgoing(root)
            with self.env(root):
                items = telegram_archive.scan_incoming() + telegram_archive.scan_outgoing()

        self.assertEqual([item.key for item in items], ["received:000000007", f"sent:{'a' * 32}"])
        self.assertEqual(items[0].filename, "2026-07-26-13:55_FROM_0547337787.pdf")
        self.assertEqual(items[0].caption, "")
        self.assertEqual(items[0].path.name, "fax000000007.tif")
        self.assertIn("to 022848302", items[1].caption)
        self.assertNotIn("request.pdf", items[1].caption)
        self.assertNotIn("job ", items[1].caption)
        self.assertEqual(
            items[1].caption,
            "Sent fax.\n: to 022848302\n: 2026-08-09 21:00",
        )

    def test_archive_uploads_each_document_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.create_incoming(root)
            self.create_outgoing(root)
            uploaded = []

            def uploader(item):
                uploaded.append(item.key)
                return {"messageId": len(uploaded)}

            with self.env(root):
                first = telegram_archive.scan_and_archive(uploader=uploader)
                second = telegram_archive.scan_and_archive(uploader=uploader)
                state = telegram_archive.load_state()

        self.assertEqual(first, 2)
        self.assertEqual(second, 0)
        self.assertEqual(len(uploaded), 2)
        self.assertEqual(set(state["archived"]), {"received:000000007", f"sent:{'a' * 32}"})

    def test_first_run_baselines_existing_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.create_incoming(root)
            uploader = mock.Mock()
            with self.env(root, FAX_TELEGRAM_ARCHIVE_MARK_EXISTING_ON_FIRST_RUN="true"):
                count = telegram_archive.scan_and_archive(uploader=uploader)
                state = telegram_archive.load_state()

        self.assertEqual(count, 0)
        uploader.assert_not_called()
        self.assertEqual(state["archived"]["received:000000007"]["status"], "baselined")

    def test_send_document_posts_multipart_without_enabling_notifications(self):
        class Response:
            def read(self):
                return b'{"ok":true,"result":{"message_id":42}}'

        captured = {}

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            document = root / "fax.pdf"
            document.write_bytes(b"%PDF-test")
            item = telegram_archive.ArchiveItem(
                key="sent:test",
                direction="sent",
                path=document,
                filename="fax.pdf",
                caption="Sent fax.",
            )
            with self.env(root):
                result = telegram_archive.send_document(item, opener=opener)

        body = captured["request"].data
        self.assertEqual(result, {"messageId": 42})
        self.assertIn(b'name="chat_id"', body)
        self.assertIn(b"123456", body)
        self.assertIn(b'name="message_thread_id"\r\n\r\n77', body)
        self.assertIn(b'name="disable_notification"\r\n\r\ntrue', body)
        self.assertIn(b"%PDF-test", body)
        self.assertNotIn(b"test-token", body)

    def test_received_tiff_is_converted_and_uploaded_without_caption(self):
        class Response:
            def read(self):
                return b'{"ok":true,"result":{"message_id":43}}'

        captured = {}

        def opener(request, timeout):
            captured["body"] = request.data
            captured["timeout"] = timeout
            return Response()

        def converter(_source, output):
            output.write_bytes(b"%PDF-converted")

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "fax000000007.tif"
            source.write_bytes(b"TIFF-incoming")
            item = telegram_archive.ArchiveItem(
                key="received:000000007",
                direction="received",
                path=source,
                filename="2026-07-26-13:55_FROM_0547337787.pdf",
                caption="",
            )
            with self.env(root):
                result = telegram_archive.send_document(
                    item,
                    opener=opener,
                    converter=converter,
                )

        self.assertEqual(result, {"messageId": 43})
        self.assertIn(b'filename="2026-07-26-13:55_FROM_0547337787.pdf"', captured["body"])
        self.assertIn(b"%PDF-converted", captured["body"])
        self.assertNotIn(b'name="caption"', captured["body"])

    def test_send_document_preserves_korean_filename_metadata(self):
        class Response:
            def read(self):
                return b'{"ok":true,"result":{"message_id":44}}'

        captured = {}

        def opener(request, timeout):
            captured["body"] = request.data
            return Response()

        filename = "초2_2학기_곱셈의뜻_30문제_문제집형.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            document = root / "document.pdf"
            document.write_bytes(b"%PDF-test")
            item = telegram_archive.ArchiveItem(
                key="sent:korean",
                direction="sent",
                path=document,
                filename=filename,
                caption="Sent fax.",
            )
            with self.env(root):
                result = telegram_archive.send_document(item, opener=opener)

        encoded = urllib.parse.quote(filename, safe="").encode("ascii")
        self.assertEqual(result, {"messageId": 44})
        self.assertIn(f'filename="{filename}"'.encode("utf-8"), captured["body"])
        self.assertIn(b"filename*=UTF-8''" + encoded, captured["body"])

    def test_shared_supergroup_and_named_fax_topic_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with self.env(
                root,
                FAX_TELEGRAM_ARCHIVE_CHAT_ID="",
                FAX_TELEGRAM_ARCHIVE_TOPIC_ID="",
                TELEGRAM_SUPERGROUP_CHAT_ID="-100123",
                TELEGRAM_TOPIC_FAX_ID="88",
            ):
                self.assertEqual(telegram_archive.chat_id(), "-100123")
                self.assertEqual(telegram_archive.topic_id(), "88")

if __name__ == "__main__":
    unittest.main()

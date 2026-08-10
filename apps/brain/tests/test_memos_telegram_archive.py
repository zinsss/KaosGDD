import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.memos import telegram_archive


class MemosTelegramArchiveTests(unittest.TestCase):
    def env(self, root):
        return mock.patch.dict(
            os.environ,
            {
                "MEMOS_TELEGRAM_ARCHIVE_ENABLED": "true",
                "MEMOS_TELEGRAM_ARCHIVE_STATE_PATH": str(root / "telegram-archive.json"),
                "MEMOS_PERSONAL_USERNAME": "zin",
                "TELEGRAM_BOT_TOKEN": "token",
                "TELEGRAM_SUPERGROUP_CHAT_ID": "-100123",
                "TELEGRAM_TOPIC_MEMOS_ID": "88",
            },
            clear=False,
        )

    @staticmethod
    def memo(name="memos/one", content="First memo", update_time="2026-08-10T01:00:00Z"):
        return {
            "name": name,
            "state": "NORMAL",
            "creator": "users/zin",
            "content": content,
            "createTime": "2026-08-10T00:00:00Z",
            "updateTime": update_time,
            "attachments": [],
        }

    @staticmethod
    def requester(pages):
        calls = []

        def request(method, path, access_token=""):
            calls.append((method, path, access_token))
            page = pages[len(calls) - 1]
            return 200, "application/json", json.dumps(page).encode("utf-8")

        return request, calls

    def test_initial_scan_archives_personal_memos_and_stores_only_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            request, calls = self.requester([{"memos": [self.memo()]}])
            sent = []

            def sender(_token, _chat, text, **kwargs):
                sent.append((text, kwargs))
                return {"message_id": 501}

            with self.env(root), mock.patch.object(
                telegram_archive.relay, "load_token", return_value="personal-token"
            ):
                result = telegram_archive.scan_once(requester=request, sender=sender)
                state = telegram_archive.load_state()

        self.assertEqual(result, (1, 0, 0, 1))
        self.assertEqual(state["memos"]["memos/one"]["messageIds"], [501])
        self.assertNotIn("First memo", json.dumps(state))
        self.assertIn("First memo", sent[0][0])
        self.assertEqual(sent[0][1]["thread_id"], "88")
        self.assertIn("filter=creator+%3D%3D+%22users%2Fzin%22", calls[0][1])

    def test_changed_memo_edits_existing_message_without_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            request, _calls = self.requester([{"memos": [self.memo(content="Changed")]}])
            edits = []
            telegram_archive.save_state(
                {
                    "memos": {
                        "memos/one": {
                            "messageIds": [501],
                            "contentHash": "old",
                            "deleted": False,
                        }
                    }
                },
                root / "telegram-archive.json",
            )

            with self.env(root), mock.patch.object(
                telegram_archive.relay, "load_token", return_value="personal-token"
            ):
                result = telegram_archive.scan_once(
                    requester=request,
                    sender=mock.Mock(),
                    editor=lambda token, chat, message_id, text: edits.append(
                        (token, chat, message_id, text)
                    ),
                )

        self.assertEqual(result, (0, 1, 0, 1))
        self.assertEqual(edits[0][2], 501)
        self.assertIn("Changed", edits[0][3])

    def test_long_memo_is_archived_without_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            content = "A" * 8000
            request, _calls = self.requester([{"memos": [self.memo(content=content)]}])
            sent = []

            def sender(_token, _chat, text, **_kwargs):
                sent.append(text)
                return {"message_id": 600 + len(sent)}

            with self.env(root), mock.patch.object(
                telegram_archive.relay, "load_token", return_value="personal-token"
            ):
                result = telegram_archive.scan_once(requester=request, sender=sender)
                state = telegram_archive.load_state()

        self.assertEqual(result[0], 1)
        self.assertGreater(len(sent), 1)
        self.assertTrue(all(len(value) <= 4096 for value in sent))
        self.assertEqual(len(state["memos"]["memos/one"]["messageIds"]), len(sent))
        self.assertEqual("".join(part.split("\n\n", 1)[1] for part in sent).count("A"), 8000)

    def test_missing_memo_keeps_archive_and_sends_deletion_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            request, _calls = self.requester([{"memos": []}])
            telegram_archive.save_state(
                {
                    "memos": {
                        "memos/one": {
                            "messageIds": [501],
                            "contentHash": "old",
                            "deleted": False,
                        }
                    }
                },
                root / "telegram-archive.json",
            )
            sent = []

            def sender(_token, _chat, text, **_kwargs):
                sent.append(text)
                return {"message_id": 700}

            with self.env(root), mock.patch.object(
                telegram_archive.relay, "load_token", return_value="personal-token"
            ):
                result = telegram_archive.scan_once(requester=request, sender=sender)
                state = telegram_archive.load_state()

        record = state["memos"]["memos/one"]
        self.assertEqual(result, (0, 0, 1, 0))
        self.assertEqual(record["messageIds"], [501])
        self.assertEqual(record["deletionMessageId"], 700)
        self.assertTrue(record["deleted"])
        self.assertIn("deleted from Memos", sent[0])

    def test_failed_list_does_not_mark_archived_memos_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            telegram_archive.save_state(
                {"memos": {"memos/one": {"messageIds": [501], "deleted": False}}},
                root / "telegram-archive.json",
            )

            def request(*_args, **_kwargs):
                return 503, "application/json", b"{}"

            with self.env(root), mock.patch.object(
                telegram_archive.relay, "load_token", return_value="personal-token"
            ):
                with self.assertRaisesRegex(RuntimeError, "memos_list_http_503"):
                    telegram_archive.scan_once(requester=request, sender=mock.Mock())
                state = telegram_archive.load_state()

        self.assertFalse(state["memos"]["memos/one"]["deleted"])

    def test_pagination_and_creator_filter_are_enforced(self):
        other = self.memo(name="memos/family")
        other["creator"] = "users/family"
        request, calls = self.requester(
            [
                {"memos": [self.memo(), other], "nextPageToken": "next"},
                {"memos": [self.memo(name="memos/two")]},
            ]
        )
        with mock.patch.dict(os.environ, {"MEMOS_PERSONAL_USERNAME": "zin"}), mock.patch.object(
            telegram_archive.relay, "load_token", return_value="personal-token"
        ):
            result = telegram_archive.list_personal_memos(requester=request)

        self.assertEqual([memo["name"] for memo in result], ["memos/one", "memos/two"])
        self.assertIn("pageToken=next", calls[1][1])


if __name__ == "__main__":
    unittest.main()

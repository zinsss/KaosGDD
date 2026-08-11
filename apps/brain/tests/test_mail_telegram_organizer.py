import os
import pathlib
import sys
import tempfile
import time
import unittest
from datetime import datetime
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.mail import telegram_organizer


class FakeInboxServer:
    def __init__(self):
        self.uidvalidity = "42"
        self.messages = {
            7: self.message("Newest unread", "new@example.test", "First line\nSecond line"),
            3: self.message("Older unread", "old@example.test", "Older body"),
        }
        self.seen = set()
        self.moved = []

    @staticmethod
    def message(subject, sender, body):
        return (
            f"From: {sender}\r\n"
            f"Subject: {subject}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "MIME-Version: 1.0\r\n\r\n"
            f"{body}"
        ).encode("utf-8")

    def factory(self, _host, _port, timeout):
        self.timeout = timeout
        return FakeIMAP(self)


class FakeIMAP:
    def __init__(self, server):
        self.server = server

    def login(self, _username, _password):
        return "OK", [b"logged in"]

    def select(self, mailbox, readonly=False):
        self.mailbox = mailbox
        self.readonly = readonly
        return "OK", [str(len(self.server.messages)).encode()]

    def response(self, code):
        return code, [self.server.uidvalidity.encode()]

    def uid(self, command, *args):
        command = command.lower()
        if command == "search":
            values = [uid for uid in self.server.messages if uid not in self.server.seen]
            return "OK", [" ".join(str(uid) for uid in sorted(values)).encode()]
        if command == "fetch":
            uid = int(args[0])
            return "OK", [(b"message", self.server.messages[uid])]
        sequence = [int(value) for value in str(args[0]).split(",") if value]
        if command == "store":
            self.server.seen.update(sequence)
            return "OK", [b"stored"]
        if command == "move":
            self.server.moved.append((sequence, args[1]))
            for uid in sequence:
                self.server.messages.pop(uid, None)
            return "OK", [b"moved"]
        raise AssertionError((command, args))

    def unselect(self):
        return "OK", [b"unselected"]

    def logout(self):
        return "BYE", [b"logout"]


class MailTelegramOrganizerTests(unittest.TestCase):
    def environment(self, root, **overrides):
        values = {
            "MAIL_ORGANIZER_ENABLED": "true",
            "MAIL_ORGANIZER_ALLOWED_USER_IDS": "777",
            "MAIL_ORGANIZER_STATE_PATH": str(root / "organizer.json"),
            "MAIL_NOTIFY_NAVER_ENABLED": "true",
            "MAIL_NOTIFY_NAVER_USERNAME": "user",
            "MAIL_NOTIFY_NAVER_PASSWORD": "password",
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_SUPERGROUP_CHAT_ID": "-100123",
            "TELEGRAM_TOPIC_MAIL_ID": "99",
        }
        values.update(overrides)
        return mock.patch.dict(os.environ, values, clear=False)

    @staticmethod
    def callback(data, *, message_id=20, user_id=777, date=None):
        return {
            "id": "callback-1",
            "data": data,
            "from": {"id": user_id},
            "message": {
                "message_id": message_id,
                "message_thread_id": 99,
                "date": int(date if date is not None else time.time()),
                "chat": {"id": -100123, "type": "supergroup"},
            },
        }

    def send_digest(self, root, server):
        sent = []

        def sender(_token, _chat_id, text, **kwargs):
            sent.append((text, kwargs))
            return {"message_id": 20 + len(sent)}

        with self.environment(root):
            result = telegram_organizer.send_digest(imap_factory=server.factory, sender=sender)
            state = telegram_organizer.load_state()
        return result, state, sent

    def test_digest_lists_each_unread_subject_as_one_button_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            result, state, sent = self.send_digest(root, FakeInboxServer())

        digest = state["digests"][result["digestId"]]
        rows = sent[0][1]["reply_markup"]["inline_keyboard"]
        self.assertEqual(sent[0][0].splitlines()[0], "Naver Mail")
        self.assertEqual([row[0]["text"] for row in rows], ["Newest unread", "Older unread", "Menu"])
        self.assertEqual(result["unreadCount"], 2)
        self.assertNotIn("preview", next(iter(digest["items"].values())))

    def test_open_sends_detail_with_actions_and_does_not_mark_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            server = FakeInboxServer()
            result, state, _sent = self.send_digest(root, server)
            item_id = next(
                key
                for key, item in state["digests"][result["digestId"]]["items"].items()
                if item["uid"] == 7
            )
            details = []
            answers = []
            with self.environment(root):
                action = telegram_organizer.process_callback(
                    self.callback(f"mail:o:{result['digestId']}:{item_id}"),
                    imap_factory=server.factory,
                    sender=lambda _token, _chat, text, **kwargs: details.append((text, kwargs)) or {"message_id": 40},
                    callback_answerer=lambda *args: answers.append(args),
                )

        self.assertEqual(action, "opened")
        self.assertIn("Newest unread", details[0][0])
        self.assertEqual(
            [button["text"] for button in details[0][1]["reply_markup"]["inline_keyboard"][0]],
            ["Mark Read", "Import", "Delete"],
        )
        self.assertEqual(server.seen, set())
        self.assertTrue(answers)

    def test_mark_read_mutates_naver_and_removes_digest_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            server = FakeInboxServer()
            result, state, _sent = self.send_digest(root, server)
            digest = state["digests"][result["digestId"]]
            item_id, item = next(iter(digest["items"].items()))
            edits = []
            with self.environment(root):
                action = telegram_organizer.process_callback(
                    self.callback(f"mail:r:{result['digestId']}:{item_id}"),
                    imap_factory=server.factory,
                    callback_answerer=lambda *_args: None,
                    markup_editor=lambda *args: edits.append(args),
                )
                saved = telegram_organizer.load_state()

        self.assertEqual(action, "read")
        self.assertEqual(server.seen, {item["uid"]})
        self.assertNotIn(item_id, saved["digests"][result["digestId"]]["items"])
        self.assertEqual(len(edits), 2)

    def test_delete_requires_fresh_confirmation_and_moves_to_naver_trash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            server = FakeInboxServer()
            result, state, _sent = self.send_digest(root, server)
            item_id = next(iter(state["digests"][result["digestId"]]["items"]))
            confirmations = []
            deleted_messages = []
            with self.environment(root):
                first = telegram_organizer.process_callback(
                    self.callback(f"mail:d:{result['digestId']}:{item_id}"),
                    sender=lambda _token, _chat, text, **kwargs: confirmations.append((text, kwargs)) or {"message_id": 50},
                    callback_answerer=lambda *_args: None,
                )
                second = telegram_organizer.process_callback(
                    self.callback(f"mail:cd:{result['digestId']}:{item_id}", message_id=50),
                    imap_factory=server.factory,
                    callback_answerer=lambda *_args: None,
                    markup_editor=lambda *_args: None,
                    message_deleter=lambda *args: deleted_messages.append(args),
                )

        self.assertEqual(first, "confirmation")
        self.assertEqual(second, "delete")
        self.assertEqual(server.moved[0][1], '"Deleted Messages"')
        self.assertTrue(deleted_messages)

    def test_delete_all_uses_only_the_digest_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            server = FakeInboxServer()
            result, _state, _sent = self.send_digest(root, server)
            server.messages[9] = server.message("Arrived later", "later@example.test", "Not in digest")
            with self.environment(root):
                telegram_organizer.process_callback(
                    self.callback(f"mail:cda:{result['digestId']}", message_id=50),
                    imap_factory=server.factory,
                    callback_answerer=lambda *_args: None,
                    markup_editor=lambda *_args: None,
                    message_deleter=lambda *_args: None,
                )

        self.assertEqual(set(server.moved[0][0]), {3, 7})
        self.assertIn(9, server.messages)

    def test_import_reuses_archive_without_marking_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            server = FakeInboxServer()
            result, state, _sent = self.send_digest(root, server)
            item_id, selected = next(iter(state["digests"][result["digestId"]]["items"].items()))
            archived = []
            with self.environment(root), mock.patch.object(
                telegram_organizer.telegram_archive,
                "archive_mail",
                side_effect=lambda mail, progress, persist=None: archived.append(mail.subject),
            ):
                action = telegram_organizer.process_callback(
                    self.callback(f"mail:i:{result['digestId']}:{item_id}"),
                    imap_factory=server.factory,
                    callback_answerer=lambda *_args: None,
                    markup_editor=lambda *_args: None,
                )

        self.assertEqual(action, "imported")
        self.assertEqual(archived, [selected["subject"]])
        self.assertEqual(server.seen, set())

    def test_scheduler_sends_latest_due_slot_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            sent = []
            now = datetime.fromisoformat("2026-08-11T18:00:00+09:00")
            with self.environment(root), mock.patch.object(telegram_organizer, "configured", return_value=True):
                first = telegram_organizer.send_due_digest(
                    now=now,
                    settings_getter=lambda: {"runsPerDay": 2, "firstTime": "09:00", "secondTime": "17:00"},
                    digest_sender=lambda **_kwargs: sent.append("sent") or {"ok": True},
                )
                second = telegram_organizer.send_due_digest(
                    now=now,
                    settings_getter=lambda: {"runsPerDay": 2, "firstTime": "09:00", "secondTime": "17:00"},
                    digest_sender=lambda **_kwargs: sent.append("sent") or {"ok": True},
                )

        self.assertEqual(first, {"ok": True})
        self.assertIsNone(second)
        self.assertEqual(sent, ["sent"])

    def test_once_daily_allows_first_time_after_unused_second_time(self):
        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, _sql, values):
                self.values = values
                return self

            def fetchone(self):
                return (1, self.values[1], self.values[2], datetime.now())

        with mock.patch.object(telegram_organizer, "connect", return_value=Connection()):
            settings = telegram_organizer.update_settings(
                {"runsPerDay": 1, "firstTime": "20:00", "secondTime": "17:00"}
            )

        self.assertEqual(settings["firstTime"], "20:00")
        with self.assertRaisesRegex(ValueError, "times_out_of_order"):
            telegram_organizer.update_settings(
                {"runsPerDay": 2, "firstTime": "20:00", "secondTime": "17:00"}
            )


if __name__ == "__main__":
    unittest.main()

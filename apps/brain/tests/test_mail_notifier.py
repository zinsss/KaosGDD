import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.mail import notifier


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b"ok"


class FakeMailboxServer:
    def __init__(self):
        root = notifier.encode_modified_utf7("각종공문")
        child = notifier.encode_modified_utf7("각종공문/보건소")
        tax = notifier.encode_modified_utf7("세무사")
        tax_child = notifier.encode_modified_utf7("세무사/부가세")
        self.mailboxes = {
            root: {"uidvalidity": "10", "messages": {1: self.header("Existing")}},
            child: {"uidvalidity": "11", "messages": {}},
            tax: {"uidvalidity": "12", "messages": {}},
            tax_child: {"uidvalidity": "13", "messages": {}},
        }

    @staticmethod
    def header(subject, to_address="clinic@example.test"):
        return (
            f"From: Sender <sender@example.test>\r\n"
            f"To: {to_address}\r\n"
            f"Subject: {subject}\r\n"
            f"Message-ID: <{subject.lower()}@example.test>\r\n\r\n"
        ).encode()

    def factory(self, _host, _port, timeout):
        self.timeout = timeout
        return FakeIMAP(self)


class FakeIMAP:
    def __init__(self, server):
        self.server = server
        self.selected = ""

    def login(self, _username, _password):
        return "OK", [b"logged in"]

    def list(self):
        rows = [f'(\\HasNoChildren) "/" "{name}"'.encode() for name in self.server.mailboxes]
        return "OK", rows

    def select(self, mailbox, readonly=False):
        self.readonly = readonly
        self.selected = notifier.unquote_imap(mailbox)
        return "OK", [str(len(self.server.mailboxes[self.selected]["messages"])).encode()]

    def response(self, code):
        self.response_code = code
        return code, [self.server.mailboxes[self.selected]["uidvalidity"].encode()]

    def uid(self, command, *args):
        mailbox = self.server.mailboxes[self.selected]
        if command == "search":
            values = " ".join(str(uid) for uid in sorted(mailbox["messages"]))
            return "OK", [values.encode()]
        if command == "fetch":
            uid = int(args[0])
            return "OK", [(b"header", mailbox["messages"][uid])]
        raise AssertionError(command)

    def close(self):
        return "OK", [b"closed"]

    def logout(self):
        return "BYE", [b"logout"]


class MailNotifierTests(unittest.TestCase):
    def setUp(self):
        notifier.WORKER_STATE["started"] = False
        notifier.WORKER_STATE["lastScanAt"] = ""
        notifier.WORKER_STATE["lastNotifyAt"] = ""
        notifier.WORKER_STATE["notifiedCount"] = 0
        notifier.WORKER_STATE["accounts"] = {
            "naver": {"lastError": "", "mailboxCount": 0},
            "gmailFax": {"lastError": "", "mailboxCount": 0},
        }

    def test_modified_utf7_round_trip(self):
        value = "각종공문/하위 폴더 & test"
        self.assertEqual(notifier.decode_modified_utf7(notifier.encode_modified_utf7(value)), value)

    def test_discovers_naver_root_and_descendants(self):
        server = FakeMailboxServer()
        client = server.factory("imap.naver.com", 993, timeout=20)
        config = notifier.AccountConfig(
            key="naver",
            label="Naver",
            enabled=True,
            host="imap.naver.com",
            port=993,
            username="user",
            password="password",
            folder_root="각종공문,세무사",
            include_descendants=True,
            match_addresses=(),
        )

        mailboxes = notifier.discover_mailboxes(client, config)

        self.assertEqual(
            [mailbox.display_name for mailbox in mailboxes],
            ["각종공문", "각종공문/보건소", "세무사", "세무사/부가세"],
        )

    def test_gmail_filter_accepts_only_configured_fax_aliases(self):
        config = notifier.AccountConfig(
            key="gmailFax",
            label="Fax mail",
            enabled=True,
            host="imap.gmail.com",
            port=993,
            username="fax@example.test",
            password="password",
            folder_root="INBOX",
            include_descendants=False,
            match_addresses=("fax-in@kaosgdd.net", "fax-send@kaosgdd.net"),
        )
        matching = notifier.MailEvent(
            "gmailFax", "Fax mail", "INBOX", 1, "Fax", "Sender", ("fax-in@kaosgdd.net",), "",
        )
        unrelated = notifier.MailEvent(
            "gmailFax", "Fax mail", "INBOX", 2, "Other", "Sender", ("other@example.test",), "",
        )

        self.assertTrue(notifier.event_matches(config, matching))
        self.assertFalse(notifier.event_matches(config, unrelated))

    def test_first_scan_baselines_then_new_naver_mail_notifies_both_audiences(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp:
            state = pathlib.Path(tmp) / "state.json"
            server = FakeMailboxServer()
            environment = {
                "MAIL_NOTIFY_NAVER_ENABLED": "true",
                "MAIL_NOTIFY_NAVER_USERNAME": "user",
                "MAIL_NOTIFY_NAVER_PASSWORD": "password",
                "MAIL_NOTIFY_GMAIL_ENABLED": "false",
                "MAIL_NOTIFY_STATE_PATH": str(state),
                "NTFY_URL": "http://ntfy",
                "NTFY_TOPIC_IOS": "kaosgdd-ios",
                "NTFY_TOPIC_DESKTOP": "kaosgdd-desktop",
                "NTFY_TOPIC_SYSTEM": "kaosgdd-system",
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                first_sent = notifier.scan_and_notify(
                    imap_factories={"naver": server.factory},
                    opener=opener,
                )
                root = notifier.encode_modified_utf7("각종공문")
                server.mailboxes[root]["messages"][2] = server.header("New notice")
                second_sent = notifier.scan_and_notify(
                    imap_factories={"naver": server.factory},
                    opener=opener,
                )

            saved = notifier.load_state(state)

        self.assertEqual(first_sent, 0)
        self.assertEqual(second_sent, 1)
        self.assertEqual(
            [request.full_url for request, _timeout in requests],
            ["http://ntfy/kaosgdd-ios", "http://ntfy/kaosgdd-desktop"],
        )
        self.assertIn(b"New notice", requests[0][0].data)
        self.assertEqual(saved["accounts"]["naver"]["mailboxes"][root]["lastUid"], 2)


if __name__ == "__main__":
    unittest.main()

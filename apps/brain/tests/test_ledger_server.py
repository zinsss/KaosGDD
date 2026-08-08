import io
import json
import pathlib
import sys
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from api import server


class LedgerRequestTests(unittest.TestCase):
    @mock.patch.object(server.ledger_service, "list_ledger")
    def test_ledger_read_is_family_only(self, list_ledger):
        list_ledger.return_value = {"ok": True, "entries": [], "balances": {}}
        handler = mock.Mock()
        handler.path = "/api/ledger"
        handler.headers = {"Host": "family.kaosgdd.net"}
        handler.wfile = io.BytesIO()

        server.Handler.do_GET(handler)

        list_ledger.assert_called_once_with()
        handler.send_response.assert_called_once_with(200)

        denied = mock.Mock()
        denied.path = "/api/ledger"
        denied.headers = {"Host": "kaosgdd.net"}
        denied.wfile = io.BytesIO()
        server.Handler.do_GET(denied)
        denied.send_response.assert_called_once_with(404)

    @mock.patch.object(server.ledger_service, "create_entry")
    def test_create_uses_cloudflare_authenticated_actor(self, create_entry):
        create_entry.return_value = {"ok": True, "entries": []}
        payload = json.dumps(
            {"date": "2026-08-08", "category": "현금 지출", "amount": 1000, "details": "test"}
        ).encode()
        handler = mock.Mock()
        handler.path = "/api/ledger/entries"
        handler.headers = {
            "Host": "family.kaosgdd.net",
            "Content-Length": str(len(payload)),
            "Cf-Access-Authenticated-User-Email": "wife@example.com",
        }
        handler.rfile = io.BytesIO(payload)
        handler.wfile = io.BytesIO()

        server.Handler.do_POST(handler)

        create_entry.assert_called_once_with(json.loads(payload), "wife@example.com")
        handler.send_response.assert_called_once_with(201)

    @mock.patch.object(server.ledger_service, "update_entry")
    def test_revision_conflict_returns_409(self, update_entry):
        update_entry.side_effect = server.ledger_service.LedgerConflict("ledger_revision_conflict")
        payload = b'{"baseRevision":1}'
        handler = mock.Mock()
        handler.path = "/api/ledger/entries/entry-1"
        handler.headers = {"Host": "family.kaosgdd.net", "Content-Length": str(len(payload))}
        handler.rfile = io.BytesIO(payload)
        handler.wfile = io.BytesIO()

        server.Handler.do_PUT(handler)

        handler.send_response.assert_called_once_with(409)

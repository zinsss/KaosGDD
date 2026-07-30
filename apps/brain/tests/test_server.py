import pathlib
import sys
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from api import server


class BrainStatusTests(unittest.TestCase):
    @mock.patch.object(server, "adapter_status")
    @mock.patch.object(server, "database_status")
    def test_status_reports_shadow_dependencies(self, database_status, adapter_status):
        database_status.return_value = {
            "ok": True,
            "database": "kaosgdd_brain",
            "user": "kaosgdd_brain",
            "migration": "001",
        }
        adapter_status.return_value = {
            "ok": True,
            "status": 200,
            "profile": "family",
            "configured": True,
        }

        payload = server.brain_status({"Host": "family.kaosgdd.net"})

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "shadow")
        self.assertEqual(payload["profile"], "family")
        self.assertEqual(payload["database"]["migration"], "001")
        adapter_status.assert_called_once_with("family.kaosgdd.net")


if __name__ == "__main__":
    unittest.main()

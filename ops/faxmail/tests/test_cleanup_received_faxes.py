import importlib.util
import json
import pathlib
import tempfile
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "cleanup-received-faxes.py"
SPEC = importlib.util.spec_from_file_location("fax_retention", MODULE_PATH)
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)


class FaxRetentionTests(unittest.TestCase):
    def setup_case(self, root, *, sent_at, failed=False, source=None):
        state = root / "state"
        sent = state / "sent"
        failures = state / "failed"
        recvq = root / "recvq"
        backup = root / "backup"
        sent.mkdir(parents=True)
        failures.mkdir()
        recvq.mkdir()
        backup.mkdir()
        source = source or recvq / "fax000000001.tif"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"fax")
        (backup / source.name).write_bytes(b"fax-backup")
        marker = sent / "000000001.json"
        marker.write_text(
            json.dumps({"deliveryKey": "000000001", "source": str(source), "sentAt": sent_at}),
            encoding="utf-8",
        )
        if failed:
            (failures / marker.name).write_text("{}", encoding="utf-8")
        return state, recvq, backup, source, marker

    def test_old_successful_fax_and_backup_are_purged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            state, recvq, backup, source, marker = self.setup_case(root, sent_at=100)

            result = cleanup.cleanup_received_faxes(
                retention_days=30,
                now=100 + 31 * 86400,
                state_root=state,
                recvq_root=recvq,
                backup_recvq_root=backup,
            )
            payload = json.loads(marker.read_text(encoding="utf-8"))
            manifest = (backup.parent / "recvq-sha256.txt").read_text(encoding="utf-8")

            self.assertFalse(source.exists())
            self.assertFalse((backup / source.name).exists())

        self.assertEqual(result["purged"], 1)
        self.assertTrue(payload["sourcePurged"])
        self.assertEqual(payload["retentionDays"], 30)
        self.assertNotIn("fax000000001.tif", manifest)

    def test_recent_fax_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            now = 40 * 86400
            state, recvq, backup, source, _marker = self.setup_case(
                root, sent_at=now - 29 * 86400
            )

            result = cleanup.cleanup_received_faxes(
                retention_days=30,
                now=now,
                state_root=state,
                recvq_root=recvq,
                backup_recvq_root=backup,
            )

            self.assertTrue(source.exists())
            self.assertTrue((backup / source.name).exists())

        self.assertEqual(result["purged"], 0)

    def test_failed_delivery_is_never_purged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            state, recvq, backup, source, _marker = self.setup_case(
                root, sent_at=100, failed=True
            )

            result = cleanup.cleanup_received_faxes(
                retention_days=30,
                now=100 + 31 * 86400,
                state_root=state,
                recvq_root=recvq,
                backup_recvq_root=backup,
            )

            self.assertTrue(source.exists())

        self.assertEqual(result["purged"], 0)

    def test_source_outside_recvq_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            outside = root / "outside" / "fax000000001.tif"
            state, recvq, backup, source, _marker = self.setup_case(
                root, sent_at=100, source=outside
            )

            result = cleanup.cleanup_received_faxes(
                retention_days=30,
                now=100 + 31 * 86400,
                state_root=state,
                recvq_root=recvq,
                backup_recvq_root=backup,
            )

            self.assertTrue(source.exists())

        self.assertEqual(result["purged"], 0)
        self.assertEqual(result["skipped"], 1)


if __name__ == "__main__":
    unittest.main()

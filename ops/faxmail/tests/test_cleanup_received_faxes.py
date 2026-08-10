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
    def setup_case(self, root, *, archived_at, status="uploaded"):
        recvq = root / "recvq"
        backup = root / "backup" / "recvq"
        recvq.mkdir()
        backup.mkdir(parents=True)
        source = recvq / "fax000000001.tif"
        source.write_bytes(b"fax")
        (backup / source.name).write_bytes(b"fax-backup")
        state = root / "telegram-archive.json"
        state.write_text(
            json.dumps(
                {
                    "archived": {
                        "received:000000001": {
                            "at": archived_at,
                            "status": status,
                            "messageId": 42,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        return state, recvq, backup, source

    def test_old_telegram_archived_fax_and_backup_are_purged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            state, recvq, backup, source = self.setup_case(
                root,
                archived_at="2026-01-01T00:00:00Z",
            )

            result = cleanup.cleanup_received_faxes(
                retention_days=30,
                now=cleanup.timestamp("2026-02-01T00:00:01Z"),
                telegram_state_path=state,
                recvq_root=recvq,
                backup_recvq_root=backup,
            )
            manifest = (backup.parent / "recvq-sha256.txt").read_text(encoding="utf-8")

            self.assertFalse(source.exists())
            self.assertFalse((backup / source.name).exists())

        self.assertEqual(result["purged"], 1)
        self.assertNotIn("fax000000001.tif", manifest)

    def test_recent_telegram_archive_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            state, recvq, backup, source = self.setup_case(
                root,
                archived_at="2026-01-03T00:00:00Z",
            )

            result = cleanup.cleanup_received_faxes(
                retention_days=30,
                now=cleanup.timestamp("2026-02-01T00:00:00Z"),
                telegram_state_path=state,
                recvq_root=recvq,
                backup_recvq_root=backup,
            )

            self.assertTrue(source.exists())
            self.assertTrue((backup / source.name).exists())

        self.assertEqual(result["purged"], 0)

    def test_baselined_fax_is_never_purged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            state, recvq, backup, source = self.setup_case(
                root,
                archived_at="2026-01-01T00:00:00Z",
                status="baselined",
            )

            result = cleanup.cleanup_received_faxes(
                retention_days=30,
                now=cleanup.timestamp("2026-02-01T00:00:01Z"),
                telegram_state_path=state,
                recvq_root=recvq,
                backup_recvq_root=backup,
            )

            self.assertTrue(source.exists())

        self.assertEqual(result["purged"], 0)
        self.assertEqual(result["skipped"], 1)

    def test_missing_telegram_state_preserves_fax(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            recvq = root / "recvq"
            backup = root / "backup" / "recvq"
            recvq.mkdir()
            backup.mkdir(parents=True)
            source = recvq / "fax000000001.tif"
            source.write_bytes(b"fax")

            result = cleanup.cleanup_received_faxes(
                retention_days=30,
                now=100 + 31 * 86400,
                telegram_state_path=root / "missing.json",
                recvq_root=recvq,
                backup_recvq_root=backup,
            )

            self.assertTrue(source.exists())

        self.assertEqual(result["purged"], 0)


if __name__ == "__main__":
    unittest.main()

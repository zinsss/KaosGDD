import io
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.hwp_handoff import store


class HwpHandoffTests(unittest.TestCase):
    def test_filename_is_sanitized_and_extension_is_required(self):
        self.assertEqual(store.clean_filename("../../진료 기록.HWP"), "진료 기록.hwp")
        with self.assertRaisesRegex(ValueError, "unsupported_hwp_extension"):
            store.clean_filename("report.pdf")

    def test_upload_validation_enforces_type_and_limit(self):
        with mock.patch.dict(os.environ, {"HWP_HANDOFF_MAX_UPLOAD_MB": "1"}):
            self.assertEqual(
                store.validate_upload("application/octet-stream", "8", "test.hwp"),
                ("test.hwp", 8),
            )
            with self.assertRaisesRegex(ValueError, "unsupported_hwp_content_type"):
                store.validate_upload("application/pdf", "8", "test.hwp")
            with self.assertRaisesRegex(ValueError, "handoff_too_large"):
                store.validate_upload("application/x-hwp", str(1024 * 1024 + 1), "test.hwp")

    def test_hwp_round_trip_returns_rhwp_open_url(self):
        payload = bytes.fromhex("d0cf11e0a1b11ae1") + b"test-hwp"
        with tempfile.TemporaryDirectory() as temporary:
            environment = {
                "HWP_HANDOFF_ROOT": temporary,
                "HWP_HANDOFF_RETENTION_MINUTES": "30",
                "KAOS_PUBLIC_ORIGIN": "https://kaosgdd.net",
            }
            with mock.patch.dict(os.environ, environment):
                item = store.store_handoff(
                    io.BytesIO(payload), len(payload), "공유 문서.hwp", "application/x-hwp"
                )
                self.assertIn("https://kaosgdd.net/rhwp/?", item["openUrl"])
                self.assertIn("filename=%EA%B3%B5%EC%9C%A0+%EB%AC%B8%EC%84%9C.hwp", item["openUrl"])
                token = item["contentPath"].split("/")[-2]
                metadata, path = store.get_handoff(token)
                self.assertEqual(metadata["filename"], "공유 문서.hwp")
                self.assertEqual(path.read_bytes(), payload)

    def test_invalid_signature_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.dict(os.environ, {"HWP_HANDOFF_ROOT": temporary}):
                with self.assertRaisesRegex(ValueError, "invalid_hwp_signature"):
                    store.store_handoff(io.BytesIO(b"not-hwp"), 7, "bad.hwp", "application/x-hwp")
                self.assertEqual(list(pathlib.Path(temporary).iterdir()), [])


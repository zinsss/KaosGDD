import io
import os
import pathlib
import sys
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from services.documents import store


class DocumentValidationTests(unittest.TestCase):
    def test_filename_removes_path_and_keeps_pdf_extension(self):
        self.assertEqual(store.clean_filename("../../검사 결과.PDF"), "검사 결과.pdf")
        self.assertEqual(store.clean_filename("scan"), "scan.pdf")

    def test_upload_requires_pdf_and_enforces_limit(self):
        with mock.patch.dict(os.environ, {"DOCUMENT_MAX_UPLOAD_MB": "1"}):
            self.assertEqual(store.validate_upload("application/pdf", "5"), 5)
            with self.assertRaisesRegex(ValueError, "pdf_required"):
                store.validate_upload("image/png", "5")
            with self.assertRaisesRegex(ValueError, "document_too_large"):
                store.validate_upload("application/pdf", str(1024 * 1024 + 1))

    def test_source_is_allowlisted(self):
        self.assertEqual(store.validate_source("stirling"), "stirling")
        with self.assertRaisesRegex(ValueError, "invalid_document_source"):
            store.validate_source("unknown")

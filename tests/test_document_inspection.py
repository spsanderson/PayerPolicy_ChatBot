"""Offline PDF-inspection tests with in-memory PDFs and local snapshots."""
import sys
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfWriter

from payer_policy.document_storage import save_pdf_candidate
from payer_policy.https_transport import FetchResult


RETRIEVAL_ID = "1234567890abcdef1234567890abcdef"


def pdf_with_pages(count: int, *, encrypted: bool = False) -> bytes:
    """Build a synthetic PDF with a known page count; optionally lock it."""
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=72, height=72)
    if encrypted:
        writer.encrypt("synthetic-test-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def save_fixture(root: Path, body: bytes) -> None:
    """Save one PDF-looking candidate without contacting a public site."""
    save_pdf_candidate(
        root,
        FetchResult("https://example.org/final", 200,
                    (("Content-Type", "application/pdf"),), body),
        retrieval_id=RETRIEVAL_ID, source_id="synthetic-source",
        requested_url="https://example.org/requested",
        retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )


@unittest.skipUnless(sys.platform == "win32", "Windows storage contract")
class DocumentInspectionTests(unittest.TestCase):
    """Inspect saved candidates without changing their original bytes."""

    def test_reports_page_count_from_verified_snapshot(self) -> None:
        """A structural count stays tied to the original byte identity."""
        from payer_policy.document_inspection import inspect_saved_pdf
        from payer_policy.provenance import fingerprint_document

        body = pdf_with_pages(2)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, body)
            original = root / "records" / RETRIEVAL_ID / "original.bin"
            receipt = original.with_name("receipt.json")
            before = (original.read_bytes(), receipt.read_bytes())

            result = inspect_saved_pdf(root, RETRIEVAL_ID)

            self.assertEqual(result.retrieval_id, RETRIEVAL_ID)
            self.assertEqual(result.sha256, fingerprint_document(body))
            self.assertEqual(result.page_count, 2)
            self.assertFalse(result.is_encrypted)
            self.assertEqual((original.read_bytes(), receipt.read_bytes()),
                             before)

    def test_encrypted_pdf_has_no_claimed_page_count(self) -> None:
        """Report a locked PDF without opening its pages or a password."""
        from payer_policy.document_inspection import inspect_saved_pdf
        from payer_policy.provenance import fingerprint_document

        body = pdf_with_pages(2, encrypted=True)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, body)
            result = inspect_saved_pdf(root, RETRIEVAL_ID)
            self.assertTrue(result.is_encrypted)
            self.assertIsNone(result.page_count)
            self.assertEqual(result.sha256, fingerprint_document(body))

    def test_marker_only_candidate_is_not_structurally_readable(self) -> None:
        """A valid opening marker alone never yields a page count."""
        from payer_policy.document_inspection import (
            PdfInspectionError, inspect_saved_pdf,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, b"%PDF-")
            original = root / "records" / RETRIEVAL_ID / "original.bin"
            with self.assertRaises(PdfInspectionError):
                inspect_saved_pdf(root, RETRIEVAL_ID)
            self.assertEqual(original.read_bytes(), b"%PDF-")

    def test_malformed_page_tree_does_not_leak_parser_failure(self) -> None:
        """A damaged page count is an inspection failure, not a page fact."""
        from payer_policy.document_inspection import (
            PdfInspectionError, inspect_saved_pdf,
        )

        body = pdf_with_pages(1)
        self.assertIn(b"/Count 1", body)
        broken = body.replace(b"/Count 1", b"/Count x", 1)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, broken)
            with self.assertRaises(PdfInspectionError):
                inspect_saved_pdf(root, RETRIEVAL_ID)

    def test_empty_pdf_reports_zero_pages(self) -> None:
        """An accessible PDF with no pages has count zero, not an error."""
        from payer_policy.document_inspection import inspect_saved_pdf

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(0))
            result = inspect_saved_pdf(root, RETRIEVAL_ID)
            self.assertEqual(result.page_count, 0)
            self.assertFalse(result.is_encrypted)

    def test_damaged_original_fails_before_pdf_inspection(self) -> None:
        """Do not mistake a changed snapshot for a PDF parser failure."""
        from payer_policy.document_inspection import inspect_saved_pdf
        from payer_policy.document_storage import StorageIntegrityError

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(1))
            original = root / "records" / RETRIEVAL_ID / "original.bin"
            original.write_bytes(b"%PDF-altered")
            with self.assertRaises(StorageIntegrityError):
                inspect_saved_pdf(root, RETRIEVAL_ID)
            self.assertEqual(original.read_bytes(), b"%PDF-altered")

    def test_rejects_unsafe_ids_and_over_limit_reads(self) -> None:
        """Reuse the storage loader's path and original-size checks."""
        from payer_policy.document_inspection import inspect_saved_pdf
        from payer_policy.document_storage import StorageIntegrityError

        body = pdf_with_pages(1)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, body)
            with self.assertRaises(ValueError):
                inspect_saved_pdf(root, "../outside")
            with self.assertRaises(ValueError):
                inspect_saved_pdf(root, RETRIEVAL_ID, max_bytes=0)
            with self.assertRaises(StorageIntegrityError):
                inspect_saved_pdf(root, RETRIEVAL_ID,
                                  max_bytes=len(body) - 1)

    def test_inspection_does_not_open_a_network_connection(self) -> None:
        """Basic structural inspection needs only the saved local bytes."""
        from unittest.mock import patch
        from payer_policy.document_inspection import inspect_saved_pdf

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(1))
            with (patch("socket.socket", side_effect=AssertionError("socket")),
                  patch("socket.getaddrinfo",
                        side_effect=AssertionError("DNS"))):
                self.assertEqual(inspect_saved_pdf(root, RETRIEVAL_ID)
                                 .page_count, 1)

"""Offline PDF-inspection tests with in-memory PDFs and local snapshots.

PdfWriter adds blank pages, encrypts them, and writes to a byte stream:
https://pypdf.readthedocs.io/en/6.19.0/modules/PdfWriter.html
save_pdf_candidate stores bytes and a receipt for real loader checks:
../payer_policy/document_storage.py
Mocks raise selected failures without changing the installed dependencies:
https://docs.python.org/3/library/unittest.mock.html#unittest.mock.Mock
"""
import sys
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, PropertyMock, patch

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

    def assert_parser_failure(
        self, body: bytes, cause: type[Exception],
        expected: Exception | None = None,
    ) -> None:
        """Check a parser failure keeps its cause and both saved files."""
        from payer_policy.document_inspection import (
            PdfInspectionError, inspect_saved_pdf,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, body)
            original = root / "records" / RETRIEVAL_ID / "original.bin"
            receipt = original.with_name("receipt.json")
            before = (original.read_bytes(), receipt.read_bytes())
            try:
                with self.assertRaises(PdfInspectionError) as raised:
                    inspect_saved_pdf(root, RETRIEVAL_ID)
                self.assertIsInstance(raised.exception.__cause__, cause)
                if expected is not None:
                    self.assertIs(raised.exception.__cause__, expected)
                self.assertEqual(str(raised.exception),
                                 "cannot inspect PDF structure")
            finally:
                self.assertEqual(
                    (original.read_bytes(), receipt.read_bytes()), before,
                )

    def test_missing_catalog_pages_is_wrapped(self) -> None:
        """A catalog without pages fails without changing saved files."""
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        del writer.root_object["/Pages"]
        output = BytesIO()
        writer.write(output)
        self.assert_parser_failure(output.getvalue(), AttributeError)

    def test_missing_encryption_revision_is_wrapped(self) -> None:
        """A missing encryption field keeps its parser cause and files."""
        body = pdf_with_pages(1, encrypted=True)
        self.assertIn(b"/R 3", body)
        self.assert_parser_failure(
            body.replace(b"/R 3", b"/X 3", 1), KeyError,
        )

    def test_invalid_encryption_length_is_wrapped(self) -> None:
        """A word used as a key length keeps its parser cause and files."""
        body = pdf_with_pages(1, encrypted=True)
        self.assertIn(b"/Length 128", body)
        self.assert_parser_failure(
            body.replace(b"/Length 128", b"/Length /xx", 1), TypeError,
        )

    def test_unsupported_encryption_version_is_wrapped(self) -> None:
        """An unsupported lock format keeps its parser cause and files."""
        body = pdf_with_pages(1, encrypted=True)
        self.assertIn(b"/V 2", body)
        self.assert_parser_failure(
            body.replace(b"/V 2", b"/V 9", 1), NotImplementedError,
        )

    def test_pypdf_error_family_at_each_parser_seam(self) -> None:
        """Simulated family errors keep their cause at each parser step."""
        from pypdf.errors import ParseError

        for seam in ("construction", "encryption", "page_count"):
            with self.subTest(seam=seam):
                failure = ParseError("synthetic parser failure")
                reader = MagicMock()
                reader.is_encrypted = False
                if seam == "encryption":
                    type(reader).is_encrypted = PropertyMock(
                        side_effect=failure,
                    )
                elif seam == "page_count":
                    reader.pages.__len__.side_effect = failure
                with patch(
                    "payer_policy.document_inspection.PdfReader",
                    return_value=reader,
                    side_effect=failure if seam == "construction" else None,
                ):
                    self.assert_parser_failure(
                        pdf_with_pages(1), ParseError, failure,
                    )

    def test_missing_encryption_backend_simulation_is_wrapped(self) -> None:
        """Simulate a missing backend; keep its cause and saved files."""
        from pypdf.errors import DependencyError

        failure = DependencyError("simulated missing encryption backend")
        with patch("payer_policy.document_inspection.PdfReader",
                   side_effect=failure):
            self.assert_parser_failure(
                pdf_with_pages(1, encrypted=True), DependencyError, failure,
            )

    def test_loader_failures_are_not_wrapped(self) -> None:
        """Storage and input failures pass through before parsing starts."""
        from payer_policy.document_inspection import inspect_saved_pdf
        from payer_policy.document_storage import StorageIntegrityError

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(1))
            original = root / "records" / RETRIEVAL_ID / "original.bin"
            receipt = original.with_name("receipt.json")
            before = (original.read_bytes(), receipt.read_bytes())
            for cause in (StorageIntegrityError, TypeError, ValueError):
                with self.subTest(cause=cause.__name__):
                    failure = cause("simulated loader failure")
                    with (
                        patch(
                            "payer_policy.document_inspection."
                            "load_saved_candidate", side_effect=failure,
                        ),
                        patch("payer_policy.document_inspection.PdfReader")
                        as parser,
                    ):
                        with self.assertRaises(cause) as raised:
                            inspect_saved_pdf(root, RETRIEVAL_ID)
                        self.assertIs(raised.exception, failure)
                        self.assertIsNone(raised.exception.__cause__)
                        parser.assert_not_called()
                    self.assertEqual(
                        (original.read_bytes(), receipt.read_bytes()), before,
                    )

    def test_resource_and_process_exceptions_are_not_wrapped(self) -> None:
        """Stops and memory exhaustion pass through every parser step."""
        from payer_policy.document_inspection import inspect_saved_pdf

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(1))
            original = root / "records" / RETRIEVAL_ID / "original.bin"
            receipt = original.with_name("receipt.json")
            before = (original.read_bytes(), receipt.read_bytes())
            for cause in (MemoryError, KeyboardInterrupt, SystemExit):
                for seam in ("construction", "encryption", "page_count"):
                    with self.subTest(cause=cause.__name__, seam=seam):
                        failure = cause("simulated stop")
                        reader = MagicMock()
                        reader.is_encrypted = False
                        if seam == "encryption":
                            type(reader).is_encrypted = PropertyMock(
                                side_effect=failure,
                            )
                        elif seam == "page_count":
                            reader.pages.__len__.side_effect = failure
                        with patch(
                            "payer_policy.document_inspection.PdfReader",
                            return_value=reader,
                            side_effect=(failure if seam == "construction"
                                         else None),
                        ):
                            with self.assertRaises(cause) as raised:
                                inspect_saved_pdf(root, RETRIEVAL_ID)
                            self.assertIs(raised.exception, failure)
                            self.assertIsNone(raised.exception.__cause__)
                        self.assertEqual(
                            (original.read_bytes(), receipt.read_bytes()),
                            before,
                        )

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
        """Report encryption without application decryption or counting."""
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

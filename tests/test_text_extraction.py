"""Synthetic-only tests for bounded plain text extraction."""
import sys
import unittest
from dataclasses import FrozenInstanceError
from datetime import timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


def text_pdf() -> bytes:
    """Make text, blank, image-only and rotated pages without downloads."""
    from pypdf import PdfWriter
    from pypdf.generic import (
        DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
    )

    writer = PdfWriter()
    for index, text in enumerate((b"First page", None, None, b"Fourth")):
        page = writer.add_blank_page(width=300, height=300)
        if text:
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({
                    NameObject("/F1"): writer._add_object(font),
                }),
            })
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 30 100 Td (" + text + b") Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
        if index == 2:
            image = DecodedStreamObject()
            image.set_data(b"\xff\x00\x00")
            image.update({
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(1),
                NameObject("/Height"): NumberObject(1),
                NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                NameObject("/BitsPerComponent"): NumberObject(8),
            })
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/XObject"): DictionaryObject({
                    NameObject("/Im1"): writer._add_object(image),
                }),
            })
            stream = DecodedStreamObject()
            stream.set_data(b"q 100 0 0 100 0 0 cm /Im1 Do Q")
            page[NameObject("/Contents")] = writer._add_object(stream)
        if index == 3:
            page.rotate(90)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@unittest.skipUnless(sys.platform == "win32", "Windows storage contract")
class KernelTests(unittest.TestCase):
    """Exercise real pinned pypdf using synthetic saved bytes only."""

    def test_selected_physical_pages_keep_raw_text_and_provenance(
        self,
    ) -> None:
        """Return a complete selected batch, including blank/image pages."""
        from test_document_inspection import RETRIEVAL_ID, save_fixture
        from payer_policy.text_extraction import (
            ExtractionLimits, _extract_saved_pages,
        )

        with TemporaryDirectory() as name:
            root = Path(name)
            body = text_pdf()
            save_fixture(root, body)
            result = _extract_saved_pages(
                root, RETRIEVAL_ID, (1, 2, 3, 4), ExtractionLimits())
        self.assertEqual(result.retrieval_id, RETRIEVAL_ID)
        from hashlib import sha256
        self.assertEqual(result.sha256, sha256(body).hexdigest())
        self.assertEqual(result.schema_version, 1)
        self.assertEqual(result.page_count, 4)
        self.assertEqual(result.requested_pages, (1, 2, 3, 4))
        self.assertEqual(result.parser_name, "pypdf")
        self.assertEqual(result.parser_version, "6.19.0")
        self.assertEqual(result.mode, "plain")
        self.assertEqual(result.extracted_at.tzinfo, timezone.utc)
        self.assertEqual([p.text for p in result.pages],
                         ["First page", "", "", "Fourth"])
        self.assertEqual([p.status for p in result.pages],
                         ["text", "empty", "empty", "text"])
        self.assertEqual([p.page_number for p in result.pages], [1, 2, 3, 4])

    def test_batch_rejects_encryption_range_and_parser_failures(self) -> None:
        """Known PDF failures are typed; unknown library bugs escape."""
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        from payer_policy.text_extraction import (
            ExtractionError, ExtractionLimits, _extract_saved_pages,
        )
        from pypdf.errors import PdfReadError

        for body, pages, code in (
            (pdf_with_pages(1, encrypted=True), (1,), "encrypted"),
            (text_pdf(), (1, 5), "range_error"),
            (b"%PDF-", (1,), "parser_error"),
        ):
            with self.subTest(code=code), TemporaryDirectory() as name:
                root = Path(name)
                save_fixture(root, body)
                with self.assertRaises(ExtractionError) as caught:
                    _extract_saved_pages(root, RETRIEVAL_ID, pages,
                                         ExtractionLimits())
                self.assertEqual(caught.exception.code, code)
        with TemporaryDirectory() as name:
            root = Path(name)
            save_fixture(root, text_pdf())
            for error in (ValueError("bug"), TypeError("bug")):
                with patch("pypdf._page.PageObject.extract_text",
                           side_effect=error):
                    with self.assertRaises(type(error)) as caught:
                        _extract_saved_pages(root, RETRIEVAL_ID, (1,),
                                             ExtractionLimits())
                    self.assertIs(caught.exception, error)
            with patch("pypdf._page.PageObject.extract_text",
                       side_effect=["first", PdfReadError("bad page")]):
                with self.assertRaises(ExtractionError) as caught:
                    _extract_saved_pages(root, RETRIEVAL_ID, (1, 2),
                                         ExtractionLimits())
                self.assertEqual(caught.exception.code, "parser_error")

    def test_default_text_caps_accept_exact_and_reject_one_extra_byte(
        self,
    ) -> None:
        """Injected text reaches real page and batch byte checks unchanged."""
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        from payer_policy.text_extraction import (
            ExtractionError, ExtractionLimits, _extract_saved_pages,
        )

        limits = ExtractionLimits()
        full_page = "é" * (limits.max_page_text_bytes // 2)
        with TemporaryDirectory() as name:
            root = Path(name)
            save_fixture(root, pdf_with_pages(10))
            for texts, fails in (
                ([full_page], False), ([full_page + "x"], True),
                ([full_page] * 8 + ["", ""], False),
                ([full_page] * 8 + ["x"], True),
            ):
                pages = tuple(range(1, len(texts) + 1))
                with self.subTest(pages=len(pages), fails=fails):
                    with patch("pypdf._page.PageObject.extract_text",
                               side_effect=texts) as extract:
                        if fails:
                            with self.assertRaises(ExtractionError) as got:
                                _extract_saved_pages(
                                    root, RETRIEVAL_ID, pages, limits)
                            self.assertEqual(got.exception.code,
                                             "output_limit")
                        else:
                            result = _extract_saved_pages(
                                root, RETRIEVAL_ID, pages, limits)
                            self.assertEqual([p.text for p in result.pages],
                                             texts)
                            self.assertEqual(result.requested_pages, pages)
                            self.assertEqual(result.page_count, 10)
                        self.assertEqual(extract.call_count, len(texts))

    def test_utf8_page_and_batch_budgets_preserve_whitespace(self) -> None:
        """Injected Unicode measures bytes, not real-PDF glyph decoding."""
        from test_document_inspection import RETRIEVAL_ID, save_fixture
        from payer_policy.text_extraction import (
            ExtractionError, ExtractionLimits, _extract_saved_pages,
        )

        with TemporaryDirectory() as name:
            root = Path(name)
            save_fixture(root, text_pdf())
            for page_cap, total_cap, fails in (
                (4, 7, False), (3, 7, True), (4, 6, True),
            ):
                with self.subTest(page=page_cap, total=total_cap):
                    limits = ExtractionLimits(
                        max_page_text_bytes=page_cap,
                        max_total_text_bytes=total_cap)
                    with patch("pypdf._page.PageObject.extract_text",
                               side_effect=["éé", " \t\n"]):
                        if fails:
                            with self.assertRaises(ExtractionError) as got:
                                _extract_saved_pages(
                                    root, RETRIEVAL_ID, (1, 4), limits)
                            self.assertEqual(got.exception.code,
                                             "output_limit")
                        else:
                            result = _extract_saved_pages(
                                root, RETRIEVAL_ID, (1, 4), limits)
                            self.assertEqual(result.pages[1].text, " \t\n")
                            self.assertEqual(result.pages[1].status, "empty")
                            self.assertEqual(result.limits, limits)


class InputTests(unittest.TestCase):
    """Require explicit page selections and immutable bounded settings."""

    def test_every_setting_has_exact_noncoercing_boundaries(self) -> None:
        """Accept integer cap endpoints; reject nearby or untyped values."""
        from payer_policy.text_extraction import (
            ExtractionLimits, validate_limits, validate_pages,
        )

        for key, minimum, maximum in (
            ("max_bytes", 1, 10_000_000),
            ("max_page_text_bytes", 1, 65_536),
            ("max_total_text_bytes", 1, 524_288),
            ("max_result_bytes", 1, 1_048_576),
            ("memory_bytes", 16_777_216, 268_435_456),
        ):
            for value in (minimum, maximum):
                with self.subTest(key=key, accepted=value):
                    validate_limits(ExtractionLimits(**{key: value}))
            for value in (minimum - 1, maximum + 1, True, False,
                          float(minimum), str(minimum), None):
                with self.subTest(key=key, rejected=value):
                    with self.assertRaises(ValueError):
                        validate_limits(ExtractionLimits(**{key: value}))
        for value in (0.001, 60, 60.0):
            validate_limits(ExtractionLimits(timeout_seconds=value))
        for value in (0, -1, 60.001, True, False, None, "30",
                      float("inf"), float("-inf"), float("nan")):
            with self.subTest(timeout=value):
                with self.assertRaises(ValueError):
                    validate_limits(ExtractionLimits(timeout_seconds=value))
        validate_pages((1,))
        validate_pages(tuple(range(1, 11)))
        with self.assertRaises(ValueError):
            validate_pages(tuple(range(1, 12)))
        with self.assertRaises(TypeError):
            validate_limits({})

    def test_limits_and_pages_reject_coercion(self) -> None:
        """Reject invalid budgets and pages rather than repairing them."""
        from payer_policy.text_extraction import (
            ExtractionLimits, validate_limits, validate_pages,
        )

        limits = ExtractionLimits()
        validate_limits(limits)
        self.assertEqual(limits.max_bytes, 10_000_000)
        self.assertEqual(limits.max_page_text_bytes, 65_536)
        self.assertEqual(limits.max_total_text_bytes, 524_288)
        self.assertEqual(limits.max_result_bytes, 1_048_576)
        with self.assertRaises(FrozenInstanceError):
            limits.max_bytes = 1
        for key, values in {
            "max_bytes": (True, 0, 10_000_001, 1.0),
            "max_page_text_bytes": (False, 0, 65_537),
            "max_total_text_bytes": (0, 524_289),
            "max_result_bytes": (0, 1_048_577),
            "timeout_seconds": (True, 0, 61, float("nan")),
            "memory_bytes": (True, 16_777_215, 268_435_457),
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    with self.assertRaises((TypeError, ValueError)):
                        validate_limits(ExtractionLimits(**{key: value}))
        for pages in ([], (), (0,), (True,), (1.0,), (2, 1), (1, 1),
                      tuple(range(1, 12))):
            with self.subTest(pages=pages):
                with self.assertRaises((TypeError, ValueError)):
                    validate_pages(pages)
        validate_pages((1, 3, 9))
        validate_limits(ExtractionLimits(
            max_bytes=1, max_page_text_bytes=1, max_total_text_bytes=1,
            max_result_bytes=1, memory_bytes=16_777_216,
            timeout_seconds=0.01,
        ))

"""Synthetic response checks; these fixtures are not real policy PDFs.

FetchResult is defined in payer_policy/https_transport.py. dataclasses.replace
creates altered fixtures without changing the original response:
https://docs.python.org/3.11/library/dataclasses.html#dataclasses.replace.
The I/O guards use unittest.mock.patch to fail if an entry point is called:
https://docs.python.org/3.11/library/unittest.mock.html#unittest.mock.patch.
"""
import unittest

from payer_policy.https_transport import FetchResult


class DocumentValidationTests(unittest.TestCase):
    """Check candidate rules without downloading or parsing documents."""

    def test_accepts_candidate_without_changing_response(self) -> None:
        """Return None and preserve every supplied field and byte."""
        from payer_policy.document_validation import validate_pdf_candidate

        headers = (("Content-Type", "application/pdf"),)
        body = b"%PDF-1.7\nsynthetic, not a structurally valid PDF"
        result = FetchResult(
            "https://example.org/document", 200, headers, body)
        before = (result.url, result.status, result.headers, result.body)
        self.assertIsNone(validate_pdf_candidate(result))
        self.assertEqual(
            (result.url, result.status, result.headers, result.body), before)
        self.assertIs(result.headers, headers)
        self.assertIs(result.body, body)

    def test_rejects_incorrect_input_types(self) -> None:
        """Reject malformed response fields rather than converting them."""
        from dataclasses import replace
        from payer_policy.document_validation import validate_pdf_candidate

        result = FetchResult(
            "https://example.org/a", 200,
            (("Content-Type", "application/pdf"),), b"%PDF-")
        cases = [None, {}, result.body]
        cases.extend(replace(result, body=value) for value in (
            None, "%PDF-", bytearray(b"%PDF-"), memoryview(b"%PDF-"),
        ))
        cases.extend(replace(result, status=value) for value in
                     (True, 200.0, "200", None))
        cases.extend(replace(result, headers=value) for value in (
            None, [], {}, "Content-Type: application/pdf",
            (["Content-Type", "application/pdf"],),
            (("Content-Type",),), (("a", "b", "c"),),
            ((b"Content-Type", "application/pdf"),),
            (("Content-Type", None),), (None,),
        ))
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    validate_pdf_candidate(value)

    def test_requires_status_200(self) -> None:
        """Reject statuses other than 200, including partial responses."""
        from payer_policy.document_validation import validate_pdf_candidate

        for status in (0, 199, 201, 204, 206, 299, 301, 400, 500):
            result = FetchResult("https://example.org/a", status,
                                 (("Content-Type", "application/pdf"),),
                                 b"%PDF-")
            with self.subTest(status=status):
                with self.assertRaisesRegex(ValueError, "200") as caught:
                    validate_pdf_candidate(result)
                self.assertEqual(type(caught.exception).__name__,
                                 "DocumentValidationError")

    def test_rejects_content_range(self) -> None:
        """Even HTTP 200 must not advertise a document fragment."""
        from payer_policy.document_validation import (
            DocumentValidationError, validate_pdf_candidate,
        )

        for name in ("Content-Range", "content-range", "CONTENT-RANGE"):
            for value in ("bytes 0-4/100", "", "garbage"):
                result = FetchResult("https://example.org/a", 200,
                                     (("Content-Type", "application/pdf"),
                                      (name, value)), b"%PDF-")
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(
                            DocumentValidationError, "Content-Range"):
                        validate_pdf_candidate(result)

    def test_rejects_empty_body(self) -> None:
        """A PDF label cannot make an empty response a candidate."""
        from payer_policy.document_validation import (
            DocumentValidationError, validate_pdf_candidate,
        )

        result = FetchResult("https://example.org/a", 200,
                             (("Content-Type", "application/pdf"),), b"")
        with self.assertRaisesRegex(DocumentValidationError, "empty"):
            validate_pdf_candidate(result)

    def test_requires_one_bare_pdf_content_type(self) -> None:
        """Reject absent, ambiguous, or unsupported PDF labels."""
        from payer_policy.document_validation import (
            DocumentValidationError, validate_pdf_candidate,
        )

        cases = [(), (("X-Type", "application/pdf"),)]
        cases.extend((("Content-Type", value),) for value in (
            "", " ", "text/html", "application/octet-stream",
            "application/x-pdf", "application/pdf; charset=utf-8",
            "application/pdf;", "application/pdf, application/pdf",
            "application/pdf\r\n", "\napplication/pdf", "application/pdf\x00",
            "\u00a0application/pdf", "application /pdf", '"application/pdf"',
        ))
        cases.extend((
            (("Content-Type", "application/pdf"),
             ("content-type", "application/pdf")),
            (("Content-Type", "application/pdf"),
             ("CONTENT-TYPE", "text/html")),
        ))
        for headers in cases:
            with self.subTest(headers=headers):
                result = FetchResult("https://example.org/a", 200,
                                     headers, b"%PDF-")
                with self.assertRaisesRegex(
                        DocumentValidationError, "Content-Type"):
                    validate_pdf_candidate(result)

    def test_rejects_unsupported_content_encoding(self) -> None:
        """Reject compression or ambiguous encoding even with a PDF marker."""
        from payer_policy.document_validation import (
            DocumentValidationError, validate_pdf_candidate,
        )

        cases = [(("Content-Encoding", value),) for value in (
            "", " ", "gzip", "br", "deflate", "identity, identity",
            "gzip, identity", "identity; q=1", "identity\n", "\u00a0identity",
        )]
        cases.extend((
            (("Content-Encoding", "identity"),
             ("content-encoding", "identity")),
            (("Content-Encoding", "identity"),
             ("CONTENT-ENCODING", "gzip")),
        ))
        for extra in cases:
            with self.subTest(extra=extra):
                result = FetchResult(
                    "https://example.org/a", 200,
                    (("Content-Type", "application/pdf"),) + extra, b"%PDF-")
                with self.assertRaisesRegex(
                        DocumentValidationError, "Content-Encoding"):
                    validate_pdf_candidate(result)

    def test_requires_exact_marker_at_start(self) -> None:
        """Reject HTML and misplaced, incomplete, or altered PDF markers."""
        from payer_policy.document_validation import (
            DocumentValidationError, validate_pdf_candidate,
        )

        bodies = (
            b"%", b"%P", b"%PD", b"%PDF", b"%pdf-", b"PDF-",
            b" ", b" %PDF-", b"\n%PDF-", b"\xef\xbb\xbf%PDF-",
            b"<html>login</html>", b"<html>%PDF-</html>",
            b"{\"error\": \"denied\"}", b"\x1f\x8b%PDF-", b"\x00%PDF-",
        )
        for body in bodies:
            with self.subTest(body=body):
                result = FetchResult("https://example.org/a.pdf", 200,
                                     (("Content-Type", "application/pdf"),),
                                     body)
                with self.assertRaisesRegex(
                        DocumentValidationError, "start with %PDF-"):
                    validate_pdf_candidate(result)

    def test_accepts_case_and_surrounding_space_or_tab(self) -> None:
        """Compare supported headers without rewriting the original values."""
        from payer_policy.document_validation import validate_pdf_candidate

        for encoding in ((), (("cOnTeNt-EnCoDiNg", " \tIdEnTiTy\t "),)):
            headers = (("cOnTeNt-TyPe", "\t Application/PDF \t"),) + encoding
            result = FetchResult("https://example.org/no-extension", 200,
                                 headers, b"%PDF-2.0\nnot a real PDF")
            self.assertIsNone(validate_pdf_candidate(result))
            self.assertIs(result.headers, headers)

    def test_marker_only_is_deliberately_a_candidate(self) -> None:
        """Passing does not establish a valid version, structure, or policy."""
        from payer_policy.document_validation import validate_pdf_candidate

        for body in (b"%PDF-", b"%PDF-nonsense", b"%PDF-<html>not PDF</html>"):
            with self.subTest(body=body):
                result = FetchResult("https://example.org/a", 200,
                                     (("Content-Type", "application/pdf"),),
                                     body)
                self.assertIsNone(validate_pdf_candidate(result))

    def test_validation_has_no_io_or_input_changes(self) -> None:
        """Guard file/socket access on accepted and rejected responses."""
        from contextlib import ExitStack
        from unittest.mock import patch
        from payer_policy.document_validation import (
            DocumentValidationError, validate_pdf_candidate,
        )

        cases = (
            (200, (("Content-Type", "application/pdf"),), b"%PDF-", None),
            (206, (("Content-Type", "application/pdf"),),
             b"%PDF-", ValueError),
            (200, (("Content-Type", "application/pdf"),
                   ("Content-Range", "")), b"%PDF-", ValueError),
            (200, (("Content-Type", "application/pdf"),), b"", ValueError),
            (200, (("Content-Type", "text/html"),), b"%PDF-", ValueError),
            (200, (("Content-Type", "application/pdf"),
                   ("Content-Encoding", "gzip")), b"%PDF-", ValueError),
            (200, (("Content-Type", "application/pdf"),), b"HTML", ValueError),
            (200, (("Content-Type", "application/pdf"),), "text", TypeError),
        )
        with ExitStack() as stack:
            guards = [stack.enter_context(patch(
                name, side_effect=AssertionError("unexpected I/O")))
                for name in ("builtins.open", "io.open", "os.open",
                             "socket.socket", "socket.getaddrinfo")]
            for status, headers, body, error in cases:
                result = FetchResult("https://example.org/a", status,
                                     headers, body)
                before = (result.url, result.status,
                          result.headers, result.body)
                if error is None:
                    self.assertIsNone(validate_pdf_candidate(result))
                else:
                    expected = (TypeError if error is TypeError
                                else DocumentValidationError)
                    with self.assertRaises(expected):
                        validate_pdf_candidate(result)
                self.assertEqual((result.url, result.status,
                                  result.headers, result.body), before)
                self.assertIs(result.headers, headers)
                self.assertIs(result.body, body)
            for guard in guards:
                guard.assert_not_called()

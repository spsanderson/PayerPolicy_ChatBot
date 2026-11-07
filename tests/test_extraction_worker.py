"""Offline extraction protocol and real Windows worker tests."""
import copy
import json
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from test_document_inspection import RETRIEVAL_ID, save_fixture
from test_text_extraction import text_pdf


REQUEST_ID = "a" * 32


def sample_extraction():
    """Return a synthetic result, not text claimed from a real PDF."""
    from payer_policy.text_extraction import (
        ExtractionLimits, PageText, PdfTextExtraction,
    )

    return PdfTextExtraction(
        RETRIEVAL_ID, "b" * 64, 4, (1, 4),
        (PageText(1, 'é\\"\n', "text"), PageText(4, " \t", "empty")),
        datetime(2026, 1, 2, tzinfo=timezone.utc), ExtractionLimits(),
    )


def sample_request(root: Path) -> dict:
    """Build the fixed request shape for protocol tests only."""
    return {
        "schema_version": 1, "operation": "extract_text",
        "request_id": REQUEST_ID, "retrieval_id": RETRIEVAL_ID,
        "root": str(root), "requested_pages": [1, 4],
        "limits": asdict(sample_extraction().limits),
        "runtime": {"base_prefix": str(root), "packages": str(root)},
    }


class WorkerTests(unittest.TestCase):
    """Run the production isolated child with actual Windows job cleanup."""

    def test_native_worker_loads_and_parses_only_in_child(self) -> None:
        """Return selected text without parent parsing or source mutation."""
        from payer_policy.extraction_worker import (
            extract_saved_pdf_pages_in_worker,
        )

        with TemporaryDirectory() as name:
            root = Path(name)
            save_fixture(root, text_pdf())
            before = {p: p.read_bytes() for p in root.rglob("*")
                      if p.is_file()}
            with patch("pypdf.PdfReader", side_effect=AssertionError), patch(
                "payer_policy.document_storage.load_saved_candidate",
                side_effect=AssertionError,
            ):
                result = extract_saved_pdf_pages_in_worker(
                    root, RETRIEVAL_ID, pages=(1, 4))
            self.assertEqual([p.text for p in result.pages],
                             ["First page", "Fourth"])
            self.assertEqual(result.requested_pages, (1, 4))
            self.assertEqual(before, {p: p.read_bytes() for p in before})


    def test_native_document_errors_are_atomic_and_typed(self) -> None:
        """Refuse encryption, bad ranges, damaged originals and tiny output."""
        from test_document_inspection import pdf_with_pages
        from payer_policy.extraction_worker import (
            extract_saved_pdf_pages_in_worker as extract,
        )
        from payer_policy.text_extraction import ExtractionError, ExtractionLimits

        for body, pages, limits, damage, code in (
            (pdf_with_pages(1, encrypted=True), (1,), None, False,
             "encrypted"),
            (text_pdf(), (1, 5), None, False, "range_error"),
            (b"%PDF-", (1,), None, False, "parser_error"),
            (text_pdf(), (1,), None, True, "storage_error"),
            (text_pdf(), (1,), ExtractionLimits(max_result_bytes=1), False,
             "output_limit"),
        ):
            with self.subTest(code=code), TemporaryDirectory() as name:
                root = Path(name)
                save_fixture(root, body)
                if damage:
                    original = root / "records" / RETRIEVAL_ID / "original.bin"
                    original.write_bytes(b"%PDF-changed")
                with self.assertRaises(ExtractionError) as caught:
                    extract(root, RETRIEVAL_ID, pages=pages, limits=limits)
                self.assertEqual(caught.exception.code, code)

    def test_child_unknown_bug_escapes_and_memory_is_explicit(self) -> None:
        """Do not mislabel ordinary parser ValueError as bad caller input."""
        from payer_policy import _extraction_child as child

        with TemporaryDirectory() as name:
            root = Path(name)
            save_fixture(root, text_pdf())
            request = sample_request(root)
            for error in (ValueError("parser bug"), TypeError("parser bug")):
                with patch("pypdf._page.PageObject.extract_text",
                           side_effect=error):
                    with self.assertRaises(type(error)) as caught:
                        child.extract_request(request)
                    self.assertIs(caught.exception, error)
            with patch.object(child, "_extract_saved_pages",
                              side_effect=MemoryError):
                result = child.extract_request(request)
            self.assertEqual(result["status"], "memory_error")
            self.assertIsNone(result["facts"])


class ProtocolTests(unittest.TestCase):
    """Treat child JSON as untrusted complete batches, never partial facts."""

    def test_serialized_exact_and_over_budgets_include_escaping(self) -> None:
        """Characterize escaped Unicode plus metadata, not character counts."""
        from payer_policy import _extraction_protocol as protocol
        from payer_policy import _extraction_child as child

        with TemporaryDirectory() as name:
            request = sample_request(Path(name))
            result = sample_extraction()
            for _ in range(4):
                message = protocol.result_message(request, result)
                size = len(protocol.encode(message, protocol.RESULT_BYTES))
                result = replace(result, limits=replace(
                    result.limits, max_result_bytes=size))
                request["limits"] = asdict(result.limits)
            message = protocol.result_message(request, result)
            size = len(protocol.encode(message, protocol.RESULT_BYTES))
            self.assertEqual(size, result.limits.max_result_bytes)
            self.assertIn(b'\\u00e9', protocol.encode(message, size))
            path = Path(name) / "result.json"
            protocol.publish(path, message, size)
            self.assertEqual(protocol.read_result(path, request), result)
            with self.assertRaises(protocol.ProtocolError):
                protocol.encode(message, size - 1)
            with patch.object(child, "_extract_saved_pages", return_value=result):
                self.assertEqual(child.extract_request(request)["status"], "ok")
            result = replace(result, limits=replace(
                result.limits, max_result_bytes=size - 1))
            request["limits"] = asdict(result.limits)
            with patch.object(child, "_extract_saved_pages", return_value=result):
                failed = child.extract_request(request)
            self.assertEqual(failed["status"], "output_limit")
            self.assertIsNone(failed["facts"])


class SupervisorTests(unittest.TestCase):
    """Characterize reused containment failures and early input validation."""

    def test_invalid_inputs_never_reach_runtime(self) -> None:
        """No native setup, loading or temporary files for caller mistakes."""
        from payer_policy import extraction_worker as worker
        from payer_policy.text_extraction import ExtractionLimits

        with TemporaryDirectory() as name, patch.object(worker, "_runtime") as run:
            for pages, limits in (([1], None), ((True,), None),
                                  ((1,), ExtractionLimits(max_bytes=True))):
                with self.assertRaises((TypeError, ValueError)):
                    worker.extract_saved_pdf_pages_in_worker(
                        Path(name), RETRIEVAL_ID, pages=pages, limits=limits)
            run.assert_not_called()

    def test_supervisor_fault_categories_and_cleanup(self) -> None:
        """Injected native/IPC failures never return a plausible success."""
        from payer_policy import extraction_worker as worker
        from payer_policy._windows_job import CleanupError
        from payer_policy.inspection_worker import WorkerInspectionError
        from payer_policy.text_extraction import ExtractionError

        with TemporaryDirectory() as name:
            root = Path(name)
            for boundary, error, code in (
                ("_runtime", WorkerInspectionError("unsupported_runtime"),
                 "unsupported_runtime"),
                ("_temporary_directory", WorkerInspectionError("cleanup_error"),
                 "cleanup_error"),
            ):
                with patch.object(worker, boundary, side_effect=error):
                    with self.assertRaises(ExtractionError) as caught:
                        worker.extract_saved_pdf_pages_in_worker(
                            root, RETRIEVAL_ID, pages=(1,))
                    self.assertEqual(caught.exception.code, code)
            for failure, code in ((TimeoutError(), "timeout"),
                                  (OSError(), "ipc_error"), (7, "crash")):
                with patch("payer_policy._windows_job.Job") as job:
                    wait = job.return_value.__enter__.return_value.wait
                    if isinstance(failure, Exception):
                        wait.side_effect = failure
                    else:
                        wait.return_value = failure
                    with self.assertRaises(ExtractionError) as caught:
                        worker.extract_saved_pdf_pages_in_worker(
                            root, RETRIEVAL_ID, pages=(1,))
                    self.assertEqual(caught.exception.code, code)
                    job.return_value.__exit__.assert_called_once()
            for error, code in ((OSError(), "setup_error"),
                                (CleanupError("test"), "cleanup_error")):
                with patch("payer_policy._windows_job.Job", side_effect=error):
                    with self.assertRaises(ExtractionError) as caught:
                        worker.extract_saved_pdf_pages_in_worker(
                            root, RETRIEVAL_ID, pages=(1,))
                    self.assertEqual(caught.exception.code, code)


    def test_request_strict_schema_and_json_bounds(self) -> None:
        """Reject duplicate keys, NaN, depth, coercion and unknown fields."""
        from payer_policy import _extraction_protocol as protocol

        with TemporaryDirectory() as name:
            root = Path(name)
            path = root / "request.json"
            request = sample_request(root)
            protocol.publish(path, request, protocol.REQUEST_BYTES)
            self.assertEqual(protocol.read_request(path), request)
            for key, value in (
                ("schema_version", True), ("operation", "inspect"),
                ("request_id", "../x"), ("retrieval_id", 1),
                ("requested_pages", [True]), ("requested_pages", [4, 1]),
                ("requested_pages", []), ("limits", {}),
                ("root", "relative"), ("runtime", {}), ("extra", 1),
            ):
                bad = copy.deepcopy(request)
                bad[key] = value
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.subTest(key=key):
                    with self.assertRaises(protocol.ProtocolError):
                        protocol.read_request(path)
            for raw in (b'{"a":1,"a":2}', b'{"x":NaN}',
                        b'[' * 2000 + b']' * 2000, b'\xff', b'[]',
                        b' ' * (protocol.REQUEST_BYTES + 1)):
                path.write_bytes(raw)
                with self.subTest(raw=raw[:30]):
                    with self.assertRaises(protocol.ProtocolError):
                        protocol.read_request(path)

    def test_result_echo_rejects_bool_that_compares_equal_to_int(self) -> None:
        """Python equality must not let booleans impersonate page numbers."""
        from payer_policy import _extraction_protocol as protocol

        with TemporaryDirectory() as name:
            request = sample_request(Path(name))
            message = protocol.result_message(request, sample_extraction())
            message["requested_pages"] = [True, 4]
            path = Path(name) / "result.json"
            protocol.publish(path, message, protocol.RESULT_BYTES)
            with self.assertRaises(protocol.ProtocolError):
                protocol.read_result(path, request)

    def test_result_roundtrip_rejects_changed_identity_and_facts(self) -> None:
        """Match identities, exact pages, limits and complete typed facts."""
        from payer_policy import _extraction_protocol as protocol

        expected = sample_extraction()
        with TemporaryDirectory() as name:
            path = Path(name) / "result.json"
            request = sample_request(Path(name))
            message = protocol.result_message(request, expected)
            protocol.publish(path, message, protocol.RESULT_BYTES)
            self.assertEqual(protocol.read_result(path, request), expected)
            mutations = [
                ("request_id", "c" * 32), ("retrieval_id", "c" * 32),
                ("schema_version", True), ("operation", "inspect"),
                ("requested_pages", [4, 1]), ("status", "invented"),
                ("extra", 1), ("facts", None),
            ]
            for key, value in mutations:
                bad = copy.deepcopy(message)
                bad[key] = value
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.subTest(key=key):
                    with self.assertRaises(protocol.ProtocolError):
                        protocol.read_result(path, request)
            facts_mutations = [
                ("sha256", "B" * 64), ("schema_version", True),
                ("retrieval_id", "c" * 32), ("parser_version", "0"),
                ("parser_name", "other"), ("mode", "layout"),
                ("page_count", True), ("page_count", 3),
                ("requested_pages", [1]), ("extracted_at", "yesterday"),
                ("extra", 0), ("pages", []),
            ]
            for key, value in facts_mutations:
                bad = copy.deepcopy(message)
                bad["facts"][key] = value
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.subTest(fact=key):
                    with self.assertRaises(protocol.ProtocolError):
                        protocol.read_result(path, request)
            bad = copy.deepcopy(message)
            bad["facts"]["limits"]["max_bytes"] = 123
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(protocol.ProtocolError):
                protocol.read_result(path, request)

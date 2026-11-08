"""Offline extraction protocol and real Windows worker tests."""
import copy
import json
import sys
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from test_document_inspection import RETRIEVAL_ID, save_fixture
from test_text_extraction import text_pdf
from payer_policy.text_extraction import PdfTextExtraction


REQUEST_ID = "a" * 32


def sample_extraction() -> PdfTextExtraction:
    """Return a synthetic result, not text claimed from a real PDF."""
    from payer_policy.text_extraction import (
        ExtractionLimits, PageText,
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


@unittest.skipUnless(sys.platform == "win32", "Windows storage contract")
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
        from payer_policy.text_extraction import (
            ExtractionError, ExtractionLimits,
        )

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

    def test_native_original_budget_accepts_exact_and_rejects_over(
        self,
    ) -> None:
        """The child verifies bounded originals before attempting parsing."""
        from payer_policy import extraction_worker as worker
        from payer_policy.text_extraction import ExtractionError
        from payer_policy.text_extraction import ExtractionLimits

        with TemporaryDirectory() as name:
            root = Path(name)
            body = text_pdf()
            save_fixture(root, body)
            before = {p: p.read_bytes() for p in root.rglob("*")
                      if p.is_file()}
            result = worker.extract_saved_pdf_pages_in_worker(
                root, RETRIEVAL_ID, pages=(1,),
                limits=ExtractionLimits(max_bytes=len(body)))
            self.assertEqual(result.pages[0].text, "First page")
            with self.assertRaises(ExtractionError) as caught:
                worker.extract_saved_pdf_pages_in_worker(
                    root, RETRIEVAL_ID, pages=(1,),
                    limits=ExtractionLimits(max_bytes=len(body) - 1))
            self.assertEqual(caught.exception.code, "storage_error")
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_native_timeout_crash_and_parser_bug_leave_no_result(self) -> None:
        """Real jobs stop failed children; parser bugs stay worker crashes."""
        import shutil
        from payer_policy import extraction_worker as worker
        from payer_policy._windows_job import Job
        from payer_policy.text_extraction import ExtractionError
        from payer_policy.text_extraction import ExtractionLimits

        launch = Job.launch
        jobs = []
        outputs = []

        def substitute(job: Job, interpreter: Path, script: Path,
                       arguments: list[str]) -> None:
            """Launch a test-only child with real containment and cleanup."""
            jobs.append(job)
            outputs.append(Path(arguments[1]))
            launch(job, interpreter, replacement, arguments)

        with TemporaryDirectory() as name:
            folder = Path(name)
            root = folder / "saved"
            root.mkdir()
            save_fixture(root, text_pdf())
            before = {p: p.read_bytes() for p in root.rglob("*")
                      if p.is_file()}
            source = Path(worker.__file__).parent
            copied = folder / "copied" / "payer_policy"
            shutil.copytree(source, copied,
                            ignore=shutil.ignore_patterns("__pycache__"))
            child = copied / "_extraction_child.py"
            marker = folder / "parser-entered"
            injection = (
                '    import pypdf._page\n'
                '    def fail_parser(*args: object, **kwargs: object)'
                ' -> str:\n'
                '        """Mark a real child parser call, then fail."""\n'
                f'        Path({str(marker)!r}).write_text("entered")\n'
                '        raise ValueError("injected parser bug")\n'
                '    pypdf._page.PageObject.extract_text = fail_parser\n'
            )
            child.write_text(child.read_text(encoding="utf-8").replace(
                '    result = extract_request(request)\n',
                injection + '    result = extract_request(request)\n'),
                encoding="utf-8")
            sleeper = folder / "sleep.py"
            sleeper.write_text("import time\ntime.sleep(60)\n")
            crash = folder / "crash.py"
            crash.write_text("import os\nos._exit(17)\n")
            memory = copied / "memory_child.py"
            memory.write_text(child.read_text(encoding="utf-8").replace(
                '        raise ValueError("injected parser bug")',
                '        bytearray(128 * 1024 * 1024)\n        return ""'),
                encoding="utf-8")
            for replacement, code in ((sleeper, "timeout"),
                                      (crash, "crash"), (child, "crash"),
                                      (memory, "memory_error")):
                with self.subTest(child=replacement.name):
                    with patch.object(Job, "launch", substitute):
                        with self.assertRaises(ExtractionError) as caught:
                            worker.extract_saved_pdf_pages_in_worker(
                                root, RETRIEVAL_ID, pages=(1,),
                                limits=ExtractionLimits(
                                    memory_bytes=67_108_864,
                                    timeout_seconds=(
                                        0.2 if code == "timeout" else 10)))
                    self.assertEqual(caught.exception.code, code)
                    self.assertEqual(jobs[-1].configured.process_memory,
                                     67_108_864)
                    self.assertEqual(jobs[-1].configured.job_memory,
                                     67_108_864)
                    self.assertTrue(jobs[-1].closed)
                    self.assertEqual(jobs[-1].active_after_cleanup, 0)
                    self.assertFalse(outputs[-1].parent.exists())
                    self.assertEqual(before,
                                     {p: p.read_bytes() for p in before})
                    if replacement in (child, memory):
                        self.assertEqual(marker.read_text(), "entered")
                        marker.unlink()
            result = worker.extract_saved_pdf_pages_in_worker(
                root, RETRIEVAL_ID, pages=(1,))
            self.assertEqual(result.pages[0].text, "First page")

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

    def test_response_schema_rejects_every_incomplete_or_untyped_part(
        self,
    ) -> None:
        """Reject malformed page facts, metadata and each settings field."""
        from payer_policy import _extraction_protocol as protocol
        from payer_policy.text_extraction import CHILD_ERRORS, ExtractionError

        missing = object()
        request = sample_request(Path.cwd())
        message = protocol.result_message(request, sample_extraction())
        mutations = []
        for prefix, mapping in (
            ((), message), (("facts",), message["facts"]),
            (("limits",), message["limits"]),
            (("facts", "limits"), message["facts"]["limits"]),
            (("facts", "pages", 0), message["facts"]["pages"][0]),
        ):
            mutations.extend((prefix + (key,), missing) for key in mapping)
            mutations.append((prefix + ("extra",), 1))
        for prefix in (("limits",), ("facts", "limits")):
            for key in request["limits"]:
                for value in (True, False, None, "1", 0, -1):
                    mutations.append((prefix + (key,), value))
        for key, values in {
            "schema_version": (False, 0, 2, "1"),
            "sha256": (None, "", "../hash", True),
            "retrieval_id": (None, "A" * 32, "../id"),
            "page_count": (False, 0, -1, 4.0, "4"),
            "parser_name": (None, True, "other"),
            "parser_version": (None, True, "6.19.1"),
            "mode": (None, True, "layout"),
            "extracted_at": (None, True, "2026-01-02T00:00:00Z",
                             "2026-01-02T00:00:00.000000+00:00",
                             "2026-02-30T00:00:00.000000Z"),
            "requested_pages": (None, [], [True, 4], [1, 1], [4, 1]),
            "pages": (None, {}, [], message["facts"]["pages"][:1],
                      message["facts"]["pages"][::-1]),
        }.items():
            mutations.extend((("facts", key), value) for value in values)
        for key, values in {
            "page_number": (True, False, 0, 4, 1.0, "1"),
            "text": (None, False, 1, [], {}, "\ud800", " \t"),
            "status": (None, False, 1, "empty", "unknown"),
        }.items():
            mutations.extend((("facts", "pages", 0, key), value)
                             for value in values)
        mutations.extend([
            (("facts", "pages", 1, "text"), "not empty"),
            (("facts", "pages", 0), None),
            (("status",), True), (("status",), []),
        ])
        with TemporaryDirectory() as name:
            path = Path(name) / "result.json"
            for keys, value in mutations:
                bad = copy.deepcopy(message)
                part = bad
                for key in keys[:-1]:
                    part = part[key]
                if value is missing:
                    del part[keys[-1]]
                else:
                    part[keys[-1]] = value
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.subTest(keys=keys, value=repr(value)):
                    with self.assertRaises(protocol.ProtocolError):
                        protocol.read_result(path, request)
            for status in sorted(CHILD_ERRORS):
                for facts in (None, message["facts"], {}):
                    bad = dict(message, status=status, facts=facts)
                    path.write_text(json.dumps(bad), encoding="utf-8")
                    with self.subTest(status=status, facts=facts is None):
                        if facts is None:
                            with self.assertRaises(ExtractionError) as caught:
                                protocol.read_result(path, request)
                            self.assertEqual(caught.exception.code, status)
                        else:
                            with self.assertRaises(protocol.ProtocolError):
                                protocol.read_result(path, request)

    def test_selected_result_cap_counts_received_whitespace(self) -> None:
        """A full JSON reply cannot hide excess bytes in legal whitespace."""
        from payer_policy import _extraction_protocol as protocol

        result = sample_extraction()
        result = replace(result, limits=replace(
            result.limits, max_result_bytes=2048))
        request = sample_request(Path.cwd())
        request["limits"] = asdict(result.limits)
        raw = protocol.encode(protocol.result_message(request, result), 2048)
        self.assertLess(len(raw), 2048)
        raw += b" " * (2048 - len(raw))
        with TemporaryDirectory() as name:
            path = Path(name) / "result.json"
            path.write_bytes(raw)
            self.assertEqual(protocol.read_result(path, request), result)
            path.write_bytes(raw + b" ")
            with self.assertRaises(protocol.ProtocolError):
                protocol.read_result(path, request)

    def test_protocol_reads_exact_caps_and_rejects_oversize_before_decode(
        self,
    ) -> None:
        """Both wire formats count raw bytes before parsing untrusted JSON."""
        from functools import partial
        from payer_policy import _extraction_protocol as protocol

        with TemporaryDirectory() as name:
            root = Path(name)
            path = root / "message.json"
            request = sample_request(root)
            message = protocol.result_message(request, sample_extraction())
            for value, cap, reader in (
                (request, protocol.REQUEST_BYTES, protocol.read_request),
                (message, protocol.RESULT_BYTES,
                 partial(protocol.read_result, request=request)),
            ):
                raw = protocol.encode(value, cap)
                raw += b" " * (cap - len(raw))
                with self.subTest(cap=cap):
                    path.write_bytes(raw)
                    self.assertIsNotNone(reader(path))
                    path.write_bytes(raw + b" ")
                    with patch.object(protocol, "decode") as decode:
                        with self.assertRaises(protocol.ProtocolError):
                            reader(path)
                        decode.assert_not_called()
            for raw in (b'{"status":"ok","status":"ok"}',
                        b'{"value":NaN}', b'{"value":Infinity}',
                        b'[' * 2000 + b']' * 2000, b'\xff', b'[]', b'null'):
                with self.subTest(raw=raw[:35]):
                    path.write_bytes(raw)
                    with self.assertRaises(protocol.ProtocolError):
                        protocol.read_result(path, request)
            path.unlink()
            with self.assertRaises(protocol.ProtocolError):
                protocol.read_result(path, request)

    @unittest.skipUnless(sys.platform == "win32", "Windows storage contract")
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
            with patch.object(child, "_extract_saved_pages",
                              return_value=result):
                self.assertEqual(child.extract_request(request)["status"],
                                 "ok")
            result = replace(result, limits=replace(
                result.limits, max_result_bytes=size - 1))
            request["limits"] = asdict(result.limits)
            with patch.object(child, "_extract_saved_pages",
                              return_value=result):
                failed = child.extract_request(request)
            self.assertEqual(failed["status"], "output_limit")
            self.assertIsNone(failed["facts"])


@unittest.skipUnless(sys.platform == "win32", "Windows storage contract")
class SupervisorTests(unittest.TestCase):
    """Characterize reused containment failures and early input validation."""

    def test_invalid_inputs_never_reach_runtime(self) -> None:
        """No native setup, loading or temporary files for caller mistakes."""
        from payer_policy import extraction_worker as worker
        from payer_policy.text_extraction import ExtractionLimits

        with (TemporaryDirectory() as name,
              patch.object(worker, "_runtime") as run):
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
                ("_temporary_directory",
                 WorkerInspectionError("cleanup_error"), "cleanup_error"),
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
            for prefix, mapping in (
                ((), request), (("limits",), request["limits"]),
                (("runtime",), request["runtime"]),
            ):
                for key in mapping:
                    bad = copy.deepcopy(request)
                    part = bad[prefix[0]] if prefix else bad
                    del part[key]
                    path.write_text(json.dumps(bad), encoding="utf-8")
                    with self.subTest(missing=prefix + (key,)):
                        with self.assertRaises(protocol.ProtocolError):
                            protocol.read_request(path)
            for key in request["limits"]:
                bad = copy.deepcopy(request)
                bad["limits"][key] = True
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.subTest(boolean_limit=key):
                    with self.assertRaises(protocol.ProtocolError):
                        protocol.read_request(path)
            for key in request["runtime"]:
                for value in (True, None, "relative", str(root) + "\x00",
                              "\\\\server\\share"):
                    bad = copy.deepcopy(request)
                    bad["runtime"][key] = value
                    path.write_text(json.dumps(bad), encoding="utf-8")
                    with self.subTest(runtime=key, value=value):
                        with self.assertRaises(protocol.ProtocolError):
                            protocol.read_request(path)
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

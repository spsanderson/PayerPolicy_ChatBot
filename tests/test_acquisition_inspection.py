"""Offline composition tests with real storage and Windows PDF workers.

[test_https_transport.controlled_reply](test_https_transport.py) supplies
only DNS/TCP/TLS fixtures, keeping the HTTP parser real.
[test_document_inspection.pdf_with_pages](test_document_inspection.py)
generates synthetic PDFs, never downloaded policies.
[acquire_and_inspect_pdf](../payer_policy/acquisition_inspection.py) joins
the existing boundaries; [fingerprint_document](../payer_policy/provenance.py)
checks that reported digests identify the exact fixture bytes.
"""
import os
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from payer_policy.acquisition import AcquisitionApproval, AcquisitionLimits
from payer_policy.inspection_worker import InspectionLimits
from payer_policy.provenance import fingerprint_document
from test_document_inspection import RETRIEVAL_ID, pdf_with_pages
from test_https_transport import controlled_reply


SOURCE_ID = "synthetic-source"
URL = "https://example.org/policy.pdf"


@unittest.skipUnless(os.name == "nt", "Windows storage contract")
class AcquisitionInspectionTests(unittest.TestCase):
    """Use scratch files and deny accidental live DNS/socket operations."""

    def setUp(self) -> None:
        """Create local review/storage fixtures and block public requests."""
        temporary = TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        note = self.root / "review.txt"
        note.write_text("Synthetic fixture review only.", encoding="utf-8")
        self.registry = {SOURCE_ID: {
            "source_id": SOURCE_ID, "name": "Synthetic source",
            "url": URL, "publisher": "Fixture publisher",
            "category": "reference", "plan": "unknown",
            "program": "unknown", "applicability_status": "unknown",
            "evidence_url": "", "access_restrictions": "review required",
        }}
        self.approval = AcquisitionApproval(
            SOURCE_ID, URL, ("example.org",), note)
        for target in ("socket.getaddrinfo", "socket.socket"):
            blocker = patch(target, side_effect=AssertionError("live network"))
            blocker.start()
            self.addCleanup(blocker.stop)

    def run_pipeline(self, **changes: object) -> object:
        """Run explicit coordinator fixtures; return facts or raise errors."""
        from payer_policy.acquisition_inspection import acquire_and_inspect_pdf

        arguments = dict(
            registry=self.registry, source_id=SOURCE_ID, root=self.root,
            retrieval_id=RETRIEVAL_ID, approval=self.approval,
            acquisition_limits=AcquisitionLimits(),
            inspection_limits=InspectionLimits())
        arguments.update(changes)
        return acquire_and_inspect_pdf(**arguments)

    def real_pipeline(self, body: bytes) -> object:
        """Run real composition with a controlled HTTP reply, not sockets."""
        reply = (b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n"
                 + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        with controlled_reply(reply) as (dns, sockets, _, _):
            try:
                result = self.run_pipeline()
            finally:
                dns.assert_called_once()
                sockets.assert_called_once()
        return result

    def test_real_pdf_is_saved_then_inspected(self) -> None:
        """Real acquisition/worker agree on bytes and return frozen facts."""
        body = pdf_with_pages(2)
        result = self.real_pipeline(body)
        self.assertEqual(result.acquisition.original_path.read_bytes(), body)
        self.assertTrue(result.acquisition.receipt_path.is_file())
        self.assertEqual(result.inspection.retrieval_id, RETRIEVAL_ID)
        self.assertEqual(result.inspection.sha256, fingerprint_document(body))
        self.assertEqual(result.inspection.sha256, result.acquisition.sha256)
        self.assertEqual(result.inspection.page_count, 2)
        self.assertFalse(result.inspection.is_encrypted)
        with self.assertRaises(FrozenInstanceError):
            result.inspection = None

    def test_malformed_pdf_failure_keeps_saved_record(self) -> None:
        """A real parser rejection keeps exact original bytes and its cause."""
        from payer_policy.acquisition_inspection import PipelineInspectionError
        from payer_policy.inspection_worker import WorkerInspectionError

        with self.assertRaises(PipelineInspectionError) as caught:
            self.real_pipeline(b"%PDF-")
        failure = caught.exception
        self.assertEqual(failure.code, "parser_error")
        self.assertIsInstance(failure.cause, WorkerInspectionError)
        self.assertIs(failure.cause, failure.__cause__)
        self.assertEqual(failure.acquisition.retrieval_id, RETRIEVAL_ID)
        self.assertEqual(failure.acquisition.original_path.read_bytes(),
                         b"%PDF-")
        self.assertEqual(failure.acquisition.sha256,
                         fingerprint_document(b"%PDF-"))
        self.assertTrue(failure.acquisition.receipt_path.is_file())

    def test_inspection_identity_must_match_saved_record(self) -> None:
        """Neither a wrong retrieval ID nor a wrong digest can be success."""
        from payer_policy import inspection_worker as worker
        from payer_policy.acquisition_inspection import PipelineInspectionError
        from payer_policy.document_inspection import PdfInspection

        digest = fingerprint_document(b"%PDF-")
        for field, value in (("retrieval_id", "b" * 32),
                             ("sha256", "c" * 64)):
            facts = dict(retrieval_id=RETRIEVAL_ID, sha256=digest,
                         page_count=1, is_encrypted=False)
            facts[field] = value
            with self.subTest(field=field):
                # Each successful acquisition needs a fresh record directory.
                self.root = self.root / field
                self.root.mkdir()
                with patch.object(worker, "inspect_saved_pdf_in_worker",
                                  return_value=PdfInspection(**facts)):
                    with self.assertRaises(PipelineInspectionError) as caught:
                        self.real_pipeline(b"%PDF-")
                failure = caught.exception
                self.assertEqual(failure.code, "identity_mismatch")
                self.assertIsNone(failure.cause)
                self.assertIsNone(failure.__cause__)
                saved = failure.acquisition
                self.assertEqual(saved.retrieval_id, RETRIEVAL_ID)
                self.assertEqual(failure.acquisition.sha256, digest)
                self.assertEqual(saved.original_path.read_bytes(), b"%PDF-")

    def test_encrypted_pdf_returns_flags_not_readability(self) -> None:
        """A real encrypted PDF is a result with no asserted page count."""
        body = pdf_with_pages(2, encrypted=True)
        result = self.real_pipeline(body)
        self.assertTrue(result.inspection.is_encrypted)
        self.assertIsNone(result.inspection.page_count)
        self.assertEqual(result.acquisition.original_path.read_bytes(), body)
        self.assertEqual(result.inspection.sha256, result.acquisition.sha256)

    def test_worker_failures_retain_exact_record_and_cause(self) -> None:
        """Worker codes, including late setup failures, retain the record."""
        from payer_policy import acquisition, inspection_worker as worker
        from payer_policy.acquisition_inspection import PipelineInspectionError

        saved = acquisition.AcquisitionResult(
            SOURCE_ID, RETRIEVAL_ID, URL, "c" * 64,
            self.root / "original.bin", self.root / "receipt.json")
        for code in ("timeout", "setup_error", "unsupported_runtime",
                     "storage_error", "invalid_result", "cleanup_error",
                     "crash", "memory_error"):
            failure = worker.WorkerInspectionError(code)
            with self.subTest(code=code):
                with (patch.object(acquisition, "acquire_pdf_candidate",
                                   return_value=saved) as acquire,
                      patch.object(worker, "inspect_saved_pdf_in_worker",
                                   side_effect=failure) as inspect):
                    with self.assertRaises(PipelineInspectionError) as caught:
                        self.run_pipeline()
                self.assertEqual(caught.exception.code, code)
                self.assertIs(caught.exception.acquisition, saved)
                self.assertIs(caught.exception.cause, failure)
                self.assertIs(caught.exception.__cause__, failure)
                acquire.assert_called_once()
                inspect.assert_called_once()

    def test_acquisition_failure_never_inspects(self) -> None:
        """Acquisition exceptions are unchanged and cannot start inspection."""
        from payer_policy import acquisition, inspection_worker as worker

        failures = [acquisition.AcquisitionError(
            "fetch", RETRIEVAL_ID, OSError("fixture failure")),
            worker.WorkerInspectionError("setup_error")]
        for failure in failures:
            with self.subTest(failure=failure):
                with (patch.object(acquisition, "acquire_pdf_candidate",
                                   side_effect=failure) as acquire,
                      patch.object(worker, "inspect_saved_pdf_in_worker")
                      as inspect):
                    with self.assertRaises(type(failure)) as caught:
                        self.run_pipeline()
                self.assertIs(caught.exception, failure)
                acquire.assert_called_once()
                inspect.assert_not_called()

    def test_unexpected_failures_and_interrupts_propagate(self) -> None:
        """Never wrap programming errors, exhausted memory or interruptions."""
        from payer_policy import acquisition, inspection_worker as worker

        saved = acquisition.AcquisitionResult(
            SOURCE_ID, RETRIEVAL_ID, URL, "c" * 64,
            self.root / "original.bin", self.root / "receipt.json")
        stages = ((worker, "_validate_inputs"), (worker, "_runtime"),
                  (acquisition, "acquire_pdf_candidate"),
                  (worker, "inspect_saved_pdf_in_worker"))
        for module, name in stages:
            for kind in (TypeError, ValueError, RuntimeError, MemoryError,
                         KeyboardInterrupt, SystemExit):
                failure = kind("injected downstream failure")
                with self.subTest(stage=name, kind=kind):
                    with (patch.object(acquisition, "acquire_pdf_candidate",
                                       return_value=saved) as acquire,
                          patch.object(worker, "inspect_saved_pdf_in_worker")
                          as inspect,
                          patch.object(module, name, side_effect=failure)
                          as failing):
                        with self.assertRaises(kind) as caught:
                            self.run_pipeline()
                    self.assertIs(caught.exception, failure)
                    failing.assert_called_once()
                    if name != "inspect_saved_pdf_in_worker":
                        inspect.assert_not_called()
                    if name in ("_validate_inputs", "_runtime"):
                        acquire.assert_not_called()

    def test_limit_snapshots_bind_both_stages(self) -> None:
        """Caller mutation cannot change checked budgets or returned values."""
        from payer_policy import acquisition, inspection_worker as worker
        from payer_policy.document_inspection import PdfInspection

        limits = AcquisitionLimits(max_bytes=2048, timeout=1, max_redirects=0)
        worker_limits = InspectionLimits(timeout_seconds=2)
        saved = acquisition.AcquisitionResult(
            SOURCE_ID, "b" * 32, URL, "c" * 64,
            self.root / "original.bin", self.root / "receipt.json")
        facts = PdfInspection(saved.retrieval_id, saved.sha256, 1, False)

        def acquire_then_mutate(*args: object, **kwargs: object) -> object:
            """Mutate caller-owned limits, then return a saved record."""
            object.__setattr__(limits, "max_bytes", 1)
            object.__setattr__(worker_limits, "timeout_seconds", 0)
            return saved

        with (patch.object(acquisition, "acquire_pdf_candidate",
                           side_effect=acquire_then_mutate) as acquire,
              patch.object(worker, "inspect_saved_pdf_in_worker",
                           return_value=facts) as inspect):
            result = self.run_pipeline(
                acquisition_limits=limits, inspection_limits=worker_limits)
        checked = acquire.call_args.kwargs["limits"]
        checked_worker = inspect.call_args.kwargs["limits"]
        self.assertIsNot(checked, limits)
        self.assertIsNot(checked_worker, worker_limits)
        acquire.assert_called_once_with(
            self.registry, SOURCE_ID, self.root, retrieval_id=RETRIEVAL_ID,
            approval=self.approval,
            limits=AcquisitionLimits(2048, 1, 0))
        inspect.assert_called_once_with(
            self.root, saved.retrieval_id, max_bytes=2048,
            limits=InspectionLimits(timeout_seconds=2))
        self.assertIs(result.acquisition, saved)
        self.assertIs(result.inspection, facts)
        with self.assertRaises(FrozenInstanceError):
            checked_worker.timeout_seconds = 5

    def test_bad_worker_inputs_never_acquire(self) -> None:
        """Reject invalid limits, paths and IDs before acquisition starts."""
        from payer_policy import acquisition, inspection_worker as worker

        cases = [
            ({"acquisition_limits": None}, TypeError),
            ({"acquisition_limits": AcquisitionLimits(max_bytes=True)},
             ValueError),
            ({"acquisition_limits": AcquisitionLimits(timeout=11)},
             ValueError),
            ({"acquisition_limits": AcquisitionLimits(max_redirects=4)},
             ValueError),
            ({"inspection_limits": None}, TypeError),
            ({"inspection_limits": InspectionLimits(timeout_seconds=0)},
             ValueError),
            ({"inspection_limits": InspectionLimits(memory_bytes=True)},
             ValueError),
            ({"root": str(self.root)}, TypeError),
            ({"root": Path("relative")}, ValueError),
            ({"retrieval_id": "A" * 32}, ValueError),
        ]
        for changes, error in cases:
            with self.subTest(changes=changes):
                with (patch.object(acquisition, "acquire_pdf_candidate")
                      as acquire, patch.object(
                          worker, "inspect_saved_pdf_in_worker") as inspect):
                    with self.assertRaises(error):
                        self.run_pipeline(**changes)
                    acquire.assert_not_called()
                    inspect.assert_not_called()

    def test_preflight_errors_propagate_before_acquisition(self) -> None:
        """Input/runtime refusal retains its error identity without saving."""
        from payer_policy import acquisition, inspection_worker as worker

        for helper, code in (("_validate_inputs", "input_error"),
                             ("_runtime", "unsupported_runtime")):
            failure = worker.WorkerInspectionError(code)
            with self.subTest(helper=helper):
                with (patch.object(worker, helper, side_effect=failure),
                      patch.object(acquisition, "acquire_pdf_candidate")
                      as acquire, patch.object(
                          worker, "inspect_saved_pdf_in_worker") as inspect):
                    with self.assertRaises(type(failure)) as caught:
                        self.run_pipeline()
                    self.assertIs(caught.exception, failure)
                    acquire.assert_not_called()
                    inspect.assert_not_called()

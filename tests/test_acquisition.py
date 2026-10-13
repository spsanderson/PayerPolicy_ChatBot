"""Offline coordinator tests; synthetic bytes never enter a PDF parser.

Real storage and shallow validation are exercised below. Transport boundary
fixtures follow test_https_transport.py's controlled_reply implementation.
"""
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from payer_policy.https_transport import FetchResult
from payer_policy.provenance import fingerprint_document


RETRIEVAL_ID = "1234567890abcdef1234567890abcdef"
SOURCE_ID = "example-source"
REQUESTED_URL = "https://EXAMPLE.org:443/a%2fb?q=2&b=1"


@unittest.skipUnless(os.name == "nt", "Windows storage contract")
class AcquisitionTests(unittest.TestCase):
    """Use real scratch files and block accidental public network access."""

    def setUp(self) -> None:
        """Create an isolated root and review note; forbid live DNS/socket."""
        temporary = TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.note = self.root / "review.txt"
        self.note.write_text("Synthetic fixture review only.", "utf-8")
        self.registry = {SOURCE_ID: {
            "source_id": SOURCE_ID, "name": "Synthetic source",
            "url": REQUESTED_URL, "publisher": "Fixture publisher",
            "category": "reference", "plan": "unknown",
            "program": "unknown", "applicability_status": "unknown",
            "evidence_url": "", "access_restrictions": "review required",
        }}
        for target in ("socket.getaddrinfo", "socket.socket"):
            blocker = patch(target, side_effect=AssertionError("live network"))
            blocker.start()
            self.addCleanup(blocker.stop)

    def acquire(self, **changes: object) -> object:
        """Run the coordinator with synthetic approval; propagate failures."""
        from payer_policy.acquisition import (
            AcquisitionApproval, AcquisitionLimits, acquire_pdf_candidate,
        )

        arguments = dict(
            registry=self.registry, source_id=SOURCE_ID, root=self.root,
            retrieval_id=RETRIEVAL_ID,
            approval=AcquisitionApproval(
                SOURCE_ID, REQUESTED_URL, ("example.org",), self.note),
            limits=AcquisitionLimits())
        arguments.update(changes)
        return acquire_pdf_candidate(**arguments)

    def test_approval_must_match_exact_source_and_url(self) -> None:
        """Registry membership or applicability never substitutes approval."""
        from payer_policy.acquisition import (
            AcquisitionApproval, AcquisitionError,
        )

        self.registry[SOURCE_ID].update(
            applicability_status="confirmed_applicable",
            evidence_url="https://example.org/evidence")
        cases = [None, AcquisitionApproval(
            "other-source", REQUESTED_URL, ("example.org",), self.note)]
        for url in (REQUESTED_URL.lower(), REQUESTED_URL + "&extra=1"):
            cases.append(AcquisitionApproval(
                SOURCE_ID, url, ("example.org",), self.note))
        for approval in cases:
            with self.subTest(approval=approval):
                with (patch("payer_policy.acquisition.fetch_https") as fetch,
                      patch("payer_policy.acquisition.save_pdf_candidate")
                      as save, self.assertRaises(AcquisitionError) as caught):
                    self.acquire(approval=approval)
                self.assertEqual(caught.exception.stage, "approval")
                self.assertEqual(caught.exception.retrieval_id, RETRIEVAL_ID)
                self.assertIs(caught.exception.cause,
                              caught.exception.__cause__)
                self.assertIsInstance(caught.exception.cause, ValueError)
                fetch.assert_not_called()
                save.assert_not_called()

    def test_limits_reject_invalid_types_and_excess_budgets(self) -> None:
        """Bad limits fail before transport or storage, without coercion."""
        from dataclasses import replace
        from payer_policy.acquisition import AcquisitionLimits

        cases = [("max_bytes", value) for value in
                 (True, 0, -1, 1.0, "1", None, 10_000_001)]
        cases += [("timeout", value) for value in
                  (True, 0, -1, "1", None, float("inf"), float("nan"),
                   10.001, 10 ** 1000)]
        cases += [("max_redirects", value) for value in
                  (True, -1, 4, 1.0, "1", None)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with (patch("payer_policy.acquisition.fetch_https") as fetch,
                      patch("payer_policy.acquisition.save_pdf_candidate")
                      as save):
                    with self.assertRaises((TypeError, ValueError)):
                        limits = replace(AcquisitionLimits(), **{field: value})
                        self.acquire(limits=limits)
                    fetch.assert_not_called()
                    save.assert_not_called()
        with patch("payer_policy.acquisition.fetch_https") as fetch:
            with self.assertRaises(TypeError):
                self.acquire(limits=None)
            fetch.assert_not_called()

    def test_selected_source_and_identifiers_validate_before_fetch(
        self,
    ) -> None:
        """Reject unknown/malformed selected sources and unsafe IDs offline."""
        cases = [dict(source_id="missing"), dict(source_id=None),
                 dict(registry=None), dict(registry={SOURCE_ID: None}),
                 dict(registry={SOURCE_ID: {}})]
        for value in (None, "", "A" * 32, "a" * 31, "../escaped", 1):
            cases.append(dict(retrieval_id=value))
        for field, value in (("source_id", "different"), ("name", ""),
                             ("url", "http://example.org/"),
                             ("url", "https://example.org/é")):
            source = dict(self.registry[SOURCE_ID], **{field: value})
            cases.append(dict(registry={SOURCE_ID: source}))
        for changes in cases:
            with self.subTest(changes=changes):
                with (patch("payer_policy.acquisition.fetch_https") as fetch,
                      patch("payer_policy.acquisition.save_pdf_candidate")
                      as save):
                    with self.assertRaises((TypeError, ValueError)):
                        self.acquire(**changes)
                    fetch.assert_not_called()
                    save.assert_not_called()

    def test_reviewed_hosts_and_note_are_checked_before_fetch(self) -> None:
        """Reject malformed host scope or missing/unsafe note references."""
        from payer_policy.acquisition import AcquisitionApproval

        cases = [(hosts, self.note) for hosts in (
            None, "example.org", {"example.org": True}, [],
            ["EXAMPLE.org"], ["example.org", "Bad.Host"],
            ["127.0.0.1"], ["example.org:443"], ["other.example.org"],
            ["example.org", 1], iter(["example.org"]))]
        cases += [(("example.org",), note) for note in (
            None, str(self.note), self.root, self.root / "missing",
            Path("relative-note"), Path("//server/share/review.txt"))]
        for hosts, note in cases:
            with self.subTest(hosts=hosts, note=note):
                with (patch("payer_policy.acquisition.fetch_https") as fetch,
                      patch("payer_policy.acquisition.save_pdf_candidate")
                      as save):
                    with self.assertRaises((TypeError, ValueError)):
                        self.acquire(approval=AcquisitionApproval(
                            SOURCE_ID, REQUESTED_URL, hosts, note))
                    fetch.assert_not_called()
                    save.assert_not_called()
        with patch("payer_policy.acquisition.fetch_https") as fetch:
            with self.assertRaises(TypeError):
                self.acquire(approval=object())
            fetch.assert_not_called()

    def test_immutable_values_snapshot_caller_hosts_and_inputs(self) -> None:
        """Later caller edits cannot change the checked request or budgets."""
        from dataclasses import FrozenInstanceError
        from payer_policy.acquisition import (
            AcquisitionApproval, AcquisitionLimits,
        )

        hosts = ["example.org"]
        approval = AcquisitionApproval(
            SOURCE_ID, REQUESTED_URL, hosts, self.note)
        limits = AcquisitionLimits(max_bytes=5, timeout=0.25, max_redirects=0)
        hosts.append("unreviewed.example.org")
        self.assertEqual(approval.allowed_hosts, ("example.org",))
        response = FetchResult(REQUESTED_URL, 200,
                               (("Content-Type", "application/pdf"),),
                               b"%PDF-")

        def fetch_then_mutate(*args: object, **kwargs: object) -> FetchResult:
            """Mutate caller inputs after preflight; return fixture bytes."""
            self.registry[SOURCE_ID]["url"] = "https://example.org/changed"
            object.__setattr__(limits, "max_bytes", 1)
            return response

        with patch("payer_policy.acquisition.fetch_https",
                   side_effect=fetch_then_mutate) as fetch:
            result = self.acquire(approval=approval, limits=limits)
        fetch.assert_called_once_with(
            REQUESTED_URL, ("example.org",), max_bytes=5,
            timeout=0.25, max_redirects=0)
        receipt = json.loads(result.receipt_path.read_text("utf-8"))
        self.assertEqual(receipt["requested_url"], REQUESTED_URL)
        for value, field in ((approval, "source_id"),
                             (limits, "max_bytes"), (result, "sha256")):
            with self.subTest(field=field):
                with self.assertRaises(FrozenInstanceError):
                    setattr(value, field, "changed")

    def test_storage_paths_are_safe_before_any_fetch(self) -> None:
        """Reject invalid roots and existing unsafe storage components."""
        import stat
        from types import SimpleNamespace

        for root in (None, str(self.root), Path("relative"), self.note,
                     self.root / "missing", Path("//server/share/root")):
            with self.subTest(root=root):
                with (patch("payer_policy.acquisition.fetch_https") as fetch,
                      self.assertRaises((TypeError, ValueError))):
                    self.acquire(root=root)
                fetch.assert_not_called()
        for name in ("records", ".staging"):
            component = self.root / name
            component.write_bytes(b"not a directory")
            with self.subTest(component=name):
                with (patch("payer_policy.acquisition.fetch_https") as fetch,
                      self.assertRaises(ValueError)):
                    self.acquire()
                fetch.assert_not_called()
            component.unlink()
            component.mkdir()
        real_lstat = Path.lstat
        for unsafe in (self.root, self.root / "records",
                       self.root / ".staging", self.note):
            def reparse_info(path: Path) -> object:
                """Model Windows reparse attributes without link privileges."""
                if path == unsafe:
                    return SimpleNamespace(
                        st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
                return real_lstat(path)

            with self.subTest(unsafe=unsafe):
                with (patch.object(Path, "lstat", reparse_info),
                      patch("payer_policy.acquisition.fetch_https") as fetch,
                      self.assertRaisesRegex(ValueError, "reparse")):
                    self.acquire()
                fetch.assert_not_called()

    def test_existing_retrieval_never_fetches_even_identical_data(
        self,
    ) -> None:
        """Acquisition refuses retries without changing storage idempotence."""
        from payer_policy.acquisition import AcquisitionError
        from payer_policy.document_storage import StorageConflictError

        response = FetchResult(REQUESTED_URL, 200,
                               (("Content-Type", "application/pdf"),),
                               b"%PDF-identical")
        with patch("payer_policy.acquisition.fetch_https",
                   return_value=response):
            first = self.acquire()
        before = first.receipt_path.read_bytes()
        with (patch("payer_policy.acquisition.fetch_https") as fetch,
              patch("payer_policy.acquisition.save_pdf_candidate") as save,
              self.assertRaises(AcquisitionError) as caught):
            self.acquire()
        self.assertEqual(caught.exception.stage, "storage")
        self.assertEqual(caught.exception.retrieval_id, RETRIEVAL_ID)
        self.assertIsInstance(caught.exception.cause, StorageConflictError)
        self.assertIs(caught.exception.cause, caught.exception.__cause__)
        fetch.assert_not_called()
        save.assert_not_called()
        self.assertEqual(first.receipt_path.read_bytes(), before)
        self.assertEqual(first.original_path.read_bytes(), response.body)

    def test_expected_fetch_failures_keep_stage_id_and_cause(self) -> None:
        """Network policy and transport failures stop without storage/retry."""
        from payer_policy.acquisition import AcquisitionError
        from payer_policy.https_transport import TransportError
        from payer_policy.network_safety import NetworkSafetyError

        for cause in (TransportError("truncated"), OSError("DNS failed"),
                      NetworkSafetyError("unsafe DNS")):
            with self.subTest(cause=cause):
                with (patch("payer_policy.acquisition.fetch_https",
                            side_effect=cause) as fetch,
                      patch("payer_policy.acquisition.save_pdf_candidate")
                      as save, self.assertRaises(AcquisitionError) as caught):
                    self.acquire()
                self.assertEqual(caught.exception.stage, "fetch")
                self.assertEqual(caught.exception.retrieval_id, RETRIEVAL_ID)
                self.assertIs(caught.exception.cause, cause)
                self.assertIs(caught.exception.__cause__, cause)
                fetch.assert_called_once()
                save.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [self.note])

    def test_invalid_fetched_candidates_never_reach_storage(self) -> None:
        """Classify shallow validation, byte limits, and final URL failures."""
        from dataclasses import replace
        from payer_policy.acquisition import (
            AcquisitionError, AcquisitionLimits,
        )

        valid = FetchResult(REQUESTED_URL, 200,
                            (("Content-Type", "application/pdf"),), b"%PDF-")
        cases = [None, replace(valid, body="%PDF-"),
                 replace(valid, body=b"<html>login</html>"),
                 replace(valid, body=b"%PDF-too big"),
                 replace(valid, status=206), replace(valid, status=404),
                 replace(valid, headers=()),
                 replace(valid, headers=valid.headers * 2),
                 replace(valid, headers=(("Content-Type", "text/html"),)),
                 replace(valid, headers=valid.headers +
                         (("Content-Encoding", "gzip"),)),
                 replace(valid, headers=valid.headers +
                         (("Content-Range", "bytes 0-4/5"),)),
                 replace(valid, url="https://example.org/é"),
                 replace(valid, url="https://unreviewed.example.org/a")]
        for response in cases:
            with self.subTest(response=response):
                with (patch("payer_policy.acquisition.fetch_https",
                            return_value=response),
                      patch("payer_policy.acquisition.save_pdf_candidate")
                      as save, self.assertRaises(AcquisitionError) as caught):
                    self.acquire(limits=AcquisitionLimits(max_bytes=5))
                self.assertEqual(caught.exception.stage, "validation")
                self.assertEqual(caught.exception.retrieval_id, RETRIEVAL_ID)
                self.assertIsInstance(caught.exception.cause,
                                      (TypeError, ValueError))
                self.assertIs(caught.exception.__cause__,
                              caught.exception.cause)
                save.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [self.note])

    def test_known_storage_failures_keep_stage_id_and_cause(self) -> None:
        """Classify expected write/conflict/integrity errors without retry."""
        from payer_policy.acquisition import AcquisitionError
        from payer_policy.document_storage import (
            StorageConflictError, StorageIntegrityError,
        )

        response = FetchResult(REQUESTED_URL, 200,
                               (("Content-Type", "application/pdf"),),
                               b"%PDF-")
        for cause in (OSError("disk full"), StorageConflictError("race"),
                      StorageIntegrityError("published record damaged")):
            with self.subTest(cause=cause):
                with (patch("payer_policy.acquisition.fetch_https",
                            return_value=response) as fetch,
                      patch("payer_policy.acquisition.save_pdf_candidate",
                            side_effect=cause) as save,
                      self.assertRaises(AcquisitionError) as caught):
                    self.acquire()
                self.assertEqual(caught.exception.stage, "storage")
                self.assertEqual(caught.exception.retrieval_id, RETRIEVAL_ID)
                self.assertIs(caught.exception.cause, cause)
                self.assertIs(caught.exception.__cause__, cause)
                fetch.assert_called_once()
                save.assert_called_once()

    def test_receipt_budget_failure_is_classified_before_storage(self) -> None:
        """JSON escaping can exceed storage's cap below HTTP's header cap."""
        from payer_policy.acquisition import AcquisitionError

        response = FetchResult(
            REQUESTED_URL, 200,
            (("Content-Type", "application/pdf"), ("ETag", "ÿ" * 12_000)),
            b"%PDF-")
        with (patch("payer_policy.acquisition.fetch_https",
                    return_value=response),
              patch("payer_policy.acquisition.save_pdf_candidate") as save,
              self.assertRaises(AcquisitionError) as caught):
            self.acquire()
        self.assertEqual(caught.exception.stage, "storage")
        self.assertEqual(caught.exception.retrieval_id, RETRIEVAL_ID)
        self.assertIsInstance(caught.exception.cause, ValueError)
        self.assertIn("64 KiB", str(caught.exception.cause))
        self.assertIs(caught.exception.__cause__, caught.exception.cause)
        save.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [self.note])

    def test_preflight_io_failures_have_approval_or_storage_stage(
        self,
    ) -> None:
        """Permission errors inspecting local paths never start a fetch."""
        from payer_policy.acquisition import AcquisitionError

        real_lstat = Path.lstat
        for target, stage in ((self.note, "approval"),
                              (self.root / "records", "storage")):
            cause = PermissionError("fixture denied")

            def denied_stat(path: Path) -> object:
                """Raise the supplied OS failure only for the target entry."""
                if path == target:
                    raise cause
                return real_lstat(path)

            with self.subTest(stage=stage):
                with (patch.object(Path, "lstat", denied_stat),
                      patch("payer_policy.acquisition.fetch_https") as fetch,
                      self.assertRaises(AcquisitionError) as caught):
                    self.acquire()
                self.assertEqual(caught.exception.stage, stage)
                self.assertEqual(caught.exception.retrieval_id, RETRIEVAL_ID)
                self.assertIs(caught.exception.cause, cause)
                self.assertIs(caught.exception.__cause__, cause)
                fetch.assert_not_called()

    def test_unexpected_bugs_and_interrupts_propagate_unchanged(self) -> None:
        """Keep unexpected bugs and interrupts outside normal failures."""
        from contextlib import ExitStack

        response = FetchResult(REQUESTED_URL, 200,
                               (("Content-Type", "application/pdf"),),
                               b"%PDF-")
        for boundary in ("fetch_https", "validate_pdf_candidate",
                         "save_pdf_candidate"):
            failures = [RuntimeError("bug"), KeyError("bug"),
                        AssertionError("bug"), MemoryError("memory"),
                        KeyboardInterrupt(), SystemExit(7)]
            if boundary != "validate_pdf_candidate":
                failures += [TypeError("bug"), ValueError("bug")]
            for cause in failures:
                with self.subTest(boundary=boundary, cause=type(cause)):
                    with ExitStack() as stack:
                        stack.enter_context(patch(
                            "payer_policy.acquisition.fetch_https",
                            return_value=response))
                        stack.enter_context(patch(
                            "payer_policy.acquisition." + boundary,
                            side_effect=cause))
                        with self.assertRaises(type(cause)) as caught:
                            self.acquire()
                    self.assertIs(caught.exception, cause)
        self.assertEqual(list(self.root.iterdir()), [self.note])

    def test_published_failure_keeps_record_for_later_inspection(self) -> None:
        """Keep published bytes after a later verification failure."""
        from payer_policy.acquisition import AcquisitionError
        from payer_policy import document_storage as storage

        response = FetchResult(REQUESTED_URL, 200,
                               (("Content-Type", "application/pdf"),),
                               b"%PDF-published")
        cause = storage.StorageIntegrityError("late read failure")
        with (patch("payer_policy.acquisition.fetch_https",
                    return_value=response),
              patch.object(storage, "load_saved_candidate", side_effect=cause),
              self.assertRaises(AcquisitionError) as caught):
            self.acquire()
        self.assertEqual(caught.exception.stage, "storage")
        self.assertIs(caught.exception.cause, cause)
        loaded = storage.load_saved_candidate(self.root, RETRIEVAL_ID)
        self.assertEqual(loaded.body, response.body)
        self.assertEqual(loaded.receipt["requested_url"], REQUESTED_URL)
        self.assertEqual(list((self.root / ".staging").iterdir()), [])

    def test_publication_race_keeps_other_writer_record(self) -> None:
        """Characterize existing conflict rules when an ID appears midfetch."""
        from payer_policy.acquisition import AcquisitionError
        from payer_policy import document_storage as storage

        response = FetchResult(REQUESTED_URL, 200,
                               (("Content-Type", "application/pdf"),),
                               b"%PDF-other writer")

        def racing_fetch(*args: object, **kwargs: object) -> FetchResult:
            """Publish competing bytes after preflight, before returning."""
            storage.save_pdf_candidate(
                self.root, response, retrieval_id=RETRIEVAL_ID,
                source_id=SOURCE_ID, requested_url=REQUESTED_URL,
                retrieved_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
            return FetchResult(REQUESTED_URL, 200, response.headers,
                               b"%PDF-this acquisition")

        with (patch("payer_policy.acquisition.fetch_https",
                    side_effect=racing_fetch),
              self.assertRaises(AcquisitionError) as caught):
            self.acquire()
        self.assertEqual(caught.exception.stage, "storage")
        self.assertIsInstance(caught.exception.cause,
                              storage.StorageConflictError)
        self.assertEqual(storage.load_saved_candidate(
            self.root, RETRIEVAL_ID).body, response.body)

    def test_real_transport_parser_reaches_verified_storage(self) -> None:
        """Characterize real HTTP parsing through validation and storage.

        [controlled_reply](test_https_transport.py) replaces DNS/TCP/TLS
        peers only; the production fetcher and writer remain unchanged.
        """
        from test_https_transport import controlled_reply
        from payer_policy.document_storage import load_saved_candidate

        body = b"%PDF-synthetic\x00\xff"
        reply = (b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n"
                 b"Content-Length: " + str(len(body)).encode("ascii")
                 + b"\r\nETag: fixture\r\n\r\n" + body)
        with controlled_reply(reply) as (dns, make_socket, raw, tls):
            result = self.acquire()
        dns.assert_called_once()
        make_socket.assert_called_once()
        raw.connect.assert_called_once_with(("8.8.8.8", 443))
        tls.close.assert_called()
        loaded = load_saved_candidate(self.root, RETRIEVAL_ID)
        self.assertEqual(loaded.body, body)
        self.assertEqual(loaded.receipt["requested_url"], REQUESTED_URL)
        self.assertEqual(loaded.receipt["final_url"], REQUESTED_URL)
        self.assertEqual(result.sha256, fingerprint_document(body))
        self.assertEqual(result.receipt_path, loaded.receipt_path)

    def test_real_transport_failure_never_publishes(self) -> None:
        """Reject truncated HTTP and HTML before creating storage records."""
        from test_https_transport import controlled_reply
        from payer_policy.acquisition import AcquisitionError

        cases = (
            (b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n"
             b"Content-Length: 100\r\n\r\n%PDF-", "fetch"),
            (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
             b"Content-Length: 5\r\n\r\nlogin", "validation"),
        )
        for reply, stage in cases:
            with self.subTest(stage=stage):
                with controlled_reply(reply) as (_, _, _, tls):
                    with self.assertRaises(AcquisitionError) as caught:
                        self.acquire()
                self.assertEqual(caught.exception.stage, stage)
                self.assertEqual(caught.exception.retrieval_id, RETRIEVAL_ID)
                self.assertIs(caught.exception.__cause__,
                              caught.exception.cause)
                tls.close.assert_called()
                self.assertEqual(list(self.root.iterdir()), [self.note])

    def test_success_preserves_bytes_receipt_and_completion_time(self) -> None:
        """Return small metadata only after real storage verifies the bytes."""
        from payer_policy.acquisition import (
            AcquisitionApproval, AcquisitionLimits, acquire_pdf_candidate,
        )

        response = FetchResult(
            "https://cdn.example.org/final?x=1", 200,
            (("Content-Type", "application/pdf"), ("ETag", '"fixture"'),
             ("Set-Cookie", "not retained")), b"%PDF-synthetic\x00\xff")
        approval = AcquisitionApproval(
            SOURCE_ID, REQUESTED_URL,
            ("example.org", "cdn.example.org"), self.note)
        started = datetime.now(timezone.utc)
        with patch("payer_policy.acquisition.fetch_https",
                   return_value=response) as fetch:
            result = acquire_pdf_candidate(
                self.registry, SOURCE_ID, self.root,
                retrieval_id=RETRIEVAL_ID, approval=approval,
                limits=AcquisitionLimits())
        finished = datetime.now(timezone.utc)
        fetch.assert_called_once_with(
            REQUESTED_URL, ("example.org", "cdn.example.org"),
            max_bytes=10_000_000, timeout=10, max_redirects=3)
        self.assertEqual(result.source_id, SOURCE_ID)
        self.assertEqual(result.retrieval_id, RETRIEVAL_ID)
        self.assertEqual(result.final_url, response.url)
        self.assertEqual(result.sha256, fingerprint_document(response.body))
        self.assertFalse(hasattr(result, "body"))
        record = self.root / "records" / RETRIEVAL_ID
        self.assertEqual(result.original_path, record / "original.bin")
        self.assertEqual(result.receipt_path, record / "receipt.json")
        self.assertEqual(result.original_path.read_bytes(), response.body)
        receipt = json.loads(result.receipt_path.read_text("utf-8"))
        self.assertEqual(receipt["requested_url"], REQUESTED_URL)
        self.assertEqual(receipt["final_url"], response.url)
        self.assertEqual(receipt["sha256"], result.sha256)
        self.assertEqual(receipt["headers"],
                         [list(pair) for pair in response.headers[:2]])
        instant = datetime.fromisoformat(receipt["retrieved_at"])
        self.assertEqual(instant.tzinfo, timezone.utc)
        self.assertLessEqual(started, instant)
        self.assertLessEqual(instant, finished)
        self.assertEqual(list((self.root / ".staging").iterdir()), [])

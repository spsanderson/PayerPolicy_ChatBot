"""Offline Windows storage tests using synthetic candidates and real files."""
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from payer_policy.https_transport import FetchResult
from payer_policy.provenance import fingerprint_document


RETRIEVAL_ID = "1234567890abcdef1234567890abcdef"
RETRIEVED_AT = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def candidate(body: bytes = b"%PDF-synthetic") -> FetchResult:
    """Return a PDF-looking response, not a structurally valid document."""
    return FetchResult("https://example.org/final", 200,
                       (("Content-Type", "application/pdf"),), body)


def save_fixture(root: Path, **changes: object) -> object:
    """Save a synthetic retrieval with explicit, repeatable metadata."""
    from payer_policy.document_storage import save_pdf_candidate

    arguments = dict(result=candidate(), retrieval_id=RETRIEVAL_ID,
                     source_id="example-source",
                     requested_url="https://example.org/requested",
                     retrieved_at=RETRIEVED_AT)
    arguments.update(changes)
    return save_pdf_candidate(root, **arguments)


@unittest.skipUnless(sys.platform == "win32", "Windows storage contract")
class DocumentStorageTests(unittest.TestCase):
    """Exercise actual temporary files, receipts, and returned content."""

    def test_save_and_load_exact_original(self) -> None:
        """Verify the saved bytes, receipt, and loaded record."""
        from payer_policy.document_storage import load_saved_candidate

        with TemporaryDirectory() as directory:
            root = Path(directory)
            stored = save_fixture(root, max_bytes=len(candidate().body))
            record = root / "records" / RETRIEVAL_ID
            self.assertEqual(stored.original_path, record / "original.bin")
            self.assertEqual(stored.receipt_path, record / "receipt.json")
            self.assertEqual(stored.body, candidate().body)
            self.assertEqual(stored.original_path.read_bytes(), stored.body)
            receipt = json.loads(stored.receipt_path.read_text("utf-8"))
            self.assertEqual(receipt, {
                "schema_version": 1, "retrieval_id": RETRIEVAL_ID,
                "source_id": "example-source",
                "requested_url": "https://example.org/requested",
                "final_url": "https://example.org/final",
                "retrieved_at": "2025-01-02T03:04:05.000000Z",
                "http_status": 200,
                "headers": [["Content-Type", "application/pdf"]],
                "byte_count": len(stored.body),
                "sha256": fingerprint_document(stored.body),
                "validation": "pdf_candidate", "validation_version": 1,
            })
            loaded = load_saved_candidate(root, RETRIEVAL_ID)
            self.assertEqual(loaded, stored)
            self.assertEqual(list((root / ".staging").iterdir()), [])

    def test_invalid_inputs_do_not_create_records(self) -> None:
        """Reject bad input; oversized bodies never reach receipt work."""
        from dataclasses import replace
        from unittest.mock import patch

        from payer_policy import document_storage as storage

        cases = [
            {"result": candidate(b"HTML")}, {"result": candidate(b"")},
            {"result": None}, {"result": replace(candidate(), url="http://x")},
            {"retrieval_id": "../escaped"}, {"retrieval_id": "A" * 32},
            {"retrieval_id": "a" * 31}, {"retrieval_id": None},
            {"source_id": "Bad Source"}, {"source_id": "../source"},
            {"source_id": ""}, {"source_id": None},
            {"requested_url": "https://user:secret@example.org/a"},
            {"requested_url": "https://example.org/a#fragment"},
            {"requested_url": "https://example.org/\npath"},
            {"requested_url": "https://example.org/%xx"},
            {"requested_url": "https://example.org:bad/a"},
            {"requested_url": None},
            {"retrieved_at": datetime(2025, 1, 1)},
            {"retrieved_at": "2025-01-01"}, {"retrieved_at": None},
            {"max_bytes": True}, {"max_bytes": 0}, {"max_bytes": -1},
            {"max_bytes": 10.0}, {"max_bytes": 1},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                with TemporaryDirectory() as directory:
                    root = Path(directory)
                    with self.assertRaises((TypeError, ValueError)):
                        save_fixture(root, **changes)
                    self.assertEqual(list(root.iterdir()), [])

        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = candidate()
            with (patch.object(storage, "_make_receipt",
                               wraps=storage._make_receipt) as make_receipt,
                  patch.object(storage, "_encode_receipt",
                               wraps=storage._encode_receipt) as encode,
                  patch.object(storage, "fingerprint_document",
                               wraps=storage.fingerprint_document) as hash_):
                with self.assertRaisesRegex(
                        ValueError, "^original exceeds max_bytes$"):
                    save_fixture(root, result=result,
                                 max_bytes=len(result.body) - 1)
                make_receipt.assert_not_called()
                encode.assert_not_called()
                hash_.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])

    def test_receipt_preserves_selected_metadata_only(self) -> None:
        """Keep UTC time and exact useful header pairs, not cookies."""
        from datetime import timedelta
        from dataclasses import replace

        headers = (("cOnTeNt-TyPe", " Application/PDF "),
                   ("ETag", '"first"'), ("etag", '"second"'),
                   ("Content-Length", str(len(candidate().body))),
                   ("Last-Modified", "not a benefit date"),
                   ("Date", "server date"), ("Content-Encoding", "identity"),
                   ("Transfer-Encoding", "chunked"),
                   ("Set-Cookie", "private"), ("X-Other", "ignore"))
        result = replace(candidate(), headers=headers,
                         url="https://EXAMPLE.org:443/a%2fb?q=2&b=1")
        instant = RETRIEVED_AT.astimezone(timezone(timedelta(hours=-5)))
        with TemporaryDirectory() as directory:
            stored = save_fixture(Path(directory), result=result,
                                  retrieved_at=instant)
            self.assertEqual(stored.receipt["headers"],
                             [list(pair) for pair in headers[:-2]])
            self.assertEqual(stored.receipt["final_url"], result.url)
            self.assertEqual(stored.receipt["retrieved_at"],
                             "2025-01-02T03:04:05.000000Z")
            self.assertNotIn(b"private", stored.receipt_path.read_bytes())

    def test_retries_and_conflicts_preserve_first_snapshot(self) -> None:
        """Same attempt is idempotent; conflicting data never replaces it."""
        from payer_policy.document_storage import StorageConflictError

        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = save_fixture(root)
            first_stat = first.original_path.stat().st_mtime_ns
            self.assertEqual(save_fixture(root), first)
            self.assertEqual(first.original_path.stat().st_mtime_ns,
                             first_stat)
            for change in ({"result": candidate(b"%PDF-changed")},
                           {"requested_url": "https://example.org/other"}):
                with self.subTest(change=change):
                    with self.assertRaises(StorageConflictError):
                        save_fixture(root, **change)
                    self.assertEqual(first.original_path.read_bytes(),
                                     first.body)
            self.assertEqual(list((root / ".staging").iterdir()), [])

    def test_distinct_retrievals_keep_distinct_snapshots(self) -> None:
        """Matching content and changed content retain separate receipts."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = save_fixture(root)
            second = save_fixture(root, retrieval_id="b" * 32)
            third = save_fixture(root, retrieval_id="c" * 32,
                                 result=candidate(b"%PDF-changed"))
            self.assertEqual(first.receipt["sha256"], second.receipt["sha256"])
            self.assertNotEqual(first.receipt["sha256"],
                                third.receipt["sha256"])
            self.assertEqual(len(list((root / "records").iterdir())), 3)

    def test_failed_write_or_publish_leaves_no_completed_record(self) -> None:
        """A disk or publication error never creates a completed snapshot."""
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("payer_policy.document_storage.os.fsync",
                       side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    save_fixture(root)
            self.assertEqual(list((root / "records").iterdir()), [])
            self.assertEqual(list((root / ".staging").iterdir()), [])
            with patch("payer_policy.document_storage.os.rename",
                       side_effect=OSError("publish failure")):
                with self.assertRaises(OSError):
                    save_fixture(root)
            self.assertEqual(list((root / "records").iterdir()), [])
            self.assertEqual(list((root / ".staging").iterdir()), [])

    def test_interrupted_child_before_and_after_publication(self) -> None:
        """Check staging and retry around a child-process interruption."""
        import subprocess

        from payer_policy.document_storage import load_saved_candidate

        program = """
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from payer_policy import document_storage as storage
from payer_policy.https_transport import FetchResult
root, phase = Path(sys.argv[1]), sys.argv[2]
original_rename = os.rename
def interrupted(source, destination):
    if phase == 'before':
        os._exit(17)
    original_rename(source, destination)
    os._exit(18)
with patch.object(storage.os, 'rename', side_effect=interrupted):
    storage.save_pdf_candidate(
        root, FetchResult('https://example.org/final', 200,
                          (('Content-Type', 'application/pdf'),),
                          b'%PDF-synthetic'),
        retrieval_id='1234567890abcdef1234567890abcdef',
        source_id='example-source',
        requested_url='https://example.org/requested',
        retrieved_at=datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
"""
        for phase, expected in (("before", 17), ("after", 18)):
            with self.subTest(phase=phase), TemporaryDirectory() as directory:
                root = Path(directory)
                process = subprocess.run(
                    [sys.executable, "-c", program, str(root), phase],
                    cwd=Path(__file__).resolve().parents[1],
                    capture_output=True, text=True, timeout=20)
                self.assertEqual(process.returncode, expected, process.stderr)
                if phase == "before":
                    self.assertFalse(
                        (root / "records" / RETRIEVAL_ID).exists())
                    self.assertTrue(list((root / ".staging").iterdir()))
                else:
                    self.assertEqual(
                        load_saved_candidate(root, RETRIEVAL_ID).body,
                                     candidate().body)
                self.assertEqual(save_fixture(root).body, candidate().body)

    def test_simultaneous_writers_do_not_replace_a_snapshot(self) -> None:
        """Competing threads use real Windows directory publication."""
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from payer_policy.document_storage import (
            StorageConflictError, load_saved_candidate,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            gate = Barrier(2)

            def compete(body: bytes) -> object:
                """Wait for the other writer before saving distinct bytes."""
                gate.wait(timeout=10)
                try:
                    return save_fixture(root, result=candidate(body))
                except StorageConflictError as error:
                    return error

            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(compete, b"%PDF-one")
                second = executor.submit(compete, b"%PDF-two")
                outcomes = (first.result(timeout=20),
                            second.result(timeout=20))
            self.assertEqual(sum(isinstance(x, StorageConflictError)
                                 for x in outcomes), 1)
            published = load_saved_candidate(root, RETRIEVAL_ID)
            self.assertIn(published.body, (b"%PDF-one", b"%PDF-two"))
            self.assertEqual(list((root / ".staging").iterdir()), [])

    def test_receipt_size_limit_before_io(self) -> None:
        """Reject oversized serialized metadata without publishing anything."""
        from dataclasses import replace

        result = replace(candidate(), headers=candidate().headers +
                         (("ETag", "x" * 65_536),))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "receipt"):
                save_fixture(root, result=result)
            self.assertEqual(list(root.iterdir()), [])

    def test_loader_rejects_corruption_and_ambiguous_receipts(self) -> None:
        """Never accept damaged bytes, metadata, or duplicate JSON keys."""
        from payer_policy.document_storage import (
            StorageIntegrityError, load_saved_candidate,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            stored = save_fixture(root)
            receipt_bytes = stored.receipt_path.read_bytes()
            original_bytes = stored.original_path.read_bytes()
            variants = (
                (stored.original_path, b"%PDF-altered"),
                (stored.original_path, b"%PDF-"),
                (stored.receipt_path, b"{}"),
                (stored.receipt_path, b"{"),
                (stored.receipt_path, receipt_bytes[:-1] + b',"sha256":"a"}'),
                (stored.receipt_path, receipt_bytes.replace(
                    b'"schema_version": 1', b'"schema_version": true')),
                (stored.receipt_path, receipt_bytes.replace(
                    b'"validation_version": 1',
                    b'"validation_version": true')),
                (stored.receipt_path, receipt_bytes.replace(
                    b'"retrieval_id": "1234567890abcdef1234567890abcdef"',
                    b'"retrieval_id": "ffffffffffffffffffffffffffffffff"')),
                (stored.receipt_path, receipt_bytes.replace(
                    b'"retrieved_at": "2025-01-02T03:04:05.000000Z"',
                    b'"retrieved_at": "2025-01-02T03:04:05Z"')),
                (stored.receipt_path, receipt_bytes.replace(
                    b'"validation": "pdf_candidate"',
                    b'"validation": "valid_policy"')),
                (stored.receipt_path, receipt_bytes.replace(
                    b'"byte_count": 14', b'"byte_count": 15')),
                (stored.receipt_path, receipt_bytes.replace(
                    b'"sha256": "', b'"sha256": "a')),
            )
            for path, broken in variants:
                with self.subTest(path=path, broken=broken[:40]):
                    path.write_bytes(broken)
                    with self.assertRaises(StorageIntegrityError):
                        load_saved_candidate(root, RETRIEVAL_ID)
                    is_original = path == stored.original_path
                    replacement = (original_bytes if is_original
                                   else receipt_bytes)
                    path.write_bytes(replacement)

    def test_loader_rejects_overly_nested_json(self) -> None:
        """A damaged receipt cannot escape the integrity error contract."""
        from payer_policy.document_storage import (
            StorageIntegrityError, load_saved_candidate,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            saved = save_fixture(root)
            saved.receipt_path.write_bytes(b"[" * 2000 + b"0" + b"]" * 2000)
            with self.assertRaises(StorageIntegrityError):
                load_saved_candidate(root, RETRIEVAL_ID)

    def test_loader_rejects_oversized_files_and_unsafe_id(self) -> None:
        """A caller cannot use IDs as paths or read beyond size limits."""
        from payer_policy.document_storage import (
            StorageIntegrityError, load_saved_candidate,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            saved = save_fixture(root)
            with self.assertRaises(ValueError):
                load_saved_candidate(root, "../escape")
            with self.assertRaises(StorageIntegrityError):
                load_saved_candidate(root, RETRIEVAL_ID,
                                     max_bytes=len(saved.body) - 1)
            saved.receipt_path.write_bytes(b" " * 65_537)
            with self.assertRaises(StorageIntegrityError):
                load_saved_candidate(root, RETRIEVAL_ID)

    def test_offline_parser_storage_and_verified_load(self) -> None:
        """Connect real HTTP parsing to saving without a public request."""
        from test_https_transport import controlled_reply
        from payer_policy.https_transport import fetch_https
        from payer_policy.document_storage import load_saved_candidate

        response = (b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n"
                    b"Content-Length: 5\r\n\r\n%PDF-")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with controlled_reply(response):
                fetched = fetch_https("https://example.org/requested",
                                      ["example.org"])
            saved = save_fixture(root, result=fetched)
            self.assertEqual(saved.body, b"%PDF-")
            self.assertEqual(saved.receipt["final_url"], fetched.url)
            self.assertEqual(load_saved_candidate(root, RETRIEVAL_ID), saved)

    def test_storage_never_creates_sockets_or_resolves_hosts(self) -> None:
        """Saving supplied bytes is local-only, not a downloader."""
        from unittest.mock import patch
        from payer_policy.document_storage import load_saved_candidate

        with TemporaryDirectory() as directory:
            root = Path(directory)
            with (patch("socket.socket", side_effect=AssertionError("socket")),
                  patch("socket.getaddrinfo",
                        side_effect=AssertionError("DNS"))):
                saved = save_fixture(root)
                self.assertEqual(load_saved_candidate(root, RETRIEVAL_ID),
                                 saved)

    def test_file_link_is_rejected_as_integrity_failure(self) -> None:
        """Never follow a redirected original into another local file."""
        from payer_policy.document_storage import (
            StorageIntegrityError, load_saved_candidate,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            saved = save_fixture(root)
            outside = root / "outside.bin"
            outside.write_bytes(saved.body)
            saved.original_path.unlink()
            try:
                saved.original_path.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"Windows link creation unavailable: {exc}")
            with self.assertRaises(StorageIntegrityError):
                load_saved_candidate(root, RETRIEVAL_ID)
            with self.assertRaises(StorageIntegrityError):
                save_fixture(root)
            self.assertEqual(outside.read_bytes(), saved.body)

    def test_invalid_root_does_not_create_files(self) -> None:
        """Require a pre-existing absolute root selected by the caller."""
        from payer_policy.document_storage import save_pdf_candidate

        with TemporaryDirectory() as directory:
            root = Path(directory)
            for bad in (Path("relative-library"), root / "missing",
                        root / "file"):
                with self.subTest(root=bad):
                    if bad.name == "file":
                        bad.write_bytes(b"not a directory")
                    with self.assertRaises((TypeError, ValueError)):
                        save_pdf_candidate(
                            bad, candidate(), retrieval_id=RETRIEVAL_ID,
                            source_id="example-source",
                            requested_url="https://example.org/requested",
                            retrieved_at=RETRIEVED_AT)
            self.assertFalse((root / "missing").exists())

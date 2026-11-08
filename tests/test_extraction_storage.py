"""Synthetic derived storage without touching source snapshots."""
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from test_document_inspection import RETRIEVAL_ID, save_fixture
from test_text_extraction import text_pdf


@unittest.skipUnless(sys.platform == "win32", "Windows storage contract")
class StorageTests(unittest.TestCase):
    """Publish a separate, verified derived artifact without overwriting."""

    def test_competing_writers_publish_one_intact_winner(self) -> None:
        """Two staged attempts race on one ID without replacing the winner."""
        from concurrent.futures import ThreadPoolExecutor
        from hashlib import sha256
        from threading import Barrier
        from payer_policy import extraction_storage as storage
        from payer_policy.document_storage import StorageConflictError
        from test_extraction_worker import sample_extraction

        rename = storage.os.rename
        barrier = Barrier(2)

        def together(source: Path, destination: Path) -> None:
            """Let both real writers reach the no-overwrite rename at once."""
            barrier.wait(timeout=10)
            rename(source, destination)

        with TemporaryDirectory() as name:
            root = Path(name)
            body = text_pdf()
            save_fixture(root, body)
            before = {p: p.read_bytes() for p in root.rglob("*")
                      if p.is_file()}
            first = replace(sample_extraction(),
                            sha256=sha256(body).hexdigest())
            second = replace(first, pages=(
                replace(first.pages[0], text="other writer"), first.pages[1]))
            with patch.object(storage.os, "rename", together):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(
                        storage.save_text_extraction, root, result,
                        extraction_id="a" * 32) for result in (first, second)]
                    winners = []
                    conflicts = []
                    for index, future in enumerate(futures):
                        try:
                            winners.append((index, future.result(timeout=15)))
                        except StorageConflictError as error:
                            conflicts.append(error)
            self.assertEqual(len(winners), 1)
            self.assertEqual(len(conflicts), 1)
            index, target = winners[0]
            artifact = json.loads(target.read_bytes())
            self.assertEqual(artifact["extraction"],
                             storage.extraction_facts((first, second)[index]))
            self.assertEqual(list((root / "derived").iterdir()),
                             [target.parent])
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_child_exit_before_and_after_publication_preserves_source(
        self,
    ) -> None:
        """Abrupt process exit leaves staging or one complete artifact."""
        import subprocess
        import sys
        from hashlib import sha256
        from payer_policy import extraction_storage as storage
        from payer_policy.document_storage import StorageConflictError
        from test_extraction_worker import sample_extraction

        program = '''
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from payer_policy import extraction_storage as storage
from payer_policy.text_extraction import extraction_from_facts
root, phase = Path(sys.argv[2]), sys.argv[3]
result = extraction_from_facts(json.loads(sys.argv[4]))
rename = os.rename
def interrupted(source: Path, destination: Path) -> None:
    """Exit at publication without running Python cleanup handlers."""
    if phase == "before":
        os._exit(17)
    rename(source, destination)
    os._exit(18)
with patch.object(storage.os, "rename", interrupted):
    storage.save_text_extraction(root, result, extraction_id="a" * 32)
'''
        for phase, code in (("before", 17), ("after", 18)):
            with self.subTest(phase=phase), TemporaryDirectory() as name:
                root = Path(name)
                body = text_pdf()
                save_fixture(root, body)
                before = {p: p.read_bytes() for p in root.rglob("*")
                          if p.is_file()}
                result = replace(sample_extraction(),
                                 sha256=sha256(body).hexdigest())
                process = subprocess.run(
                    [sys.executable, "-I", "-B", "-c", program,
                     str(Path(__file__).absolute().parents[1]), str(root),
                     phase, json.dumps(storage.extraction_facts(result))],
                    capture_output=True, text=True, timeout=20)
                self.assertEqual(process.returncode, code, process.stderr)
                target = root / "derived" / ("a" * 32) / "extraction.json"
                orphans = list((root / "derived").glob(".staging-*"))
                if phase == "before":
                    self.assertFalse(target.exists())
                    self.assertEqual(len(orphans), 1)
                    staged = orphans[0] / "extraction.json"
                    staged_bytes = staged.read_bytes()
                    storage.save_text_extraction(
                        root, result, extraction_id="a" * 32)
                    self.assertEqual(staged.read_bytes(), staged_bytes)
                    self.assertEqual(target.read_bytes(), staged_bytes)
                else:
                    self.assertEqual(orphans, [])
                    raw = target.read_bytes()
                    with self.assertRaises(StorageConflictError):
                        storage.save_text_extraction(
                            root, result, extraction_id="a" * 32)
                    self.assertEqual(target.read_bytes(), raw)
                self.assertEqual(json.loads(target.read_bytes())["extraction"],
                                 storage.extraction_facts(result))
                self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_readback_failure_keeps_published_artifact_and_originals(
        self,
    ) -> None:
        """An injected read error or changed read does not erase evidence."""
        from hashlib import sha256
        from payer_policy import extraction_storage as storage
        from payer_policy.document_storage import (
            StorageConflictError, StorageIntegrityError,
        )
        from test_extraction_worker import sample_extraction

        for failure in (StorageIntegrityError("read failed"), b"{}"):
            with self.subTest(failure=failure), TemporaryDirectory() as name:
                root = Path(name)
                body = text_pdf()
                save_fixture(root, body)
                before = {p: p.read_bytes() for p in root.rglob("*")
                          if p.is_file()}
                result = replace(sample_extraction(),
                                 sha256=sha256(body).hexdigest())
                target = root / "derived" / ("a" * 32) / "extraction.json"
                with patch.object(storage, "_read_bounded") as read:
                    if isinstance(failure, Exception):
                        read.side_effect = failure
                    else:
                        read.return_value = failure
                    with self.assertRaises(StorageIntegrityError):
                        storage.save_text_extraction(
                            root, result, extraction_id="a" * 32)
                read.assert_called_once_with(
                    target, result.limits.max_result_bytes)
                raw = target.read_bytes()
                self.assertEqual(json.loads(raw)["extraction"],
                                 storage.extraction_facts(result))
                with self.assertRaises(StorageConflictError):
                    storage.save_text_extraction(
                        root, result, extraction_id="a" * 32)
                self.assertEqual(raw, target.read_bytes())
                self.assertEqual(list((root / "derived").iterdir()),
                                 [target.parent])
                self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_junctions_do_not_redirect_derived_writes(self) -> None:
        """Reject real directory links without touching their target files."""
        import _winapi
        from hashlib import sha256
        from payer_policy import extraction_storage as storage
        from payer_policy.document_storage import StorageConflictError
        from test_extraction_worker import sample_extraction

        for location in ("root", "derived", "destination", "records"):
            with self.subTest(location=location), TemporaryDirectory() as name:
                folder = Path(name)
                root = folder / "saved"
                root.mkdir()
                body = text_pdf()
                save_fixture(root, body)
                result = replace(sample_extraction(),
                                 sha256=sha256(body).hexdigest())
                target = folder / "target"
                target.mkdir()
                sentinel = target / "sentinel"
                sentinel.write_bytes(b"not an extraction")
                before = {p: p.read_bytes() for p in root.rglob("*")
                          if p.is_file()}
                supplied = root
                if location == "root":
                    link = folder / "alias"
                    supplied = link
                    target = root
                elif location == "derived":
                    link = root / "derived"
                elif location == "records":
                    link = root / "records"
                    target = folder / "held-records"
                    link.rename(target)
                    before = {p: p.read_bytes() for p in target.rglob("*")
                              if p.is_file()}
                else:
                    (root / "derived").mkdir()
                    link = root / "derived" / ("a" * 32)
                _winapi.CreateJunction(str(target), str(link))
                try:
                    error = (StorageConflictError if location == "destination"
                             else ValueError)
                    with patch.object(storage, "_write_synced") as write:
                        with self.assertRaises(error):
                            storage.save_text_extraction(
                                supplied, result, extraction_id="a" * 32)
                        write.assert_not_called()
                    self.assertEqual(sentinel.read_bytes(),
                                     b"not an extraction")
                    self.assertEqual(before,
                                     {p: p.read_bytes() for p in before})
                    self.assertFalse(list(root.glob("derived/.staging-*")))
                finally:
                    link.rmdir()

    def test_artifact_budget_counts_escaped_metadata_before_writing(
        self,
    ) -> None:
        """Accept the exact JSON cap; reject one byte less before writing."""
        from hashlib import sha256
        from payer_policy import extraction_storage as storage
        from payer_policy import _extraction_protocol as protocol
        from test_extraction_worker import sample_extraction

        with TemporaryDirectory() as name:
            root = Path(name)
            body = text_pdf()
            save_fixture(root, body)
            before = {p: p.read_bytes() for p in root.rglob("*")
                      if p.is_file()}
            result = replace(sample_extraction(),
                             sha256=sha256(body).hexdigest())
            for _ in range(4):
                artifact = {"schema_version": 1, "extraction_id": "a" * 32,
                            "extraction": storage.extraction_facts(result)}
                raw = protocol.encode(artifact, protocol.RESULT_BYTES)
                result = replace(result, limits=replace(
                    result.limits, max_result_bytes=len(raw)))
            artifact["extraction"] = storage.extraction_facts(result)
            raw = protocol.encode(artifact, protocol.RESULT_BYTES)
            self.assertEqual(len(raw), result.limits.max_result_bytes)
            self.assertIn(b"\\u00e9", raw)
            with patch.object(storage, "_read_bounded",
                              wraps=storage._read_bounded) as read:
                target = storage.save_text_extraction(
                    root, result, extraction_id="a" * 32)
            read.assert_called_once_with(target, len(raw))
            self.assertEqual(target.read_bytes(), raw)
            over = replace(result, limits=replace(
                result.limits, max_result_bytes=len(raw) - 1))
            with patch.object(storage, "_write_synced") as write:
                with self.assertRaises(protocol.ProtocolError):
                    storage.save_text_extraction(
                        root, over, extraction_id="b" * 32)
                write.assert_not_called()
            self.assertEqual(list((root / "derived").iterdir()),
                             [target.parent])
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_changed_original_is_rehashed_before_derivative_publication(
        self,
    ) -> None:
        """An unchanged receipt cannot hide a same-length original edit."""
        from hashlib import sha256
        from payer_policy import extraction_storage as storage
        from payer_policy.document_storage import StorageIntegrityError
        from test_extraction_worker import sample_extraction

        with TemporaryDirectory() as name:
            root = Path(name)
            body = text_pdf()
            save_fixture(root, body)
            result = replace(sample_extraction(),
                             sha256=sha256(body).hexdigest())
            original = root / "records" / RETRIEVAL_ID / "original.bin"
            changed = body.replace(b"First page", b"Other page")
            self.assertNotEqual(changed, body)
            self.assertEqual(len(changed), len(body))
            original.write_bytes(changed)
            before = {p: p.read_bytes() for p in root.rglob("*")
                      if p.is_file()}
            with self.assertRaises(StorageIntegrityError):
                storage.save_text_extraction(
                    root, result, extraction_id="a" * 32)
            self.assertFalse((root / "derived").exists())
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_invalid_artifacts_fail_before_any_storage_access(self) -> None:
        """Reject unsafe IDs and inconsistent facts before opening files."""
        from payer_policy import extraction_storage as storage
        from test_extraction_worker import sample_extraction

        result = sample_extraction()
        with TemporaryDirectory() as name:
            root = Path(name)
            with patch.object(storage, "_check_root") as check:
                for identifier in ("../escape", "A" * 32, "a" * 31,
                                   "a" * 33, True, None):
                    with self.subTest(identifier=identifier):
                        with self.assertRaises(ValueError):
                            storage.save_text_extraction(
                                root, result, extraction_id=identifier)
                for invalid in (
                    replace(result, retrieval_id="../escape"),
                    replace(result, schema_version=True),
                    replace(result, parser_version="other"),
                    replace(result, extracted_at=result.extracted_at.replace(
                        tzinfo=None)),
                    replace(result, pages=result.pages[:1]),
                    replace(result, limits=replace(
                        result.limits, max_result_bytes=True)),
                ):
                    with self.subTest(invalid=invalid):
                        with self.assertRaises(ValueError):
                            storage.save_text_extraction(
                                root, invalid, extraction_id="a" * 32)
                check.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])

    def test_wrong_source_rejected_before_creating_derived_files(self) -> None:
        """A matching ID in the wrong root must not borrow another hash."""
        from payer_policy.extraction_storage import save_text_extraction
        from payer_policy.document_storage import StorageIntegrityError
        from test_extraction_worker import sample_extraction

        with TemporaryDirectory() as name:
            root = Path(name)
            save_fixture(root, text_pdf())
            with self.assertRaises(StorageIntegrityError):
                save_text_extraction(root, sample_extraction(),
                                     extraction_id="a" * 32)
            self.assertFalse((root / "derived").exists())

    def test_roundtrip_preserves_originals_and_refuses_repeat_id(self) -> None:
        """Save a complete worker result under a separate derived ID."""
        from payer_policy.extraction_worker import (
            extract_saved_pdf_pages_in_worker,
        )
        from payer_policy.extraction_storage import save_text_extraction
        from payer_policy.document_storage import StorageConflictError
        from payer_policy.text_extraction import extraction_from_facts

        with TemporaryDirectory() as name:
            root = Path(name)
            save_fixture(root, text_pdf())
            original = {p: p.read_bytes() for p in root.rglob("*")
                        if p.is_file()}
            result = extract_saved_pdf_pages_in_worker(
                root, RETRIEVAL_ID, pages=(1, 4))
            target = save_text_extraction(root, result, extraction_id="a" * 32)
            self.assertEqual(target,
                             root / "derived" / ("a" * 32) / "extraction.json")
            raw = target.read_bytes()
            artifact = json.loads(raw)
            self.assertEqual(artifact["extraction_id"], "a" * 32)
            self.assertEqual(artifact["schema_version"], 1)
            self.assertEqual(extraction_from_facts(artifact["extraction"]),
                             result)
            with self.assertRaises(StorageConflictError):
                save_text_extraction(root, result, extraction_id="a" * 32)
            self.assertEqual(target.read_bytes(), raw)
            self.assertEqual(original, {p: p.read_bytes() for p in original})

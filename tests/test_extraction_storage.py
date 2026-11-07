"""Synthetic derived storage without touching source snapshots."""
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from test_document_inspection import RETRIEVAL_ID, save_fixture
from test_text_extraction import text_pdf


class StorageTests(unittest.TestCase):
    """Publish a separate, verified derived artifact without overwriting."""

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

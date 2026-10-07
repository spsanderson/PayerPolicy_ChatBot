"""Offline caller and real-process tests for the contained PDF API."""
import importlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Windows storage contract")
class WorkerExecutionTests(unittest.TestCase):
    """Inspect real saved synthetic PDFs in the production worker."""

    def test_saved_pdf_is_parsed_only_in_child(self) -> None:
        """Match original facts and leave original/receipt bytes unchanged."""
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        from payer_policy.document_inspection import inspect_saved_pdf
        from payer_policy.inspection_worker import inspect_saved_pdf_in_worker

        with TemporaryDirectory(prefix="worker unicode é ") as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(2))
            original = root / "records" / RETRIEVAL_ID / "original.bin"
            receipt = original.with_name("receipt.json")
            before = original.read_bytes(), receipt.read_bytes()
            expected = inspect_saved_pdf(root, RETRIEVAL_ID)
            with (patch("payer_policy.document_inspection.PdfReader",
                        side_effect=AssertionError("parent parsed PDF")),
                  patch("payer_policy.document_inspection.load_saved_candidate",
                        side_effect=AssertionError("parent read snapshot"))):
                result = inspect_saved_pdf_in_worker(root, RETRIEVAL_ID)
            self.assertEqual(result, expected)
            self.assertEqual((original.read_bytes(), receipt.read_bytes()),
                             before)


class WorkerValidationTests(unittest.TestCase):
    """Reject caller mistakes before making files or native objects."""

    def test_invalid_inputs_have_no_launch_side_effects(self) -> None:
        """Validate exact budgets, identifiers and roots before setup."""
        try:
            worker = importlib.import_module("payer_policy.inspection_worker")
        except ModuleNotFoundError:
            self.fail("contained inspection API is missing")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [
                ({"root": str(root)}, TypeError),
                ({"root": Path("relative")}, ValueError),
                ({"root": root / "missing"}, ValueError),
                ({"retrieval_id": 123}, TypeError),
                ({"retrieval_id": "A" * 32}, ValueError),
                ({"retrieval_id": "a" * 31}, ValueError),
                ({"max_bytes": True}, ValueError),
                ({"max_bytes": 10_000_001}, ValueError),
                ({"max_bytes": 0}, ValueError),
                ({"max_bytes": 1.0}, ValueError),
                ({"limits": object()}, TypeError),
            ]
            for value in (True, 0, -1, 61, float("nan"), float("inf")):
                cases.append(({"limits": worker.InspectionLimits(
                    timeout_seconds=value)}, ValueError))
            for value in (True, 0, 16_777_215, 268_435_457, 16_777_216.0):
                cases.append(({"limits": worker.InspectionLimits(
                    memory_bytes=value)}, ValueError))
            with (patch("tempfile.mkdtemp") as temporary,
                  patch("ctypes.WinDLL", create=True) as native):
                for changes, error in cases:
                    with self.subTest(changes=changes):
                        arguments = {"root": root, "retrieval_id": "a" * 32}
                        arguments.update(changes)
                        with self.assertRaises(error):
                            worker.inspect_saved_pdf_in_worker(**arguments)
                temporary.assert_not_called()
                native.assert_not_called()


if __name__ == "__main__":
    unittest.main()

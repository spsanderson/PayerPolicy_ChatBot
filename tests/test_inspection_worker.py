"""Offline caller and real-process tests for the contained PDF API."""
import importlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


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
            with patch("tempfile.mkdtemp") as temporary:
                for changes, error in cases:
                    with self.subTest(changes=changes):
                        arguments = {"root": root, "retrieval_id": "a" * 32}
                        arguments.update(changes)
                        with self.assertRaises(error):
                            worker.inspect_saved_pdf_in_worker(**arguments)
                temporary.assert_not_called()
            self.assertNotIn("payer_policy._windows_job", sys.modules)


if __name__ == "__main__":
    unittest.main()

"""Inspect a saved PDF in a resource-limited Windows child, not a sandbox.

The existing inspector and storage checks remain unchanged:
../payer_policy/document_inspection.py and document_storage.py.
Root validation checks directory entries, never stored document contents.
"""
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from payer_policy.document_inspection import PdfInspection
from payer_policy.document_storage import _check_root


class WorkerInspectionError(RuntimeError):
    """Expose a stable failure category, not a remote exception object."""

    def __init__(self, code: str) -> None:
        """Keep the public category as both message and code."""
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class InspectionLimits:
    """Set worker wait and committed-memory budgets, not permissions."""

    timeout_seconds: float = 30
    memory_bytes: int = 256 * 1024 * 1024


def _validate_inputs(
    root: Path, retrieval_id: str, max_bytes: int,
    limits: InspectionLimits,
) -> None:
    """Reject caller mistakes before temporary files or native setup."""
    if not isinstance(root, Path):
        raise TypeError("root must be a Path")
    if not root.is_absolute() or str(root).startswith("\\\\"):
        raise ValueError("root must be an absolute local path")
    if type(retrieval_id) is not str:
        raise TypeError("retrieval_id must be a string")
    if re.fullmatch(r"[0-9a-f]{32}", retrieval_id) is None:
        raise ValueError("invalid retrieval_id")
    if type(max_bytes) is not int or not 0 < max_bytes <= 10_000_000:
        raise ValueError("invalid max_bytes")
    if type(limits) is not InspectionLimits:
        raise TypeError("limits must be InspectionLimits")
    timeout = limits.timeout_seconds
    if (type(timeout) not in (int, float) or not 0 < timeout <= 60
            or not math.isfinite(timeout)):
        raise ValueError("invalid timeout_seconds")
    memory = limits.memory_bytes
    if type(memory) is not int or not 16_777_216 <= memory <= 268_435_456:
        raise ValueError("invalid memory_bytes")
    if sys.platform != "win32":
        raise WorkerInspectionError("unsupported_runtime")
    _check_root(root)


def inspect_saved_pdf_in_worker(
    root: Path, retrieval_id: str, *, max_bytes: int = 10_000_000,
    limits: InspectionLimits | None = None,
) -> PdfInspection:
    """Return child-inspected facts; reject invalid callers before launch.

    Local type/value failures remain ordinary exceptions. Worker failures
    use WorkerInspectionError codes, without copying remote tracebacks.
    """
    selected = InspectionLimits() if limits is None else limits
    _validate_inputs(root, retrieval_id, max_bytes, selected)
    raise WorkerInspectionError("unsupported_runtime")

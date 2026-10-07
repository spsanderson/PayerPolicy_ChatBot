"""Inspect a saved PDF in a resource-limited Windows child, not a sandbox.

The existing inspector and storage checks remain unchanged:
../payer_policy/document_inspection.py and document_storage.py.
Root validation checks directory entries, never stored document contents.
"""
import math
import re
import secrets
import struct
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pypdf

from payer_policy import _inspection_protocol as protocol

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


def _runtime() -> tuple[Path, Path]:
    """Select only this standard CPython base and approved package folder.

    Windows venv executables can redirect to another process; launch the
    base executable directly. -I ignores PYTHONPATH/user site; -S avoids
    site initialization and .pth execution:
    https://docs.python.org/3.11/using/cmdline.html
    https://docs.python.org/3.11/library/sys.html#sys.base_prefix
    """
    if (sys.platform != "win32" or sys.implementation.name != "cpython"
            or sys.version_info < (3, 11) or struct.calcsize("P") != 8
            or getattr(sys, "frozen", False)):
        raise WorkerInspectionError("unsupported_runtime")
    # Canonicalize the already trusted interpreter alias, never caller root.
    base = Path(sys.base_prefix).resolve(strict=True)
    interpreter = base / "python.exe"
    packages = Path(sysconfig.get_path("purelib"))
    app = Path(__file__).absolute().parent.parent
    expected_executable = (Path(sys.prefix) / "Scripts" / "python.exe"
                           if sys.prefix != sys.base_prefix else interpreter)
    if (Path(sys.executable).resolve() != expected_executable.resolve()
            or Path(sys._base_executable).resolve() != interpreter
            or packages != Path(sys.prefix) / "Lib" / "site-packages"
            or Path(pypdf.__file__).parent != packages / "pypdf"
            or pypdf.__version__ != "6.19.0"
            or not (app / "requirements.txt").is_file()
            or not interpreter.is_file()
            or not (base / "Lib" / "encodings").is_dir()):
        raise WorkerInspectionError("unsupported_runtime")
    try:
        for directory in (base, packages, app):
            _check_root(directory)
    except (OSError, ValueError) as exc:
        raise WorkerInspectionError("unsupported_runtime") from exc
    return interpreter, packages


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
    interpreter, packages = _runtime()
    from payer_policy._windows_job import Job

    request_id = secrets.token_hex(16)
    request = {
        "schema_version": 1, "operation": "inspect",
        "request_id": request_id, "retrieval_id": retrieval_id,
        "root": str(root), "max_bytes": max_bytes,
        "runtime": {"base_prefix": str(interpreter.parent),
                    "packages": str(packages)},
    }
    with TemporaryDirectory(prefix="pdf-inspection-") as directory:
        request_path = Path(directory) / "request.json"
        output = Path(directory) / "result.json"
        protocol.publish(request_path, request)
        with Job(selected.memory_bytes) as job:
            job.launch(interpreter, Path(__file__).with_name(
                "_inspection_child.py").absolute(),
                [str(request_path), str(output)])
            if job.wait(selected.timeout_seconds) != 0:
                raise WorkerInspectionError("crash")
        result = protocol.read_result(output, request_id, retrieval_id)
        facts = result["facts"]
        return PdfInspection(retrieval_id, facts["sha256"],
                             facts["page_count"], facts["is_encrypted"])

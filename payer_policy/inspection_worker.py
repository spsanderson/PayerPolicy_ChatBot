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
from collections.abc import Iterator
from contextlib import contextmanager
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
        """Store a known category; raise ValueError for unknown codes."""
        allowed = protocol.CHILD_ERRORS | {
            "unsupported_runtime", "setup_error", "timeout", "crash",
            "invalid_result", "ipc_error", "cleanup_error",
        }
        if type(code) is not str or code not in allowed:
            raise ValueError("unknown worker error code")
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
    try:
        _check_root(root)
    except OSError as exc:
        raise WorkerInspectionError("input_error") from exc


def _runtime() -> tuple[Path, Path]:
    """Return approved paths; classify inaccessible layouts as unsupported."""
    try:
        return _runtime_paths()
    except (OSError, ValueError) as exc:
        raise WorkerInspectionError("unsupported_runtime") from exc


def _runtime_paths() -> tuple[Path, Path]:
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
    for directory in (base, packages, app):
        _check_root(directory)
    return interpreter, packages


@contextmanager
def _temporary_directory() -> Iterator[Path]:
    """Yield private IPC storage; do not accept unconfirmed removal.

    TemporaryDirectory.cleanup removes owned files before success:
    https://docs.python.org/3.11/library/tempfile.html
    """
    try:
        temporary = TemporaryDirectory(prefix="pdf-inspection-")
    except OSError as exc:
        raise WorkerInspectionError("setup_error") from exc
    primary: BaseException | None = None
    try:
        yield Path(temporary.name)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            temporary.cleanup()
        except OSError as exc:
            if primary is not None and (
                    not isinstance(primary, Exception)
                    or isinstance(primary, MemoryError)):
                primary.add_note("temporary cleanup failed: " + repr(exc))
            else:
                failure = WorkerInspectionError("cleanup_error")
                failure.add_note(repr(exc))
                raise failure from (primary or exc)


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
    from payer_policy._windows_job import CleanupError, Job

    request_id = secrets.token_hex(16)
    request = {
        "schema_version": 1, "operation": "inspect",
        "request_id": request_id, "retrieval_id": retrieval_id,
        "root": str(root), "max_bytes": max_bytes,
        "runtime": {"base_prefix": str(interpreter.parent),
                    "packages": str(packages)},
    }
    with _temporary_directory() as directory:
        request_path = Path(directory) / "request.json"
        output = Path(directory) / "result.json"
        try:
            protocol.publish(request_path, request)
        except (OSError, protocol.ProtocolError) as exc:
            raise WorkerInspectionError("ipc_error") from exc
        try:
            with Job(selected.memory_bytes) as job:
                job.launch(interpreter, Path(__file__).with_name(
                    "_inspection_child.py").absolute(),
                    [str(request_path), str(output)])
                try:
                    exit_code = job.wait(selected.timeout_seconds)
                except TimeoutError as exc:
                    raise WorkerInspectionError("timeout") from exc
                except OSError as exc:
                    raise WorkerInspectionError("ipc_error") from exc
                if exit_code != 0:
                    raise WorkerInspectionError("crash")
        except CleanupError as exc:
            raise WorkerInspectionError("cleanup_error") from exc
        except OSError as exc:
            raise WorkerInspectionError("setup_error") from exc
        try:
            result = protocol.read_result(output, request_id, retrieval_id)
        except protocol.ProtocolError as exc:
            raise WorkerInspectionError("invalid_result") from exc
        except OSError as exc:
            raise WorkerInspectionError("ipc_error") from exc
        if result["status"] != "ok":
            raise WorkerInspectionError(result["status"])
        facts = result["facts"]
        return PdfInspection(retrieval_id, facts["sha256"],
                             facts["page_count"], facts["is_encrypted"])

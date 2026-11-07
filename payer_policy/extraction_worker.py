"""Windows selected-page extraction in a bounded child, not a sandbox.

Reuse native containment and trusted runtime checks unchanged:
../payer_policy/_windows_job.py and inspection_worker.py.
Only the child opens stored originals or invokes the PDF parser.
"""
import secrets
import sys
from dataclasses import asdict
from pathlib import Path

from payer_policy import _extraction_protocol as protocol
from payer_policy.document_storage import _check_root
from payer_policy.inspection_worker import (
    WorkerInspectionError, _runtime, _temporary_directory,
)
from payer_policy.text_extraction import (
    ExtractionError, ExtractionLimits, PdfTextExtraction,
    validate_id, validate_limits, validate_pages,
)


def extract_saved_pdf_pages_in_worker(
    root: Path, retrieval_id: str, *, pages: tuple[int, ...],
    limits: ExtractionLimits | None = None,
) -> PdfTextExtraction:
    """Return a complete selected batch only after confirmed child cleanup.

    Caller type/value errors occur before launch. ExtractionError.code
    describes worker failures. timeout_seconds bounds the child wait, not
    the whole pipeline; memory limits do not change child permissions.
    """
    selected = ExtractionLimits() if limits is None else limits
    validate_limits(selected)
    validate_pages(pages)
    validate_id(retrieval_id)
    if not isinstance(root, Path):
        raise TypeError("root must be a Path")
    if sys.platform != "win32":
        raise ExtractionError("unsupported_runtime")
    _check_root(root)
    try:
        interpreter, packages = _runtime()
        request = {
            "schema_version": 1, "operation": "extract_text",
            "request_id": secrets.token_hex(16),
            "retrieval_id": retrieval_id, "root": str(root),
            "requested_pages": list(pages), "limits": asdict(selected),
            "runtime": {"base_prefix": str(interpreter.parent),
                        "packages": str(packages)},
        }
        with _temporary_directory() as directory:
            result = _run(directory, interpreter, request, selected)
        return result
    except WorkerInspectionError as exc:
        raise ExtractionError(exc.code) from exc


def _run(
    directory: Path, interpreter: Path, request: dict,
    limits: ExtractionLimits,
) -> PdfTextExtraction:
    """Launch the fixed child; reject crashes, invalid replies or cleanup."""
    from payer_policy._windows_job import CleanupError, Job

    request_path, output = directory / "request.json", directory / "result.json"
    try:
        protocol.publish(request_path, request, protocol.REQUEST_BYTES)
    except (OSError, protocol.ProtocolError) as exc:
        raise ExtractionError("ipc_error") from exc
    try:
        with Job(limits.memory_bytes) as job:
            job.launch(interpreter, Path(__file__).with_name(
                "_extraction_child.py").absolute(),
                [str(request_path), str(output)])
            try:
                exit_code = job.wait(limits.timeout_seconds)
            except TimeoutError as exc:
                raise ExtractionError("timeout") from exc
            except OSError as exc:
                raise ExtractionError("ipc_error") from exc
            if exit_code != 0:
                raise ExtractionError("crash")
    except CleanupError as exc:
        raise ExtractionError("cleanup_error") from exc
    except OSError as exc:
        raise ExtractionError("setup_error") from exc
    try:
        return protocol.read_result(output, request)
    except protocol.ProtocolError as exc:
        raise ExtractionError("invalid_result") from exc
    except OSError as exc:
        raise ExtractionError("ipc_error") from exc

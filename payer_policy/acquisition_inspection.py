"""Connect reviewed acquisition to saved-PDF inspection without extraction."""
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from payer_policy import acquisition, inspection_worker
from payer_policy.acquisition import (
    AcquisitionApproval, AcquisitionLimits, AcquisitionResult,
)
from payer_policy.document_inspection import PdfInspection
from payer_policy.inspection_worker import (
    InspectionLimits, WorkerInspectionError,
)


class PipelineInspectionError(RuntimeError):
    """Keep a saved acquisition available when later inspection fails."""

    def __init__(
        self, code: str, acquisition: AcquisitionResult,
        cause: Exception | None = None,
    ) -> None:
        """Store the failure code, saved record and optional original cause."""
        self.code = code
        self.acquisition = acquisition
        self.cause = cause
        super().__init__(f"{code} for {acquisition.retrieval_id}")


@dataclass(frozen=True)
class AcquiredPdfInspection:
    """Keep the existing saved-record and inspection values, not PDF bytes."""

    acquisition: AcquisitionResult
    inspection: PdfInspection


def acquire_and_inspect_pdf(
    registry: Mapping[str, Mapping[str, object]], source_id: str, root: Path,
    *, retrieval_id: str, approval: AcquisitionApproval | None,
    acquisition_limits: AcquisitionLimits, inspection_limits: InspectionLimits,
) -> AcquiredPdfInspection:
    """Return saved-record and PDF facts; propagate acquisition failures.

    [acquire_pdf_candidate](acquisition.py) enforces reviewed access and
    preserves exact bytes. [inspect_saved_pdf_in_worker](inspection_worker.py)
    parses only the saved record in a resource-limited Windows process.

    Private same-package helpers are intentional preflight dependencies:
    [_checked_limits](acquisition.py) snapshots acquisition budgets;
    [_validate_inputs and _runtime](inspection_worker.py) reject invalid
    worker inputs and unsupported layouts before acquisition. Their errors
    propagate unchanged, as do acquisition failures and unexpected bugs.
    Later WorkerInspectionError becomes PipelineInspectionError with the
    saved record and chained cause. An ID/hash mismatch uses that same
    wrapper with code identity_mismatch and no cause. Native setup or a
    changed runtime may still fail after saving; preflight cannot prevent it.

    This is not a sandbox, whole-pipeline deadline, or proof of safe,
    authentic, applicable, or readable content. Encrypted results may have
    no page count. There is no retry or rollback of saved evidence.
    """
    acquisition_limits = acquisition._checked_limits(acquisition_limits)
    if type(inspection_limits) is not InspectionLimits:
        raise TypeError("inspection_limits must be InspectionLimits")
    inspection_limits = InspectionLimits(
        inspection_limits.timeout_seconds, inspection_limits.memory_bytes)
    inspection_worker._validate_inputs(
        root, retrieval_id, acquisition_limits.max_bytes, inspection_limits)
    inspection_worker._runtime()
    saved = acquisition.acquire_pdf_candidate(
        registry, source_id, root, retrieval_id=retrieval_id,
        approval=approval, limits=acquisition_limits)
    try:
        inspected = inspection_worker.inspect_saved_pdf_in_worker(
            root, saved.retrieval_id, max_bytes=acquisition_limits.max_bytes,
            limits=inspection_limits)
    except WorkerInspectionError as exc:
        raise PipelineInspectionError(exc.code, saved, exc) from exc
    if (inspected.retrieval_id != saved.retrieval_id
            or inspected.sha256 != saved.sha256):
        raise PipelineInspectionError("identity_mismatch", saved)
    return AcquiredPdfInspection(saved, inspected)

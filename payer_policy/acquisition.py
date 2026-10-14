"""Acquire one explicitly reviewed candidate, never parse a PDF.

Project boundaries: [fetch_https](https_transport.py) checks DNS and TLS;
[validate_pdf_candidate](document_validation.py) checks only the outer shape;
[save_pdf_candidate](document_storage.py) preserves and verifies exact bytes.
A candidate is not proof of authenticity, applicability, or safe PDF content.
"""
import stat
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from payer_policy import document_storage as storage
from payer_policy.document_storage import save_pdf_candidate
from payer_policy.document_validation import validate_pdf_candidate
from payer_policy.https_transport import fetch_https
from payer_policy.source_registry import validate_source_definition
from payer_policy.network_safety import (
    NetworkSafetyError, _validate_allowlist, validate_destination_url,
)


class AcquisitionError(Exception):
    """Report an expected boundary failure without concealing its cause."""

    def __init__(
        self, stage: str, retrieval_id: str, cause: Exception,
    ) -> None:
        """Keep the failing stage, exact retrieval ID, and original error."""
        self.stage = stage
        self.retrieval_id = retrieval_id
        self.cause = cause
        super().__init__(f"{stage} failed for {retrieval_id}: {cause}")


@dataclass(frozen=True)
class AcquisitionApproval:
    """Carry a trusted reviewed decision, not legal proof or registry trust.

    The existing local note is a reference, not parsed authorization. The
    caller is responsible for its meaning and the reviewed host scope.
    """

    source_id: str
    requested_url: str
    allowed_hosts: Collection[str]
    review_note: Path

    def __post_init__(self) -> None:
        """Freeze reviewed hosts; reject malformed collections, not repair.

        [_validate_allowlist](network_safety.py) rejects strings, mappings,
        generators, and malformed hosts before tuple conversion hides them.
        """
        _validate_allowlist(self.allowed_hosts)
        object.__setattr__(self, "allowed_hosts", tuple(self.allowed_hosts))


@dataclass(frozen=True)
class AcquisitionLimits:
    """Bound a single acquisition's bytes, socket wait, and redirects."""

    max_bytes: int = 10_000_000
    timeout: int | float = 10
    max_redirects: int = 3


@dataclass(frozen=True)
class AcquisitionResult:
    """Return verified paths and identifiers without retaining bytes."""

    source_id: str
    retrieval_id: str
    final_url: str
    sha256: str
    original_path: Path
    receipt_path: Path


def _checked_limits(limits: AcquisitionLimits) -> AcquisitionLimits:
    """Return a checked snapshot; reject invalid types or excess budgets."""
    if type(limits) is not AcquisitionLimits:
        raise TypeError("limits must be AcquisitionLimits")
    max_bytes, timeout, max_redirects = (
        limits.max_bytes, limits.timeout, limits.max_redirects)
    if type(max_bytes) is not int or not 0 < max_bytes <= 10_000_000:
        raise ValueError("max_bytes must be an integer in 1..10000000")
    if type(timeout) not in (int, float) or not 0 < timeout <= 10:
        raise ValueError("timeout must be finite and in (0, 10]")
    if type(max_redirects) is not int or not 0 <= max_redirects <= 3:
        raise ValueError("max_redirects must be an integer in 0..3")
    return AcquisitionLimits(max_bytes, timeout, max_redirects)


def _selected_url(
    registry: Mapping[str, Mapping[str, object]], source_id: str,
) -> str:
    """Return one source's URL; reject invalid selected-source configuration.

    [validate_source_definition](source_registry.py) checks structure only;
    other registry entries and applicability claims do not authorize access.
    """
    storage._check_id(source_id, storage._SOURCE_PATTERN, "source_id")
    if not isinstance(registry, Mapping):
        raise TypeError("registry must be a source-ID mapping")
    if source_id not in registry:
        raise ValueError("unknown source_id")
    selected = registry[source_id]
    if not isinstance(selected, Mapping):
        raise TypeError("selected source must be a mapping")
    selected = dict(selected)
    errors = validate_source_definition(selected)
    if errors:
        raise ValueError("; ".join(errors))
    if selected["source_id"] != source_id:
        raise ValueError("registry key does not match selected source_id")
    requested_url = selected["url"]
    storage._check_url(requested_url)
    return requested_url


def _approved_hosts(
    approval: AcquisitionApproval | None, source_id: str,
    requested_url: str, retrieval_id: str,
) -> tuple[str, ...]:
    """Return checked host scope after exact binding and local note checks.

    [validate_destination_url](network_safety.py) checks URL/host syntax
    offline, not DNS. Bad configuration raises TypeError/ValueError;
    missing/mismatched approval or note I/O raises AcquisitionError.
    The note is not opened; its trusted semantic meaning is caller-owned.
    """
    if approval is not None and type(approval) is not AcquisitionApproval:
        raise TypeError("approval must be AcquisitionApproval or None")
    if (approval is None or approval.source_id != source_id or
            approval.requested_url != requested_url):
        cause = ValueError("approval must bind the exact source ID and URL")
        raise AcquisitionError("approval", retrieval_id, cause) from cause
    allowed_hosts = tuple(approval.allowed_hosts)
    validate_destination_url(requested_url, allowed_hosts)
    note = approval.review_note
    if not isinstance(note, Path):
        raise TypeError("review_note must be a Path")
    try:
        storage._check_root(note.parent)
        try:
            storage._check_path(note)
        except FileNotFoundError as exc:
            raise ValueError("review_note must exist") from exc
        if not stat.S_ISREG(note.lstat().st_mode):
            raise ValueError("review_note must be a regular local file")
    except OSError as exc:
        raise AcquisitionError("approval", retrieval_id, exc) from exc
    return allowed_hosts


def _preflight_storage(root: Path, retrieval_id: str) -> None:
    """Reject unsafe local paths and any existing ID without creating files.

    [_check_root/_check_path](document_storage.py) reject reparse points.
    Bad paths raise TypeError/ValueError; OS errors and existing IDs become
    storage AcquisitionError. These checks cannot eliminate local races.
    """
    try:
        storage._check_root(root)
        for directory in (root / "records", root / ".staging"):
            try:
                storage._check_path(directory)
            except FileNotFoundError:
                continue
            if not directory.is_dir():
                raise ValueError("storage component is not a directory")
        try:
            (root / "records" / retrieval_id).lstat()
        except FileNotFoundError:
            pass
        else:
            raise storage.StorageConflictError("retrieval_id already exists")
    except (OSError, storage.StorageConflictError) as exc:
        raise AcquisitionError("storage", retrieval_id, exc) from exc


def acquire_pdf_candidate(
    registry: Mapping[str, Mapping[str, object]], source_id: str, root: Path,
    *, retrieval_id: str, approval: AcquisitionApproval | None,
    limits: AcquisitionLimits,
) -> AcquisitionResult:
    """Fetch one approved candidate and return verified paths/fingerprint.

    All caller configuration is checked before network or storage writes.
    Known failures carry approval/fetch/validation/storage stage and cause.
    No retries, parsing, worker invocation, or rollback deletion occur: a
    post-publication failure may leave a record. Unexpected errors propagate.
    An untyped ValueError inside the writer (including a raced path change)
    propagates rather than hiding a possible bug.

    The UTC timestamp records fetch completion, not a policy effective date.
    datetime.now provides an aware clock value:
    https://docs.python.org/3/library/datetime.html#datetime.datetime.now.
    """
    limits = _checked_limits(limits)
    storage._check_id(retrieval_id, storage._ID_PATTERN, "retrieval_id")
    requested_url = _selected_url(registry, source_id)
    allowed_hosts = _approved_hosts(
        approval, source_id, requested_url, retrieval_id)
    _preflight_storage(root, retrieval_id)
    try:
        response = fetch_https(
            requested_url, allowed_hosts, max_bytes=limits.max_bytes,
            timeout=limits.timeout, max_redirects=limits.max_redirects)
    except (OSError, NetworkSafetyError) as exc:
        raise AcquisitionError("fetch", retrieval_id, exc) from exc
    retrieved_at = datetime.now(timezone.utc)
    try:
        validate_pdf_candidate(response)
        if len(response.body) > limits.max_bytes:
            raise ValueError("original exceeds max_bytes")
        validate_destination_url(response.url, allowed_hosts)
        storage._check_url(response.url)
    except (TypeError, ValueError) as exc:
        raise AcquisitionError("validation", retrieval_id, exc) from exc
    receipt = storage._make_receipt(
        response, retrieval_id, source_id, requested_url, retrieved_at)
    try:
        storage._encode_receipt(receipt)
    except (TypeError, ValueError) as exc:
        raise AcquisitionError("storage", retrieval_id, exc) from exc
    try:
        stored = save_pdf_candidate(
            root, response, retrieval_id=retrieval_id, source_id=source_id,
            requested_url=requested_url, retrieved_at=retrieved_at,
            max_bytes=limits.max_bytes)
    except (OSError, storage.StorageConflictError,
            storage.StorageIntegrityError) as exc:
        raise AcquisitionError("storage", retrieval_id, exc) from exc
    return AcquisitionResult(
        source_id, retrieval_id, response.url, stored.receipt["sha256"],
        stored.original_path, stored.receipt_path)

"""Windows-local candidate snapshots; no download or PDF parsing.

os.rename raises FileExistsError for an existing destination on Windows,
so it publishes without intentionally replacing a prior snapshot:
https://docs.python.org/3.11/library/os.html#os.rename.
"""
import json
import os
import re
import shutil
import stat
from urllib.parse import urlsplit
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

from payer_policy.document_validation import validate_pdf_candidate
from payer_policy.https_transport import FetchResult
from payer_policy.provenance import fingerprint_document

_RECEIPT_LIMIT = 65_536
_HEADER_NAMES = frozenset({
    "content-type", "content-encoding", "content-length",
    "transfer-encoding", "etag", "last-modified", "date",
})
_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_SOURCE_PATTERN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
_UTC_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")


class StorageConflictError(ValueError):
    """A retrieval ID is already assigned to different data."""


class StorageIntegrityError(ValueError):
    """A published record is damaged or inconsistent."""


@dataclass(frozen=True)
class StoredCandidate:
    """Keep verified bytes, a receipt copy, and published paths."""

    original_path: Path
    receipt_path: Path
    receipt: dict[str, object]
    body: bytes


def _check_id(value: str, pattern: re.Pattern[str], label: str) -> None:
    """Reject path-like IDs and preserve exact caller spelling."""
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not pattern.fullmatch(value):
        raise ValueError(f"invalid {label}")


def _check_limit(max_bytes: int) -> None:
    """Require a positive whole-byte limit without coercion."""
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")


def _check_path(path: Path) -> None:
    """Reject reparse points (links/junctions), not their targets.

    lstat inspects the entry itself; see
    https://docs.python.org/3.11/library/os.html#os.lstat.
    This cannot stop a hostile local process replacing paths concurrently.
    """
    info = path.lstat()
    if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError("storage path is a reparse point")


def _check_root(root: Path) -> None:
    """Require an existing absolute Windows root; reject UNC paths.

    A mapped network drive can still look local: the caller must choose
    a trusted physical/local folder.
    """
    if os.name != "nt":
        raise OSError("storage writer requires Windows")
    if not isinstance(root, Path):
        raise TypeError("root must be a Path")
    if not root.is_absolute() or str(root).startswith("\\"):
        raise ValueError("root must be an absolute local path")
    try:
        for part in (root, *root.parents):
            _check_path(part)
    except FileNotFoundError as exc:
        raise ValueError("root must be an existing directory") from exc
    if not root.is_dir():
        raise ValueError("root must be an existing directory")


def _check_url(value: str) -> None:
    """Check preserved HTTPS metadata syntax, not destination permission."""
    if not isinstance(value, str):
        raise TypeError("URL must be a string")
    if (not value.isascii() or any(ord(c) <= 32 or ord(c) == 127
                                  for c in value) or
            "\\" in value or "#" in value or
            re.search(r"%(?![0-9a-fA-F]{2})", value)):
        raise ValueError("invalid HTTPS metadata URL")
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or
            parts.username is not None or parts.password is not None or
            parts.netloc.endswith(":") or parts.port not in (None, 443)):
        raise ValueError("invalid HTTPS metadata URL")
    label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    hostname_rule = label + r"(?:\." + label + r")*"
    if (len(parts.hostname) > 253 or
            not re.fullmatch(hostname_rule, parts.hostname)):
        raise ValueError("invalid HTTPS metadata hostname")


def _make_receipt(
    result: FetchResult, retrieval_id: str, source_id: str,
    requested_url: str, retrieved_at: datetime,
) -> dict[str, object]:
    """Describe exact candidate bytes and selected non-cookie metadata."""
    validate_pdf_candidate(result)
    _check_id(retrieval_id, _ID_PATTERN, "retrieval_id")
    _check_id(source_id, _SOURCE_PATTERN, "source_id")
    _check_url(requested_url)
    _check_url(result.url)
    if not isinstance(retrieved_at, datetime):
        raise TypeError("retrieved_at must be a datetime")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    return {
        "schema_version": 1, "retrieval_id": retrieval_id,
        "source_id": source_id, "requested_url": requested_url,
        "final_url": result.url,
        "retrieved_at": retrieved_at.astimezone(timezone.utc).isoformat(
            timespec="microseconds").replace("+00:00", "Z"),
        "http_status": result.status,
        "headers": [list(pair) for pair in result.headers
                    if pair[0].lower() in _HEADER_NAMES],
        "byte_count": len(result.body),
        "sha256": fingerprint_document(result.body),
        "validation": "pdf_candidate", "validation_version": 1,
    }


def _encode_receipt(receipt: dict[str, object]) -> bytes:
    """Reject metadata beyond the loader's fixed read budget."""
    data = json.dumps(receipt, ensure_ascii=True).encode("utf-8")
    if len(data) > _RECEIPT_LIMIT:
        raise ValueError("receipt exceeds 64 KiB")
    return data


def _write_synced(path: Path, data: bytes) -> None:
    """Flush a new file before publishing its containing directory.

    flush sends Python's buffer onward; os.fsync requests an OS file flush.
    https://docs.python.org/3.11/library/os.html#os.fsync
    This is not a power-loss or backup guarantee.
    """
    with path.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def _read_bounded(path: Path, limit: int) -> bytes:
    """Read at most one excess byte from a regular, non-reparse file."""
    try:
        _check_path(path)
        if not stat.S_ISREG(path.lstat().st_mode):
            raise StorageIntegrityError("record entry is not a regular file")
        with path.open("rb") as input_file:
            data = input_file.read(limit + 1)
    except (OSError, ValueError) as exc:
        raise StorageIntegrityError("missing or unsafe record file") from exc
    if len(data) > limit:
        raise StorageIntegrityError("record exceeds size limit")
    return data


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON keys instead of losing ambiguous evidence.

    json.loads calls object_pairs_hook before creating the mapping:
    https://docs.python.org/3.11/library/json.html#json.loads.
    """
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StorageIntegrityError("duplicate receipt key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    """Reject NaN and Infinity, which are not JSON numbers."""
    raise StorageIntegrityError("invalid receipt constant")


def save_pdf_candidate(
    root: Path, result: FetchResult, *, retrieval_id: str, source_id: str,
    requested_url: str, retrieved_at: datetime, max_bytes: int = 10_000_000,
) -> StoredCandidate:
    """Publish unchanged bytes and a receipt; verify before returning.

    validate_pdf_candidate (document_validation.py) checks types and the
    PDF marker before measuring the body. Reject oversized bytes before
    receipt creation or hashing; the caller already holds these bytes.

    mkdtemp creates unique same-root staging; os.rename publishes after
    both files are flushed. An identical same-ID retry returns the prior
    verified record, while conflicting input cannot overwrite it.
    https://docs.python.org/3.11/library/tempfile.html#tempfile.mkdtemp
    """
    _check_limit(max_bytes)
    validate_pdf_candidate(result)
    if len(result.body) > max_bytes:
        raise ValueError("original exceeds max_bytes")
    receipt = _make_receipt(result, retrieval_id, source_id,
                            requested_url, retrieved_at)
    receipt_bytes = _encode_receipt(receipt)
    _check_root(root)
    records, staging = root / "records", root / ".staging"
    for directory in (records, staging):
        directory.mkdir(exist_ok=True)
        _check_path(directory)
        if not directory.is_dir():
            raise ValueError("storage component is not a directory")
    destination = records / retrieval_id
    if destination.exists() or destination.is_symlink():
        existing = load_saved_candidate(root, retrieval_id,
                                        max_bytes=max_bytes)
        if existing.receipt != receipt or existing.body != result.body:
            raise StorageConflictError(
                "retrieval_id belongs to another record")
        return existing
    attempt = Path(mkdtemp(dir=staging))
    try:
        _write_synced(attempt / "original.bin", result.body)
        _write_synced(attempt / "receipt.json", receipt_bytes)
        try:
            os.rename(attempt, destination)
        except FileExistsError:
            existing = load_saved_candidate(root, retrieval_id,
                                            max_bytes=max_bytes)
            if existing.receipt != receipt or existing.body != result.body:
                raise StorageConflictError(
                    "retrieval_id belongs to another record")
            return existing
    finally:
        if attempt.exists():
            shutil.rmtree(attempt)
    return load_saved_candidate(root, retrieval_id, max_bytes=max_bytes)


def load_saved_candidate(
    root: Path, retrieval_id: str, *, max_bytes: int = 10_000_000,
) -> StoredCandidate:
    """Read verified bytes, rejecting damaged records and unsafe paths.

    Bounded reads prevent a changed file consuming unlimited memory. The
    fingerprint detects mismatch with the receipt, not authenticity when
    someone can change both files together.
    """
    _check_limit(max_bytes)
    _check_id(retrieval_id, _ID_PATTERN, "retrieval_id")
    _check_root(root)
    record = root / "records" / retrieval_id
    try:
        _check_path(root / "records")
        _check_path(record)
        if not record.is_dir():
            raise StorageIntegrityError("record is not a directory")
    except (OSError, ValueError) as exc:
        raise StorageIntegrityError("record is missing or unsafe") from exc
    original = record / "original.bin"
    receipt_path = record / "receipt.json"
    receipt_data = _read_bounded(receipt_path, _RECEIPT_LIMIT)
    body = _read_bounded(original, max_bytes)
    try:
        receipt = json.loads(receipt_data.decode("utf-8"),
                             object_pairs_hook=_unique_pairs,
                             parse_constant=_reject_constant)
        if not isinstance(receipt, dict):
            raise ValueError("invalid receipt shape")
        if (type(receipt.get("schema_version")) is not int or
                type(receipt.get("validation_version")) is not int or
                type(receipt.get("byte_count")) is not int):
            raise ValueError("invalid receipt number types")
        if not isinstance(receipt.get("retrieved_at"), str):
            raise ValueError("invalid receipt timestamp")
        timestamp = receipt["retrieved_at"]
        if not _UTC_PATTERN.fullmatch(timestamp):
            raise ValueError("invalid UTC timestamp")
        instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        headers = receipt["headers"]
        if (not isinstance(headers, list) or any(
                not isinstance(pair, list) or len(pair) != 2 or
                not all(isinstance(part, str) for part in pair)
                for pair in headers)):
            raise ValueError("invalid receipt headers")
        response = FetchResult(receipt["final_url"],
                               receipt["http_status"],
                               tuple(tuple(pair) for pair in headers), body)
        expected = _make_receipt(
            response, retrieval_id, receipt["source_id"],
            receipt["requested_url"], instant)
        if receipt != expected or set(receipt) != set(expected):
            raise ValueError("receipt does not match original")
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError,
            KeyError, OverflowError, RecursionError) as exc:
        raise StorageIntegrityError("invalid or inconsistent receipt") from exc
    return StoredCandidate(original, receipt_path, receipt, body)

"""Separate Windows-local derived artifacts; originals are never rewritten.

Reuse trusted-path, bounded-read and flush helpers from document_storage.py.
Windows os.rename refuses an existing destination; this is not portable:
https://docs.python.org/3.11/library/os.html#os.rename
"""
import os
import shutil
from pathlib import Path
from tempfile import mkdtemp

from payer_policy import _extraction_protocol as protocol
from payer_policy.document_storage import (
    StorageConflictError, StorageIntegrityError, _check_path, _check_root,
    _read_bounded, _write_synced,
)
from payer_policy.text_extraction import (
    PdfTextExtraction, extraction_facts, validate_id,
)


def save_text_extraction(
    root: Path, extraction: PdfTextExtraction, *, extraction_id: str,
) -> Path:
    """Publish complete bounded JSON, then read it back before success.

    Repeating an ID is always a conflict, even for identical data. A failure
    after publication can leave an artifact; no prior artifact is deleted.
    Flushing files is not a power-loss, backup or hostile-writer guarantee.
    """
    validate_id(extraction_id)
    facts = extraction_facts(extraction)
    artifact = {"schema_version": 1, "extraction_id": extraction_id,
                "extraction": facts}
    raw = protocol.encode(artifact, extraction.limits.max_result_bytes)
    _check_root(root)
    from payer_policy.document_storage import load_saved_candidate

    stored = load_saved_candidate(root, extraction.retrieval_id,
                                  max_bytes=extraction.limits.max_bytes)
    if stored.receipt["sha256"] != extraction.sha256:
        raise StorageIntegrityError("extraction source does not match root")
    derived = root / "derived"
    try:
        derived.mkdir(exist_ok=True)
    except FileExistsError as exc:
        raise ValueError("derived must be a directory") from exc
    _check_path(derived)
    if not derived.is_dir():
        raise ValueError("derived must be a directory")
    destination = derived / extraction_id
    if destination.exists() or destination.is_symlink():
        raise StorageConflictError("extraction_id already exists")
    attempt = Path(mkdtemp(prefix=".staging-", dir=derived))
    try:
        _write_synced(attempt / "extraction.json", raw)
        try:
            os.rename(attempt, destination)
        except FileExistsError as exc:
            raise StorageConflictError("extraction_id already exists") from exc
    finally:
        if attempt.exists():
            shutil.rmtree(attempt)
    _check_path(destination)
    target = destination / "extraction.json"
    observed = _read_bounded(target, extraction.limits.max_result_bytes)
    if observed != raw or protocol.decode(observed) != artifact:
        raise StorageIntegrityError("derived artifact changed during save")
    return target

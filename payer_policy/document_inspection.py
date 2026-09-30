"""Inspect verified local PDF candidates without changing their originals.

PdfReader accepts a seekable byte stream and exposes encryption and pages:
https://pypdf.readthedocs.io/en/latest/modules/PdfReader.html
Opening a PDF is not proof of safety, authenticity, or policy applicability.
"""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import cast

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from payer_policy.document_storage import load_saved_candidate


class PdfInspectionError(ValueError):
    """The verified candidate cannot supply the requested PDF facts."""


@dataclass(frozen=True)
class PdfInspection:
    """Hold basic structural facts tied to a verified stored fingerprint."""

    retrieval_id: str
    sha256: str
    page_count: int | None
    is_encrypted: bool


def inspect_saved_pdf(
    root: Path, retrieval_id: str, *, max_bytes: int = 10_000_000,
) -> PdfInspection:
    """Return basic PDF structure from verified bytes, or fail on bad storage.

    load_saved_candidate verifies the receipt and bounds the original read:
    ../payer_policy/document_storage.py. The parser sees only those returned
    bytes, never a separate unverified path. This does not extract page text.
    PDF read failures become PdfInspectionError, not storage failures.
    """
    stored = load_saved_candidate(root, retrieval_id, max_bytes=max_bytes)
    try:
        reader = PdfReader(BytesIO(stored.body), strict=True)
        encrypted = reader.is_encrypted
        page_count = None if encrypted else len(reader.pages)
    except PdfReadError as exc:
        raise PdfInspectionError("cannot inspect PDF structure") from exc
    return PdfInspection(
        retrieval_id, cast(str, stored.receipt["sha256"]),
        page_count, encrypted,
    )

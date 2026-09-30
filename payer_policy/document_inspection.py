"""Inspect verified local PDF candidates without changing their originals.

PdfReader accepts a seekable byte stream and exposes encryption and pages:
https://pypdf.readthedocs.io/en/6.19.0/modules/PdfReader.html
Its error reference warns that broken PDFs can also raise other exceptions;
DependencyError is separate from the PyPdfError family:
https://pypdf.readthedocs.io/en/6.19.0/modules/errors.html
The built-in errors caught below cover tested malformed catalog/encryption
data and unsupported encryption, not process stops or memory exhaustion.
Opening a PDF is not proof of safety, authenticity, or policy applicability.
"""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import cast

from pypdf import PdfReader
from pypdf.errors import DependencyError, PyPdfError

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
    Supported parser failures become PdfInspectionError with their cause;
    storage and input failures pass through unchanged.
    """
    stored = load_saved_candidate(root, retrieval_id, max_bytes=max_bytes)
    try:
        # No application password or explicit decrypt call. pypdf 6.19.0
        # internally tries an empty password during initialization:
        # https://pypdf.readthedocs.io/en/6.19.0/_modules/pypdf/_reader.html
        reader = PdfReader(BytesIO(stored.body), strict=True)
        encrypted = reader.is_encrypted
        page_count = None if encrypted else len(reader.pages)
    except (
        PyPdfError, DependencyError, AttributeError, KeyError, TypeError,
        NotImplementedError,
    ) as exc:
        raise PdfInspectionError("cannot inspect PDF structure") from exc
    return PdfInspection(
        retrieval_id, cast(str, stored.receipt["sha256"]),
        page_count, encrypted,
    )

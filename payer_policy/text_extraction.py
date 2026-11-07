"""Immutable page text and pure validation; no PDF is opened on import."""
import math
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import cast


CHILD_ERRORS = frozenset({
    "input_error", "storage_error", "encrypted", "range_error",
    "parser_error", "output_limit", "memory_error",
})


class ExtractionError(RuntimeError):
    """Keep a stable extraction failure category, without remote objects."""

    def __init__(self, code: str) -> None:
        """Store a known failure code; reject invented categories."""
        allowed = CHILD_ERRORS | {
            "unsupported_runtime", "setup_error", "timeout", "crash",
            "ipc_error", "invalid_result", "cleanup_error",
        }
        if type(code) is not str or code not in allowed:
            raise ValueError("unknown extraction error code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PageText:
    """Keep exact parser text for one physical page, including whitespace."""

    page_number: int
    text: str
    status: str


@dataclass(frozen=True)
class PdfTextExtraction:
    """Describe a complete requested batch, not complete document coverage."""

    retrieval_id: str
    sha256: str
    page_count: int
    requested_pages: tuple[int, ...]
    pages: tuple[PageText, ...]
    extracted_at: datetime
    limits: "ExtractionLimits"
    schema_version: int = 1
    parser_name: str = "pypdf"
    parser_version: str = "6.19.0"
    mode: str = "plain"


def _extract_saved_pages(
    root: Path, retrieval_id: str, pages: tuple[int, ...],
    limits: "ExtractionLimits",
) -> PdfTextExtraction:
    """Read verified stored bytes and extract only requested pages.

    Private child kernel; public callers use extraction_worker.py.
    document_storage.py#load_saved_candidate verifies exact original bytes.
    PdfReader and plain extraction use the pinned library unchanged:
    https://pypdf.readthedocs.io/en/6.19.0/modules/PdfReader.html
    https://pypdf.readthedocs.io/en/6.19.0/modules/PageObject.html
    """
    from pypdf import PdfReader
    from pypdf.errors import DependencyError, PyPdfError
    from payer_policy.document_storage import load_saved_candidate

    stored = load_saved_candidate(root, retrieval_id,
                                  max_bytes=limits.max_bytes)
    try:
        # pypdf can internally try an empty password at initialization.
        # Always refuse encrypted documents, even if that attempt succeeds.
        reader = PdfReader(BytesIO(stored.body), strict=True)
        if reader.is_encrypted:
            raise ExtractionError("encrypted")
        count = len(reader.pages)
        if pages[-1] > count:
            raise ExtractionError("range_error")
        extracted = []
        total = 0
        for number in pages:
            text = reader.pages[number - 1].extract_text(
                extraction_mode="plain")
            size = len(text.encode("utf-8"))
            total += size
            if (size > limits.max_page_text_bytes
                    or total > limits.max_total_text_bytes):
                raise ExtractionError("output_limit")
            extracted.append(PageText(number, text,
                                      "text" if text.strip() else "empty"))
    except (PyPdfError, DependencyError) as exc:
        raise ExtractionError("parser_error") from exc
    return PdfTextExtraction(
        retrieval_id, cast(str, stored.receipt["sha256"]), count, pages,
        tuple(extracted), datetime.now(timezone.utc), limits,
    )


@dataclass(frozen=True)
class ExtractionLimits:
    """Snapshot byte, wait and memory ceilings for one selected batch."""

    max_bytes: int = 10_000_000
    max_page_text_bytes: int = 65_536
    max_total_text_bytes: int = 524_288
    max_result_bytes: int = 1_048_576
    timeout_seconds: float = 30
    memory_bytes: int = 268_435_456


def validate_limits(limits: ExtractionLimits) -> None:
    """Reject settings above fixed caps or values needing conversion."""
    if type(limits) is not ExtractionLimits:
        raise TypeError("limits must be ExtractionLimits")
    for name, maximum in (
        ("max_bytes", 10_000_000), ("max_page_text_bytes", 65_536),
        ("max_total_text_bytes", 524_288), ("max_result_bytes", 1_048_576),
    ):
        value = getattr(limits, name)
        if type(value) is not int or not 0 < value <= maximum:
            raise ValueError("invalid " + name)
    timeout = limits.timeout_seconds
    if (type(timeout) not in (int, float) or not 0 < timeout <= 60
            or not math.isfinite(timeout)):
        raise ValueError("invalid timeout_seconds")
    if (type(limits.memory_bytes) is not int
            or not 16_777_216 <= limits.memory_bytes <= 268_435_456):
        raise ValueError("invalid memory_bytes")


def validate_pages(pages: tuple[int, ...]) -> None:
    """Require one to ten ascending, unique, physical one-based pages."""
    if type(pages) is not tuple:
        raise TypeError("pages must be an explicit tuple")
    if not 1 <= len(pages) <= 10:
        raise ValueError("select one to ten pages")
    previous = 0
    for page in pages:
        if type(page) is not int or page <= previous:
            raise ValueError("pages must be ascending positive integers")
        previous = page


def validate_id(value: str) -> None:
    """Reject noncanonical IDs rather than converting path-like input."""
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise ValueError("invalid identifier")


def validate_extraction(value: PdfTextExtraction) -> None:
    """Require complete, bounded, internally consistent selected-page facts."""
    if type(value) is not PdfTextExtraction:
        raise TypeError("expected PdfTextExtraction")
    validate_id(value.retrieval_id)
    validate_limits(value.limits)
    validate_pages(value.requested_pages)
    if (type(value.schema_version) is not int or value.schema_version != 1
            or value.parser_name != "pypdf" or value.parser_version != "6.19.0"
            or value.mode != "plain"):
        raise ValueError("unexpected version, parser or mode")
    if (type(value.sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", value.sha256) is None
            or type(value.page_count) is not int
            or value.page_count < value.requested_pages[-1]):
        raise ValueError("invalid fingerprint or page count")
    instant = value.extracted_at
    if (type(instant) is not datetime or instant.tzinfo is not timezone.utc):
        raise ValueError("timestamp must be aware UTC")
    if (type(value.pages) is not tuple
            or len(value.pages) != len(value.requested_pages)):
        raise ValueError("incomplete selected batch")
    total = 0
    for number, page in zip(value.requested_pages, value.pages):
        if (type(page) is not PageText or type(page.page_number) is not int
                or page.page_number != number or type(page.text) is not str
                or type(page.status) is not str
                or page.status != ("text" if page.text.strip() else "empty")):
            raise ValueError("invalid page facts")
        size = len(page.text.encode("utf-8"))
        total += size
        if (size > value.limits.max_page_text_bytes
                or total > value.limits.max_total_text_bytes):
            raise ValueError("text exceeds budget")


def extraction_facts(value: PdfTextExtraction) -> dict:
    """Return JSON-ready facts without changing any page text."""
    validate_extraction(value)
    facts = asdict(value)
    facts["requested_pages"] = list(value.requested_pages)
    facts["pages"] = [asdict(page) for page in value.pages]
    facts["extracted_at"] = value.extracted_at.isoformat(
        timespec="microseconds").replace("+00:00", "Z")
    return facts


def limits_from_facts(value: dict) -> ExtractionLimits:
    """Decode an exact settings object; reject missing or extra fields."""
    if (type(value) is not dict
            or set(value) != {field.name for field in fields(ExtractionLimits)}):
        raise ValueError("invalid limits keys")
    limits = ExtractionLimits(**value)
    validate_limits(limits)
    return limits


def extraction_from_facts(facts: dict) -> PdfTextExtraction:
    """Decode only the versioned result schema; reject incomplete facts."""
    keys = {field.name for field in fields(PdfTextExtraction)}
    if type(facts) is not dict or set(facts) != keys:
        raise ValueError("invalid extraction keys")
    if (type(facts["pages"]) is not list
            or type(facts["requested_pages"]) is not list):
        raise ValueError("invalid page arrays")
    pages = []
    for page in facts["pages"]:
        if (type(page) is not dict
                or set(page) != {"page_number", "text", "status"}):
            raise ValueError("invalid page keys")
        pages.append(PageText(**page))
    timestamp = facts["extracted_at"]
    if (type(timestamp) is not str or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z",
            timestamp) is None):
        raise ValueError("invalid UTC timestamp")
    values = dict(facts)
    values.update(
        pages=tuple(pages), requested_pages=tuple(facts["requested_pages"]),
        limits=limits_from_facts(facts["limits"]),
        extracted_at=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
    )
    result = PdfTextExtraction(**values)
    validate_extraction(result)
    return result

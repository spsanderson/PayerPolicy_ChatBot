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
    keys = {field.name for field in fields(ExtractionLimits)}
    if type(value) is not dict or set(value) != keys:
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

@dataclass(frozen=True)
class SpacingCorrection:
    """Identify one reviewed TJ item and its exact raw output span."""

    page_number: int
    space_offset: int
    expected_span: str
    span_start: int
    operation_index: int
    item_index: int


def corrected_text_view(
    source_bytes: bytes, raw: PdfTextExtraction, *, retrieval_id: str,
    source_sha256: str, corrections: tuple[SpacingCorrection, ...],
) -> dict:
    """Derive text only after exact, isolated TJ counterfactual checks.

    Explicit local API; unlike the extraction worker this parses in-process.
    Never use with untrusted PDFs outside a resource-bounded caller.
    No bytes, receipts, raw results or parser globals are modified.
    """
    from copy import deepcopy
    from hashlib import sha256
    import pypdf
    from pypdf import PdfReader
    from pypdf.generic import (
        ContentStream, DecodedStreamObject, NameObject, NumberObject,
    )
    from pypdf.generic import TextStringObject

    validate_extraction(raw)
    if (type(source_bytes) is not bytes
            or len(source_bytes) > raw.limits.max_bytes
            or retrieval_id != raw.retrieval_id
            or source_sha256 != raw.sha256
            or sha256(source_bytes).hexdigest() != source_sha256
            or pypdf.__version__ != raw.parser_version):
        raise ValueError('stale source identity or parser')
    if (type(corrections) is not tuple or not corrections
            or len(corrections) > 20):
        raise ValueError('explicit bounded corrections required')
    reader = PdfReader(BytesIO(source_bytes), strict=True)
    if reader.is_encrypted or len(reader.pages) != raw.page_count:
        raise ValueError('source page mismatch or encryption')
    pages = {page.page_number: page.text for page in raw.pages}
    evidence = []
    occupied = {}
    for edit in corrections:
        if type(edit) is not SpacingCorrection:
            raise ValueError('invalid correction')
        for name in ('page_number', 'space_offset', 'span_start',
                     'operation_index', 'item_index'):
            if type(getattr(edit, name)) is not int:
                raise ValueError('integer coordinates required')
        text = pages.get(edit.page_number)
        start = edit.span_start
        offset = edit.space_offset
        span = edit.expected_span
        if (text is None or type(span) is not str or not span
                or start < 0 or not start <= offset < start + len(span)
                or text[start:start + len(span)] != span
                or text.count(span) != 1 or offset < 1
                or text[offset - 1:offset + 1] != 'Y '
                or offset + 1 >= len(text)
                or not 'a' <= text[offset + 1] <= 'z'):
            raise ValueError('stale, repeated or unrelated output span')
        intervals = occupied.setdefault(edit.page_number, [])
        end = start + len(span)
        if any(start < right and left < end for left, right in intervals):
            raise ValueError('overlapping correction spans')
        intervals.append((start, end))
        page = reader.pages[edit.page_number - 1]
        if page.extract_text(extraction_mode='plain') != text:
            raise ValueError('raw parser text mismatch')
        stream = ContentStream(page.get_contents(), reader)
        if any(operator == b'Do' for _, operator in stream.operations):
            raise ValueError('nested or external content is unsupported')
        op = edit.operation_index
        item = edit.item_index
        if not 0 <= op < len(stream.operations):
            raise ValueError('operation outside content stream')
        operands, operator = stream.operations[op]
        if operator != b'TJ' or len(operands) != 1:
            raise ValueError('not a TJ operation')
        array = operands[0]
        if not 0 < item < len(array) - 1:
            raise ValueError('item outside TJ interior')
        left, adjustment, right = array[item - 1:item + 2]
        if (not isinstance(left, TextStringObject)
                or not isinstance(right, TextStringObject)
                or not left.endswith('Y') or not right
                or not 'a' <= right[0] <= 'z'
                or not isinstance(adjustment, (int, float))
                or isinstance(adjustment, bool) or adjustment != 126):
            raise ValueError('not the approved TJ boundary')
        # Neutralize one item, never rewrite or serialize a PDF.
        trial = deepcopy(stream)
        trial.operations[op][0][0][item] = NumberObject(0)
        from copy import copy
        trial_page = copy(page)
        # Plain extraction reparses stream bytes with forced_encoding='bytes'.
        # A direct ContentStream bypasses that path and can decode unrelated
        # font bytes differently. Flatten indirect/array contents only in this
        # isolated trial, then let extract_text use its normal decoding path.
        trial_contents = DecodedStreamObject()
        trial_contents.set_data(trial.get_data())
        trial_page[NameObject('/Contents')] = trial_contents
        expected = text[:offset] + text[offset + 1:]
        if trial_page.extract_text(extraction_mode='plain') != expected:
            raise ValueError('ambiguous TJ to output mapping')
        evidence.append({
            **asdict(edit), 'adjustment': 126, 'replacement': '',
            'raw_page_sha256': sha256(text.encode('utf-8')).hexdigest(),
            'proof': 'isolated-TJ-neutralization-exact-single-deletion',
        })
    corrected = []
    for page in raw.pages:
        text = page.text
        offsets = sorted((edit.space_offset for edit in corrections
                          if edit.page_number == page.page_number),
                         reverse=True)
        for offset in offsets:
            text = text[:offset] + text[offset + 1:]
        corrected.append({'page_number': page.page_number, 'text': text})
    return {
        'schema_version': 1, 'kind': 'corrected-derived-text',
        'retrieval_id': retrieval_id, 'source_sha256': source_sha256,
        'parser_name': raw.parser_name, 'parser_version': raw.parser_version,
        'mode': raw.mode, 'corrections': evidence, 'pages': corrected,
        'raw_extraction': extraction_facts(raw),
    }

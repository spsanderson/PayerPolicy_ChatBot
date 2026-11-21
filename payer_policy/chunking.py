"""Deterministic structure-aware blocks for validated pilot pages."""
import re
from dataclasses import dataclass

from payer_policy.pilot_inputs import ValidatedPilotPage


_LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)]|[A-Za-z][.)])\s+")
_HEADING_PATTERN = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?[ :]?|[A-Z][A-Z0-9 /&()'’-]{2,})$"
)


@dataclass(frozen=True)
class PageBlock:
    """Hold one exact page-text range and a conservative structure label."""

    start_offset: int
    end_offset: int
    line_start: int
    line_end: int
    text: str
    kind: str
    confidence: str
    boundary_note: str | None = None


def _line_ranges(text: str) -> list[tuple[int, int, int, str]]:
    """Return one-based line numbers and exact string ranges for page text."""
    ranges = []
    offset = 0
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        end = offset + len(line)
        ranges.append((number, offset, end, line))
        offset = end
    return ranges


def _block_ranges(
    text: str,
) -> list[tuple[int, int, int, int]]:
    """Split exact text ranges at runs of blank lines."""
    lines = _line_ranges(text)
    if not lines or not any(line.strip() for _, _, _, line in lines):
        return [(0, len(text), 1, len(lines))] if text else []

    ranges: list[tuple[int, int, int, int]] = []
    block_start = 0
    block_line_start = 1
    saw_content = False
    blank_start: int | None = None
    blank_end: int | None = None
    blank_line_end: int | None = None

    for number, start, end, line in lines:
        if not line.strip():
            if saw_content and blank_start is None:
                blank_start = start
            if saw_content:
                blank_end = end
                blank_line_end = number
            continue
        if blank_end is not None:
            ranges.append((
                block_start,
                blank_end,
                block_line_start,
                blank_line_end or number - 1,
            ))
            block_start = blank_end
            block_line_start = number
            blank_start = None
            blank_end = None
            blank_line_end = None
        saw_content = True

    ranges.append((block_start, len(text), block_line_start, len(lines)))
    return ranges


def _is_table_like(lines: list[str]) -> bool:
    """Return true only for repeated, visible pipe-delimited rows."""
    return sum("|" in line for line in lines) >= 2


def _classify_block(text: str) -> tuple[str, str, str | None]:
    """Label one block without reconstructing visual PDF layout."""
    visible_lines = [
        line.strip() for line in text.splitlines() if line.strip()
    ]
    if not visible_lines:
        return "unknown", "low", "structure is whitespace-only"
    if _is_table_like(visible_lines):
        return "table", "medium", None
    if any(_LIST_MARKER.match(line) for line in visible_lines):
        return "list", "medium", None
    if len(visible_lines) == 1:
        line = visible_lines[0]
        if len(line) <= 120 and not line.endswith((".", "!", "?", ";")):
            if _HEADING_PATTERN.fullmatch(line):
                return "heading", "medium", None
    if len(visible_lines) > 1:
        return "paragraph", "medium", None
    return "paragraph", "low", "single-line structure is uncertain"


def segment_page_blocks(
    page: ValidatedPilotPage,
) -> tuple[PageBlock, ...]:
    """Return exact, page-local blocks with conservative structure labels.

    No whitespace or text normalization occurs. Empty text returns no blocks;
    nonempty whitespace remains an ``unknown`` block. The function performs no
    filesystem or parser work and never crosses the supplied page boundary.
    """
    if not isinstance(page, ValidatedPilotPage):
        raise TypeError("page must be ValidatedPilotPage")
    ranges = _block_ranges(page.text)
    blocks = []
    for start, end, line_start, line_end in ranges:
        text = page.text[start:end]
        kind, confidence, note = _classify_block(text)
        blocks.append(PageBlock(
            start_offset=start,
            end_offset=end,
            line_start=line_start,
            line_end=line_end,
            text=text,
            kind=kind,
            confidence=confidence,
            boundary_note=note,
        ))
    return tuple(blocks)

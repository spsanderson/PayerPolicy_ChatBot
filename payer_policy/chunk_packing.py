"""Deterministic protected-block packing for validated pilot pages."""
from dataclasses import dataclass

from payer_policy.chunking import PageBlock
from payer_policy.pilot_inputs import ValidatedPilotPage


@dataclass(frozen=True)
class PageChunk:
    """Hold one immutable packed chunk and its page provenance."""

    chunk_id: str
    source_id: str
    retrieval_id: str
    pdf_sha256: str
    raw_text_sha256: str
    selected_text_sha256: str
    artifact_kind: str
    quality_verdict: str
    parser_name: str
    parser_version: str
    extraction_mode: str
    page_number: int
    ordinal: int
    start_offset: int
    end_offset: int
    line_start: int
    line_end: int
    text: str
    word_count: int
    block_kinds: tuple[str, ...]
    boundary_note: str | None = None


def _validate_pack_parameters(target_words: int, max_words: int) -> None:
    """Reject invalid word-size settings before any chunk is created."""
    if type(target_words) is not int or target_words < 1:
        raise ValueError("target_words must be a positive integer")
    if type(max_words) is not int or max_words < 1:
        raise ValueError("max_words must be a positive integer")
    if target_words > max_words:
        raise ValueError("target_words cannot exceed max_words")


def _validate_page_blocks(
    page: ValidatedPilotPage,
    blocks: tuple[PageBlock, ...],
) -> None:
    """Require ordered blocks to reconstruct the exact selected page text."""
    expected_start = 0
    for block in blocks:
        if not isinstance(block, PageBlock):
            raise TypeError("blocks must contain PageBlock instances")
        if block.start_offset != expected_start:
            raise ValueError("blocks must be contiguous and ordered")
        if block.end_offset <= block.start_offset:
            raise ValueError("blocks must have positive spans")
        if not isinstance(block.text, str):
            raise TypeError("block text must be a string")
        if block.text != page.text[block.start_offset:block.end_offset]:
            raise ValueError("block text does not match page text span")
        if block.kind not in {
            "heading", "paragraph", "list", "table", "unknown"
        }:
            raise ValueError("block kind is invalid")
        if block.line_start < 1 or block.line_end < block.line_start:
            raise ValueError("block line range is invalid")
        expected_start = block.end_offset
    if expected_start != len(page.text):
        raise ValueError("blocks must reconstruct the full page text")


def _word_count(text: str) -> int:
    """Count words without changing the text stored in a chunk."""
    return len(text.split())


def _make_page_chunk(
    page: ValidatedPilotPage,
    blocks: list[PageBlock],
    ordinal: int,
    notes: list[str],
) -> PageChunk:
    """Create one immutable chunk from contiguous whole blocks."""
    start = blocks[0].start_offset
    end = blocks[-1].end_offset
    text = page.text[start:end]
    return PageChunk(
        chunk_id=f"{page.retrieval_id}:p{page.page_number:04d}:c{ordinal:04d}",
        source_id=page.source_id,
        retrieval_id=page.retrieval_id,
        pdf_sha256=page.pdf_sha256,
        raw_text_sha256=page.raw_text_sha256,
        selected_text_sha256=page.selected_text_sha256,
        artifact_kind=page.artifact_kind,
        quality_verdict=page.quality_verdict,
        parser_name=page.parser_name,
        parser_version=page.parser_version,
        extraction_mode=page.extraction_mode,
        page_number=page.page_number,
        ordinal=ordinal,
        start_offset=start,
        end_offset=end,
        line_start=blocks[0].line_start,
        line_end=blocks[-1].line_end,
        text=text,
        word_count=_word_count(text),
        block_kinds=tuple(block.kind for block in blocks),
        boundary_note="; ".join(notes) if notes else None,
    )


def _packing_units(
    blocks: tuple[PageBlock, ...],
    max_words: int,
) -> list[tuple[list[PageBlock], list[str]]]:
    """Group headings with following blocks when the maximum permits it."""
    units: list[tuple[list[PageBlock], list[str]]] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if block.kind == "heading" and index + 1 < len(blocks):
            following = blocks[index + 1]
            combined = _word_count(block.text + following.text)
            if combined <= max_words:
                units.append(([block, following], []))
                index += 2
                continue
            units.append((
                [block],
                ["heading_not_attached_within_maximum"],
            ))
            index += 1
            continue
        notes = []
        if _word_count(block.text) > max_words:
            notes.append("oversized_block")
        units.append(([block], notes))
        index += 1
    return units


def pack_page_blocks(
    page: ValidatedPilotPage,
    blocks: tuple[PageBlock, ...],
    *,
    target_words: int = 550,
    max_words: int = 700,
) -> tuple[PageChunk, ...]:
    """Pack whole page blocks into deterministic, page-local chunks.

    Blocks are never split. The target is a soft size goal; the maximum is
    enforced except for one indivisible oversized block. Headings attach to the
    following block when that pair fits within the maximum.
    """
    if not isinstance(page, ValidatedPilotPage):
        raise TypeError("page must be ValidatedPilotPage")
    if not isinstance(blocks, tuple):
        raise TypeError("blocks must be a tuple of PageBlock instances")
    _validate_pack_parameters(target_words, max_words)
    _validate_page_blocks(page, blocks)
    if not blocks:
        return ()

    chunks: list[PageChunk] = []
    current: list[PageBlock] = []
    current_notes: list[str] = []
    ordinal = 1
    for unit, unit_notes in _packing_units(blocks, max_words):
        if not current:
            current = list(unit)
            current_notes = list(unit_notes)
            continue
        current_words = _word_count(
            page.text[current[0].start_offset:current[-1].end_offset]
        )
        unit_words = _word_count(
            page.text[unit[0].start_offset:unit[-1].end_offset]
        )
        if current_words >= target_words:
            chunks.append(
                _make_page_chunk(page, current, ordinal, current_notes)
            )
            ordinal += 1
            current = list(unit)
            current_notes = list(unit_notes)
            continue
        if current_words + unit_words > max_words:
            chunks.append(
                _make_page_chunk(page, current, ordinal, current_notes)
            )
            ordinal += 1
            current = list(unit)
            current_notes = list(unit_notes)
            continue
        current.extend(unit)
        current_notes.extend(unit_notes)

    chunks.append(_make_page_chunk(page, current, ordinal, current_notes))
    return tuple(chunks)

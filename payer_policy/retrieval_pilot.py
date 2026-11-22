"""Deterministic lexical retrieval over validated pilot chunks."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from payer_policy.chunk_packing import PageChunk


_TOKEN = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class LexicalHit:
    """Hold one ranked chunk and its explainable lexical score."""

    chunk: PageChunk
    score: float


@dataclass(frozen=True)
class LexicalIndex:
    """Hold immutable chunks and document frequencies for retrieval."""

    chunks: tuple[PageChunk, ...]
    document_frequency: tuple[tuple[str, int], ...]

    @property
    def frequency_map(self) -> dict[str, int]:
        """Return a detached token-frequency mapping for scoring."""
        return dict(self.document_frequency)


def _tokens(text: str) -> tuple[str, ...]:
    """Return lowercase alphanumeric comparison tokens."""
    return tuple(match.group(0).casefold() for match in _TOKEN.finditer(text))


def build_lexical_index(
    chunks: tuple[PageChunk, ...],
) -> LexicalIndex:
    """Build a deterministic index without changing stored chunk text."""
    if not isinstance(chunks, tuple):
        raise TypeError("chunks must be a tuple")
    if any(not isinstance(chunk, PageChunk) for chunk in chunks):
        raise TypeError("chunks must contain PageChunk instances")
    identifiers = [chunk.chunk_id for chunk in chunks]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("chunk IDs must be unique")
    frequencies: dict[str, int] = {}
    for chunk in chunks:
        for token in set(_tokens(chunk.text)):
            frequencies[token] = frequencies.get(token, 0) + 1
    return LexicalIndex(
        chunks=chunks,
        document_frequency=tuple(sorted(frequencies.items())),
    )


def retrieve_lexical(
    index: LexicalIndex,
    query: str,
    *,
    limit: int = 3,
) -> tuple[LexicalHit, ...]:
    """Return stable positive-overlap hits with complete chunk provenance."""
    if not isinstance(index, LexicalIndex):
        raise TypeError("index must be LexicalIndex")
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return ()
    frequencies = index.frequency_map
    total = len(index.chunks)
    hits: list[LexicalHit] = []
    for chunk in index.chunks:
        chunk_tokens = set(_tokens(chunk.text))
        overlap = query_tokens & chunk_tokens
        if not overlap:
            continue
        score = sum(
            math.log((total + 1) / (frequencies[token] + 1)) + 1
            for token in overlap
        ) / math.sqrt(max(chunk.word_count, 1))
        hits.append(LexicalHit(chunk=chunk, score=score))
    hits.sort(key=lambda hit: (
        -hit.score,
        hit.chunk.source_id,
        hit.chunk.page_number,
        hit.chunk.ordinal,
        hit.chunk.chunk_id,
    ))
    return tuple(hits[:limit])

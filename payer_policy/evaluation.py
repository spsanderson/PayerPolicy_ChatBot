"""Evaluate deterministic retrieval without generating policy answers."""
from __future__ import annotations

from dataclasses import dataclass

from payer_policy.retrieval_pilot import LexicalIndex, retrieve_lexical


@dataclass(frozen=True)
class EvaluationQuery:
    """Describe one answerable or deliberate no-evidence retrieval query."""

    query_id: str
    text: str
    expected_chunk_ids: tuple[str, ...]
    answerable: bool
    expected_source_id: str | None = None
    expected_page_number: int | None = None


@dataclass(frozen=True)
class QueryEvaluation:
    """Hold one query's retrieved IDs and correctness observations."""

    query_id: str
    retrieved_chunk_ids: tuple[str, ...]
    expected_chunk_ids: tuple[str, ...]
    recall_at_1: bool
    recall_at_3: bool
    citation_at_1: bool
    no_evidence_rejected: bool


@dataclass(frozen=True)
class EvaluationReport:
    """Hold per-query results and aggregate pilot metrics."""

    results: tuple[QueryEvaluation, ...]
    recall_at_1: float
    recall_at_3: float
    citation_accuracy: float
    no_evidence_accuracy: float


def _validate_queries(queries: tuple[EvaluationQuery, ...]) -> None:
    """Reject duplicate IDs and inconsistent answerability declarations."""
    if not isinstance(queries, tuple):
        raise TypeError("queries must be a tuple")
    identifiers = [query.query_id for query in queries]
    if any(not isinstance(query, EvaluationQuery) for query in queries):
        raise TypeError("queries must contain EvaluationQuery instances")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("query IDs must be unique")
    for query in queries:
        if not isinstance(query.text, str):
            raise TypeError("query text must be a string")
        if query.answerable and not query.expected_chunk_ids:
            raise ValueError("answerable queries need expected chunks")
        if query.answerable and (
            not isinstance(query.expected_source_id, str)
            or not query.expected_source_id.strip()
            or type(query.expected_page_number) is not int
            or query.expected_page_number < 1
        ):
            raise ValueError(
                "answerable queries need expected source and page"
            )
        if not query.answerable and query.expected_chunk_ids:
            raise ValueError("no-evidence queries cannot expect chunks")


def evaluate_queries(
    index: LexicalIndex,
    queries: tuple[EvaluationQuery, ...],
) -> EvaluationReport:
    """Run every query once and report deterministic citation metrics."""
    if not isinstance(index, LexicalIndex):
        raise TypeError("index must be LexicalIndex")
    _validate_queries(queries)
    results: list[QueryEvaluation] = []
    for query in queries:
        hits = retrieve_lexical(index, query.text, limit=3)
        retrieved = tuple(hit.chunk.chunk_id for hit in hits)
        expected = set(query.expected_chunk_ids)
        recall_at_1 = bool(retrieved[:1] and retrieved[0] in expected)
        recall_at_3 = bool(expected.intersection(retrieved[:3]))
        citation_at_1 = bool(
            hits
            and recall_at_1
            and hits[0].chunk.source_id == query.expected_source_id
            and hits[0].chunk.page_number == query.expected_page_number
        )
        no_evidence_rejected = not query.answerable and not retrieved
        results.append(QueryEvaluation(
            query_id=query.query_id,
            retrieved_chunk_ids=retrieved,
            expected_chunk_ids=query.expected_chunk_ids,
            recall_at_1=recall_at_1,
            recall_at_3=recall_at_3,
            citation_at_1=citation_at_1,
            no_evidence_rejected=no_evidence_rejected,
        ))
    total = len(results) or 1
    answerable = [result for result, query in zip(results, queries)
                  if query.answerable]
    no_evidence = [result for result, query in zip(results, queries)
                   if not query.answerable]
    answerable_total = len(answerable) or 1
    no_evidence_total = len(no_evidence) or 1
    return EvaluationReport(
        results=tuple(results),
        recall_at_1=sum(r.recall_at_1 for r in answerable) / answerable_total,
        recall_at_3=sum(r.recall_at_3 for r in answerable) / answerable_total,
        citation_accuracy=(
            sum(r.citation_at_1 for r in answerable) / answerable_total
        ),
        no_evidence_accuracy=(
            sum(r.no_evidence_rejected for r in no_evidence)
            / no_evidence_total
        ),
    )

"""Validate the human-reviewed query boundary for the pilot."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from payer_policy.evaluation import EvaluationQuery


QUERY_CATEGORIES = frozenset({
    "coverage",
    "definition",
    "amendment",
    "report",
    "list",
    "numeric",
    "contact",
    "distractor",
    "no_evidence",
})
REVIEW_STATUSES = frozenset({
    "draft",
    "human_approved",
    "human_rejected",
    "needs_revision",
})


@dataclass(frozen=True)
class ValidatedPilotQuery:
    """Hold one immutable query after contract and chunk checks pass."""

    query_id: str
    category: str
    text: str
    answerable: bool
    expected_chunk_ids: tuple[str, ...]
    expected_source_id: str | None
    expected_page_number: int | None
    review_status: str
    review_note: str


def _required_text(record: Mapping[str, object], field: str) -> str:
    """Return one required nonempty text field or raise a contract error."""
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"query has invalid {field}")
    return value


def _approved_locations(
    approved_chunk_locations: Mapping[str, object],
) -> dict[str, tuple[str, int]]:
    """Normalize approved chunk locations without mutating caller data."""
    if not isinstance(approved_chunk_locations, Mapping):
        raise TypeError("approved_chunk_locations must be a mapping")
    normalized: dict[str, tuple[str, int]] = {}
    for chunk_id, location in approved_chunk_locations.items():
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("approved chunk IDs must be nonempty strings")
        if (
            not isinstance(location, (tuple, list))
            or len(location) != 2
        ):
            raise ValueError(f"invalid location for chunk {chunk_id}")
        source_id, page_number = location
        if (
            not isinstance(source_id, str)
            or not source_id.strip()
            or type(page_number) is not int
            or page_number < 1
        ):
            raise ValueError(f"invalid location for chunk {chunk_id}")
        normalized[chunk_id] = (source_id, page_number)
    return normalized


def _expected_chunk_ids(record: Mapping[str, object]) -> tuple[str, ...]:
    """Return unique expected chunk IDs in their declared order."""
    values = record.get("expected_chunk_ids")
    if not isinstance(values, (list, tuple)):
        raise ValueError("query has invalid expected_chunk_ids")
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("expected chunk IDs must be nonempty strings")
    result = tuple(values)
    if len(set(result)) != len(result):
        raise ValueError("expected chunk IDs must be unique")
    return result


def validate_query_set(
    records: object,
    approved_chunk_locations: Mapping[str, object],
    *,
    require_human_approval: bool = False,
) -> tuple[ValidatedPilotQuery, ...]:
    """Return immutable validated queries or reject the complete set.

    Answerable queries must cite one or more approved chunks from the same
    source and physical page. No-evidence queries must not carry a citation.
    Setting ``require_human_approval`` makes draft and unresolved records fail
    closed before final evaluation.
    """
    if not isinstance(records, (list, tuple)):
        raise TypeError("records must be a list or tuple")
    locations = _approved_locations(approved_chunk_locations)
    validated: list[ValidatedPilotQuery] = []
    seen: set[str] = set()
    for index, raw_record in enumerate(records):
        if not isinstance(raw_record, Mapping):
            raise ValueError(f"query record {index} is not an object")
        query_id = _required_text(raw_record, "query_id")
        if query_id in seen:
            raise ValueError(f"duplicate query_id: {query_id}")
        seen.add(query_id)
        category = _required_text(raw_record, "category")
        if category not in QUERY_CATEGORIES:
            raise ValueError(f"query {query_id} has invalid category")
        text = _required_text(raw_record, "text")
        answerable = raw_record.get("answerable")
        if type(answerable) is not bool:
            raise ValueError(f"query {query_id} has invalid answerable")
        expected_ids = _expected_chunk_ids(raw_record)
        source_id = raw_record.get("expected_source_id")
        page_number = raw_record.get("expected_page_number")
        status = _required_text(raw_record, "review_status")
        if status not in REVIEW_STATUSES:
            raise ValueError(f"query {query_id} has invalid review_status")
        note = raw_record.get("review_note", "")
        if not isinstance(note, str):
            raise ValueError(f"query {query_id} has invalid review_note")
        if status in {"human_rejected", "needs_revision"} and not note.strip():
            raise ValueError(
                f"query {query_id} needs a review note for status {status}"
            )
        if require_human_approval and status != "human_approved":
            raise ValueError(f"query {query_id} is not human approved")

        if answerable:
            if category == "no_evidence" or not expected_ids:
                raise ValueError(
                    f"answerable query {query_id} needs expected chunks"
                )
            if (
                not isinstance(source_id, str)
                or not source_id.strip()
                or type(page_number) is not int
                or page_number < 1
            ):
                raise ValueError(
                    f"answerable query {query_id} needs source and page"
                )
            expected_location = (source_id, page_number)
            for chunk_id in expected_ids:
                if chunk_id not in locations:
                    raise ValueError(
                        f"query {query_id} cites unknown chunk {chunk_id}"
                    )
                if locations[chunk_id] != expected_location:
                    raise ValueError(
                        f"query {query_id} has mismatched chunk provenance"
                    )
        else:
            if category != "no_evidence" or expected_ids:
                raise ValueError(
                    f"no-evidence query {query_id} cannot cite chunks"
                )
            if source_id is not None or page_number is not None:
                raise ValueError(
                    f"no-evidence query {query_id} cannot cite source/page"
                )

        validated.append(ValidatedPilotQuery(
            query_id=query_id,
            category=category,
            text=text,
            answerable=answerable,
            expected_chunk_ids=expected_ids,
            expected_source_id=source_id if answerable else None,
            expected_page_number=page_number if answerable else None,
            review_status=status,
            review_note=note,
        ))
    return tuple(validated)


def load_query_set_file(
    path: Path,
    approved_chunk_locations: Mapping[str, object],
    *,
    expected_sha256: str | None = None,
    require_human_approval: bool = False,
) -> tuple[ValidatedPilotQuery, ...]:
    """Read, hash-bind, decode, and validate one bounded query artifact."""
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("path must be an absolute Path")
    if expected_sha256 is not None and (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef"
               for character in expected_sha256)
    ):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
    try:
        if path.stat().st_size > 1_048_576:
            raise ValueError("query set is too large")
        body = path.read_bytes()
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError("query set cannot be read") from exc
    if len(body) > 1_048_576:
        raise ValueError("query set is too large")
    actual_sha256 = hashlib.sha256(body).hexdigest()
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise ValueError("query set SHA-256 does not match expected digest")
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("query set is not valid UTF-8 JSON") from exc
    return validate_query_set(
        decoded,
        approved_chunk_locations,
        require_human_approval=require_human_approval,
    )

def as_evaluation_queries(
    queries: tuple[ValidatedPilotQuery, ...],
    *,
    require_human_approval: bool = False,
) -> tuple[EvaluationQuery, ...]:
    """Convert validated query records into the existing evaluator contract."""
    if not isinstance(queries, tuple):
        raise TypeError("queries must be a tuple")
    if any(not isinstance(query, ValidatedPilotQuery) for query in queries):
        raise TypeError("queries must contain ValidatedPilotQuery instances")
    if require_human_approval and any(
        query.review_status != "human_approved" for query in queries
    ):
        raise ValueError("all queries must be human approved")
    return tuple(EvaluationQuery(
        query_id=query.query_id,
        text=query.text,
        expected_chunk_ids=query.expected_chunk_ids,
        answerable=query.answerable,
        expected_source_id=query.expected_source_id,
        expected_page_number=query.expected_page_number,
    ) for query in queries)

"""Serialize deterministic pilot chunks as local derived artifacts."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Mapping

from payer_policy.chunk_packing import PageChunk


SCHEMA_VERSION = 1
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_MAX_ARTIFACT_BYTES = 1_048_576


def chunk_to_record(chunk: PageChunk) -> dict[str, object]:
    """Return one JSON-safe chunk record with complete provenance."""
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "retrieval_id": chunk.retrieval_id,
        "pdf_sha256": chunk.pdf_sha256,
        "raw_text_sha256": chunk.raw_text_sha256,
        "selected_text_sha256": chunk.selected_text_sha256,
        "artifact_kind": chunk.artifact_kind,
        "quality_verdict": chunk.quality_verdict,
        "parser_name": chunk.parser_name,
        "parser_version": chunk.parser_version,
        "extraction_mode": chunk.extraction_mode,
        "page_number": chunk.page_number,
        "ordinal": chunk.ordinal,
        "start_offset": chunk.start_offset,
        "end_offset": chunk.end_offset,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "text": chunk.text,
        "word_count": chunk.word_count,
        "block_kinds": list(chunk.block_kinds),
        "boundary_note": chunk.boundary_note,
    }


def build_chunk_artifact(
    chunks: tuple[PageChunk, ...],
    *,
    input_manifest_sha256: str,
) -> dict[str, object]:
    """Build a stable artifact without changing any chunk text."""
    if not isinstance(chunks, tuple):
        raise TypeError("chunks must be a tuple")
    if not isinstance(input_manifest_sha256, str):
        raise TypeError("input_manifest_sha256 must be a string")
    if _SHA256_PATTERN.fullmatch(input_manifest_sha256) is None:
        raise ValueError("input_manifest_sha256 must be a SHA-256 hex digest")
    if any(not isinstance(chunk, PageChunk) for chunk in chunks):
        raise TypeError("chunks must contain PageChunk instances")
    records = [chunk_to_record(chunk) for chunk in chunks]
    return {
        "schema_version": SCHEMA_VERSION,
        "input_manifest_sha256": input_manifest_sha256,
        "chunk_count": len(records),
        "chunks": records,
    }


def _validate_chunk_records(chunks: list[object]) -> None:
    """Reject malformed, duplicated, or cross-identity chunk records."""
    seen: set[str] = set()
    required_digests = (
        "retrieval_id", "pdf_sha256", "raw_text_sha256",
        "selected_text_sha256",
    )
    for index, record in enumerate(chunks):
        if not isinstance(record, Mapping):
            raise ValueError(f"chunk record {index} is not an object")
        chunk_id = record.get("chunk_id")
        retrieval_id = record.get("retrieval_id")
        page_number = record.get("page_number")
        ordinal = record.get("ordinal")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError(f"chunk record {index} has no chunk_id")
        if chunk_id in seen:
            raise ValueError(f"duplicate chunk_id: {chunk_id}")
        seen.add(chunk_id)
        if (
            not isinstance(retrieval_id, str)
            or re.fullmatch(r"[0-9a-f]{32}", retrieval_id) is None
        ):
            raise ValueError(f"chunk record {index} has invalid retrieval_id")
        if type(page_number) is not int or page_number < 1:
            raise ValueError(f"chunk record {index} has invalid page_number")
        if type(ordinal) is not int or ordinal < 1:
            raise ValueError(f"chunk record {index} has invalid ordinal")
        expected_id = f"{retrieval_id}:p{page_number:04d}:c{ordinal:04d}"
        if chunk_id != expected_id:
            raise ValueError(f"chunk record {index} has mismatched chunk_id")
        for field in required_digests[1:]:
            value = record.get(field)
            if (
                not isinstance(value, str)
                or _SHA256_PATTERN.fullmatch(value) is None
            ):
                raise ValueError(f"chunk record {index} has invalid {field}")
        for field in (
            "source_id", "parser_name", "parser_version", "extraction_mode"
        ):
            value = record.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"chunk record {index} has invalid {field}")
        if record.get("artifact_kind") not in {"raw", "corrected"}:
            raise ValueError(f"chunk record {index} has invalid artifact_kind")
        if record.get("quality_verdict") not in {
            "usable", "usable_with_caveats"
        }:
            raise ValueError(
                f"chunk record {index} has invalid quality_verdict"
            )
        text = record.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError(f"chunk record {index} has invalid text")
        start = record.get("start_offset")
        end = record.get("end_offset")
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end
        ):
            raise ValueError(f"chunk record {index} has invalid offsets")
        line_start = record.get("line_start")
        line_end = record.get("line_end")
        if (
            type(line_start) is not int or type(line_end) is not int
            or not 1 <= line_start <= line_end
        ):
            raise ValueError(f"chunk record {index} has invalid line range")
        if record.get("word_count") != len(text.split()):
            raise ValueError(f"chunk record {index} has invalid word_count")
        block_kinds = record.get("block_kinds")
        if (
            not isinstance(block_kinds, list)
            or not block_kinds
            or any(
                not isinstance(kind, str) or not kind
                for kind in block_kinds
            )
        ):
            raise ValueError(f"chunk record {index} has invalid block_kinds")


def _validate_artifact_mapping(
    artifact: Mapping[str, object],
) -> dict[str, object]:
    """Validate the bounded JSON shape shared by writer and loader."""
    if not isinstance(artifact, Mapping):
        raise TypeError("artifact must be a mapping")
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported chunk artifact schema")
    digest = artifact.get("input_manifest_sha256")
    if (
        not isinstance(digest, str)
        or _SHA256_PATTERN.fullmatch(digest) is None
    ):
        raise ValueError("invalid input manifest digest")
    chunks = artifact.get("chunks")
    count = artifact.get("chunk_count")
    if type(count) is not int or not isinstance(chunks, list):
        raise ValueError("chunk artifact count or records is invalid")
    if count != len(chunks):
        raise ValueError("chunk artifact count does not match records")
    _validate_chunk_records(chunks)
    return dict(artifact)


def write_chunk_artifact(
    path: Path,
    artifact: Mapping[str, object],
) -> None:
    """Write one new JSON artifact and refuse to replace an existing file."""
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("path must be an absolute Path")
    validated = _validate_artifact_mapping(artifact)
    body = (json.dumps(validated, indent=2, ensure_ascii=False) + "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise FileExistsError(path) from None
        temporary.unlink()
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_chunk_artifact(path: Path) -> dict[str, object]:
    """Read and validate one bounded chunk artifact without rewriting it."""
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("path must be an absolute Path")
    try:
        if path.stat().st_size > _MAX_ARTIFACT_BYTES:
            raise ValueError("chunk artifact is too large")
        body = path.read_bytes()
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError("chunk artifact cannot be read") from exc
    if len(body) > _MAX_ARTIFACT_BYTES:
        raise ValueError("chunk artifact is too large")
    try:
        artifact = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("chunk artifact is not valid UTF-8 JSON") from exc
    if not isinstance(artifact, dict):
        raise ValueError("chunk artifact must be an object")
    return _validate_artifact_mapping(artifact)

"""Separate extraction JSON; never change the inspection wire contract.

JSON schema helpers in text_extraction.py validate complete page facts.
The private inspection JSON hooks reject duplicate keys and NaN unchanged:
../payer_policy/_inspection_protocol.py
"""
import json
from pathlib import Path

from payer_policy._inspection_protocol import _constant, _pairs
from payer_policy.text_extraction import (
    ExtractionError, PdfTextExtraction, extraction_facts,
    extraction_from_facts, validate_id,
)

REQUEST_BYTES = 65_536
RESULT_BYTES = 1_048_576
IDENTITY_KEYS = {
    "schema_version", "operation", "request_id", "retrieval_id",
    "requested_pages", "limits",
}


class ProtocolError(ValueError):
    """An extraction message is ambiguous, oversized or inconsistent."""


def encode(message: dict, limit: int) -> bytes:
    """Count full escaped JSON bytes, including metadata, before writing."""
    raw = json.dumps(message, ensure_ascii=True, allow_nan=False).encode()
    if len(raw) > limit:
        raise ProtocolError("oversized message")
    return raw


def decode(raw: bytes) -> dict:
    """Parse only a strict JSON object; reject deep or ambiguous messages."""
    try:
        message = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                             parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("invalid JSON") from exc
    if type(message) is not dict:
        raise ProtocolError("expected object")
    return message


def read_message(path: Path, limit: int) -> dict:
    """Read no more than limit plus one byte before decoding JSON."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
    except FileNotFoundError as exc:
        raise ProtocolError("missing message") from exc
    if len(raw) > limit:
        raise ProtocolError("oversized message")
    return decode(raw)


def publish(path: Path, message: dict, limit: int) -> None:
    """Close a bounded temporary message before replacing its destination.

    Path.replace publishes one IPC message, not a durable storage record:
    https://docs.python.org/3.11/library/pathlib.html#pathlib.Path.replace
    """
    raw = encode(message, limit)
    temporary = path.with_suffix(".tmp")
    with temporary.open("xb") as stream:
        stream.write(raw)
    temporary.replace(path)


def read_request(path: Path) -> dict:
    """Read the extraction request; never open its saved document here."""
    from payer_policy.text_extraction import limits_from_facts, validate_pages

    message = read_message(path, REQUEST_BYTES)
    try:
        if set(message) != IDENTITY_KEYS | {"root", "runtime"}:
            raise ValueError("invalid request keys")
        validate_id(message["request_id"])
        validate_id(message["retrieval_id"])
        if (type(message["schema_version"]) is not int
                or message["schema_version"] != 1
                or message["operation"] != "extract_text"
                or type(message["requested_pages"]) is not list):
            raise ValueError("invalid version, operation or pages")
        validate_pages(tuple(message["requested_pages"]))
        limits_from_facts(message["limits"])
        runtime = message["runtime"]
        if (type(runtime) is not dict
                or set(runtime) != {"base_prefix", "packages"}):
            raise ValueError("invalid runtime")
        for value in (message["root"], *runtime.values()):
            if (type(value) is not str or "\x00" in value
                    or not Path(value).is_absolute()
                    or value.startswith("\\")):
                raise ValueError("invalid local path")
    except (ValueError, TypeError, KeyError) as exc:
        raise ProtocolError("invalid request") from exc
    return message


def result_message(
    request: dict, extraction: PdfTextExtraction | None = None,
    *, status: str = "ok",
) -> dict:
    """Bind a complete result or empty error to the exact request."""
    message = {key: request[key] for key in IDENTITY_KEYS}
    message.update(status=status, facts=(
        extraction_facts(extraction) if extraction is not None else None))
    return message


def read_result(path: Path, request: dict) -> PdfTextExtraction:
    """Accept only matching complete facts; raise a typed child failure."""
    from payer_policy.text_extraction import CHILD_ERRORS

    message = read_message(path, RESULT_BYTES)
    if set(message) != IDENTITY_KEYS | {"status", "facts"}:
        raise ProtocolError("invalid result keys")
    try:
        validate_id(message["request_id"])
        validate_id(message["retrieval_id"])
        if (type(message["schema_version"]) is not int
                or message["schema_version"] != 1
                or message["operation"] != "extract_text"
                or any(message[key] != request[key] for key in IDENTITY_KEYS)):
            raise ValueError("result does not match request")
        from payer_policy.text_extraction import (
            limits_from_facts, validate_pages,
        )
        if type(message["requested_pages"]) is not list:
            raise ValueError("invalid page array")
        validate_pages(tuple(message["requested_pages"]))
        limits_from_facts(message["limits"])
        status = message["status"]
        if type(status) is not str:
            raise ValueError("invalid status")
        if status in CHILD_ERRORS and message["facts"] is None:
            raise ExtractionError(status)
        if status != "ok":
            raise ValueError("invalid result status")
        result = extraction_from_facts(message["facts"])
        if (result.retrieval_id != request["retrieval_id"]
                or list(result.requested_pages) != request["requested_pages"]
                or message["facts"]["limits"] != request["limits"]):
            raise ValueError("facts do not match request")
        encode(message, result.limits.max_result_bytes)
    except (TypeError, ValueError, KeyError, RecursionError) as exc:
        raise ProtocolError("invalid result facts") from exc
    return result

"""Fixed, byte-bounded JSON for one inspection attempt, never executable data.

JSON hooks reject duplicate keys and nonstandard constants before meaning
is lost; read limit+1 distinguishes full messages from oversized ones:
https://docs.python.org/3.11/library/json.html
This does not defend against a hostile process with the same file access.
"""
import json
import re
from pathlib import Path
from typing import Any

MESSAGE_BYTES = 65_536
CHILD_ERRORS = frozenset({
    "input_error", "storage_error", "parser_error", "memory_error",
})
IDENTITY_KEYS = {"schema_version", "operation", "request_id", "retrieval_id"}


class ProtocolError(ValueError):
    """A message is absent, ambiguous, oversized or outside the schema."""


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build an object only when every JSON key appears once."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    """Reject nonstandard numbers rather than treating them as facts."""
    raise ProtocolError("nonstandard constant")


def read_message(path: Path) -> dict[str, Any]:
    """Read one bounded JSON object; preserve real OS read failures."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(MESSAGE_BYTES + 1)
    except FileNotFoundError as exc:
        raise ProtocolError("missing message") from exc
    if len(raw) > MESSAGE_BYTES:
        raise ProtocolError("oversized message")
    try:
        message = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                             parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("invalid JSON") from exc
    if type(message) is not dict:
        raise ProtocolError("expected object")
    return message


def _identity(message: dict[str, Any]) -> None:
    """Require the fixed version/operation and exact lowercase IDs."""
    if (type(message.get("schema_version")) is not int
            or message["schema_version"] != 1
            or message.get("operation") != "inspect"):
        raise ProtocolError("invalid operation or version")
    for key in ("request_id", "retrieval_id"):
        value = message.get(key)
        if (type(value) is not str
                or re.fullmatch(r"[0-9a-f]{32}", value) is None):
            raise ProtocolError("invalid identity")


def read_request(path: Path) -> dict[str, Any]:
    """Validate the fixed inspection request without reading saved data."""
    message = read_message(path)
    _identity(message)
    if set(message) != IDENTITY_KEYS | {"root", "max_bytes", "runtime"}:
        raise ProtocolError("invalid request keys")
    maximum = message["max_bytes"]
    if type(maximum) is not int or not 0 < maximum <= 10_000_000:
        raise ProtocolError("invalid input budget")
    runtime = message["runtime"]
    if (type(runtime) is not dict
            or set(runtime) != {"base_prefix", "packages"}):
        raise ProtocolError("invalid runtime")
    paths = (message["root"], runtime["base_prefix"], runtime["packages"])
    for value in paths:
        if (type(value) is not str or "\x00" in value
                or not Path(value).is_absolute() or value.startswith("\\\\")):
            raise ProtocolError("invalid local path")
    return message


def publish(path: Path, message: dict[str, Any]) -> None:
    """Replace a result only after the complete bounded JSON file is closed.

    Path.replace is an OS rename, not a durability or hostile-user defense:
    https://docs.python.org/3.11/library/pathlib.html#pathlib.Path.replace
    Real write failures remain OS errors for the supervisor to classify.
    """
    raw = json.dumps(message, ensure_ascii=True, allow_nan=False).encode()
    if len(raw) > MESSAGE_BYTES:
        raise ProtocolError("oversized message")
    temporary = path.with_suffix(".tmp")
    with temporary.open("xb") as stream:
        stream.write(raw)
    temporary.replace(path)


def read_result(
    path: Path, request_id: str, retrieval_id: str,
) -> dict[str, Any]:
    """Accept only matching, complete facts or allowlisted error codes."""
    message = read_message(path)
    _identity(message)
    if (set(message) != IDENTITY_KEYS | {"status", "facts"}
            or message["request_id"] != request_id
            or message["retrieval_id"] != retrieval_id):
        raise ProtocolError("result does not match request")
    status, facts = message["status"], message["facts"]
    if type(status) is not str:
        raise ProtocolError("invalid status")
    if status in CHILD_ERRORS and facts is None:
        return message
    if status != "ok" or type(facts) is not dict:
        raise ProtocolError("invalid result")
    if set(facts) != {"sha256", "is_encrypted", "page_count"}:
        raise ProtocolError("invalid facts")
    digest, encrypted, pages = (
        facts["sha256"], facts["is_encrypted"], facts["page_count"])
    if (type(digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or type(encrypted) is not bool):
        raise ProtocolError("invalid fingerprint or encryption")
    if (encrypted and pages is not None) or (not encrypted and (
            type(pages) is not int or pages < 0)):
        raise ProtocolError("invalid page count")
    return message

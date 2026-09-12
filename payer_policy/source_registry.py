"""Source definition validation; no network access or trust inference."""
import json
import re
from pathlib import Path
from collections.abc import Mapping
from typing import Dict, List, Tuple, NoReturn
from urllib.parse import urlsplit


REQUIRED_FIELDS = (
    "source_id", "name", "url", "publisher", "category", "plan", "program",
    "applicability_status", "evidence_url", "access_restrictions",
)
APPLICABILITY_STATUSES = (
    "unknown", "needs_review", "reference", "outside_scope",
    "confirmed_applicable",
)


class RegistryValidationError(ValueError):
    """A registry has invalid content and cannot be loaded partially."""


def _unique_json_object(pairs: List[Tuple[str, object]]) -> dict:
    """Reject duplicate JSON keys instead of letting decoding overwrite."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise RegistryValidationError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    """Disallow NaN and Infinity, which are not JSON numbers."""
    raise RegistryValidationError(f"JSON: unsupported constant {value}")


def parse_source_registry(text: str) -> Dict[str, dict]:
    """Parse and validate an entire registry, preserving values and order."""
    try:
        data = json.loads(
            text, object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise RegistryValidationError(
            f"JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(data, dict):
        raise RegistryValidationError("registry: expected an object")
    version = data.get("schema_version")
    if type(version) is not int or version != 1:
        raise RegistryValidationError("schema_version: expected integer 1")
    if not isinstance(data.get("sources"), list):
        raise RegistryValidationError("sources: expected a list")
    result: Dict[str, dict] = {}
    for index, source in enumerate(data["sources"]):
        errors = validate_source_definition(source)
        if errors:
            raise RegistryValidationError(
                f"sources[{index}]: " + "; ".join(errors)
            )
        source_id = source["source_id"]
        if source_id in result:
            raise RegistryValidationError(
                f"sources[{index}]: duplicate source_id {source_id!r}"
            )
        result[source_id] = source
    return result


def load_source_registry(path: Path) -> Dict[str, dict]:
    """Read a UTF-8 registry, propagating file and decoding errors.

    Invalid registry content raises RegistryValidationError. No network access
    occurs and no partial registry is returned. Paths are caller-selected.
    """
    return parse_source_registry(path.read_text(encoding="utf-8"))


def validate_source_definition(source: object) -> List[str]:
    """Return field-prefixed errors without modifying a source mapping.

    An empty result means structurally valid, not reviewed or authoritative.
    Evidence may be empty unless applicability is claimed as confirmed.
    """
    if not isinstance(source, Mapping):
        return ["source: expected a mapping"]
    errors: List[str] = []
    for field in REQUIRED_FIELDS:
        value = source.get(field)
        if not isinstance(value, str):
            errors.append(f"{field}: required string")
        elif not value.strip() and not (field == "evidence_url" and value == ""):
            errors.append(f"{field}: must not be blank")
    if errors:
        return errors
    if not re.fullmatch(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", source["source_id"]):
        errors.append("source_id: use lowercase letters/digits with - or _")
    status = source["applicability_status"]
    if status not in APPLICABILITY_STATUSES:
        errors.append("applicability_status: unsupported value")
    if status == "confirmed_applicable" and not source["evidence_url"]:
        errors.append("evidence_url: required for confirmed applicability")
    for field in ("url", "evidence_url"):
        value = source[field]
        if field == "evidence_url" and value == "":
            continue
        try:
            # Inspect the original before urlsplit can discard controls.
            if any(
                char.isspace() or ord(char) < 32 or 0x7F <= ord(char) <= 0x9F
                for char in value
            ):
                raise ValueError
            if "\\" in value or re.search(r"%(?![0-9a-fA-F]{2})", value):
                raise ValueError
            parts = urlsplit(value)
            host = parts.hostname or ""
            label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
            if (
                parts.scheme not in ("http", "https")
                or not re.fullmatch(label + r"(?:\." + label + r")*", host)
                or len(host) > 253
                or parts.username is not None
                or parts.password is not None
                or parts.netloc.endswith(":")
                or parts.port == 0
            ):
                raise ValueError
        except ValueError:
            errors.append(
                f"{field}: expected an HTTP(S) URL with DNS host "
                "and no credentials, whitespace, or invalid port"
            )
    return errors

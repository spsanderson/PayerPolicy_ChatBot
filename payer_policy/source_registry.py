"""Source definition validation; no network access or trust inference."""
import re
from collections.abc import Mapping
from typing import List
from urllib.parse import urlsplit


REQUIRED_FIELDS = (
    "source_id", "name", "url", "publisher", "category", "plan", "program",
    "applicability_status", "evidence_url", "access_restrictions",
)
APPLICABILITY_STATUSES = (
    "unknown", "needs_review", "reference", "outside_scope",
    "confirmed_applicable",
)


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
            if any(char.isspace() or ord(char) < 32 for char in value):
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

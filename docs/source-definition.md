# Source definition contract

`validate_source_definition(source: object) -> List[str]`

Returns `[]` when structurally valid, otherwise field-prefixed error messages.
Accepts a mapping and never changes it. Invalid containers return a clear error.
Required-field errors are reported first; format checks run once required
strings are present. Extra fields are currently ignored, not removed.

## Required fields

| Field | Contract |
|---|---|
| source_id | Lowercase letters/digits separated by single hyphens or underscores; no automatic normalization |
| name | Nonblank display name |
| url | Absolute HTTP(S) URL with ASCII DNS-style hostname |
| publisher | Nonblank publisher label; not proof of official ownership |
| category | Nonblank source category; vocabulary not yet restricted |
| plan | Nonblank plan association |
| program | Nonblank benefit-program association |
| applicability_status | unknown, needs_review, reference, outside_scope, or confirmed_applicable |
| evidence_url | Required string; may be empty unless confirmed_applicable |
| access_restrictions | Nonblank access notes; use an explicit unreviewed note when unknown |

URLs cannot contain credentials, whitespace/control characters (including
DEL and the full U+0080–U+009F C1 range), backslashes,
malformed percent escapes, or invalid ports. DNS-style host labels are checked;
IPv6 literals and unencoded internationalized hostnames are not supported in
this first contract. Original casing, encoding, paths, and query values remain
untouched. Source IDs are validated before any lookup; nothing is repaired.

The validator does not resolve DNS, check HTTP responses, inspect robots rules,
confirm ownership, review evidence, or grant permission to download. A valid URL
can still point to a private destination. Future fetching must enforce separate
address/redirect/size/time limits. No downloader should rely on this function
as its network security boundary.

## Runnable offline example (illustrative, not a reviewed source)

Run Python from the repository root:

```python
from payer_policy.source_registry import validate_source_definition

source = {
    "source_id": "example-source",
    "name": "Example policy resources",
    "url": "https://example.org/policies",
    "publisher": "Example publisher",
    "category": "plan_resources",
    "plan": "Empire Plan",
    "program": "Hospital Program",
    "applicability_status": "unknown",
    "evidence_url": "",
    "access_restrictions": "Not yet reviewed",
}
errors = validate_source_definition(source)
assert errors == []
assert source["applicability_status"] == "unknown"
```

Confirmed status is a caller-supplied claim requiring a structurally valid
supporting URL, not an automated finding. The loader validates structure, not
the truth of review evidence. Individual documents still require applicability
review. One reviewed reference entry ships; no network connector exists.

## Registry format and loading

```json
{"schema_version": 1, "sources": []}
```

- `parse_source_registry(text: str) -> Dict[str, dict]` accepts JSON text.
- `load_source_registry(path: Path) -> Dict[str, dict]` reads a local UTF-8 file.
- Both return an insertion-ordered mapping keyed by exact source IDs.
- Version must be integer `1` (not a boolean, float, or string).
- `sources` must be a list; an explicitly empty list is valid.
- Duplicate JSON keys anywhere, duplicate source IDs, malformed JSON, NaN,
  Infinity, or invalid source entries raise `RegistryValidationError`.
- Entry errors include the zero-based `sources[index]` and field. Parsing stops
  at the first invalid entry; no partial result is returned.
- File-access errors remain `OSError` subclasses; invalid UTF-8 raises
  `UnicodeDecodeError`. Missing files never masquerade as empty registries.
- UTF-8 BOM is rejected by the JSON decoder. Save without BOM.
- Extra source metadata is preserved, not authenticated. Extra envelope fields
  are currently ignored. Values, URLs, and identifiers are not normalized.
- Caller-selected files are read wholly into memory; this is not an untrusted
  upload interface or a network security boundary.

See the [README loading example](../README.md) and the
[checked-in reference review](source-reviews/anthem-empire-plan-overview.md).

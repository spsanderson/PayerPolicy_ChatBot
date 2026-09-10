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
supporting URL, not an automated finding. A registry loader and review process
will control trusted entries. Individual documents still require applicability
review. No real registry entry or network connector ships in this increment.

# Offline PDF-candidate validation

## Purpose and boundary

`validate_pdf_candidate(result: FetchResult) -> None` is implemented in
[`payer_policy/document_validation.py`](../payer_policy/document_validation.py).
It checks the response's label and opening marker, like checking a package
before opening it. A login page returned instead of a PDF must not quietly
become a policy document.

**Passing means PDF candidate, not valid PDF or applicable policy.** Even the
five bytes `%PDF-` can pass. Structural parsing, readability, malware safety,
source authority, coverage dates and permission to collect/reuse are not checked.

This is a standalone helper. It does not call the transport, write a library,
or connect the source registry to downloads. Offline tests explicitly pass a
transport result to it; no acquisition worker has been built.

## Contract

The input is the existing
[`FetchResult`](../payer_policy/https_transport.py), which keeps the final URL,
HTTP status, original header pairs (including duplicates), and body bytes.

- Return `None` when every candidate rule passes.
- Raise `DocumentValidationError` (a `ValueError`) for rejected responses.
  Messages name the failed rule without including response content.
- Raise `TypeError` for a wrong response object, non-bytes body, non-integer
  status (including booleans), or headers not shaped as a tuple of two-string
  tuples. Do not silently convert lists, mutable buffers, or strings.
- Stop at the first detected problem; this is not an all-errors report.
- Keep the response fields and exact bytes unchanged, on success or failure.
- Do not perform network/file operations, decompress, or validate the URL.
  A manually constructed `FetchResult` is not evidence of a safe connection.

### Exact acceptance rules

| Field | Rule |
|---|---|
| Status | Exactly integer `200`; other statuses, including `204` and `206`, reject. |
| `Content-Range` | Must be absent, even on a 200 response and even if empty. |
| Body | Nonempty immutable `bytes`. |
| `Content-Type` | Exactly one header, with the bare value `application/pdf`. Missing, empty, duplicate (even identical), comma-separated, or parameterized values reject. |
| `Content-Encoding` | Absent, or exactly one `identity` value. Empty/duplicate values, lists, parameters, and other encodings reject. |
| Opening marker | Exact case-sensitive `%PDF-` at byte zero; no preceding whitespace or byte-order mark. |

Header names are compared without regard to case. For the two supported header
values, comparison ignores case and surrounding ASCII spaces/tabs only. The
original values are not rewritten. Newlines and other whitespace are not
silently stripped. Unrelated string header pairs are ignored; this is not a
complete HTTP header-syntax validator. Duplicate relevant headers are never
collapsed into a dictionary.

These are intentionally strict application rules, not a full HTTP/PDF parser.
A genuine PDF with an unusual server label can be rejected. Compatibility
exceptions require separate evidence and review, not a silent fallback.

### Why these methods

- [RFC 8118, section 8](https://www.rfc-editor.org/rfc/rfc8118.html#section-8)
  registers `application/pdf`, defines no media-type parameters, and identifies
  `%PDF-` followed by a version as the opening signature. This helper checks
  only the marker, not the version or file structure.
- [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html), sections 5.1 and 8.3.1,
  describes case-insensitive field names and media-type tokens. Sections 14.4
  and 15.3.7 describe range metadata and partial responses. This project rejects
  range responses rather than attempting to assemble fragments.
- Exact comparisons and a prefix check need no parser package, no decoding of
  the document, and no copy of the body. Work scales with supplied headers,
  not with the PDF's contents beyond its opening marker.
- The [transport](https-transport.md) owns connection, framing and byte limits.
  This helper does not repeat them or impose a new download-size setting.
  Callers supplying their own response objects must manage resource limits.

## Runnable offline example

From Python launched at the repository root:

```python
from payer_policy.document_validation import (
    DocumentValidationError, validate_pdf_candidate,
)
from payer_policy.https_transport import FetchResult

# Synthetic bytes only: deliberately not a structurally valid PDF.
result = FetchResult(
    url="https://example.org/document",
    status=200,
    headers=(("Content-Type", "application/pdf"),),
    body=b"%PDF-",
)
assert validate_pdf_candidate(result) is None
assert result.body == b"%PDF-"

login_page = FetchResult(
    url="https://example.org/document.pdf",
    status=200,
    headers=(("Content-Type", "application/pdf"),),
    body=b"<html>login required</html>",
)
try:
    validate_pdf_candidate(login_page)
except DocumentValidationError as error:
    print(error)  # body must start with %PDF-
else:
    raise AssertionError("The mislabeled login page was accepted")
```

## Verification

Baseline: Python 3.11.16; documented minimum remains Python 3.11.

- 64 offline test methods pass, including synthetic input/rejection matrices,
  unchanged-response checks, and guarded file/socket entry points.
- Offline composition tests use the real transport HTTP parser with controlled
  sockets: fixed-length and chunked candidates pass; HTML fails even when
  labeled `application/pdf`.
- The separate real local TLS test passes using an OpenSSL-generated temporary
  certificate. It verifies transport behavior, not public-source access.
- No policy documents were downloaded or copied into tests. No third-party
  runtime dependency, registry permission, or storage behavior was added.

The original 51 offline methods remain covered. The new checks do not establish
that a real policy document can be safely parsed, indexed, or redistributed.
Original-file storage, structural parsing, and live application acquisition
remain separate approval gates.

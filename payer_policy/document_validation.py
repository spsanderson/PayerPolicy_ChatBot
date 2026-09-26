"""Offline PDF-candidate checks, not structural or policy validation.

RFC 8118 section 8 registers application/pdf without parameters and describes
its opening marker:
https://www.rfc-editor.org/rfc/rfc8118.html#section-8.
RFC 9110 sections 5.1 and 8.3.1 define case-insensitive field names and
media-type tokens:
https://www.rfc-editor.org/rfc/rfc9110.html. Exact single-value comparisons are
our conservative acceptance policy, not a general HTTP header parser.
"""
from payer_policy.https_transport import FetchResult


class DocumentValidationError(ValueError):
    """A response failed the shallow PDF-candidate rules."""


def validate_pdf_candidate(result: FetchResult) -> None:
    """Return None for a candidate; reject content or incorrect input types.

    FetchResult (https_transport.py) preserves raw body bytes and duplicate
    headers; keep those duplicates visible rather than collapse them to a dict.
    Require HTTP 200, no Content-Range, nonempty bytes, one bare PDF type,
    absent/identity encoding, and %PDF- at byte zero. Raise
    DocumentValidationError for rejected responses, TypeError for wrong types.
    No I/O, decompression, mutation, URL approval, or structural PDF checks.
    Even b"%PDF-" can pass; passing is not proof of a valid or safe document.
    """
    if not isinstance(result, FetchResult):
        raise TypeError("result must be a FetchResult")
    if not isinstance(result.body, bytes):
        raise TypeError("body must be immutable bytes")
    if type(result.status) is not int:
        raise TypeError("status must be an integer")
    if not isinstance(result.headers, tuple):
        raise TypeError("headers must be a tuple of string pairs")
    if result.status != 200:
        raise DocumentValidationError("PDF candidate requires HTTP 200")
    for pair in result.headers:
        if (not isinstance(pair, tuple) or len(pair) != 2 or
                not all(isinstance(value, str) for value in pair)):
            raise TypeError("headers must be a tuple of string pairs")
    if any(name.lower() == "content-range" for name, _ in result.headers):
        raise DocumentValidationError("Content-Range is not accepted")
    if not result.body:
        raise DocumentValidationError("PDF candidate body is empty")
    content_types = [value.strip(" \t").lower()
                     for name, value in result.headers
                     if name.lower() == "content-type"]
    if content_types != ["application/pdf"]:
        raise DocumentValidationError(
            "require one Content-Type: application/pdf without parameters")
    encodings = [value.strip(" \t").lower()
                 for name, value in result.headers
                 if name.lower() == "content-encoding"]
    if encodings not in ([], ["identity"]):
        raise DocumentValidationError(
            "Content-Encoding must be absent or one identity value")
    if not result.body.startswith(b"%PDF-"):
        raise DocumentValidationError("body must start with %PDF-")

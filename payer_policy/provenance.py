"""Document content provenance; no network or filesystem side effects."""
from hashlib import sha256


def fingerprint_document(content: bytes) -> str:
    """Return a SHA-256 hex digest of exact, unmodified document bytes.

    This identifies content, not authenticity, plan applicability, or dates.
    """
    if not isinstance(content, bytes):
        raise TypeError("content must be immutable bytes")
    return sha256(content).hexdigest()

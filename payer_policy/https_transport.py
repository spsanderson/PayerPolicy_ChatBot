"""Small HTTPS GET transport pinned to a checked numeric address.

The address check is in :mod:`payer_policy.network_safety`. This module is not
an authorization to crawl or proof that a retrieved policy applies to a plan.
"""
import http.client
import ipaddress
import math
import socket
import ssl
from collections.abc import Collection
from dataclasses import dataclass
from typing import BinaryIO
from urllib.parse import urlsplit

from payer_policy.network_safety import (
    NetworkSafetyError, validate_destination_url, validate_redirect,
    validate_resolved_addresses,
)


class TransportError(OSError):
    """A checked request could not complete safely."""


@dataclass(frozen=True)
class FetchResult:
    """Return the final request URL, response status, headers, and raw bytes."""

    url: str
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


class _LimitedHeaderReader:
    """Share one byte budget across headers and chunk metadata, not payload."""

    def __init__(self, stream: BinaryIO) -> None:
        """Keep the response stream and cumulative metadata count."""
        self.stream = stream
        self.total = 0

    def readline(self, limit: int = -1) -> bytes:
        """Count status, header, chunk-size, and trailer lines before parsing."""
        remaining = 65_536 - self.total + 1
        size = remaining if limit < 0 else min(limit, remaining)
        line = self.stream.readline(size)
        self.count(len(line))
        return line

    def count(self, size: int) -> None:
        """Charge metadata bytes, rejecting anything beyond the shared cap."""
        self.total += size
        if self.total > 65_536:
            raise TransportError(
                "response headers exceed 64 KiB including framing/trailers")

    def read(self, size: int = -1) -> bytes:
        """Pass payload reads through; fetch_https enforces their size limit."""
        return self.stream.read(size)

    def flush(self) -> None:
        """Forward HTTPResponse.close's flush before closing the input file."""
        self.stream.flush()

    def close(self) -> None:
        """Close the wrapped file when HTTPResponse finishes or fails."""
        self.stream.close()


class _BoundedHTTPResponse(http.client.HTTPResponse):
    """Limit headers and chunk metadata throughout a response.

    HTTPResponse reads status, headers, chunk sizes, and trailers via readline;
    chunk separators use read instead. Keep both under one budget. This uses
    a private parser hook, so rerun transport tests on Python upgrades. See:
    https://github.com/python/cpython/blob/3.11/Lib/http/client.py.
    """

    def begin(self) -> None:
        """Keep line counting active through the final chunk and trailers."""
        if self.headers is not None:
            return
        self.fp = _LimitedHeaderReader(self.fp)
        try:
            super().begin()
        except BaseException:
            self.close()
            raise

    def _get_chunk_left(self) -> int | None:
        """Charge the separator that Python reads outside readline().

        The linked CPython implementation reads two separator bytes when
        chunk_left is zero, then reads the next size and trailers as lines.
        Reserve those two bytes first; payload reads stay outside this budget.
        """
        if self.chunk_left == 0:
            self.fp.count(2)
        return super()._get_chunk_left()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to one validated IP while TLS still checks the original host.

    HTTPSConnection normally resolves its ``host`` in ``connect``. Replacing
    that step avoids a second unchecked lookup; the SSL context still checks
    the certificate for ``server_hostname``. See
    https://docs.python.org/3/library/http.client.html#http.client.HTTPSConnection
    and https://docs.python.org/3/library/ssl.html#ssl.SSLContext.wrap_socket.
    """

    response_class = _BoundedHTTPResponse

    def __init__(self, host: str, address: tuple, family: socket.AddressFamily,
                 *, timeout: float, context: ssl.SSLContext) -> None:
        """Keep the approved host and its selected numeric TCP endpoint."""
        super().__init__(host, port=443, timeout=timeout, context=context)
        self._address = address
        self._family = family

    def connect(self) -> None:
        """Check the connected peer before wrapping the socket in verified TLS."""
        raw = socket.socket(self._family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        try:
            raw.settimeout(self.timeout)
            raw.connect(self._address)
            peer = raw.getpeername()
            if (ipaddress.ip_address(peer[0]) !=
                    ipaddress.ip_address(self._address[0]) or
                    peer[1] != self._address[1]):
                raise TransportError("connected peer differs from checked address")
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _resolve_checked_address(host: str) -> tuple[socket.AddressFamily, tuple]:
    """Reject all unsafe TCP answers before selecting the first endpoint.

    getaddrinfo supplies family/type/protocol and numeric socket addresses
    (https://docs.python.org/3/library/socket.html#socket.getaddrinfo).
    validate_resolved_addresses in network_safety.py rejects the full answer
    set if even one address is restricted; no partial safe subset is used.
    """
    answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM,
                                 proto=socket.IPPROTO_TCP)
    addresses = []
    for family, socktype, proto, _canonical, sockaddr in answers:
        if (family not in (socket.AF_INET, socket.AF_INET6) or
                socktype != socket.SOCK_STREAM or
                proto != socket.IPPROTO_TCP or
                not isinstance(sockaddr, tuple) or
                len(sockaddr) != (2 if family == socket.AF_INET else 4) or
                sockaddr[1] != 443 or
                (family == socket.AF_INET6 and sockaddr[2:] != (0, 0))):
            raise NetworkSafetyError("invalid TCP address answer")
        addresses.append(sockaddr[0])
    validate_resolved_addresses(addresses)
    return answers[0][0], answers[0][4]


def fetch_https(url: str, allowed_hosts: Collection[str], *,
                max_redirects: int = 3, timeout: float = 10,
                max_bytes: int = 10_000_000) -> FetchResult:
    """Fetch checked HTTPS bytes with fresh validation at every redirect.

    network_safety.py's URL and redirect checks require the same reviewed
    host allowlist for each hop; its address check rejects mixed DNS answers.
    No proxies, retries, filesystem writes, or source applicability decisions
    are made. Positive finite time/body limits are required. A socket timeout
    does not bound operating-system DNS resolution.
    """
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("timeout must be positive and finite")
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    if type(max_redirects) is not int or max_redirects < 0:
        raise ValueError("max_redirects must be a nonnegative integer")
    validate_destination_url(url, allowed_hosts)
    visited = [url]
    while True:
        current = visited[-1]
        parts = urlsplit(current)
        host = parts.hostname
        if host is None:
            raise NetworkSafetyError("URL must include a hostname")
        target = (parts.path or "/") + (
            "?" + parts.query if "?" in current else ""
        )
        if not target.isascii():
            raise NetworkSafetyError("request path/query must be ASCII encoded")
        try:
            family, address = _resolve_checked_address(host)
            context = ssl.create_default_context()
            connection = _PinnedHTTPSConnection(
                host, address, family, timeout=timeout, context=context,
            )
            try:
                connection.request("GET", target, headers={
                    "Host": parts.netloc, "Accept-Encoding": "identity",
                    "Connection": "close",
                })
                response = connection.getresponse()
                headers = tuple(response.getheaders())
                if response.status in (301, 302, 303, 307, 308):
                    locations = [value for name, value in headers
                                 if name.lower() == "location"]
                    if len(locations) != 1:
                        raise TransportError("redirect requires one Location")
                    next_url = validate_redirect(
                        current, locations[0], allowed_hosts, visited,
                        max_redirects,
                    )
                elif 200 <= response.status < 300:
                    lengths = [value for name, value in headers
                               if name.lower() == "content-length"]
                    encodings = [value for name, value in headers
                                 if name.lower() == "transfer-encoding"]
                    if (len(lengths) > 1 or len(encodings) > 1 or
                            (lengths and encodings) or
                            (encodings and encodings[0].lower() != "chunked") or
                            (lengths and not lengths[0].isascii()) or
                            (lengths and not lengths[0].isdecimal())):
                        raise TransportError("invalid response framing")
                    declared = int(lengths[0]) if lengths else None
                    if declared is not None and declared > max_bytes:
                        raise TransportError("response exceeds max_bytes")
                    body = response.read(max_bytes + 1)
                    if len(body) > max_bytes:
                        raise TransportError("response exceeds max_bytes")
                    if declared is not None and len(body) != declared:
                        raise TransportError("incomplete response body")
                    return FetchResult(current, response.status, headers, body)
                else:
                    raise TransportError(
                        f"HTTP status {response.status} not accepted")
            finally:
                connection.close()
        except (NetworkSafetyError, TransportError):
            raise
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise TransportError("HTTPS request failed") from exc
        visited.append(next_url)

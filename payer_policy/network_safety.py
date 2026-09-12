"""Pure network policy checks; these helpers never resolve or connect."""
import ipaddress
import re
from collections.abc import Collection as CollectionABC, Mapping
from collections.abc import Sequence as SequenceABC
from typing import Collection, Sequence, Tuple
from urllib.parse import SplitResult, urljoin, urlsplit


# Explicit conservative exclusions supplement version-dependent ipaddress data.
_IPV4_EXCLUSIONS = tuple(ipaddress.ip_network(cidr) for cidr in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
    "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24",
    "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
))
_IPV6_GLOBAL_UNICAST = ipaddress.ip_network("2000::/3")
_IPV6_EXCLUSIONS = tuple(ipaddress.ip_network(cidr) for cidr in (
    "2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20",
))


class NetworkSafetyError(ValueError):
    """An input violates the acquisition destination policy."""


def _validate_raw_reference(value: str) -> SplitResult:
    """Check raw text before urllib can discard controls or repair input."""
    if not isinstance(value, str):
        raise NetworkSafetyError("URL/reference must be a string")
    if not value:
        raise NetworkSafetyError("URL/reference must not be empty")
    if any(c.isspace() or ord(c) < 32 or 0x7F <= ord(c) <= 0x9F
           for c in value):
        raise NetworkSafetyError("URL contains whitespace or control")
    if "\\" in value:
        raise NetworkSafetyError("URL contains backslash")
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise NetworkSafetyError("URL contains malformed percent escape")
    if "#" in value:
        raise NetworkSafetyError("URL fragments are not permitted")
    try:
        return urlsplit(value)
    except ValueError as exc:
        raise NetworkSafetyError("malformed URL/reference") from exc


def _valid_hostname(host: str) -> bool:
    """Accept ASCII DNS labels, excluding numeric resolver alternatives."""
    if not isinstance(host, str) or not host.isascii() or len(host) > 253:
        return False
    label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    if not re.fullmatch(label + r"(?:\." + label + r")*", host):
        return False
    # Legacy resolvers interpret dotted, octal, and hex integers as IPv4.
    return not all(re.fullmatch(r"(?:[0-9]+|0[xX][0-9a-fA-F]+)", part)
                   for part in host.split("."))


def _validate_allowlist(allowed_hosts: Collection[str]) -> None:
    """Reject malformed reviewed configuration rather than normalizing it."""
    if (not isinstance(allowed_hosts, CollectionABC)
            or isinstance(allowed_hosts, (str, bytes, Mapping))):
        raise NetworkSafetyError("allowlist must be a collection of hostnames")
    for host in allowed_hosts:
        if not _valid_hostname(host) or host != host.lower():
            raise NetworkSafetyError("allowlist requires lowercase DNS hosts")


def _request_identity(url: str) -> Tuple[str, int, str, str]:
    """Compare validated requests without decoding or query reordering."""
    parts = urlsplit(url)
    return (parts.hostname, parts.port or 443, parts.path or "/", parts.query)


def validate_redirect(
    current_url: str, location: str, allowed_hosts: Collection[str],
    visited_urls: Sequence[str], max_redirects: int,
) -> str:
    """Resolve a redirect reference into an approved absolute URL."""
    validate_destination_url(current_url, allowed_hosts)
    reference = _validate_raw_reference(location)
    if ((reference.scheme and not reference.netloc)
            or (location.startswith("//") and not reference.netloc)
            or (not reference.scheme and not reference.netloc
                and ":" in reference.path.split("/")[0])):
        raise NetworkSafetyError("malformed redirect reference")
    if type(max_redirects) is not int or max_redirects < 0:
        raise NetworkSafetyError("max_redirects must be a nonnegative integer")
    if (not isinstance(visited_urls, SequenceABC)
            or isinstance(visited_urls, (str, bytes, bytearray))
            or not visited_urls or visited_urls[-1] != current_url):
        raise NetworkSafetyError("history must be nonempty and end at current")
    identities = set()
    for visited in visited_urls:
        try:
            validate_destination_url(visited, allowed_hosts)
        except NetworkSafetyError as exc:
            raise NetworkSafetyError(f"invalid history: {exc}") from exc
        identity = _request_identity(visited)
        if identity in identities:
            raise NetworkSafetyError("history contains a repeated request")
        identities.add(identity)
    if len(visited_urls) - 1 >= max_redirects:
        raise NetworkSafetyError("redirect limit reached")
    target = urljoin(current_url, location)
    # urllib loses an explicitly empty query and can inherit the old one.
    if "?" in location and not reference.query:
        target = target.split("?", 1)[0] + "?"
    validate_destination_url(target, allowed_hosts)
    if _request_identity(target) in identities:
        raise NetworkSafetyError("redirect loop detected")
    return target


def validate_resolved_addresses(addresses: Sequence[str]) -> Tuple[str, ...]:
    """Return the complete accepted address set without changing spelling."""
    if (not isinstance(addresses, SequenceABC)
            or isinstance(addresses, (str, bytes, bytearray))):
        raise NetworkSafetyError("addresses must be a sequence of strings")
    if not addresses:
        raise NetworkSafetyError("address answer set is empty")
    for text in addresses:
        if not isinstance(text, str):
            raise NetworkSafetyError("each address must be a string")
        if "%" in text:
            raise NetworkSafetyError("address scope identifiers are forbidden")
        try:
            address = ipaddress.ip_address(text)
        except ValueError as exc:
            raise NetworkSafetyError("invalid address text") from exc
        if address.version == 4:
            excluded = any(address in net for net in _IPV4_EXCLUSIONS)
        else:
            # This excludes mapped, compatible, NAT64, local and reserved
            # space, in addition to special-use blocks within global unicast.
            isatap = address.packed[8:12] in (
                b"\x00\x00\x5e\xfe", b"\x02\x00\x5e\xfe",
            )
            excluded = (address not in _IPV6_GLOBAL_UNICAST or isatap
                        or any(address in net for net in _IPV6_EXCLUSIONS))
        if (excluded or not address.is_global or address.is_multicast
                or address.is_reserved or address.is_unspecified
                or address.is_loopback or address.is_link_local):
            raise NetworkSafetyError("address is not permitted public unicast")
    return tuple(addresses)


def validate_destination_url(url: str, allowed_hosts: Collection[str]) -> str:
    """Return the unchanged approved acquisition URL, or raise an error.

    Approval is lexical only: fresh complete DNS-answer validation and a
    validated-address transport are still required before any connection.
    """
    _validate_allowlist(allowed_hosts)
    parts = _validate_raw_reference(url)
    if parts.scheme != "https" or not parts.netloc:
        raise NetworkSafetyError("URL requires absolute HTTPS")
    if parts.username is not None or parts.password is not None:
        raise NetworkSafetyError("URL credentials are not permitted")
    if (not parts.netloc.isascii() or "[" in parts.netloc
            or "]" in parts.netloc
            or not _valid_hostname(parts.hostname or "")):
        raise NetworkSafetyError("invalid DNS hostname")
    try:
        port = parts.port
    except ValueError as exc:
        raise NetworkSafetyError("invalid port") from exc
    if port not in (None, 443) or parts.netloc.endswith(":"):
        raise NetworkSafetyError("only port 443 is permitted")
    if parts.hostname not in allowed_hosts:
        raise NetworkSafetyError("hostname is not approved")
    return url

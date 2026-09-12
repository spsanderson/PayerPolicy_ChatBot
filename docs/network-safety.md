# Offline network-safety contract

Implemented in `payer_policy/network_safety.py`, following the
[approved plan](network-safety-plan.md). Standard library only; no DNS, HTTP,
filesystem writes, downloads, or provider calls. These are policy helpers,
**not an SSRF-proof transport or permission to crawl**.

All rejected inputs raise `NetworkSafetyError`, a `ValueError` subclass, with
an explanatory reason. Inputs are not changed. The existing
[source-registry validator](source-definition.md) remains separate: structurally
valid source metadata does not approve a network destination.

## Destination URL

`validate_destination_url(url: str, allowed_hosts: Collection[str]) -> str`

Returns the original string unchanged if accepted:

- Absolute HTTPS, an exact approved ASCII DNS hostname, and omitted port or
  explicit port 443. Hostname comparison is case-insensitive; subdomains must
  be approved separately. No suffix matching or implicit trust inheritance.
- `allowed_hosts` is reviewed caller configuration, not source metadata or a
  redirect response. Entries must already be lowercase ASCII DNS hostnames.
  Lists, tuples, and sets work. Strings, bytes, mappings, generators, and
  malformed entries fail closed; an empty collection approves nothing.
- DNS labels are 1–63 ASCII letters/digits/hyphens, cannot begin/end with a
  hyphen, and the complete hostname cannot exceed 253 characters.
- Reject credentials, missing/invalid hosts, trailing dots, IP literals
  (including bracketed IPvFuture), numeric resolver alternatives (decimal,
  dotted, octal, and hexadecimal forms), encoded hostnames, and unencoded
  internationalized hosts. Unicode case folding cannot turn a hostname into
  an approved ASCII name. ASCII `xn--` labels are treated as exact DNS labels,
  not decoded or automatically approved.
- Inspect raw input before parsing: reject backslashes, malformed percent
  escapes, whitespace, all C0 controls, DEL, all C1 controls, and fragments
  (including an empty `#`). Non-string and empty input fail clearly.
- Do not decode valid escapes, reorder queries, repair malformed input, or
  change path/query spelling. Encoded path/query data is not content-reviewed.

## Complete resolved-address set

`validate_resolved_addresses(addresses: Sequence[str]) -> Tuple[str, ...]`

The caller supplies the **entire** DNS answer set. This function does not perform
DNS or associate the answers with a hostname. It returns an immutable tuple in
input order, preserving spelling and duplicates. A single restricted or invalid
answer rejects the whole set, even alongside public addresses.

Reject empty results, non-sequence containers (including bare strings, bytes,
sets, mappings, and generators), non-string entries, invalid address text,
CIDR notation, brackets, whitespace, and scope/zone identifiers. The public
unicast checks reject private, loopback, link-local, unspecified, multicast,
reserved, documentation, shared, and special-use address space.

### Conservative exclusions and interpreter coverage

Verified on **Python 3.11.16**. `ipaddress` classifications can change between
Python releases; this implementation combines `is_global` and explicit status
checks with exclusions, rather than relying on `is_private` alone. Other Python
versions have not been exercised here; run the regression fixtures on each
supported interpreter before release.

Explicit IPv4 exclusions:

```text
0.0.0.0/8       10.0.0.0/8      100.64.0.0/10    127.0.0.0/8
169.254.0.0/16  172.16.0.0/12   192.0.0.0/24     192.0.2.0/24
192.88.99.0/24  192.168.0.0/16  198.18.0.0/15    198.51.100.0/24
203.0.113.0/24  224.0.0.0/4     240.0.0.0/4
```

IPv6 must be inside `2000::/3`, excluding `2001::/23`, `2001:db8::/32`,
`2002::/16`, and `3fff::/20`. ISATAP interface IDs with `0000:5efe` or
`0200:5efe` in bits 64–95 are also rejected. This conservatively excludes
IPv4-mapped/compatible forms, well-known/local-use NAT64 prefixes, Teredo,
6to4, ISATAP, and special-use space. Some globally reachable special-use
addresses are intentionally refused, including IPv4 `192.0.0.9` and `.10`.
This is not discovery of arbitrary network-specific translation/tunnel setups.

## Redirects and caller-owned history

`validate_redirect(current_url, location, allowed_hosts, visited_urls, max_redirects) -> str`

Returns an approved absolute target; never follows it or changes history.

1. Validate the current URL and raw Location before relative resolution.
   Relative, root-relative, scheme-relative, query-only, and absolute references
   are supported. Empty Location, fragments, controls, backslashes, malformed
   escapes, missing authorities after `//`, incomplete absolute URLs such as
   `https:/path`, and colons in a relative first path segment are rejected.
2. `visited_urls` must be a nonempty sequence of approved URLs, beginning with
   the initial URL and ending with the **exact** `current_url` string. Repeated
   request identities or invalid entries make history inconsistent. The caller
   must provide truthful, complete history; the helper cannot reconstruct
   earlier requests or prove that a request was actually made.
3. `max_redirects` must be a nonnegative integer, not a boolean. With N URLs in
   history, N−1 redirects have been followed. Reject when that count reaches
   the limit. Zero prevents the first redirect; the Nth allowed hop succeeds
   when the limit is N, and the next is refused.
4. Resolve the reference using URI resolution and validate the resulting URL
   with the same explicit allowlist, including same-host targets. No downgrade,
   new host approval, or unsafe port can slip through a redirect. Relative dot
   segments are resolved, but escapes and query order are not normalized.
   Explicit empty queries clear an inherited query and retain their `?`.
5. Reject a loop against any history entry using lowercase hostname, effective
   port 443, empty-path-as-`/`, and exact parsed path/query. An absent and empty
   query compare alike. Escape spelling, query order, and other aliases are not
   equated; the finite hop limit bounds those aliases.

An accepted redirect still requires **fresh complete address validation** before
any connection, even when the hostname is unchanged.

## Runnable offline example

Run from the repository root. These addresses are literal test fixtures, not
DNS answers collected from `example.org` and not authorization to contact it.

```python
from payer_policy.network_safety import (
    NetworkSafetyError,
    validate_destination_url,
    validate_resolved_addresses,
    validate_redirect,
)

allowed = frozenset({"example.org", "cdn.example.org"})
start = "https://example.org/policies/start"
assert validate_destination_url(start, allowed) == start
assert validate_resolved_addresses(
    ["8.8.8.8", "2606:4700:4700::1111"]
) == ("8.8.8.8", "2606:4700:4700::1111")

history = [start]
target = validate_redirect(start, "../current?q=1", allowed, history, 1)
assert target == "https://example.org/current?q=1"
assert history == [start]  # Pure helper: caller records accepted hops.
history.append(target)

for operation in (
    lambda: validate_destination_url("https://evil.test/", allowed),
    lambda: validate_resolved_addresses(["8.8.8.8", "127.0.0.1"]),
    lambda: validate_redirect(target, "/next", allowed, history, 1),
):
    try:
        operation()
    except NetworkSafetyError:
        pass
    else:
        raise AssertionError("unsafe input was accepted")
print("Offline network-safety example passed")
```

## Verification and remaining transport gate

`python -m unittest discover -s tests -v` exercises 30 test methods, including
17 network-safety methods with adversarial subtest matrices. Socket construction,
DNS lookup entry points, and connection helpers are blocked in network tests.
Coverage includes all raw C0/DEL/C1 controls, malformed authorities, restricted
and mixed addresses, transition IPv6, relative redirects, loops, exact hop
boundaries, and input preservation. No live destination or HTTP client is tested.

A future downloader must disable automatic redirects and unsafe proxy/environment
fallbacks, resolve every target, validate the complete answer set, and connect
**only to a validated address** while retaining the original hostname for SNI
and verified TLS certificates. It must not perform a second unchecked DNS lookup.
Actual connection behavior, rebinding, retries, proxy handling, and redirects
need transport integration tests. Pure helpers alone cannot prevent SSRF.

Still separate and unimplemented: robots/access permission review, response
size/time limits, MIME/content validation, immutable originals, retries,
source-specific connectors, and document applicability review. The reviewed
host allowlist is caller-owned; this increment does not supply one for live use.

See [architecture](architecture.md), [delivery plan](implementation-plan.md),
and [README](../README.md).

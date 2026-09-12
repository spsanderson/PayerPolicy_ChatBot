# Implementation plan: Network destination and redirect checks

**Phase:** 1 — Source and packaging validation  
**Module:** `payer_policy/network_safety.py` (implemented)  
**Status:** Approved by Steve; implemented and offline-verified.  
**Purpose:** Establish offline safety checks before implementing a downloader.

## Scope and boundaries

Build pure validation functions using Python's standard library. No DNS queries,
HTTP requests, downloads, filesystem writes, or provider connections occur in
these functions. Existing source-registry validation remains unchanged: a
structurally valid source URL is not automatically an approved destination.

A caller-supplied allowlist represents reviewed configuration. Neither source
metadata nor a redirect response can add hosts to it. Begin with exact ASCII
DNS hostnames, HTTPS, and port 443 only. Subdomains need their own approval.

## Function contracts

### 1. `validate_destination_url(url: str, allowed_hosts: Collection[str]) -> str`

Return the original URL unchanged when acceptable; otherwise raise
`NetworkSafetyError`, a `ValueError` subclass with a clear reason.

- Require an absolute HTTPS URL and exact approved hostname.
- Permit an omitted port or explicit 443; reject all other ports.
- Reject credentials, missing/invalid hosts, backslashes, malformed percent
  escapes, whitespace, C0 controls, DEL, and C1 controls before URL parsing.
- Reject IP-literal URLs, numeric-only host forms, percent-encoded hostnames,
  trailing-dot hosts, and unencoded internationalized hostnames in this version.
- Allowlist entries must be lowercase ASCII DNS hostnames, not URLs, wildcards,
  paths, or host:port strings. Invalid configuration fails closed.
- Compare valid URL hostnames case-insensitively without changing the original
  URL. Preserve path/query spelling and encoding; do not repair malformed input.
- Reject fragments for acquisition URLs, avoiding ambiguous request identity.
- An empty allowlist approves no destination.

### 2. `validate_resolved_addresses(addresses: Sequence[str]) -> Tuple[str, ...]`

Validate the complete caller-supplied DNS answer set. Return the accepted input
addresses as a tuple, preserving order and spelling; otherwise raise
`NetworkSafetyError`. No DNS lookup is performed.

- Reject an empty result, invalid address text, and zone/scope identifiers.
- Reject any address that is not public unicast: private, loopback, link-local,
  multicast, unspecified, reserved, documentation, and shared address space.
- Reject mixed public/restricted answers as a whole, rather than selecting a
  seemingly safe address from the set.
- Conservatively reject IPv4-mapped and transition/translation IPv6 forms in
  this first version; do not allow encapsulation to hide a restricted address.
- Use `ipaddress` with explicit exclusions and regression fixtures. Do not rely
  on `is_private` alone or on classification being identical across Python
  releases. Document the tested interpreter and conservative exclusions.
- Wrong containers (including a bare string) and non-string entries fail clearly.

### 3. `validate_redirect(current_url: str, location: str, allowed_hosts: Collection[str], visited_urls: Sequence[str], max_redirects: int) -> str`

Return an approved absolute redirect target, or raise `NetworkSafetyError`.
The explicit allowlist parameter ensures every redirect uses the same policy.

- Validate the current URL and raw Location value before relative resolution.
- Resolve valid relative, root-relative, and scheme-relative references against
  the current URL. This is defined URI resolution, not repair of malformed input.
- Apply `validate_destination_url()` to the resolved target, including for
  same-host redirects. Reject HTTPS downgrades and unapproved hosts.
- `visited_urls` is nonempty and contains the initial URL followed by each
  accepted destination, ending with `current_url`. Reject inconsistent history.
- `max_redirects` is a nonnegative integer, not a boolean. A limit of zero
  rejects the first redirect. With N URLs in history, N-1 redirects have already
  been followed; reject a candidate when that count reaches the limit.
- Detect repeated request identities using parsed lowercase hostname, effective
  port 443, empty-path-as-slash, and exact path/query. Preserve supplied URLs;
  do not decode escapes or reorder queries. The finite hop limit bounds aliases
  beyond this deliberately conservative loop comparison.
- Reject empty Location, malformed references, and control characters.
- An accepted redirect still requires fresh DNS/address validation before any
  future connection. URL approval does not certify the resolved destination.

If implementation reveals an ambiguity in these contracts, stop and document
it rather than silently extending approval or weakening rejection rules.

## Incremental test-first sequence

Run the existing suite before editing production code. For each behavior below:
write a failing test, observe the expected failure, implement the smallest fix,
rerun focused tests, then rerun the full suite. Do not build all functions first.

| Increment | Behavior and acceptance evidence |
|---|---|
| A | Approved HTTPS URL passes unchanged; exact host matching and port rules work |
| B | Malformed URL, credentials, deceptive hosts, bad allowlists, controls, and disallowed destinations fail |
| C | Valid public IPv4/IPv6 answers pass; empty, malformed, restricted, mapped/transition, and mixed answers fail |
| D | Valid relative redirects resolve; disallowed hosts, downgrades, malformed Location, and fragments fail |
| E | History validation, loops, zero limit, exact limit, and over-limit redirects behave as specified |
| F | Full regression suite, executable examples, documentation links, and diagram structure pass |

Use offline fixtures, including adversarial URLs, all U+007F–U+009F controls,
private network ranges, IPv6 edge cases, deceptive hostname suffixes, and
redirect chains. Test errors for the relevant reason and ensure input sequences
and strings are not mutated. Valid and invalid fixtures must not trigger network
access. No performance or safety claims may exceed the exercised tests.

## Planned files

- Add `payer_policy/network_safety.py` and `tests/test_network_safety.py`.
- Add `docs/network-safety.md` with the implemented contract and examples.
- Update `README.md`, `docs/implementation-plan.md`, and
  `docs/architecture.md` to describe only completed behavior.
- Keep `docs/architecture.html` as the existing historical snapshot.

Shared helpers may be extracted only when required by these related functions;
do not refactor source-registry behavior as part of this increment.

## Transport gate: required later, not solved here

A downloader must disable automatic redirects and unsafe proxy/environment
fallbacks, resolve every target, validate all returned addresses, and connect
only to a validated address while preserving hostname/SNI and TLS certificate
verification. It must avoid a second unchecked DNS lookup and validate actual
connection behavior. DNS rebinding, transport retries, and redirects require
integration tests at that boundary; pure helpers alone cannot prevent SSRF.

Separate future work: robots/access permissions, response size and time limits,
MIME/content checks, original storage, retries, and source-specific connectors.
Nothing in this plan grants permission to crawl or establishes policy applicability.

## Completion and review gate

- [x] All three function contracts implemented in small RED/GREEN cycles.
- [x] Existing tests and new offline safety tests pass.
- [x] Examples execute and documentation links resolve.
- [x] Architecture distinguishes implemented helpers from planned transport.
- [x] Report actual results, remaining limitations, and GitHub Desktop summary.
- [x] Do not commit, push, or begin downloader implementation without direction.

Implementation followed approval. See [implemented contract](network-safety.md)
for exclusions, runnable examples, verified results, and remaining transport
limitations. The original scope above is retained as the acceptance record.

Verification: Python 3.11.16, 30 passing test methods, four executed Python
examples, and 25 resolving local Markdown links. Mermaid structure checks
passed for 20 declared/classified nodes; visual rendering was not exercised.
The historical HTML snapshot is unchanged. No downloader, commit, or push was
performed.

# Incremental implementation plan

Status: direction approved; implementation in small test-first slices.
No phase is complete merely because its first module is implemented.

## Product boundary

Windows installable; New York NYSHIP Empire Plan; Anthem-administered Hospital
Program benefits; all applicable policy categories. Applicability includes
member group, administrator, benefit context, and dates. Unresolved source
access and group-specific coverage are explicit gaps, not defaults.

## Phase 1: Source and packaging validation (in progress)

### Module 1: Document provenance

Implemented function:

`fingerprint_document(content: bytes) -> str`

- Computes SHA-256 over exact bytes without text normalization.
- Rejects non-bytes, including mutable buffers.
- No filesystem, network, database, or provider dependency.
- Does not establish trust, validity, dates, or applicability.
- Tests: known standard digest and invalid input contract.

### Module 2: Source registry — validation and local loading implemented

`validate_source_definition(source: object) -> List[str]` checks required
metadata, stable ID format, HTTP(S) URL structure, and applicability status.
It returns field-prefixed errors and leaves the input untouched. Explicit
unknown applicability is accepted; confirmed applicability requires an evidence
URL, whose truth is not automatically verified. See [contract](source-definition.md).

Implemented: `parse_source_registry(text)` and `load_source_registry(path)`.
Strict JSON parsing rejects duplicate keys, invalid envelopes/entries, and
duplicate source IDs without partial results. Local file errors remain distinct
from content errors. Exact source values and order are preserved.

Verified: 13 test methods across provenance and registry, including offline
temporary-file tests and loading the checked-in registry. One official Anthem
overview was reviewed separately and classified as reference only. Its
[review note](source-reviews/anthem-empire-plan-overview.md) records evidence,
review time, and unreviewed access/rights limitations.

### Module 3: Offline network safety — implemented

Implemented the [approved plan](network-safety-plan.md) in small RED/GREEN
increments; see the [contract and executable example](network-safety.md).

- `validate_destination_url(url, allowed_hosts)` approves exact reviewed ASCII
  DNS hosts over HTTPS/443 and returns the original URL. Invalid configuration,
  malformed input, credentials, IP literals, and fragments fail closed.
- `validate_resolved_addresses(addresses)` checks all supplied addresses and
  preserves their spelling/order in a tuple. Private/special-use and known
  transition addresses, invalid inputs, and mixed answers reject atomically.
- `validate_redirect(current_url, location, allowed_hosts, visited_urls,
  max_redirects)` resolves valid references, rechecks destination policy,
  rejects inconsistent histories/loops, and enforces the exact hop limit.

Verified on Python 3.11.16: 30 passing test methods (13 existing and 17 new
network-safety methods with offline fixture matrices). Runnable examples pass.
There are no DNS lookups, network connections, or downloader implementation.
Source-level trust is not document-level applicability.

### Module 4: Checked-address HTTPS transport — implemented building block

`fetch_https(url, allowed_hosts, *, max_redirects=3, timeout=10,
max_bytes=10_000_000)` connects to one of the approved DNS addresses without
resolving the hostname again at the HTTP connection. It retains hostname-based
TLS verification, revalidates redirects with fresh DNS results, closes each
connection, rejects failed/oversized responses, and does not use proxies or
retry a failed connection. See the [transport contract](https-transport.md).

Verified on Python 3.11.16: 51 offline unit-test methods and one separate
loopback-only TLS integration method pass. That integration test creates a
temporary test certificate with OpenSSL and checks matching and mismatched host
names. No public source was fetched. These checks do **not** establish crawl
permission, content validity, applicability, a hard DNS timeout, or an
end-to-end downloader. The source registry is not wired to this operation.

### Source-access review — completed with unresolved access/reuse decisions

On September 25, 2026, Participating Agencies (PA) was selected as the first
application example. The [PA certificate review](source-reviews/pa-certificate-2025.md)
records a January 2025 certificate, related amendments and a May 2026 report,
observed research access, precise source references, and remaining gaps.

The candidate has readable Hospital Program evidence, but current-service-date
completeness and automated collection/redistribution permission remain unresolved.
The new NYSHIP library could not be fully inspected. No registry entry or access
approval was added, and no application transport was exercised against a public
source. Successful research retrieval is not a live application integration test.

### Module 5: Offline PDF-candidate validation — implemented building block

`validate_pdf_candidate(result: FetchResult) -> None` checks HTTP 200, absence
of Content-Range, nonempty bytes, one bare application/pdf content type,
absent/identity content encoding, and %PDF- at byte zero. Content rejection
raises `DocumentValidationError`; incorrect input types raise `TypeError`.
See the [contract, decisions and runnable example](document-validation.md).

No bytes are changed, parsed, decompressed, downloaded or stored. A marker-only
fake PDF can pass; this does not establish structural validity or applicability.
The helper does not automatically run inside the transport or acquisition worker.

Verified on Python 3.11.16: 64 offline test methods and the separate local TLS
test pass. Tests use synthetic responses, guard file/socket entry points, and
pass real transport-parser output into the validator with controlled sockets.
No public-source integration, dependency or registry permission was added.

### Module 6: Offline original-byte storage — implemented building block

`save_pdf_candidate(root, result, *, retrieval_id, source_id,
requested_url, retrieved_at, max_bytes=10_000_000)` writes unchanged candidate
bytes plus a versioned receipt under a caller-chosen local Windows directory.
`load_saved_candidate(root, retrieval_id, *, max_bytes=10_000_000)` bounds the
read and checks candidate rules, receipt structure, byte count, and SHA-256
against the original. See the [contract and runnable example](document-storage.md).
A 32-character lowercase hex ID identifies each retrieval, not each file
content. Identical same-ID retries return the verified original; different
bytes or metadata cannot replace the first record. Same-root staging and
Windows directory rename prevent an interrupted pre-publication attempt from
appearing as completed. Orphan staging folders require manual review/cleanup;
file flushing is not a power-loss guarantee. The storage root must be trusted.

Verified on Python 3.11.16: 80 offline test methods ran (one optional Windows
link-creation case skipped on the checked machine) plus one separate local
loopback TLS test. The 16 new tests use synthetic bytes and temporary folders,
including killed child processes, competing writers, disk errors, malformed
receipts, and offline composition with actual transport-parser output. No
public policy was fetched or stored; no source, collection, redistribution,
structural parsing, or applicability gate was approved by this module.

Broader PDF parsing and live application acquisition remain later approval
gates. This storage helper does not make a document library or connect the
source registry to transport, and access/redistribution rights remain unresolved.

### Module 7: Offline PDF structural inspection — implemented building block

`inspect_saved_pdf(root, retrieval_id, *, max_bytes=10_000_000) ->
PdfInspection` loads a verified saved candidate, then uses pinned pypdf to
report whether it is encrypted and, if accessible, its reader-reported page
count. The result includes the retrieval ID and verified byte fingerprint.
An encrypted file returns `page_count=None`; an accessible empty PDF returns
zero. Storage integrity/input failures remain distinct from PDF read failures
(`PdfInspectionError`). See the [contract](document-inspection.md).

This module reads the already verified bytes in memory; it does not change the
original or its receipt, download another file, inspect page text, perform OCR,
or claim whole-file validity. A 10,000,000-byte input cap is **not** a parser
CPU/memory cap. Strict parsing may reject files other viewers repair. Do not
connect arbitrary public PDFs to unattended ingestion without separately
reviewed resource isolation and permission to collect.

Verified on Python 3.11.16 with pypdf 6.19.0: 88 offline test methods ran
(87 passed, one optional Windows link-creation case skipped), and the separate
local-loopback TLS test passed. Eight new tests use synthetic PDFs and temporary
storage; they cover multipage, encrypted, empty, marker-only, malformed,
damaged-record, size/path, and no-network cases. The documentation example
was not separately executed; its code path is exercised by the tests. No
public source was collected or redistributed. The Windows installer remains
planned.

Registry URL validation alone is not a network security boundary. The new
transport enforces destination/address/redirect checks and a raw byte limit,
but a future ingestion pipeline must call the candidate checker and still
address permissions, deeper PDF parsing and provenance before indexing content.
A standalone validator does not make a working ingestion pipeline.

Then validate real source access and preserve a representative document set.
Separately test Windows packaging for extraction, OCR, and embedded embeddings
before selecting the final vector index or shipping large dependencies.

### Phase 1 acceptance gate

Document an official-source applicability map, access failures/restrictions,
member-group gaps, representative extraction cases, and packaging results.
Fingerprint tests alone do not satisfy this gate.

## Phase 2: End-to-end slice (planned)

Modules: approved-source acquisition and candidate validation; integrate the
existing original-byte storage helper; extraction; keyword and semantic index;
retrieval; provider adapter; citation viewer.
Gate: real document -> real answer -> exact original passage, with provenance.

## Phase 3: Policy lifecycle (planned)

Modules: source connectors; update comparison; version metadata; extraction
corrections; chunk preview; persistent/resumable jobs.
Gate: updates retain originals; interruptions recover; edits are auditable.

## Phase 4: Retrieval and providers (planned)

Modules: applicability filtering; hybrid ranking; evaluation; provider settings.
Gate: wrong-plan, stale, conflict, and insufficient-evidence tests; model
switching without reindexing. Confirm domain judgments with Steve.

## Phase 5: Windows release (planned)

Modules: installer/launcher; protected credentials; backup/restore; upgrades;
accessibility; loopback service security.
Gate: clean Windows installation without developer tools, upgrade and restore
verification. Define code signing before public release.

## External integration evidence

- Anthem program boundary: https://www.anthembluecross.com/nys
- NYSHIP group publications:
  https://www.cs.ny.gov/employee-benefits/group/3/14/1/health-benefits.cfm
- Anthropic third-party subscription restrictions:
  https://code.claude.com/docs/en/agent-sdk/overview
- Codex product integration candidate:
  https://developers.openai.com/codex/app-server

These are research starting points, not a verified exhaustive registry. Recheck
access, applicability, and integration terms before implementing connectors.

## Open decisions

Initial member-group validation set; Codex first-release priority; signing;
licensed criteria availability; final embedded index and OCR packaging.

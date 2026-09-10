# Incremental implementation plan

Status: direction approved by Steve; implementation in small test-first slices.
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

### Module 2: Source registry — validation implemented

`validate_source_definition(source: object) -> List[str]` checks required
metadata, stable ID format, HTTP(S) URL structure, and applicability status.
It returns field-prefixed errors and leaves the input untouched. Explicit
unknown applicability is accepted; confirmed applicability requires an evidence
URL, whose truth is not automatically verified. See [contract](source-definition.md).

Verified: 7 test methods across provenance and registry, including parameterized
invalid-input cases. Tests run offline; no official source has been loaded.

Next increment (not implemented): load a reviewed registry containing one
official source entry. Preserve exact identifiers/URLs and reject duplicate
IDs. Record source review evidence; source-level trust is not document-level
applicability.

Registry URL validation is not a complete network security boundary. The later
fetcher must validate redirects, resolved addresses, response size, MIME/content,
timeouts, and destination restrictions before saving downloaded content.

Then validate real source access and preserve a representative document set.
Separately test Windows packaging for extraction, OCR, and embedded embeddings
before selecting the final vector index or shipping large dependencies.

### Phase 1 acceptance gate

Document an official-source applicability map, access failures/restrictions,
member-group gaps, representative extraction cases, and packaging results.
Fingerprint tests alone do not satisfy this gate.

## Phase 2: End-to-end slice (planned)

Modules: download validation; immutable original storage; extraction; keyword
and semantic index; retrieval; provider adapter; citation viewer.
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

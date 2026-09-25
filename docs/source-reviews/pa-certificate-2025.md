# Source review: Participating Agencies certificate, January 2025

## Decision

**Ready for offline validation planning; needs clarification before automated
collection or redistribution.** This is a source review, not an ingestion
implementation or a complete current-benefits determination.

- Review date: September 25, 2026 (UTC).
- Selected first application example: **Participating Agencies (PA)**.
  This does not identify any individual's personal coverage or approve other member groups.
- Primary candidate: the Department of Civil Service, Employee Benefits
  Division's January 1, 2025 Empire Plan Certificate for Participating Agencies.[9]
- Registry unchanged. This note records a candidate without turning review
  findings into automatic download authorization or a blanket applicability claim.
- No production code, schema, dependencies, policy library, or transport tests
  against public sources were added.

## Document identity and applicability evidence

The cover identifies the PA population, including active employees, retirees,
vestees, dependent survivors, covered dependents, COBRA and Young Adult Option
enrollees. It states that benefits are effective through January 1, 2025.[9]

Section II begins on printed page 11 (PDF page 16). It describes Hospital
Program coverage and explicitly says: "The Hospital Program Administrator is
Anthem Blue Cross." This is direct document-level evidence for the program
association, rather than an inference from a publisher's brand.[9]

The same page directs readers elsewhere for eligibility/enrollment and notes
that Medicare-primary status changes benefits. Therefore group membership,
individual eligibility, service dates, Medicare status and the particular
service still need checking before answering a coverage question.[9]

This is a multi-program certificate. Later extraction must retain section
boundaries; it must not label the whole PDF as Anthem Hospital Program content.
The cover's benefits date is not a claim that the document is complete for
services in September 2026.[9]

### Related updates, not an exhaustive inventory

The January 2025 PA amendments cover changes effective January 1, 2024 through
January 1, 2025 (cover, PDF page 1). Record the relationship rather than silently
applying amendments twice or assuming they all postdate the online certificate.[10]

The May 2026 PA Empire Plan Report, page 9, still directs readers to the
certificate and amendments with benefits effective through January 1, 2025.
This supports keeping the 2025 certificate as a representative candidate; it
does not establish that it alone contains every later change.[13]

Review boundary: cover/identity, Hospital Program introduction, related update
labels, and access conditions. This was not a benefit-by-benefit reconciliation,
clinical-policy inventory, or determination of governing precedence. Completeness
for a current service date remains **unknown**.

## Retrieval observations

These observations came from ordinary Python standard-library research requests,
not `payer_policy.https_transport.fetch_https()`. No login or supplied credentials
were used. URLs are recorded in the Sources section.

| Resource | Retrieval start (UTC, September 25, 2026) | HTTP result | Observed content type | Bytes | Extracted page segments |
|---|---|---|---|---:|---:|
| Certificate [9] | 19:55:12 | 200; requested and final URLs identical | `application/pdf` | 3,324,564 | 165 |
| Amendments [10] | 19:55:15 | 200; requested and final URLs identical | `application/pdf` | 618,431 | 16 |
| May 2026 report [13] | 19:55:15 | 200; bare `cs.ny.gov` request ended at `www.cs.ny.gov` | `application/pdf` | 1,659,659 | 12 |

The primary PDF began with a PDF signature and yielded readable text through the
already-installed `pdftotext` utility. The first stdin-based extraction attempt
failed; a temporary-file extraction succeeded. Temporary PDF files were deleted.
Extracted research text and request logs remain outside the repository in the
local Hermes cache; they are not an immutable application document library.
Some extracted symbols showed replacement characters, so this does not certify
production text-extraction fidelity. No parser was installed and no page images
were visually inspected.

The primary PDF's server `Last-Modified` was February 11, 2026 at 20:46:40 GMT.
That is server metadata, not a benefit effective date. The fetched bytes had this
SHA-256 fingerprint (identity, not authenticity or applicability):

```text
6d5a418d110000e6a5305eb8545866664a63fae63b0a5df75090c55999824692
```

For a future single-file fetch, the observed primary-document hostname is
`www.cs.ny.gov`. This is a proposed exact host, not a new allowlist entry. Any
future redirect needs its own review and the existing transport safety checks.
The observed size fits the existing default body limit, but later versions may
change size. No result here verifies checked-IP connections, TLS pinning,
application ingestion, or whole-request time limits.

## Access and reuse findings

| Question | Evidence and status |
|---|---|
| Can the selected PDFs be read without login? | Yes, in this research run: the three PDF requests returned 200 without supplied credentials. This is a point-in-time observation. |
| What does the site's robots file say? | The `User-agent: *` group includes `Allow: /employee-benefits/`, covering the selected primary path. Retrieved as HTTP 200 at 19:54:38 UTC.[4] |
| Is automated collection explicitly licensed? | **Unresolved.** Treat the robots result as a technical crawling signal, not blanket permission. No explicit automation grant was identified in the disclaimer and privacy notice reviewed.[11][12] |
| Is redistribution explicitly licensed? | **Unresolved.** Those notices did not establish permission to ship full policy documents in a public application.[11][12] |
| Do the notices guarantee accuracy? | No. The disclaimer characterizes the site's information as informational and disclaims warranties; it also separates external sites from the Department's responsibility.[11] |
| Are all site services public? | No such conclusion follows. The privacy notice describes login requirements for some services; none were accessed here.[12] |

No legal conclusion about permissible reuse is made. Before recurring automated
collection or bundling documents, obtain a supported access/reuse decision for
that specific use. No permission request was sent on Steve's behalf.

### Access failures and research limits

- The old PA health-benefits URL and the PA publications landing-page request
  failed locally with DNS-resolution errors. This run did not verify their
  complete redirect chain. Earlier planning described a migration; do not treat
  that description as a verified redirect trace from this review.
- A request to `https://nyship.ny.gov/g/pa/ep/documents-publications-library`
  returned HTTP 403. The NYSHIP robots request separately failed DNS resolution.
  No access restriction was bypassed.
- Browser inspection could not start because this session's real-profile browser
  configuration was unsupported. Website extraction was also unavailable under
  the configured extraction backend. Public search discovery plus direct,
  successful PDF requests supplied the document evidence instead.
- An Anthem robots request returned HTTP 404. That is not an authorization signal
  and was not used to approve this separate Civil Service document host.
- The new NYSHIP library was not exhaustively reviewed. Do not claim that no
  newer certificate, amendment or program notice exists.

## Proposed next implementation increment — not approved or built

Start with **offline download-candidate checks**, using synthetic fixtures rather
than copying the reviewed certificate into the test repository. This keeps
validation work independent of unresolved automated-access and reuse decisions.

Proposed contract:

```text
validate_pdf_candidate(result: FetchResult) -> None
```

- Accept a nonempty successful fetch result with one supported PDF content type,
  no unexpected content encoding, and a PDF signature at the agreed position.
- Reject empty bytes, HTML login/error responses, missing/conflicting/unsupported
  content-type values, unexpected compressed content, and obvious format mismatch
  with a dedicated `DocumentValidationError`.
- Do not modify bytes, access the network, write files, infer applicability, or
  claim full PDF structural validity, readability, malware safety or extractability.
- Explain that passing means **candidate**, not **valid policy**. A short fake PDF
  signature may pass this deliberately shallow check; later structural parsing
  remains a separate, explicit requirement before indexing.

Before coding, settle exact header/signature acceptance rules in the approval
plan. Tests should cover accepted fixtures, each rejection, unchanged bytes and
absence of network/filesystem side effects. Use failing tests first, then the
smallest implementation; rerun existing offline and local TLS suites and update
the contract documentation. No new parser dependency is proposed for this slice.

Original-file storage remains a later approval gate: define no-overwrite behavior,
crash recovery, duplicate-content handling, source/request/final URLs, UTC retrieval
time, selected response metadata and fingerprint together. Do not save partial
results or treat an orphaned file as a completed library record.

The source review is complete within these limits. Approval of this review did
**not** approve validation code, storage code, live application downloads, broad
crawling, or document redistribution.

## Verification of this documentation increment

- The documented minimum is Python 3.11; the established verification baseline
  is Python 3.11.16. A fresh baseline run passed all 51 offline tests and the
  separate local TLS test.
- The source-review session also passed those suites on Python 3.14.7. That was
  an additional interpreter run, not a change to the minimum or baseline, and
  does not establish verification of every Python version in between.
  No public-site test was added to those suites.
- All 36 checked local documentation links resolved.
- The citation ledger verified six cited sources, each with a matched excerpt.
  Unused discovery URLs remain in the local ledger and are not cited as evidence.
- The recorded primary-document byte count and fingerprint match the request log.
- `git diff --check` found no whitespace errors; Git emitted line-ending notices.
- The registry and runtime code are unchanged. Nothing was committed or pushed.

## Sources

[4] https://www.cs.ny.gov/robots.txt
    > "Allow: /employee-benefits/ Disallow: /elmspublic/"
[9] https://www.cs.ny.gov/employee-benefits/pa-market/shared/publications/certificate/2025/pa-online-certificate-2025.pdf
    > "The Hospital Program Administrator is Anthem Blue Cross."
[10] https://www.cs.ny.gov/employee-benefits/shared/publications/amendments/2025/pa-amendments-2025.pdf
    > "benefit changes effective January 1, 2024, through January 1, 2025."
[11] https://www.cs.ny.gov/home/disclaimer.cfm
    > "The information provided on our website is intended for informational use."
[12] https://www.cs.ny.gov/home/privacypolicy.cfm
    > "To access some services available on our site, you will need login credentials."
[13] https://www.cs.ny.gov/employee-benefits/pa-market/shared/publications/empire-plan-report/2026/pa-epr-2026.pdf
    > "January 1, 2025, are available on nyship.ny.gov."

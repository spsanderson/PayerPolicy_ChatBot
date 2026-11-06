# Representative PA collection: proposed download list

## Decision and scope

Research and target selection were approved first. At that stage, the three
downloads below still required exact-document approval. The research did not
fetch PDF bodies, run the coordinator, change the registry/production code, or
create live application records. Subsequent approval is recorded below.

Checked November 5, 2026, approximately 7:45-7:47 p.m. EST
(November 6, approximately 00:45-00:47 UTC). The existing
[PA certificate review](pa-certificate-2025.md) supplies the historical document
identity and selection rationale. It is not current benefit-completeness proof.
This small set contributes to Phase 1 evidence; it cannot close Phase 1 alone.

## Proposed documents, in acquisition order

1. **2025 Participating Agencies Empire Plan Certificate**
   - Proposed source ID: `pa-certificate-2025`.
   - Exact URL: `https://www.cs.ny.gov/employee-benefits/pa-market/shared/publications/certificate/2025/pa-online-certificate-2025.pdf`
   - Current HEAD: HTTP 200, `application/pdf`, Content-Length 3,324,564 bytes;
     Last-Modified February 11, 2026, 20:46:40 GMT.[3]
   - Purpose: representative long, multi-program document. Historical review
     identifies Hospital Program content inside it; do not label the whole
     certificate as an Anthem hospital policy.
2. **2025 Participating Agencies amendments**
   - Proposed source ID: `pa-amendments-2025`.
   - Exact URL: `https://www.cs.ny.gov/employee-benefits/shared/publications/amendments/2025/pa-amendments-2025.pdf`
   - Current HEAD: HTTP 200, `application/pdf`, Content-Length 618,431 bytes;
     Last-Modified February 11, 2026, 20:46:40 GMT.[4]
   - Purpose: preserve a related amendment document separately. Historical
     review warns that its changes may already be incorporated in the online
     certificate; no precedence or additive-benefit inference is approved.
3. **2026 Participating Agencies Empire Plan Report**
   - Proposed source ID: `pa-empire-plan-report-2026`.
   - Exact URL: `https://www.cs.ny.gov/employee-benefits/pa-market/shared/publications/empire-plan-report/2026/pa-epr-2026.pdf`
   - Current HEAD: HTTP 200, `application/pdf`, Content-Length 1,659,659 bytes;
     Last-Modified May 19, 2026, 16:03:36 GMT.[5]
   - Purpose: representative shorter update publication. The historical review
     identifies the May 2026 edition; no claim is made that it is the latest.

These were direct HEAD requests using Python's standard-library research
client, without credentials or redirect following. No redirect was returned.
Server labels and lengths do not prove that GET will succeed or return the
same bytes. No PDF signatures, page counts, encryption flags, or fresh hashes
were measured. Prior hashes are comparison evidence, not current expected
values; any difference must be recorded, not silently normalized away.

## Access observations and unresolved questions

- The current robots file returned HTTP 200 on retry and includes
  `Allow: /employee-benefits/` under `User-agent: *`.[1]
- The disclaimer returned HTTP 200 and describes the site as informational.[6]
- The privacy notice returned HTTP 200 and says some services require login.[7]
- No explicit automated-collection or redistribution grant was established
  from the reviewed notices. Robots rules and successful HEAD requests are
  not treated as such permission. This is not a legal conclusion.[1][6][7]
- The NYSHIP PA publications library first failed DNS resolution, then returned
  HTTP 403 on a later ordinary request. Its contents and complete publication
  inventory could not be reviewed; no restriction was bypassed.[2]
- Initial robots DNS failure resolved on one retry. These observations do not
  establish production network reliability. No newer-document completeness
  claim is made.

Research request observations and fetched notice text are temporarily retained
outside Git under the Hermes scratch directory `collection-review`. Its
`observations.json` records methods, exact URLs, UTC times, response metadata,
and failures; it is not a durable PDF library or production retrieval receipt.

## Exact proposed acquisition approval

Approve only one local acquisition-and-inspection attempt per document above,
starting with the certificate and stopping for review if an attempt fails.
Use distinct retrieval IDs and the unchanged checked transport, original-byte
storage, and contained-inspection coordinator. Do not use the research client
to fetch PDF bodies as a substitute if the production transport refuses them.

- Proposed trusted physical local root, outside Git:
  `C:\Users\steve\Documents\PayerPolicyLibrary\pilot-pa`.
- Sole allowed host: `www.cs.ny.gov`; redirect targets must still satisfy the
  existing transport policy. A different host requires separate review.
- Retain exact originals, existing receipts, and a separate local inspection
  report keyed by retrieval ID and fingerprint. Do not change receipt schemas.
- Keep unknown applicability/current completeness explicit. Source registration
  and approval notes must not assert a legal grant that has not been established.
- No redistribution, Git upload of PDFs, public hosting, recurring download,
  crawling, extraction, OCR, or policy interpretation is approved.

At the research stage, document-specific approval was still required. The
research scope alone did not authorize PDF acquisition.

## Subsequent local-pilot approval

On November 5, 2026, explicit approval was given for one local-only acquisition
and contained-inspection attempt for each of the three exact URLs and source
IDs above, in the listed order. Use the proposed storage root and sole allowed
host above; stop for review after any failure. No automatic retry or alternate
client is authorized. This records the requested local-use decision, not a
publisher license or legal determination. Redistribution and current-benefit
completeness remain unresolved. No PDF may be committed, uploaded, or included
in a public application by this approval. Execution results follow below.

## Verified local execution

Executed November 5, 2026, 7:55-7:56 p.m. EST (November 6, 00:55-00:56 UTC).
All three planned attempts succeeded in order through the unchanged
`acquire_and_inspect_pdf` coordinator. Each returned HTTP 200 with requested
and final URLs identical. All inspections reported unencrypted PDFs.

- `pa-certificate-2025`: 165 reader-reported pages, 3,324,564 bytes.
  Retrieval ID: `72ba039a0d6f4da78445bcbbe596a4ac`.
  SHA-256: `6d5a418d110000e6a5305eb8545866664a63fae63b0a5df75090c55999824692`.
- `pa-amendments-2025`: 16 reader-reported pages, 618,431 bytes.
  Retrieval ID: `365ef565cbb644a0a65d17b1097409eb`.
  SHA-256: `ae8a66ac89d9e64a26d4191fd383e0d00ca6cd7f5fa2b6c6b941134cdc1805f1`.
- `pa-empire-plan-report-2026`: 12 reader-reported pages, 1,659,659 bytes.
  Retrieval ID: `bf49adce2b59476da04e68c2ee16ca51`.
  SHA-256: `5d5ee250ec777652f038ecf51dc6bf0d65f2f44dbd66aa825d609c77b7136cf1`.

Separate disk readback verified all three originals against their receipt and
inspection-report IDs, byte counts, and SHA-256 values. The local library has
exactly three records; its staging directory is empty. The certificate hash
matches the historical September review; no prior verified hash comparison
was available here for the other two. Reader page counts are not rendering,
text-quality, scan/OCR, or benefit-applicability verification.

The approved root contains `approval.md`, `sources.json`, `manifest.json`,
`summary.json`, per-attempt `reports/<retrieval_id>-started.json` and
`reports/<retrieval_id>-result.json`, and unchanged storage records under
`records/<retrieval_id>/original.bin` plus `receipt.json`. The `.bin` extension
is the existing storage convention, not a transformed document. Originals,
local registry, and inspection reports remain outside Git.

The pinned CPython 3.11.16 environment with pypdf 6.19.0 was restored first.
All 10 coordinator tests and the separate local TLS test passed before the
live run. This pilot changed no application code, dependency, checked-in
registry, or receipt schema. The full regression count elsewhere is historical,
not a new full-suite run for this documentation-only pilot.

No retries, alternate HTTP clients, text extraction, OCR, passwords, public
uploads, or redistribution were used. The earlier blocked library inventory
remains unresolved; these three documents are not proof of complete/current
coverage. This closes the bounded three-document local pilot, not Phase 1 or
a grant for future collection or redistribution.

## Sources

[1] https://www.cs.ny.gov/robots.txt
[2] https://nyship.ny.gov/g/pa/ep/documents-publications-library
[3] https://www.cs.ny.gov/employee-benefits/pa-market/shared/publications/certificate/2025/pa-online-certificate-2025.pdf
[4] https://www.cs.ny.gov/employee-benefits/shared/publications/amendments/2025/pa-amendments-2025.pdf
[5] https://www.cs.ny.gov/employee-benefits/pa-market/shared/publications/empire-plan-report/2026/pa-epr-2026.pdf
[6] https://www.cs.ny.gov/home/disclaimer.cfm
[7] https://www.cs.ny.gov/home/privacypolicy.cfm

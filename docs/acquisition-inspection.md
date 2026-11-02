# Acquire and inspect one document

Status: implemented and verified; independent review passed with no blockers.
No live pilot has been approved or executed.

## Small connection, unchanged components

The coordinator connects [single-source acquisition](acquisition.md) to
[contained inspection](inspection-worker.md). It downloads one explicitly
approved PDF candidate, saves its exact bytes, then asks the existing Windows
worker to inspect that saved record. It does not add a downloader or parser.

```text
acquire_and_inspect_pdf(registry, source_id, root, *, retrieval_id,
                       approval, acquisition_limits, inspection_limits)
    -> AcquiredPdfInspection
```

Module: `payer_policy.acquisition_inspection`. All keyword arguments are
explicit. Use the existing `AcquisitionApproval`, `AcquisitionLimits`, and
`InspectionLimits` types. The frozen result contains two existing values:

- `acquisition`: `AcquisitionResult`, with source/retrieval IDs, final URL,
  SHA-256 fingerprint, and original/receipt paths. The receipt holds the
  requested URL and UTC retrieval time; the coordinator does not reread it.
- `inspection`: `PdfInspection`, with the same retrieval ID and fingerprint,
  an encryption flag, and page count (`None` for encrypted PDFs).

No PDF-body copy or new receipt schema is added. A matching fingerprint ties
these two observations together; it does not establish authenticity or prevent
later file changes. An encrypted result is explicitly encrypted, not proof of
readability. A page count does not certify PDF safety, complete rendering,
text availability, plan applicability, or current benefits.

## Order and budgets

1. Snapshot and check both budget objects. Check the worker's input and runtime
   layout using existing helpers before acquisition can contact a source.
2. Acquire the selected source through the unchanged approval, transport,
   validation, and storage rules.
3. Inspect the saved record in the Windows worker using the same byte limit.
   The child verifies and parses saved bytes; the coordinator does not do so.
4. Compare inspection and acquisition retrieval IDs and fingerprints. Return
   only after they match and the worker has confirmed cleanup.

Defaults remain 10,000,000 acquired bytes, ten seconds per socket operation,
three redirects, a 30-second worker wait, and 256 MiB committed memory. Pass
`AcquisitionLimits()` and `InspectionLimits()` to select those defaults. Each
component retains its existing allowed overrides and ceilings. There is no
whole-pipeline deadline, CPU quota, filesystem/network sandbox, or automatic
retry with larger limits. Runtime preflight does not guarantee that later
native process creation or filesystem access will succeed.

Private validation helpers are reused inside this package to avoid copying
rules. Changes to those helpers require coordinator regression tests. No
public behavior of acquisition, storage, or inspection is replaced.

## Failures and saved originals

- Invalid inspection settings or an unsupported runtime fail before fetching.
  Preflight exceptions retain their existing types/codes; no new record exists.
- Acquisition errors propagate unchanged. Inspection must not start afterward.
  Existing acquisition rules still allow a late storage error to leave a record.
- A known worker failure after acquisition raises `PipelineInspectionError`.
  Its `acquisition` field identifies the saved record, `code` preserves the
  worker failure category, and `cause`/exception chaining preserve the local
  `WorkerInspectionError`. This is not a reconstructed remote traceback.
- A result ID or fingerprint mismatch raises `PipelineInspectionError` with
  `code="identity_mismatch"` and no underlying exception (`cause=None`).
- Unexpected programming errors, memory errors, and interrupts propagate; they
  are not disguised as ordinary document failures.

No failed inspection deletes or retries the saved original. Recovery can use
`inspect_saved_pdf_in_worker` directly on that retrieval ID rather than fetch
again. Approval is still a trusted caller decision tied to an exact URL and
reviewed hosts; a note's existence does not prove permission.

## Offline example (executed successfully)

Run this literal Python block from the repository root on Windows using the
pinned development environment. `TMPDIR` should point to a trusted local
scratch directory. It creates a one-page blank PDF in memory with the already
pinned parser package, substitutes only the fetch response, then performs real
storage and contained inspection. Parent DNS/socket entry points are blocked;
this guard is not a child-process network sandbox. No real source is contacted.
The temporary originals and receipt are removed when the example exits.

```python
import os
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

with (patch("socket.getaddrinfo", side_effect=AssertionError("No DNS")),
      patch("socket.socket", side_effect=AssertionError("No network"))):
    from pypdf import PdfWriter
    from payer_policy.acquisition import AcquisitionApproval, AcquisitionLimits
    from payer_policy.acquisition_inspection import acquire_and_inspect_pdf
    from payer_policy.https_transport import FetchResult
    from payer_policy.inspection_worker import InspectionLimits

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    output = BytesIO()
    writer.write(output)
    body = output.getvalue()
    with TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
        root = Path(directory)
        note = root / "review.txt"
        note.write_text("Synthetic offline example only.", encoding="utf-8")
        source_id = "synthetic-source"
        url = "https://example.org/synthetic.pdf"
        registry = {source_id: {
            "source_id": source_id, "name": "Synthetic example",
            "url": url, "publisher": "Fixture publisher",
            "category": "reference", "plan": "unknown",
            "program": "unknown", "applicability_status": "unknown",
            "evidence_url": "", "access_restrictions": "offline only",
        }}
        approval = AcquisitionApproval(source_id, url, ("example.org",), note)
        response = FetchResult(
            url, 200, (("Content-Type", "application/pdf"),), body)
        with patch("payer_policy.acquisition.fetch_https",
                   return_value=response):
            result = acquire_and_inspect_pdf(
                registry, source_id, root,
                retrieval_id="0123456789abcdef0123456789abcdef",
                approval=approval, acquisition_limits=AcquisitionLimits(),
                inspection_limits=InspectionLimits())
        assert result.inspection.page_count == 1
        assert result.inspection.is_encrypted is False
        assert result.inspection.sha256 == result.acquisition.sha256
        assert result.acquisition.original_path.read_bytes() == body
        print("Offline pipeline verified: one page, matching fingerprint")
```

## Acceptance and live-pilot gate

Closeout verification on November 1, 2026, Windows, Python 3.11.16 with unchanged
`pypdf==6.19.0`: all 10 coordinator tests passed, including controlled HTTP
through real acquisition/storage/worker calls for valid, malformed, and
encrypted synthetic PDFs. Full suite: 163 methods, 162 passed and one existing
optional Windows link skip. Separate local TLS test passed. The literal
example above printed `Offline pipeline verified: one page, matching fingerprint`.
Syntax, function docstrings/annotations, and 79-character checks passed for
both new Python files. Independent review passed with no blockers and
independently ran all 10 coordinator tests. Its only suggestion was to replace
the pending verification statuses, now resolved. The reviewed code, tests, and
dependency pin were unchanged from reviewed revision `86c54a0` at closeout.
All 53 local Markdown links in the four increment documents resolved. Mermaid
structure passed (26 nodes, 29 edges); visual rendering was not verified.
Security-pattern scans and whitespace checks found no issues; these checks
are not a security guarantee. This closes the offline increment only.

The live pilot is **not approved or executed** by this implementation. The
[historical PA certificate review](source-reviews/pa-certificate-2025.md) is a
candidate, not current access or applicability evidence. Before a real pilot,
recheck the official document, access conditions and redirect hosts; present
the exact URL, local storage scope and restrictions for document-specific
approval. Do not bypass access controls, infer redistribution rights, or add
real policy PDFs to Git. Unresolved access questions keep the live gate closed.

Extraction, OCR, crawling, batching, scheduling, database, UI, installer,
new dependencies, and changed storage schemas remain excluded.

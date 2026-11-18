# Bounded page text and derived storage

Status: approved November 7, 2026; implemented and verified November 8, 2026.
Independent review passed with no blocking security, logic, or contract findings.

## Purpose and approval boundary

Read selected pages from a verified saved PDF, keeping enough information to
find each page again. Save the returned text separately so the original stays
unchanged. The implementation increment used synthetic PDFs only. A separately
approved [local PA text-quality pilot](source-reviews/pa-text-quality-pilot.md)
now covers a bounded real-document sample with local human review. The approved
automatic twelve-page sample was extracted, saved, and checked by disk readback;
human visual review remains pending. No new download, document upload, or
redistribution is included.

## Public operations

- `extract_saved_pdf_pages_in_worker(root, retrieval_id, *, pages,
  limits=None) -> PdfTextExtraction`: verify and extract inside a bounded
  Windows child; accept only a complete matching result after child cleanup.
- `save_text_extraction(root, extraction, *, extraction_id) -> Path`:
  validate the result, publish a separate JSON artifact without replacing an
  earlier run, and verify readback. A storage failure does not change originals.

`pages` is a nonempty ascending tuple of unique positive integers, at most
10 entries. Page one means the first physical PDF page, not a printed label.
Reject invalid selections instead of sorting, rounding, or silently clipping.
An out-of-range selection fails the entire batch. A successful batch says
nothing about pages not requested or overall policy completeness.

Use pinned pypdf 6.19.0 `extract_text(extraction_mode="plain")`. Preserve its
returned string: no trimming, header removal, dehyphenation, or repairs.
Per-page status distinguishes non-whitespace text from empty/whitespace-only
text without changing either. Empty extraction is not a diagnosis of scanning.
Reject encrypted documents; no password or permission-bypass feature is added.

## Budgets

Defaults and ceilings:

- Original bytes: 10,000,000.
- Selected pages: 1–10 per call.
- Text per page: 65,536 UTF-8 bytes.
- Combined text: 524,288 UTF-8 bytes.
- Serialized result/artifact: 1,048,576 bytes, including metadata and escaping.
- Request protocol: at most 65,536 bytes, separate from inspection messages.
- Worker memory: 256 MiB, with the existing supported 16–256 MiB range.
- Worker wait: 30 seconds; configurable above zero through 60 seconds.

Byte budgets may be lowered. Boolean values are not integer budgets. Text-byte
and serialized-byte checks are separate: JSON overhead can make a result fail
even when its text fits. No partial result or silently shortened text is a
success. An over-budget request is not retried with relaxed limits.

Success messages and saved artifacts must fit the selected result budget.
Small error envelopes use the fixed protocol ceiling so a budget too small
for metadata can still return an explicit `output_limit` failure.

A text-length check occurs after parser allocations, so the Windows memory
limit is essential. The wait budget and bounded cleanup do not promise an
end-to-end wall-clock deadline. Job Objects are resource/lifecycle controls,
not filesystem, network, or permission isolation.

## Provenance and publication

Retain the original retrieval ID and SHA-256, requested physical pages, exact
per-page text/status, extraction timestamp, parser/version, extraction mode,
applied limits, and schema version. Each saved run also has its own extraction
ID. These fields tie text to saved bytes; they do not establish publisher
identity, applicability, completeness, or accuracy.

Publish under the library's separate `derived/` tree, not `records/`. Use
same-root staging and Windows no-overwrite directory publication. A repeated
extraction ID conflicts rather than replacing a prior run. Verify bounded
readback after publication. Interrupted staging may remain for manual review;
a post-publication failure can leave a published artifact. File flushing and
rename are not a power-loss or hostile-same-user defense. The library root
must remain trusted.

`PdfTextExtraction` holds `retrieval_id`, `sha256`, `page_count`,
`requested_pages`, `pages`, `extracted_at`, `limits`, `schema_version`,
`parser_name`, `parser_version`, and `mode`. Each `PageText` holds
`page_number`, `text`, and `status` (`text` or `empty`). The frozen result and
settings objects cannot be changed in place. The timestamp is aware UTC; JSON
stores it with six fractional digits and a trailing `Z`.

The saved envelope contains exactly `schema_version: 1`, `extraction_id`, and
`extraction` (the result facts). Its path is
`derived/<extraction_id>/extraction.json`. The saver rechecks the original
receipt and fingerprint in the calling process; it does not parse PDF pages.
An extraction success does not guarantee that a later storage operation will
succeed. These APIs remain separate; acquisition does not invoke extraction.

## Failure boundaries

Distinguish invalid inputs/runtime, missing or altered originals, encryption,
page-range errors, supported parser failures, output limits, worker memory or
timeout/crash, malformed or mismatched results, cleanup, and storage failures.
Validate ordinary inputs in narrow handlers; an unexpected parser programming
error must not be relabeled as an ordinary invalid PDF. Fail closed on unknown
response fields, invalid identities, partial facts, or malformed JSON.

Invalid caller inputs raise `TypeError` or `ValueError` before launch.
`ExtractionError.code` distinguishes child failures (`input_error`,
`storage_error`, `encrypted`, `range_error`, `parser_error`, `output_limit`,
`memory_error`) from supervisor failures (`unsupported_runtime`, `setup_error`,
`timeout`, `crash`, `ipc_error`, `invalid_result`, `cleanup_error`).
The saver uses the existing `StorageConflictError`/`StorageIntegrityError`
for conflicts and mismatched/damaged evidence; ordinary OS errors propagate.
An oversized serialized artifact raises a protocol `ValueError` before
publication. Unknown parser errors are not translated into invalid inputs.

## Executable synthetic example

Run this Python block from the repository root on Windows using the configured
Python 3.11 development environment and pinned requirements. It creates only
temporary synthetic originals and derived text; all are removed on exit.
The DNS/connection guards apply to the calling process, not child permissions.
The small PDF fixture uses pypdf generic objects; no extra PDF-writing package
is required. The literal example passed on November 7 and again at closeout
on November 8, 2026: both selected pages, saved JSON, and unchanged
originals/receipt were checked. This is not real-policy accuracy evidence.

```python
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject, DictionaryObject, NameObject,
)
from payer_policy.document_storage import save_pdf_candidate
from payer_policy.extraction_storage import save_text_extraction
from payer_policy.extraction_worker import extract_saved_pdf_pages_in_worker
from payer_policy.https_transport import FetchResult

writer = PdfWriter()
page = writer.add_blank_page(width=300, height=300)
font = DictionaryObject({
    NameObject("/Type"): NameObject("/Font"),
    NameObject("/Subtype"): NameObject("/Type1"),
    NameObject("/BaseFont"): NameObject("/Helvetica"),
})
page[NameObject("/Resources")] = DictionaryObject({
    NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): writer._add_object(font),
    }),
})
content = DecodedStreamObject()
content.set_data(
    b"BT /F1 12 Tf 30 100 Td (Synthetic policy text.) Tj ET"
)
page[NameObject("/Contents")] = writer._add_object(content)
writer.add_blank_page(width=300, height=300)
buffer = BytesIO()
writer.write(buffer)
original_bytes = buffer.getvalue()
url = "https://example.org/synthetic.pdf"  # Metadata only; never fetched.

with TemporaryDirectory(
    prefix="policy-text-", dir=os.environ.get("TMPDIR"),
) as directory, patch(
    "socket.getaddrinfo", side_effect=AssertionError("no DNS in example"),
), patch(
    "socket.create_connection",
    side_effect=AssertionError("no connection in example"),
):
    root = Path(directory)
    retrieval_id, extraction_id = "a" * 32, "b" * 32
    saved = save_pdf_candidate(
        root,
        FetchResult(url, 200, (("Content-Type", "application/pdf"),),
                    original_bytes),
        retrieval_id=retrieval_id, source_id="synthetic-text",
        requested_url=url, retrieved_at=datetime.now(timezone.utc),
    )
    receipt_before = saved.receipt_path.read_bytes()
    extracted = extract_saved_pdf_pages_in_worker(
        root, retrieval_id, pages=(1, 2),
    )
    assert extracted.pages[0].text.strip() == "Synthetic policy text."
    assert extracted.pages[1].status == "empty"
    assert extracted.requested_pages == (1, 2)
    assert extracted.sha256 == saved.receipt["sha256"]
    target = save_text_extraction(
        root, extracted, extraction_id=extraction_id,
    )
    artifact = json.loads(target.read_text(encoding="utf-8"))
    assert artifact["extraction_id"] == extraction_id
    assert artifact["extraction"]["pages"][0]["text"] == (
        extracted.pages[0].text
    )
    assert saved.original_path.read_bytes() == original_bytes
    assert saved.receipt_path.read_bytes() == receipt_before
    print("PASS: text + blank page, saved JSON, originals unchanged")
```

## Verified closeout — November 8, 2026

Verified on Windows with CPython 3.11.16 and unchanged pypdf 6.19.0:

- Full suite: 192 methods run, 191 passed, one existing optional original-file
  symlink-privilege skip. The separate local-loopback TLS test passed.
- All 29 extraction methods passed without skips. Independent read-only review
  reran them and found no blocking security, logic, or contract defects.
- The literal example above passed. Source checks covered eight new Python
  files and 56 functions: syntax, docstrings, annotations, and 79-column lines.
- Local documentation links and diagram references passed structural checks;
  diagram rendering was not visually verified.
- Review covered the complete increment from `345c82f` through
  `cd00994159f1d7e6771c85bc5b2977f2e105e5e7`. Code/test hashes and the
  reviewed diff were unchanged before documentation-only closeout.

### What the tests establish

Real synthetic PDFs exercise known text, blank/image-only/rotated pages,
encryption, malformed files, selected-page ranges, and stored-byte limits.
Native Windows jobs exercise success and controlled timeout, nonzero exit,
parser-bug, and memory-failure children. The tests check closed jobs, no
remaining active job processes, removed IPC directories, unchanged originals,
and successful subsequent extraction. Controlled failures are not evidence
of naturally occurring parser defects or a complete security sandbox.

Storage tests exercise real competing publication, child-process interruption
before and after publication, directory-junction rejection, source rehashing,
no-overwrite behavior, and exact artifact readback. Readback and setup/cleanup
fault classifications also use injected faults. The optional original-file
symlink test remains skipped; directory-junction checks passed.

One reproduced protocol bug was corrected through RED/GREEN: success reply
limits now count received bytes, including trailing whitespace, rather than
only re-encoded JSON. UTF-8 boundaries and whitespace preservation include
injected parser strings. Serialized JSON tests include escaping and metadata.
Input-byte execution uses a lowered configured cap; the 10,000,000-byte
endpoint is validated as a setting, not a large real-document workload.

### Non-blocking follow-ups and exclusions

The reviewer suggested a real synthetic Unicode PDF and explicit cleanup
failures after a successful result. These are additional coverage opportunities;
inspection confirmed both cleanup boundaries precede the public return.
No real-policy text, layout, Unicode decoding, applicability, or completeness
was evaluated. Passing synthetic tests is not exhaustive correctness proof.

No new dependency, OCR, chunking, embeddings, indexing, search, chat, automatic
library processing, or changes to the existing inspection contract are included.
Real-document usefulness and rendering accuracy remain unverified.

## API references and rationale

- [pypdf extraction documentation](https://pypdf.readthedocs.io/en/6.19.0/user/extract-text.html):
  extracting a page processes its content stream and can require substantial
  memory; text order/layout may differ from visual appearance, and pypdf is
  not an OCR engine. Reuse the pinned parser before considering more packages.
- [Python os.rename](https://docs.python.org/3.11/library/os.html#os.rename):
  Windows raises when the destination exists. Use this platform-specific
  behavior deliberately rather than a replacement operation.
- [Original storage contract](document-storage.md): bounds and verifies saved
  bytes; trusted-root and interruption limitations still apply.
- [Inspection worker contract](inspection-worker.md): reuse trusted-runtime and
  Job Object mechanics without widening the existing inspection protocol.

## Explicit corrected derived view

`corrected_text_view` is an opt-in local computation in `text_extraction.py`.
It returns a JSON-ready derived view containing the complete unchanged raw
extraction, source retrieval ID and SHA-256, parser version, corrected pages,
and per-edit provenance. It does not save files or change the extraction
worker, raw artifact schema, PDF bytes, receipts or parser defaults.
This API parses supplied bytes in the calling process: run it only within a
resource-bounded local caller. It does not inherit the Windows worker's Job
Object containment. No pilot files were changed by this implementation.

Callers must explicitly supply the expected retrieval ID and source hash plus
a tuple of `SpacingCorrection` records. Each record identifies a physical
one-based page, zero-based raw output-space offset, exact unique context span
and its start, zero-based content-stream operation index, and zero-based TJ
array item index. These are reviewed inputs, never automatically generated
from capital-Y patterns. Real-source identities and correction manifests are
not hardcoded in the implementation.

For each record the implementation rechecks source bytes, pinned parser,
raw page text and context; rejects overlapping or repeated spans and external
content (`Do`); requires a literal Y ending the left TJ string, a lowercase
letter starting the right string, and exactly +126 between them. A separate
in-memory content stream neutralizes only that numeric item. Its bytes are
placed in a fresh decoded stream on a shallow page copy, retaining the source
resources. Indirect streams and arrays of streams are resolved and concatenated
in their original order for this trial only. Extraction must
then equal the original text with exactly the nominated space deleted.
Literal spaces, unrelated letters, wrong operations, stale hashes, stale raw
text and incorrect mappings fail with `ValueError`. No regular-expression
replacement or PDF serialization is involved. Applying the same manifest to
corrected text fails the raw-baseline check; combined corrections use original
coordinates in descending order and retain their original provenance.

The confirmed amendments physical-page-1 evidence is offsets 287 and 418,
+126 adjustments, space width 129 and threshold 122.55. These measurements
justify this narrow mechanism, not automatic correction of all candidates.
The synthetic two-offset regression uses those coordinates without policy
text. A separate metadata-only read-only probe on November 17, 2026 passed
against the saved amendments original with pypdf 6.19.0: physical page 1,
offset 287 / operation 50 / item 1 and offset 418 / operation 1425 / item 1.
The original is 618,431 bytes and has an indirect single content stream.
Each isolated correction reduced 504 characters to 503; both together
produced 502. Exact deletion comparisons, unchanged raw provenance, original
bytes and receipt bytes all passed. No external pilot artifacts were written.
Callers still supply reviewed source identity and correction coordinates.

The regression was caused by passing a direct `ContentStream` to extraction:
pypdf then skipped the normal stream-byte parse with `forced_encoding='bytes'`.
Default content-stream string decoding could change unrelated font bytes,
making the exact counterfactual fail. A synthetic high-byte string reproduces
this mismatch for both an indirect stream and an indirect array of indirect
streams. Rebuilding only the trial stream bytes restores the normal extraction
path; no complete PDF is serialized and parser defaults remain unchanged.

The [official pypdf extraction guide](https://pypdf.readthedocs.io/en/6.19.0/user/extract-text.html)
explains that positioned text makes whitespace inference difficult and that
page extraction can require substantial memory. Exact counterfactual checks
establish a parser-inserted space, not semantic or visual correctness.

Regression guidance: pypdf's `append(pages=...)` tuple denotes a range; use a
list for explicit page indexes. Synthetic +126 fixtures must declare font
widths giving the relevant insertion threshold, rather than assume that a
standard font reproduces the diagnosed boundary.
For future counterfactual changes, preserve plain extraction's stream decoding
path and test non-ASCII font bytes with indirect and array contents; ASCII-only
fixtures cannot detect this regression. Run this focused module with
`python -m unittest discover -s tests -p test_text_extraction.py -v` so its
shared test helpers resolve. On November 17, 2026 all 12 methods passed on
CPython 3.13 with pypdf 6.19.0, including
`SpacingViewTests.test_indirect_contents_preserve_parser_string_decoding`
(two content-structure subcases).

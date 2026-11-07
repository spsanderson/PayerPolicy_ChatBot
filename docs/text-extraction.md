# Bounded page text and derived storage

Status: approved November 7, 2026; implementation and verification in progress.
This document records the target contract, not a completed implementation.

## Purpose and approval boundary

Read selected pages from a verified saved PDF, keeping enough information to
find each page again. Save the returned text separately so the original stays
unchanged. This increment uses synthetic PDFs only. Processing the three
saved PA policies, and comparing their text with rendered pages, require a
separate approval. No new download, document upload, or redistribution is
included.

## Proposed public operations

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

Proposed defaults and ceilings:

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

## Failure boundaries

Distinguish invalid inputs/runtime, missing or altered originals, encryption,
page-range errors, supported parser failures, output limits, worker memory or
timeout/crash, malformed or mismatched results, cleanup, and storage failures.
Validate ordinary inputs in narrow handlers; an unexpected parser programming
error must not be relabeled as an ordinary invalid PDF. Fail closed on unknown
response fields, invalid identities, partial facts, or malformed JSON.

## Verification gates — pending

- Sequential RED/GREEN tests with real synthetic PDF fixtures.
- Known text, selected pages, blank/image-only/rotated/encrypted/malformed PDFs.
- Exact and over-limit UTF-8/serialized boundaries; no silent normalization.
- Worker failure/cleanup, strict response validation, and unchanged originals.
- Derived-artifact round-trip, conflict, interruption, and readback failures.
- Existing regressions, local TLS, source conventions, and independent review.
- A literal executable offline example, local links, and diagram structure.

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

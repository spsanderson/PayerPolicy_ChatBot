# PA text-quality pilot — local-only

Status: scope approved November 8, 2026; preparation verified; page selection,
extraction, and human visual review pending. This is not an accuracy verdict.

## Approved boundary

Use only the three originals from the [saved PA pilot](representative-pa-pilot.md):
`pa-certificate-2025`, `pa-amendments-2025`, and
`pa-empire-plan-report-2026`. No new download or document substitution.

Select at most four physical PDF pages per document, at most twelve total.
Choose pages through local visual inspection, not guessed page numbers.
Aim to cover paragraphs/headings, qualifications or exclusions, numbers/dates,
footnotes, and tables where present. Record exact selections and reasons before
extraction; printed footer labels are not physical PDF page numbers.

The unchanged [extraction worker and saver](../text-extraction.md) retain their
existing default limits. Make one selected-page batch attempt per document.
Stop at the first extraction/storage failure, record unattempted documents,
and do not retry, relax limits, or substitute another parser automatically.

The visual comparison is performed by a local human reviewer. No policy text,
page images, or PDF copies may be returned through model-facing tools or
uploaded to chat. Only metadata, counts, page numbers, and issue categories
are returned. Assistant-led visual review would need separate transmission
approval. Local processing approval does not establish publisher licensing,
redistribution rights, current benefit applicability, or complete coverage.

## Readiness and preparation

The latest committed storage change (`43bbe29`) translates an existing regular
`derived` file into a clear ValueError. A new characterization test passed on
that implementation: the blocking file, originals, receipts, and filesystem
inventory remain unchanged. No production edit was needed. Ten storage tests,
193 full-suite methods (192 passed, one existing skip), and the separate local
TLS test passed. Narrow independent review passed with no findings and
independently reran all ten storage tests. Review covered the production change
at `43bbe29f477e97f04b4613ad54c31226c24faa14` and the new unstaged test.
The reviewed production code and test remained unchanged when preparation
resumed; the storage-readiness gate is complete.

Three byte-identical `.pdf` viewing copies were published outside Git and
read back against verified saved bytes. Original files and receipt bytes were
unchanged. The historical inspected page counts are 165, 16, and 12; these are
not new rendering or text-quality findings.

Local working directory:

```text
C:\Users\steve\Documents\PayerPolicyLibrary\pilot-pa\text-quality-pilot-20261108
```

`pdfs/` holds the viewing copies. `approval.json` records the scope and
`selection.json` currently has empty page lists. `README.txt` contains the
local selection/review checklist. No pages have been extracted for this pilot.

## Completion criteria — pending

- Record at most four selected physical pages per document and their reasons.
- Verify source identity before each attempt; preserve attempt/result evidence.
- Read back each saved extraction and confirm original/receipt preservation.
- Complete local page-by-page visual review of omissions, order, negations,
  quantities, footnotes, and table relationships.
- Classify each reviewed page as usable, usable with caveats, not usable, or
  not reviewed; retain unreviewed gaps explicitly.
- Report whether this sample supports a bounded citation-preserving chunking
  experiment, exposes a specific extraction defect, or remains inconclusive.

Keep detailed text and review artifacts outside Git. Repository reporting uses
metadata, page references, and issue categories without copying policy text.
No OCR, indexing, embeddings, chat, production UI, or new dependencies are
included. A nonempty extraction is not evidence of accuracy.

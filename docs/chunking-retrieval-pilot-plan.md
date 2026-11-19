# Bounded chunking and retrieval pilot

Status: **proposed — review required; not implemented**.

## Purpose

Test whether the reviewed PA page sample can be turned into small, reviewable
chunks and retrieved with reliable source citations. This pilot is evidence for
the next design decision; it is not approval for document-wide indexing, public
collection, production search, or a full RAG system.

The pilot starts only after the text-quality gate for the reviewed sample. It
uses the twelve selected physical pages from the three-document PA sample and
the final, separately stored corrected derived views where the gate identified
parser-inserted spacing defects. Original PDFs, receipts, raw extraction, and
existing derived artifacts remain read-only inputs.

## Scope contract

### Included

- Three already approved pilot documents:
  `pa-certificate-2025`, `pa-amendments-2025`, and `pa-empire-plan-report-2026`.
- The twelve selected physical pages recorded by the text-quality pilot.
- A checked-in metadata manifest that identifies each page without copying
  policy text into the repository.
- Local deterministic chunking and a local lexical retrieval baseline.
- Evaluation against a small, reviewed query set with expected document/page
  references.
- Chunk previews and retrieval reports saved as separate derived artifacts.

### Excluded

- New downloads, OCR, parser changes, or document-wide processing.
- Indexing any page that is not in the approved twelve-page set.
- Embeddings, hosted vector databases, provider APIs, chat answers, or model
  selection.
- Automatic correction, dehyphenation, header removal, or text rewriting.
- Claims about policy applicability, legal rights, completeness, or production
  retrieval quality.
- Publishing policy text to Git, chat, telemetry, or an external service.

## Proposed input contract

The pilot will consume a local manifest assembled from the completed text-quality
review. Each entry must identify:

- stable document/source ID;
- retrieval ID and original PDF SHA-256;
- one-based physical page number;
- raw extraction artifact and page-text identity;
- optional corrected-derived artifact identity;
- parser name/version and extraction mode;
- text-quality verdict and correction-manifest reference, if applicable.

The loader will reject missing identities, mismatched hashes, duplicate
(document, page) entries, unapproved pages, altered raw artifacts, and corrected
text whose provenance does not point back to the matching raw page. It will not
silently fall back from corrected text to raw text when a correction is declared
but unavailable.

The manifest is a control plane, not a copy of the policy. Detailed text remains
outside Git in the local pilot library.

## Proposed chunk contract

Each emitted chunk will contain at least:

- deterministic `chunk_id` derived from source identity, physical page, and
  ordinal;
- source/document ID, retrieval ID, original SHA-256, and physical page;
- page-local ordinal and character/line boundary in the selected input text;
- exact chunk text, unchanged except for boundary selection;
- structure labels such as `heading`, `paragraph`, `list`, `table`, or
  `mixed/unknown`;
- parent heading path when confidently identified;
- a boundary note when a structure could not be identified safely.

A chunk must never cross a document or physical-page boundary. The default
policy will keep a heading with the content that follows it, keep contiguous
list items together when they fit, and keep a detected table-like block intact.
If a protected block exceeds the configured size, the chunker will split it only
at an explicit safe line boundary and record the split. It will never invent a
missing table layout.

Chunk text is not normalized. Whitespace, punctuation, line order, and page
content remain as supplied by the selected raw or corrected derived artifact.
The corrected view is an input choice recorded in provenance, not a replacement
of raw evidence.

## Proposed retrieval contract

The first retrieval baseline will be deterministic lexical ranking over the
pilot chunks. It will:

1. normalize only a query-side comparison copy for matching;
2. tokenize query and chunk text with a documented standard-library tokenizer;
3. score term overlap with document-frequency weighting and a length
   normalization term;
4. return a stable tie-break order using score, document ID, page number, and
   chunk ordinal;
5. return the exact chunk text and complete provenance for every hit.

The indexed chunk text and stored chunk artifact remain unchanged. Query-side
normalization is used only for comparison and must not alter citations.

This method is preferred for the first pilot because it is local, reproducible,
explainable, inexpensive, and independent of an embedding model or provider.
It gives a useful baseline before introducing semantic retrieval, whose gains
would otherwise be difficult to separate from chunking or citation defects.

## Evaluation design

Create a small test set from the approved pages. Each query record will contain:

- query ID and question text;
- expected source/document ID;
- one or more expected physical pages;
- expected chunk IDs after chunking;
- a short rationale kept outside Git if it would copy policy text;
- an `answerable` flag for deliberate no-evidence cases.

The initial test set should include, at minimum:

- heading and section lookup;
- list-item lookup;
- table-row or table-like content lookup;
- cross-page disambiguation where page provenance matters;
- a query whose evidence is absent from the twelve pages;
- at least one query for each pilot document.

The pilot will report:

- Recall@1 and Recall@3 for expected chunks;
- page-citation accuracy;
- source-document citation accuracy;
- no-evidence rejection accuracy;
- duplicate or contradictory hit observations;
- chunk-boundary and structure-preservation review findings.

These are pilot measurements, not production targets. The report must enumerate
failures with their query IDs and retrieved provenance rather than hiding them
behind an aggregate score.

## Implementation slices after approval

### Slice 1 — approved input manifest

Proposed module: `payer_policy/pilot_inputs.py`.

- Define typed manifest/page records.
- Validate source identity, hashes, page allowlist, artifact choice, and
  correction provenance.
- Add tests for valid input, stale hash, unapproved page, duplicate page,
  missing corrected artifact, and raw-artifact mutation.

**Why:** provenance errors must fail before chunking; otherwise later retrieval
results cannot be trusted or reproduced.

### Slice 2 — deterministic structure-aware chunking

Proposed module: `payer_policy/chunking.py`.

- Preserve source text exactly.
- Segment page-local blocks using conservative line and blank-line rules.
- Protect headings, contiguous lists, and table-like blocks from accidental
  splitting.
- Apply a small explicit chunk-size setting and record all boundary decisions.
- Emit a validated chunk artifact without overwriting any input.

**Why:** a simple, inspectable chunker makes boundary mistakes visible and avoids
embedding layout assumptions into a production abstraction before the sample is
understood.

### Slice 3 — chunk preview and structural review artifact

Proposed local report writer, likely alongside `chunking.py`.

- Produce metadata-only repository reports and detailed local previews.
- Show each chunk's source/page/ordinal and structure labels.
- Record reviewer verdicts for headings, lists, tables, page boundaries, and
  suspicious splits.

**Why:** retrieval scores cannot reveal that a heading was separated from its
section or that a table was split incorrectly.

### Slice 4 — lexical retrieval baseline

Proposed module: `payer_policy/retrieval_pilot.py`.

- Build an in-memory index from validated chunks.
- Rank with deterministic term overlap and document-frequency weighting.
- Return stable, provenance-complete hits.
- Reject malformed indexes, duplicate chunk IDs, and queries with invalid types.

**Why:** this establishes a low-dependency baseline and isolates chunking and
provenance behavior from embedding-model behavior.

### Slice 5 — evaluation runner and report

- Load the reviewed query set.
- Run every query without retries or hidden query rewriting.
- Compute the declared metrics and preserve per-query results.
- Verify that every reported citation resolves to the exact source/page/chunk
  used by the hit.

**Why:** an auditable per-query report is more useful than a single score for a
small exploratory sample.

## Failure boundaries

The pilot must fail closed on:

- source or retrieval identity mismatch;
- changed original SHA-256 or raw extraction;
- missing or invalid corrected-derived provenance;
- unapproved physical pages;
- duplicate or overlapping chunk IDs;
- chunks crossing page/document boundaries;
- malformed query or expected-result records;
- missing citation metadata;
- nondeterministic tie ordering;
- incomplete evaluation output.

A retrieval miss is a measured result, not an exception. An absent-evidence query
must not be converted into a guessed answer. No answer-generation component is
part of this pilot.

## Acceptance criteria

The pilot can be marked complete only when all of the following have evidence:

- every input page is reconciled to the approved text-quality manifest;
- raw and corrected-derived artifacts remain unchanged and separately stored;
- chunk artifacts round-trip and preserve exact selected text;
- all chunks have source, retrieval, hash, physical-page, and ordinal metadata;
- headings, lists, and table-like blocks receive an explicit preservation
  verdict, including `unknown` where the extraction cannot prove structure;
- no chunk crosses a document or physical-page boundary;
- retrieval results are deterministic across two runs;
- every hit cites the correct source document and physical page;
- the no-evidence query does not return an unsupported citation as a match;
- the report contains per-query results plus Recall@1, Recall@3, citation
  accuracy, and identified failures;
- focused tests, the full repository suite, source-convention checks, and the
  literal offline example (if added) pass;
- independent read-only review finds no unresolved blocking contract or
  provenance issue.

Passing these criteria authorizes only a bounded pilot conclusion. It does not
authorize production indexing or a full RAG rollout.

## Proposed verification approach

Use the repository's RED/GREEN workflow one behavior at a time:

1. write a failing test naming the missing contract;
2. implement the smallest behavior;
3. run focused tests;
4. add boundary and mutation tests;
5. run the full suite and independent report checks;
6. update the delivery plan only for behavior actually implemented.

Use standard-library `unittest` and existing project dependencies first. Do not
add an embedding package, vector database, or provider SDK for this pilot.

## Decisions requested before implementation

1. Approve the twelve-page reviewed sample as the complete pilot input.
2. Approve page-local chunks that never cross physical-page boundaries.
3. Approve conservative structure labels with explicit `unknown` rather than
   guessed table reconstruction.
4. Approve deterministic lexical retrieval as the first baseline.
5. Approve the proposed artifact and module boundaries, or identify preferred
   existing locations.
6. Approve the proposed evaluation cases and metrics as exploratory evidence,
   not production thresholds.

No implementation, dependency installation, indexing, or external publication
is included in this planning change.

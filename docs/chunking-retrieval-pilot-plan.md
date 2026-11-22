# Bounded chunking and retrieval pilot

Status: **query-set draft prepared; human review pending**.

Implemented so far: complete twelve-page manifest validation, corrected-view
provenance verification, deterministic page-block segmentation, protected-block
packing, local chunk-artifact writing, deterministic lexical retrieval, and a
small evaluation runner. The pilot remains exploratory and has not approved
production indexing, embeddings, hosted retrieval, or answer generation.

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

## Input contract

The pilot consumes the checked-in metadata-only manifest
`docs/data/pa-pilot-chunking-manifest.json` with a caller-selected local pilot
root. The current characterization output is stored outside Git under
`chunking-pilot-20261122T142619Z/`; the retrieval characterization report is
under `retrieval-evaluation-20261122T143024Z/`. Neither artifact copies policy
text into the repository.

Each entry must identify:

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

## Chunk contract

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

The initial pilot setting will target approximately **400–700 words per chunk**
with **zero overlap**. The target is a starting measurement setting, not a
production recommendation. Zero overlap makes duplicated retrieval results and
citation ambiguity easier to observe; structural grouping is more important than
forcing every chunk to the target size. The evaluation report may recommend a
different setting after inspecting misses and boundary defects.

Chunk text is not normalized. Whitespace, punctuation, line order, and page
content remain as supplied by the selected raw or corrected derived artifact.
The corrected view is an input choice recorded in provenance, not a replacement
of raw evidence.

## Retrieval contract

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

## Framework decision

The first implementation will **not depend on LangChain** or another RAG
framework. The project-local chunker and lexical retriever will define the
behavioral contract first.

This is the safer method for this pilot because the sample is small and the
important questions are evidence questions: whether a chunk boundary is safe,
whether a table/list/heading stayed coherent, and whether a citation resolves to
the exact source page. A framework would be useful only if it preserves those
fields and behaviors without hidden normalization or nondeterministic defaults.

After the baseline passes, a framework adapter may be evaluated separately. It
would have to consume the same validated chunks, preserve the existing
`chunk_id` and provenance fields, and pass the same retrieval test set. That
comparison would measure framework or embedding value rather than silently
changing the pilot's definition of a correct result.

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

### Slice 1 — approved input manifest and artifact verification

Implemented module: `payer_policy/pilot_inputs.py`.

- Validate source identity, PDF/text hashes, page allowlist, artifact choice,
  safe local paths, UTF-8, and correction provenance.
- Load immutable validated page objects without modifying source artifacts.
- Reject incomplete batches rather than returning partial page facts.
- Focused synthetic tests cover valid input, stale hashes, unapproved pages,
  duplicate pages, missing artifacts, corrected provenance, and mutation-safe
  loading.

**Why:** provenance errors must fail before chunking; otherwise later retrieval
results cannot be trusted or reproduced.

### Slice 2A — deterministic page-block segmentation

Implemented module: `payer_policy/chunking.py`.

- Preserve source text exactly through zero-based string offsets.
- Segment page-local blocks using conservative blank-line boundaries.
- Label heading, paragraph, list, table, and unknown structures without
  reconstructing visual layout.
- Return immutable blocks with one-based line provenance and uncertainty notes.

**Why:** a simple, inspectable chunker makes boundary mistakes visible and avoids
embedding layout assumptions into a production abstraction before the sample is
understood.

### Slice 2B — protected-block chunk packing

Implemented module: `payer_policy/chunk_packing.py`.

- Pack whole page blocks toward a 550-word soft target and 700-word maximum.
- Keep headings with following content when the pair fits.
- Preserve lists and table-like blocks as indivisible blocks.
- Mark oversized blocks instead of splitting them.
- Emit immutable chunks with stable IDs, ordinals, exact offsets, line ranges,
  word counts, structure labels, and source/page/hash provenance.
- Reject malformed, overlapping, non-contiguous, or non-reconstructing blocks.

The approved twelve-page characterization run produced one page-local chunk for
each page, with four pages using corrected-derived text. The current extracted
sample contains no blank-line block boundaries, so the packer correctly preserves
those pages as whole blocks rather than inventing finer structure.

**Why:** whole-block packing protects evidence and citation boundaries while
making the current extraction limitation visible instead of hiding it behind
aggressive layout reconstruction.

### Slice 3 — chunk artifact and structural review output

Implemented modules: `payer_policy/chunk_artifacts.py` and
`payer_policy/chunking.py`.

- Serialize exact chunk text with complete source/page/hash provenance.
- Bind the artifact to the input-manifest SHA-256.
- Refuse overwriting an existing artifact.
- Verify exact page reconstruction before artifact creation.
- Keep detailed artifacts outside Git and retain only metadata summaries.
- Validate every chunk record on load, including provenance, offsets, line ranges,
  block labels, word counts, and duplicate identities.
- Save the metadata-only structural review at
  `docs/data/pa-pilot-structural-review.json`.

A real twelve-page characterization produced twelve page-local chunks from
twelve conservative blocks. Five pages use corrected-derived text. The sample
has no blank-line boundaries, so the current result intentionally preserves each
page as one chunk rather than inventing finer structure.

**Why:** a durable, inspectable artifact makes source changes and boundary
mistakes detectable before retrieval is measured.

### Slice 4 — lexical retrieval baseline

Implemented module: `payer_policy/retrieval_pilot.py`.

- Build an in-memory index from validated chunks.
- Rank with deterministic term overlap and document-frequency weighting.
- Return stable, provenance-complete hits.
- Return no hits for absent evidence.
- Reject malformed indexes, duplicate chunk IDs, and invalid query limits.

A local lexical baseline is preferred because it isolates chunking and
provenance behavior from embedding-model behavior.

### Slice 5 — evaluation runner and report

Implemented module: `payer_policy/evaluation.py`.

- Validate answerable and deliberate no-evidence query records.
- Run every query once without hidden rewriting.
- Compute Recall@1, Recall@3, citation accuracy that checks both expected
  chunk identity and expected source/physical page, and no-evidence accuracy.
- Preserve per-query retrieved and expected chunk IDs.

A four-query local characterization run achieved 1.0 for all declared metrics.
This is a deterministic smoke test, not a human-reviewed policy question set
or a production quality threshold.

**Why:** an auditable per-query report is more useful than a single score for a
small exploratory sample.

### Slice 6 — human-reviewed policy query set

Implemented module: `payer_policy/query_set.py`.

- Validate immutable answerable and deliberate no-evidence query records.
- Bind expected citations to the approved chunk IDs, source IDs, and pages.
- Bind the external query file to its expected SHA-256 before validation.
- Track draft, human-approved, rejected, and revision-required statuses.
- Fail closed before final evaluation unless every query is human approved.
- Keep query text in a local derived artifact and retain only a metadata summary
  in Git.

A twelve-query draft was validated locally: ten answerable queries and two
no-evidence queries across the three approved documents. Human review and final
metrics remain pending.

**Why:** the four earlier characterization queries demonstrate pipeline wiring,
not retrieval quality. Human review is required to establish whether each query
is answerable and whether its expected citation is correct.

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
- all chunks have source, retrieval, hash, parser, extraction-mode,
  physical-page, and ordinal metadata;
- the metadata-only structural review records headings, lists, table-like blocks,
  unknown blocks, and page-boundary results;
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

## Approved scope decisions

1. Approve the twelve-page reviewed sample as the complete pilot input.
2. Approve page-local chunks that never cross physical-page boundaries.
3. Approve conservative structure labels with explicit `unknown` rather than
   guessed table reconstruction.
4. Approve deterministic lexical retrieval as the first baseline.
5. Approve the proposed artifact and module boundaries, or identify preferred
   existing locations.
6. Approve the proposed evaluation cases and metrics as exploratory evidence,
   not production thresholds.

No answer-generation component, embedding dependency, hosted index, or external
publication is included in the implemented slices.

# Offline original-byte storage

## Purpose and status

[`payer_policy/document_storage.py`](../payer_policy/document_storage.py) saves
one **PDF candidate** and a retrieval receipt in a caller-chosen local Windows
folder. A receipt is a small record of where the candidate was requested, when
it was retrieved, and what exact bytes were received. This is not a document
library or an automatic downloader. The functions do no DNS lookup or HTTP.

**A candidate is not a valid PDF, safe file, authentic source, complete current
policy, or coverage decision.** Five marker bytes, `%PDF-`, can pass the shallow
candidate check. Structural parsing, source approval, permissions to collect or
redistribute, and benefit applicability remain separate decisions. The PA source
[review](source-reviews/pa-certificate-2025.md) does not authorize live collection.

## Public functions and file layout

```text
save_pdf_candidate(root: Path, result: FetchResult, *, retrieval_id: str,
                   source_id: str, requested_url: str,
                   retrieved_at: datetime, max_bytes: int = 10_000_000)
                   -> StoredCandidate
load_saved_candidate(root: Path, retrieval_id: str, *,
                     max_bytes: int = 10_000_000) -> StoredCandidate

<root>/records/<retrieval_id>/original.bin
<root>/records/<retrieval_id>/receipt.json
<root>/.staging/<private attempt>/
```

The **original** is precisely the supplied, unmodified `bytes`; its neutral
`.bin` extension deliberately does not promise a structurally valid PDF. Each
retrieval gets its own directory, even when two retrievals have the same bytes.
There is no database, cross-retrieval deduplication, or automatic cleanup.
`root` must be a caller-selected, existing absolute path on Windows, kept
**outside the repository** and under the user's control. UNC-style paths are
rejected, but a mapped network drive can still look local; choose a trusted
local drive, not a network share. The module creates only its `records` and
`.staging` children and record entries. No website name,
response filename, or URL path is used as a filesystem path. A `retrieval_id`
must be **exactly 32 lowercase hexadecimal characters**; reuse the same ID for
a retry of the same retrieval. `source_id` uses lowercase letters/digits with
single internal hyphens or underscores; it is recorded as metadata, not
verified against the source registry. The requested and final URLs must be
well-formed HTTPS metadata with no embedded credentials or fragments; this
syntax check is **not** a source authorization or network-security check.

`save_pdf_candidate` calls
[`validate_pdf_candidate()`](../payer_policy/document_validation.py) before
writing and uses [`fingerprint_document()`](../payer_policy/provenance.py) to
calculate a SHA-256 fingerprint (a repeatable byte identity). It requires a
non-naive retrieval time and records it in UTC. The version-1 JSON receipt
contains `retrieval_id`, `source_id`, `requested_url`, `final_url`,
`retrieved_at`, `http_status`, the exact selected response-header pairs,
`byte_count`, `sha256`, `validation: "pdf_candidate"`, and
`validation_version: 1`. Selected header names are Content-Type,
Content-Encoding, Content-Length, Transfer-Encoding, ETag, Last-Modified, and
Date. Original pair order, duplicates, spelling, and values are retained;
other headers, including Set-Cookie, are omitted. URLs and even selected
headers may contain sensitive data if the **caller supplies them**; never
supply signed or secret-bearing links, and protect the storage folder.

`load_saved_candidate` checks the path, bounds its reads, rejects duplicate JSON
keys and invalid schema/field types, rechecks the candidate rules, and compares
its calculated byte count and fingerprint against the receipt. It returns the
original bytes, receipt copy, and both paths. The default original limit is
10,000,000 bytes, and receipts are limited to 65,536 bytes. Raising the limit
for one save/load call is an explicit caller decision; a smaller load limit can
reject a previously stored original. No trust or authenticity signature is
provided: someone able to alter **both** files can create a self-consistent
forgery. A returned path is not an invitation to edit the file; changed files
are detected on later loads only if their receipt is not changed consistently.

## Failure and interruption behavior

- Wrong caller types raise `TypeError`; malformed IDs, metadata, root or limits
  raise `ValueError`; rejected response content raises
  `DocumentValidationError` (a `ValueError`). These checks run before publishing
  a record. Disk and permission errors remain `OSError` where applicable.
- Same ID with the same original and receipt returns the verified first record
  without rewriting it. Different bytes **or metadata** under that ID raise
  `StorageConflictError`; existing files are not replaced. A damaged or missing
  existing entry raises `StorageIntegrityError` rather than being silently
  repaired or overwritten.
- The writer first makes unique files in `.staging`, flushes them with
  [`os.fsync`](https://docs.python.org/3.11/library/os.html#os.fsync), and uses
  [`os.rename`](https://docs.python.org/3.11/library/os.html#os.rename) on the
  same local volume to publish a complete directory. On Windows, a destination
  that already exists makes that rename fail instead of replacing it. A crash
  **before** publication leaves only an orphan staging directory, invisible to
  the verified loader; a crash **after** publication leaves a complete record.
  A retry with the original ID is safe. No code automatically deletes old
  staging attempts; review them before manual cleanup. File flushing is not a
  power-loss guarantee, and this is not a backup system.
- The loader rejects reparse-point paths (including links and junctions) when
  inspected. These checks cannot defeat a hostile local process racing to
  replace files between the path check and the open. Use a trusted storage
  directory with restrictive filesystem permissions; do not treat the receipt
  as tamper-proof evidence or share this directory with untrusted writers.

## Runnable offline example

From Python launched at the repository root; all bytes and URLs are synthetic:

```python
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from payer_policy.document_storage import save_pdf_candidate, load_saved_candidate
from payer_policy.https_transport import FetchResult

result = FetchResult(
    url="https://example.org/final", status=200,
    headers=(("Content-Type", "application/pdf"),), body=b"%PDF-synthetic",
)
with TemporaryDirectory() as directory:
    root = Path(directory)
    saved = save_pdf_candidate(
        root, result, retrieval_id="1234567890abcdef1234567890abcdef",
        source_id="example-source", requested_url="https://example.org/start",
        retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    verified = load_saved_candidate(root, "1234567890abcdef1234567890abcdef")
    assert verified == saved
    assert verified.original_path.read_bytes() == result.body
    assert verified.receipt["validation"] == "pdf_candidate"
```

## Verification and remaining boundaries

On Python 3.11.16, 80 offline unit tests ran with one optional Windows
link-creation case skipped on the checked machine; the separate local TLS
integration test passed. Storage tests use synthetic bytes and temporary
folders, including competing writers, killed child processes on either side
of publication, disk-error injection, damaged receipts, and real controlled
HTTP-parser output. No public policy file was fetched, stored, or redistributed
by this increment. No structural PDF parser, source registry integration,
installer, library UI, automatic cleanup, or new runtime dependency was added.

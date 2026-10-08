# Contained inspection of one saved PDF

## Status: implemented and verified on the documented host

The approved implementation and its synthetic example pass local verification.
Independent review passed after the error-classification correction described
below. This accepts the bounded increment, not a general security sandbox.
The earlier [Windows experiment](../spikes/001-windows-pdf-worker/README.md)
is historical evidence, not acceptance of this application entry point.

The worker is a separate helper process with memory and running-time limits.
It checks the saved copy against its receipt, opens those verified bytes, and
returns only encryption, page count, and byte identity. The parent checks the
answer and confirms cleanup before returning it. This is resource containment,
not a security sandbox or a download pipeline.

## Public contract

```text
inspect_saved_pdf_in_worker(root: Path, retrieval_id: str, *,
                            max_bytes: int = 10_000_000,
                            limits: InspectionLimits | None = None)
    -> PdfInspection

InspectionLimits(timeout_seconds=30, memory_bytes=268_435_456)
```

The entry point belongs to `payer_policy.inspection_worker`. Its result is the
existing `PdfInspection` from `payer_policy.document_inspection`:

- `retrieval_id`: the unchanged lowercase 32-character hexadecimal identifier.
- `sha256`: the fingerprint of bytes verified against the saved receipt.
- `is_encrypted`: the reader's encryption flag.
- `page_count`: a nonnegative reader-reported count, or `None` when encrypted.

The original [in-process inspector](document-inspection.md) stays available
with its original exception and return contracts. The parent of the new worker
may import the parser package but does not parse the PDF or reread/hash its
stored contents. Saved-byte verification and parsing happen in the child.
The worker uses the same strict parser behavior, including the parser's
implicit empty-password attempt; no new password or decryption feature is added.

`root` must be a trusted, existing absolute local Windows directory. Unsafe
reparse-point or UNC storage paths are rejected, not repaired by resolving them.
The existing storage contract cannot defend against hostile concurrent changes
by another process with the same filesystem permissions.

## Resource policy

| Setting | Default | Accepted changes |
| --- | --- | --- |
| Saved-original read | 10,000,000 bytes | Positive whole bytes up to this ceiling |
| Worker wait | 30 seconds | Finite number greater than zero, up to 60 seconds |
| Process committed memory | 256 MiB | Whole bytes from 16 MiB through 256 MiB |
| Aggregate job committed memory | Same as process cap | Changed by the same memory setting |
| Ordinary active processes | One | Fixed |
| Cleanup observation | Five seconds | Fixed, shared across observations |
| Request and response reads | 65,536 bytes each | Fixed |

Boolean values do not count as integer settings. These are initial development
budgets, not a promise that every legitimate PDF fits. Committed memory is memory
Windows promises to back with RAM or paging storage, not just resident RAM.
The wait budget is not a CPU-rate limit or a deadline for the complete function:
native startup, native calls, filesystem work, and cleanup have separate costs.
The message-read limit is not a disk quota or a restriction on other file writes.

## Failure contract

Invalid caller types or values raise ordinary `TypeError` or `ValueError` before
temporary files or native launch. Worker/supervisor failures use
`WorkerInspectionError`, with a stable `code` rather than a remote traceback.

| Code | Meaning |
| --- | --- |
| `unsupported_runtime` | Platform or interpreter/environment layout is unsupported |
| `setup_error` | Native job setup, launch, or supervision failed |
| `input_error` | Invalid storage input reported by the child, or parent root-check I/O failure |
| `storage_error` | Saved data is absent, unsafe, damaged, or inconsistent |
| `parser_error` | The existing inspector reported a supported PDF parsing failure |
| `memory_error` | The child explicitly reported Python `MemoryError` |
| `timeout` | The worker wait expired |
| `crash` | The worker exited unexpectedly with a nonzero code |
| `invalid_result` | The result is absent, malformed, oversized, or mismatched |
| `ipc_error` | Supervisor communication/observation failed, including temporary-file I/O, native waits, or exit-code retrieval |
| `cleanup_error` | Process/handle or temporary-file cleanup could not be confirmed |

A crash is not evidence of memory exhaustion. Remote errors do not recreate the
original exception object or its chained cause. Unexpected programming failures
must not be relabeled as malformed PDFs. Interrupts trigger cleanup and then
propagate; cleanup evidence must not turn an interrupted call into success.
There is no automatic retry with larger limits or without containment.

## Process and message boundaries

The supervisor attaches a configured Windows Job Object during process creation.
It checks actual kernel limits and worker membership. The job handle is not
inherited, and breakaway is not enabled. Normal cleanup checks job activity and
held process handles, rather than trusting PID numbers that can be reused.
Closing the last job handle also terminates members after supervisor loss.

One call has one temporary directory and a fresh request identifier. Both
request and result use exact versioned schemas and bounded JSON reads. Duplicate
keys, nonstandard numbers, unrelated requests, extra fields, empty success
facts, and contradictory encryption/count fields are rejected. Complete results
are published through a closed temporary file and rename. That publication step
is not a hostile-user defense or a durability guarantee.

The production child has only an inspection operation. Intentional hangs,
crashes, allocations, and supervisor-abandonment probes belong in test fixtures,
not in its public request schema. Successful facts are returned only after
native cleanup and temporary-file cleanup finish successfully.

## Supported development runtime

The initial target is Windows x64 CPython with the source checkout and an
ordinary approved package environment. The established baseline is Python
3.11.16 with `pypdf==6.19.0`; a newer runtime is not automatically verified.
The supervisor selects the same base interpreter explicitly, not through PATH.
Trusted interpreter aliases may be canonicalized; caller storage paths may not.

The child starts with `-I -S -B`. Its bootstrap adds the trusted application and
approved package directory explicitly. Environment `PYTHONPATH`, user-site
packages, and automatic site initialization are not part of this bootstrap.
This reduces accidental configuration interference, not user-level permissions.
Frozen executables, installers, unusual Python layouts, other architectures,
and a broad Windows compatibility matrix are outside this increment.

## Synthetic usage example — independently executed

The following example creates its own small local PDF and receipt; it downloads
nothing. Run from the repository root in the approved Python environment.
It is a new worker example, separate from the historical in-process example.

```python
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfWriter
from payer_policy.document_storage import save_pdf_candidate
from payer_policy.https_transport import FetchResult
from payer_policy.inspection_worker import inspect_saved_pdf_in_worker

retrieval_id = "1234567890abcdef1234567890abcdef"
writer = PdfWriter()
writer.add_blank_page(width=72, height=72)
output = BytesIO()
writer.write(output)
with TemporaryDirectory() as directory:
    root = Path(directory)
    saved = save_pdf_candidate(
        root,
        FetchResult("https://example.org/final", 200,
                    (("Content-Type", "application/pdf"),), output.getvalue()),
        retrieval_id=retrieval_id,
        source_id="synthetic-source",
        requested_url="https://example.org/requested",
        retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    before = (saved.original_path.read_bytes(), saved.receipt_path.read_bytes())
    result = inspect_saved_pdf_in_worker(root, retrieval_id)
    assert result.page_count == 1 and not result.is_encrypted
    assert before == (
        saved.original_path.read_bytes(), saved.receipt_path.read_bytes())
    print("page_count:", result.page_count)
    print("original_and_receipt_unchanged:", True)
```

## Verification and exclusions

Local verification used CPython 3.11.16 x64, pypdf 6.19.0, and Windows API
build 26200. The complete suite ran 135 methods: 134 passed and one existing
optional Windows symlink-privilege case skipped. The separate loopback TLS
test and all 19 historical spike methods passed. The new worker contributes
39 methods. Compilation, annotations, function docstrings, and 79-column
checks passed across its 16 source/test/fixture files.

The exact new example above was executed independently and returned:

```text
page_count: 1
original_and_receipt_unchanged: True
```

Real production-helper tests exercised configured limits, allocation refusal
with a positive control, extra-child refusal, timeout/crash recovery, and
abrupt-supervisor death with observer-held process handles. Other tests covered
concurrent inspections, copied Unicode/space runtime and checkout paths,
poisoned environment settings, actual storage junctions, unchanged snapshots,
and malformed result files. Native API failures and parser `MemoryError`
reports were explicitly simulated; no real parser exhaustion was induced.
Non-Windows import behavior was simulated, not run on another OS.
Initial independent review found no native containment/security blocker, but
withheld approval for a child error-classification defect: an unexpected parser
`ValueError` could be mislabeled as `input_error`. The correction restricts
plain input-error translation to a separate root-validation preflight. Later
unknown inspection errors escape, including a root race after that preflight;
stored bytes are still loaded only by the original inspector. Failed-before /
passed-after regressions and the full suite pass. Independent re-review passed
with no remaining logic/security blocker in the approved scope; seven focused
methods also passed during that review. The reviewer did not repeat the full
suite or example; their independent execution is recorded above.

No text extraction, OCR, downloads, source collection, indexing, worker pool,
background service, installer, or UI is added. No restricted token, AppContainer,
filesystem/network isolation, or authenticity guarantee is established. A worker
retains the user's permissions. Its reported facts and matching bytes do not
prove source authority, collection/reuse rights, full PDF validity, absence of
malicious content, document completeness, or individual policy applicability.
Unattended arbitrary public-PDF processing remains outside the approved scope.

## Primary API references

- [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects): group resource controls and lifecycle termination, not a security sandbox.
- [Process attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute): assign jobs at creation and retain attribute values until deletion.
- [Extended job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information): process and aggregate commitment caps.
- [Python startup options](https://docs.python.org/3.11/using/cmdline.html): isolated mode and suppression of site initialization.
- [Python JSON](https://docs.python.org/3.11/library/json.html): decoding hooks and input-size cautions.

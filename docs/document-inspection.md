# Offline PDF structural inspection

## What works

[`inspect_saved_pdf()`](../payer_policy/document_inspection.py) reads a **verified
saved candidate**, not a PDF path supplied by a website. It calls
[`load_saved_candidate()`](../payer_policy/document_storage.py), which checks the
saved bytes against their receipt and applies the original-byte read limit.
Then [pypdf's `PdfReader`](https://pypdf.readthedocs.io/en/latest/modules/PdfReader.html)
opens those returned bytes as a seekable in-memory stream. With strict parsing
requested, the reader reports whether the PDF is encrypted and, if it is not,
a page count. Think of this as counting pages in a book after checking that the
stored copy matches its receipt—not reading or approving the book.

```text
inspect_saved_pdf(root: Path, retrieval_id: str, *,
                  max_bytes: int = 10_000_000) -> PdfInspection

PdfInspection(retrieval_id: str, sha256: str,
              page_count: int | None, is_encrypted: bool)
```

The fingerprint is the verified receipt's SHA-256 byte identity. An encrypted
PDF that initializes successfully reports `is_encrypted=True` and
`page_count=None`. The application supplies no password, never explicitly
decrypts, and never counts encrypted pages. During initialization,
[pypdf 6.19.0's encryption handler](https://pypdf.readthedocs.io/en/6.19.0/_modules/pypdf/_reader.html)
implicitly tries an **empty password**. An accessible PDF with zero pages
reports `page_count=0`.
`pypdf` can reject PDFs that another viewer repairs; a count here is only a
reader-reported structural fact, **not** proof every page renders, that the
file is harmless, or that it belongs to a particular policy. No page text,
images, attachments, or metadata are extracted. A scanned page cannot be
classified by this increment; scanned text requires separately planned optical
character recognition (OCR).

## Separate contained entry point

The [worker API](inspection-worker.md) calls this same inspector in a bounded
Windows process and has a different, explicit remote-error contract. It is
verified on the documented Windows host and independently reviewed.
Calling `inspect_saved_pdf`
directly still runs in-process with the limitations below; no automatic
redirect or fallback changes this API.

## Failures and limits

- Invalid IDs and limits keep the storage loader's `TypeError` / `ValueError`.
  Missing, changed, oversized, or unsafe saved records raise
  `StorageIntegrityError`; they are **not** silently reclassified as malformed
  PDFs. The root must be a trusted, existing local Windows directory.
- Supported parser failures raise `PdfInspectionError` with the generic message
  `cannot inspect PDF structure` and the underlying exception as `__cause__`.
  This covers the
  [pypdf error family and separate dependency error](https://pypdf.readthedocs.io/en/6.19.0/modules/errors.html)
  (`PyPdfError`, `DependencyError`), plus tested malformed-data failures
  (`AttributeError`, `KeyError`, `TypeError`) and unsupported encryption
  (`NotImplementedError`). A missing encryption backend is covered by a
  simulation in tests, not by removing installed dependencies. The catch
  applies only to reader construction, encryption status, and page counting;
  loader failures stay outside it. `MemoryError`, `KeyboardInterrupt`, and
  `SystemExit` propagate unchanged. Other exception classes are not covered. A
  `%PDF-` marker alone passes the earlier candidate check but fails this
  structural attempt. Parser acceptance is not full PDF conformance testing.
- The default saved-original limit is **10,000,000 bytes**, inherited from the
  loader. A smaller explicit limit can reject an existing record. This limit
  does **not** cap the parser's CPU or memory use; even a small untrusted file
  could be expensive to process. There is no process sandbox or execution
  deadline. Do not wire arbitrary public files to unattended ingestion yet.
- Inspection does not edit `original.bin`, `receipt.json`, or any policy text.
  A receipt and matching bytes are not an authenticity signature if an actor
  can change both. Source authority, collection/reuse rights, policy dates,
  and individual coverage remain separate decisions. No live certificate
  collection is authorized by this module.

## Verification of the PR #35 correction

On Python 3.11.16 with pypdf 6.19.0, all 16 inspection test methods passed.
The full offline suite ran 96 methods: 95 passed and one optional Windows
link-creation case skipped; the separate local TLS integration test passed.
Four new real synthetic-PDF cases cover a missing catalog page entry, missing
encryption revision, a wrong encryption-length type, and an unsupported
version. Simulations cover the pypdf error family at each reader step and a
missing encryption backend. Additional checks keep loader errors, memory
exhaustion, and process interrupts separate. Parser-error tests verify the
original and receipt stay unchanged and the underlying cause is retained.

## Setup and offline example

Use **Python 3.11 or newer** on Windows, in an isolated environment if desired:

```console
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The requirements file pins `pypdf==6.19.0`; the established test baseline is
Python 3.11.16. The final Windows installer is not built yet. Run this example
from the repository root; it generates a small PDF in memory, not a download:

```python
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfWriter
from payer_policy.document_inspection import inspect_saved_pdf
from payer_policy.document_storage import save_pdf_candidate
from payer_policy.https_transport import FetchResult

writer = PdfWriter()
writer.add_blank_page(width=72, height=72)
output = BytesIO()
writer.write(output)
body = output.getvalue()
with TemporaryDirectory() as directory:
    root = Path(directory)
    save_pdf_candidate(
        root,
        FetchResult("https://example.org/final", 200,
                    (("Content-Type", "application/pdf"),), body),
        retrieval_id="1234567890abcdef1234567890abcdef",
        source_id="synthetic-source",
        requested_url="https://example.org/requested",
        retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    result = inspect_saved_pdf(root, "1234567890abcdef1234567890abcdef")
    assert result.page_count == 1 and not result.is_encrypted
    print(result.page_count)
```

This synthetic example illustrates saved-byte verification and page counting;
it was not separately executed. The automated tests cover the same storage and
inspection operations. It does not exercise a live source, text extraction,
optical character recognition, indexing, or a policy-applicability decision.

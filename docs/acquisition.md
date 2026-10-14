# Single-document acquisition

Status: implemented and verified on the documented Windows host; independent
code review passed with no blocking findings.

## Purpose and boundary

[acquire_pdf_candidate](../payer_policy/acquisition.py) connects three existing
helpers for **one explicitly approved source**: fetch the response, check that
it looks like a PDF, and save its exact bytes with a retrieval receipt. Think
of the receipt as a label attached to an unchanged original, not a certificate
that the document is genuine, safe, or applicable to a benefit.

This is a callable Windows-first development API, not a crawler, scheduler,
installer, document browser, or permission to collect public policies. It does
not parse a PDF or call the contained inspection worker. The checked-in
registry's overview entry does not grant download approval.

## Contract

`acquire_pdf_candidate(registry, source_id, root, *, retrieval_id, approval, limits)`
returns a frozen `AcquisitionResult` with `source_id`, `retrieval_id`, `final_url`,
`sha256`, `original_path`, and `receipt_path`. It does not retain a body field.

- `registry`: a source-ID mapping, such as the result of
  [load_source_registry](source-definition.md). Only the selected definition is
  checked here; unrelated entries are not revalidated or fetched.
- `source_id`: must match both the registry key and selected definition.
- `root`: an existing absolute `Path` on trusted local Windows storage. Existing
  ancestors and storage components must not be reparse points (links or
  junctions). UNC paths are refused; mapped drives can still look local, so
  choosing physical local storage remains the caller's responsibility.
- `retrieval_id`: exactly 32 lowercase hexadecimal characters, unused under
  `root/records`. Any existing entry is refused before fetching, even if it
  contains identical bytes. This does not change the storage helper's own
  identical-retry behavior.
- `approval`: an `AcquisitionApproval` containing the exact `source_id` and
  `requested_url`, reviewed `allowed_hosts`, and an existing local regular
  `review_note` file supplied as an absolute `Path`. URL spelling, case, and
  query order are preserved, not normalized to make an approval match.
- `limits`: an explicit `AcquisitionLimits` value. Its defaults and ceilings
  are below; booleans and silent type conversions are rejected.

| Limit | Default / maximum | Allowed lower values |
|---|---|---|
| `max_bytes` | 10,000,000 bytes | Positive integers |
| `timeout` | 10 seconds per socket operation | Finite positive integers/floats |
| `max_redirects` | 3 | Integers from 0 through 3 |

The timeout is **not** a whole-operation or DNS-resolution deadline. Existing
HTTP metadata and storage receipt limits also apply; JSON escaping can make a
receipt exceed its 64 KiB limit even when HTTP headers fit their own limit.

Approval is a **trusted caller decision**, not an authentication mechanism.
The local note's existence and path are checked, but its content is not opened
or interpreted. It must actually document the intended access decision; an
arbitrary file is not legal permission. Host scope is frozen as a tuple and
must explicitly include each allowed redirect host. Applicability metadata
never substitutes for approval. The unchanged receipt does not persist the
approval object or a copy of its note; retain review evidence separately.

## Order and failures

1. Check limits, identifiers, the selected source, exact approval binding,
   destination/host syntax, local review-note path, and storage paths before
   any fetch or storage write. Copy the selected URL and limits for this call.
2. Call [fetch_https](https-transport.md), which checks resolved addresses,
   connects to a checked numeric address, verifies hostname TLS, and checks
   redirects. Record an aware UTC timestamp when fetching finishes.
3. Call [validate_pdf_candidate](document-validation.md), enforce the body
   budget and final-URL rules, and check that the receipt fits its size limit.
4. Call [save_pdf_candidate](document-storage.md). It preserves exact bytes,
   publishes without intentionally replacing a record, and reads the saved
   record back for verification before returning metadata.

The timestamp is a retrieval-completion time, not a policy effective date.
Requested and final URLs stay separate. A final URL must satisfy both the
reviewed host rules and storage's ASCII metadata-URL rules. Existing helpers
are reused, including private validation/receipt helpers; changing those
helpers requires rerunning acquisition tests too. Receipt preparation is
repeated by the writer to preserve its unchanged standalone contract.

| Failure | Result |
|---|---|
| Invalid caller types, budgets, selected source, destination, or local path | `TypeError` / `ValueError` (including `NetworkSafetyError`) before fetching |
| Missing approval or mismatched source/URL | `AcquisitionError`, stage `approval` |
| OS failure checking the review-note path | `AcquisitionError`, stage `approval` |
| Existing retrieval ID or preflight storage OS failure | `AcquisitionError`, stage `storage` |
| Known transport or network-policy failure during fetch | `AcquisitionError`, stage `fetch` |
| Candidate, final-URL, or body-limit rejection | `AcquisitionError`, stage `validation` |
| Receipt encoding rejection or known write/conflict/integrity failure | `AcquisitionError`, stage `storage` |

`AcquisitionError` retains `stage`, `retrieval_id`, `cause`, and exception
chaining (`__cause__`). Ordinary `TypeError`/`ValueError` are translated only
inside narrow validation/receipt-encoding blocks; such errors from the fetcher
or writer propagate rather than being mislabeled. Unexpected exceptions and
interrupts are not blanket-caught. A raced path change may therefore escape as
a plain `ValueError` from the writer. A missing note is invalid configuration,
not an OS-access-failure report.

There are no retries or rollback deletions. Preflight checks do not prevent a
hostile local process changing paths later. The writer rechecks its own paths
and conflicts. An error after publication can leave a saved record: inspect
that record rather than assuming nothing was written or retrying the same ID.
These are existing trusted-local-storage limits, not a filesystem sandbox.

## Offline example

Run this Python block from the repository root on Windows with the documented
Python 3.11+ development environment. `TMPDIR` must identify an existing trusted
local scratch directory. Only temporary synthetic bytes are written, then
removed. DNS and socket creation are blocked before project imports; only the
fetch boundary is replaced. Validation, publication, and verified loading are
real. The marker-only fixture is deliberately **not a valid PDF** and must not
be sent to a PDF parser. This example does not authorize a real download.

```python
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

with (patch("socket.getaddrinfo", side_effect=AssertionError("No DNS")),
      patch("socket.socket", side_effect=AssertionError("No network"))):
    from payer_policy.acquisition import (
        AcquisitionApproval, AcquisitionLimits, acquire_pdf_candidate,
    )
    from payer_policy.document_storage import load_saved_candidate
    from payer_policy.https_transport import FetchResult

    with TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
        root = Path(directory)
        note = root / "synthetic-review.txt"
        note.write_text("Offline fixture only; no live approval.", "utf-8")
        source_id = "synthetic-source"
        url = "https://example.org/synthetic.pdf"
        registry = {source_id: {
            "source_id": source_id, "name": "Synthetic example",
            "url": url, "publisher": "Fixture publisher",
            "category": "reference", "plan": "unknown",
            "program": "unknown", "applicability_status": "unknown",
            "evidence_url": "", "access_restrictions": "offline only",
        }}
        body = b"%PDF-synthetic-not-a-real-document"
        response = FetchResult(
            url, 200, (("Content-Type", "application/pdf"),), body)
        approval = AcquisitionApproval(source_id, url, ("example.org",), note)
        with patch("payer_policy.acquisition.fetch_https",
                   return_value=response) as fetch:
            result = acquire_pdf_candidate(
                registry, source_id, root,
                retrieval_id="0123456789abcdef0123456789abcdef",
                approval=approval, limits=AcquisitionLimits())
        fetch.assert_called_once()
        saved = load_saved_candidate(root, result.retrieval_id)
        assert saved.body == body
        assert saved.receipt["sha256"] == result.sha256
        assert saved.receipt["requested_url"] == url
        assert saved.receipt["final_url"] == result.final_url
        assert not hasattr(result, "body")
        print("Offline acquisition verified:", result.retrieval_id)
```

## Verification

Closeout verification on October 13, 2026, using Windows x64, Python 3.11.16
and the unchanged `pypdf==6.19.0` pin:

- Full suite: 153 methods, 152 passed and one existing optional Windows
  link-creation skip. Separate real loopback TLS test: passed.
- Focused acquisition suite: 18 passed, also independently rerun by the reviewer.
- The literal example above executed successfully with DNS/sockets blocked,
  printing `Offline acquisition verified: 0123456789abcdef0123456789abcdef`.
- Syntax, function docstrings/annotations, and the 79-character line limit
  passed for both acquisition Python files. Added-line security-pattern checks
  and `git diff --check` found no issues. These checks are not a security proof.
- All 54 local Markdown links in the four closeout documents resolved. Mermaid
  node/edge/class references passed structural checks; visual rendering was
  not verified.
- Independent code review found no blocking security or logic issue. An optional
  combined two-hop redirect acquisition test remains a possible improvement:
  redirect behavior has transport tests, while acquisition receipt preservation
  of a redirected final URL currently uses a mocked fetcher.

The earlier interrupted implementation log records incremental failing/passing
focused runs and a passing pre-interruption regression run; it did not complete
closeout. This closeout changes no production behavior and does not claim a
new RED/GREEN implementation cycle. The focused suite is
[tests/test_acquisition.py](../tests/test_acquisition.py). It covers invalid
approval/configuration before fetch, frozen inputs, byte/receipt preservation,
completion time, failure stages/causes, late publication failures and conflicts.
Two closeout characterization tests exercise the real HTTP parser through
validation/storage with controlled DNS/TCP/TLS peers, including truncated HTTP
and HTML rejection. They test existing behavior, not new test-first production
changes. The separate loopback TLS test checks real local TLS; neither form of
test verifies a public policy endpoint or permits live collection.

See the [delivery plan](implementation-plan.md) and
[architecture](architecture.md) for the surrounding boundaries.

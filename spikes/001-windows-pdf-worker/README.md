# 001: Windows PDF-worker resource and lifecycle experiment

## Question and verdict: PARTIAL

Can a small Windows supervisor limit a PDF worker's memory and running time,
then confirm that its ordinary child processes have stopped?

**Yes on the tested host, with conditions below.** The real-process probes
passed. This is disposable experiment code, not an installed application,
a production inspection API, or approval to process arbitrary public PDFs.
A Job Object is a Windows container for managing processes together. Here it
controls resources and cleanup; it does not stop file access or network access.

## Approach

- `win_job.py` uses standard-library `ctypes` to call Windows APIs directly.
  No additional native-wrapper dependency was installed.
- A configured, unnamed Job Object is attached through
  `PROC_THREAD_ATTRIBUTE_JOB_LIST` **during process creation**. There is no
  unrestricted launch followed by assignment, and no fallback launch.
- Per-process and whole-job limits cap **committed memory**: memory Windows
  promises to back with RAM or paging storage, not simply currently used RAM.
- A supervisor wait enforces the worker deadline; job termination stops members.
  Cleanup shares one five-second observation budget and checks held process
  handles as well as the job's active count. An unconfirmed cleanup is an error.
- Closing the last job handle also stops members. Handles are not inherited,
  and breakaway flags are not enabled. A disposable supervisor exits abruptly
  only after the test observer holds handles to the live members.
- Request/result files live in temporary folders. The parent reads at most
  `result_bytes + 1` bytes and rejects oversized or inconsistent JSON. Version,
  retrieval ID, exact outer keys, workload-specific fact shapes and types are
  checked; allocation/creation error codes must agree with their boolean flags;
  lifecycle IDs must agree with the launched worker and captured members;
  duplicate keys and nonstandard numeric constants are rejected.
- The inspection probe calls the **unchanged**
  [existing inspector](../../payer_policy/document_inspection.py), which uses
  [verified storage](../../payer_policy/document_storage.py). Only encryption,
  reader-reported page count, byte fingerprint, and error categories are returned.

Default experimental budgets are 256 MiB committed memory per process and
256 MiB for the job, two ordinary active processes, a 30-second worker wait,
five-second cleanup confirmation, and a 65,536-byte result. MiB means 1,048,576
bytes. These are test settings, not tuned production settings. Input remains
subject to the existing 10,000,000-byte saved-original cap.

## Observed results

Verified on September 30, 2026, using 64-bit Python 3.11.16, pypdf 6.19.0, and
Windows API/kernel version 10.0.26200. This is one host, not an OS support matrix.

| Given / when | Observed result |
| --- | --- |
| Configured job / launch fixed hello | Worker is in the intended job; limits read back match; exit 0; no active members after cleanup. |
| Invalid budgets / attempt setup | Rejected before job creation. |
| Simulated native setup failure / launch | Error remains an error; job handle closes; no unrestricted fallback. |
| Hanging worker / 0.5-second wait expires | Classified as timeout; exit 124 after termination; zero active members; subsequent hello works. |
| Worker plus ordinary child / deadline | Held handles confirm both worker and reported child exit; all observed members stop. |
| Disposable supervisor / abrupt exit 23 | Observer opens live member handles first; Windows closes the supervisor's last job handle; all observed members exit. |
| Worker plus one ordinary child / request another | First child starts; extra ordinary child creation is refused. |
| Fixed 4 MiB then 64 MiB commitment / varied caps | Small allocation succeeds; large allocation is refused at the lower process cap and lower job cap; positive control succeeds. |
| Abrupt worker exit 37 / supervise | Classified as crash, not success, timeout, or inferred memory exhaustion. |
| Missing, malformed, oversized, duplicate-key, wrong-version/ID/type JSON | Classified as invalid result; cleanup succeeds. |
| Wrong fact shapes/types or a 32-byte result budget | Rejected rather than interpreted as valid PDF facts. |
| Real synthetic two-page, zero-page, encrypted, marker-only snapshots | Correct facts or parser-error category; original bytes and receipts unchanged. |
| Deliberately changed saved original / inspect | Storage-error category, not parser success; neither damaged original nor receipt changed further. |
| Simulated first handle-close failure / release handles | Remaining closes still attempted; original close error reported. |

The allocation cases use `(process MiB, job MiB, large allocation accepted)`:
`(64, 256, false)`, `(128, 256, true)`, `(128, 64, false)`. Allocation refusal
is not automatic process death. These are fixed small synthetic probes, not
proof of every parser's memory failure behavior.

Nineteen experiment methods passed. The unchanged production suite ran 96
methods: 95 passed and one optional Windows link-creation test skipped.
The separate local-loopback TLS test passed. Compilation and whitespace checks
passed. Initial independent review found no native/API or handle-ownership
blockers, but withheld approval for two response-contract defects: successful
facts must match the requested workload, and observations must be consistent
with error codes and actual native process identities/membership. A separate
fix pass corrected both defects using failed-before/passed-after JSON fault
regressions; native lifecycle tests retain real launch and cleanup. Independent
19-method verification, production tests, and TLS pass after correction.
Independent re-review passed with no remaining logic/security blockers in the
approved disposable scope. Four focused JSON-contract tests independently
passed during re-review; the full suite was not repeated by that reviewer.
The PARTIAL verdict and production/security limitations remain unchanged.

## Surprises and constraints

- Windows virtual environments can use redirectors. Launching one can
  introduce another Python process. The experiment instead launches the same
  base runtime using `sys.base_prefix`, and supplies the already approved
  virtual environment's package directory for the inspection probe. This
  arrangement must be reconsidered for a bundled installer.
- Windows console helpers appeared in job PID enumeration. The cleanup probe
  therefore holds a bounded list of up to 16 native member handles, rather than
  assuming the number of reported PIDs equals the ordinary-process cap.
  The ordinary-child refusal test independently checks that configured cap.
  A larger enumeration raises an error; it is not silently truncated.
- Tested x64 native structure sizes: basic limits 64, extended limits 144,
  accounting 48, startup 104, extended startup 112, process information 24,
  and the bounded PID-list record 136 bytes. Matching sizes are evidence,
  not a substitute for checking field order and signatures.
- `JOB_LIST` requires supported Windows APIs; initialization failure is fatal.
  Other Windows builds, runtime layouts, 32-bit Python, and restrictive outer
  jobs have not been validated. Existing outer jobs may impose stricter limits.
- The wait deadline begins after native process creation returns. Setup,
  native API calls, file I/O, and parent JSON decoding are not interruptible
  whole-supervisor deadlines. Parent result reads are byte-bounded, but this
  is not a proof against adversarial filesystem tampering or resource abuse.
- The worker still runs with the user's permissions. There is no restricted
  token, AppContainer, filesystem/network isolation, or protection against
  a compromised parser changing other accessible files or spawning through
  mechanisms outside the tested ordinary process tree.
- `memory_error` means the worker reported a Python `MemoryError`; this branch
  is not separately proven by an induced real parser exhaustion. Native
  allocation refusal is tested separately. Other nonzero exits remain crashes.
- IPC returns error categories, not the original Python exception objects or
  chained causes. The production inspector's error contract is unchanged.

## Run and interpret

From the repository root, use the approved Python 3.11 development environment
with `requirements.txt` already installed. Keep `TMPDIR`, `TEMP`, and `TMP`
pointing at the chosen local scratch folder. Actual verification used an
explicit path to that environment's interpreter; these are portable equivalents:

```console
python -m unittest discover -s spikes/001-windows-pdf-worker -p test_worker.py -v
python -m unittest discover -s tests -v
python -m unittest discover -s tests/integration -v
python -m compileall -q payer_policy tests spikes/001-windows-pdf-worker
python spikes/001-windows-pdf-worker/win_job.py --probe hello
git diff --check
```

The hello CLI was independently executed: `status=ok`, `exit_code=0`,
`in_job=true`, both memory limits 268,435,456 bytes, `active_limit=2`,
`kill_on_close=true`, and `active_after_cleanup=0`. Other probe behavior is
exercised by the tests; not every CLI mode was separately executed.

A saved-snapshot inspection CLI template is provided below, **not separately
executed**. Substitute an absolute existing storage root and its exact
32-character lowercase hexadecimal retrieval ID. No acquisition is performed:

```console
python spikes/001-windows-pdf-worker/win_job.py --probe inspect --root ABSOLUTE_ROOT --retrieval-id RETRIEVAL_ID
```

Do not use `--abandon` casually: it deliberately ends only its disposable
supervisor process and exists for the lifecycle test. Do not run `worker.py`
directly; that bypasses the experiment's containment setup. The older
[production documentation example](../../docs/document-inspection.md) remains
not separately executed; these probes do not change that status.

## Recommendation for the real build

Keep this code disposable. Separately scope a small production worker before
text extraction: define its caller/error contract, runtime packaging, budget
selection, request-specific result validation, and supervisor failure behavior.
Review file/network permissions separately before any unattended public-PDF
processing. Collection/reuse permission, authenticity, complete PDF validity,
source authority, completeness, and policy applicability remain unresolved by
these resource probes. No text extraction, OCR, indexing, database, UI,
installer, public download, or production API change was added.

## Native references

Important calls are linked here once; docstrings describe the relevant behavior.

- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects): manage members together, accounting, termination, last-handle cleanup, and security limitations.
- [Basic job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information) and [extended limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information): native fields, flags, committed-memory limits.
- [CreateJobObjectW](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-createjobobjectw), [SetInformationJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-setinformationjobobject), [QueryInformationJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject), [TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject): create, configure, observe, stop.
- [InitializeProcThreadAttributeList](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-initializeprocthreadattributelist), [UpdateProcThreadAttribute](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute), [DeleteProcThreadAttributeList](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-deleteprocthreadattributelist): allocate the list; keep job-handle values alive through deletion.
- [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw), [STARTUPINFOEXW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-startupinfoexw), [PROCESS_INFORMATION](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-process_information): explicit application, mutable command line, extended startup, owned handles.
- [PID list](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list), [accounting record](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information), [OpenProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess), [IsProcessInJob](https://learn.microsoft.com/en-us/windows/win32/api/jobapi/nf-jobapi-isprocessinjob): enumerate then hold/recheck process objects, not reused PID numbers.
- [WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject), [GetExitCodeProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getexitcodeprocess), [CloseHandle](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-closehandle): confirm exits and release owned references.
- [VirtualAlloc](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc), [VirtualFree](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualfree): bounded commitment probes and whole-reservation release.
- [ctypes](https://docs.python.org/3.11/library/ctypes.html), [Windows argument quoting](https://docs.python.org/3.11/library/subprocess.html#converting-an-argument-sequence-to-a-string-on-windows), [JSON hooks](https://docs.python.org/3.11/library/json.html#json.loads): explicit native types, no shell, strict/bounded protocol parsing.
- [Windows venv redirectors](https://docs.python.org/3.11/library/venv.html), [sys.base_prefix](https://docs.python.org/3.11/library/sys.html#sys.base_prefix), [os._exit](https://docs.python.org/3.11/library/os.html#os._exit): same base runtime selection and deliberately abrupt supervisor-exit test.

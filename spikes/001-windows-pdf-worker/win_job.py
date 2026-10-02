"""Disposable Windows job runner, not a security sandbox or production API.

JOB_LIST assigns the job during creation. Keep attribute values alive until
DeleteProcThreadAttributeList. Memory caps limit commitment, not working set.
Kill-on-close acts on the last non-inherited job handle. Native API signatures,
layouts, and relevant behavior are linked in README.md#native-references.
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
"""
import ctypes as C
import json
import math
import re
import subprocess
import sys
import time
from ctypes import wintypes as W
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

if sys.platform != "win32":
    raise OSError("this experiment requires Windows")

K = C.WinDLL("kernel32", use_last_error=True)
SIZE = C.c_size_t
FLAGS = 0x2000 | 0x100 | 0x200 | 0x8
JOB_LIST = 0x2000D


class BasicLimits(C.Structure):
    """Mirror JOBOBJECT_BASIC_LIMIT_INFORMATION without packed alignment."""

    _fields_ = [("process_time", C.c_longlong), ("job_time", C.c_longlong),
                ("flags", W.DWORD), ("min_ws", SIZE), ("max_ws", SIZE),
                ("active", W.DWORD), ("affinity", SIZE),
                ("priority", W.DWORD), ("scheduling", W.DWORD)]


class ExtendedLimits(C.Structure):
    """Keep native limit fields and reserved IO counters in SDK order."""

    _fields_ = [("basic", BasicLimits), ("io", C.c_ulonglong * 6),
                ("process_memory", SIZE), ("job_memory", SIZE),
                ("peak_process", SIZE), ("peak_job", SIZE)]


class Accounting(C.Structure):
    """Read job activity for verified post-termination cleanup."""

    _fields_ = [("times", C.c_longlong * 4), ("faults", W.DWORD),
                ("total", W.DWORD), ("active", W.DWORD),
                ("terminated", W.DWORD)]


class ProcessIds(C.Structure):
    """Bound PID enumeration, including Windows console helper processes."""

    _fields_ = [("assigned", W.DWORD), ("listed", W.DWORD),
                ("pids", SIZE * 16)]


class Startup(C.Structure):
    """Mirror STARTUPINFOW; explicit wide strings avoid ANSI conversion."""

    _fields_ = [("cb", W.DWORD), ("reserved", W.LPWSTR),
                ("desktop", W.LPWSTR), ("title", W.LPWSTR),
                ("x", W.DWORD), ("y", W.DWORD),
                ("width", W.DWORD), ("height", W.DWORD),
                ("chars_x", W.DWORD), ("chars_y", W.DWORD),
                ("fill", W.DWORD), ("flags", W.DWORD),
                ("show", W.WORD), ("reserved_size", W.WORD),
                ("reserved_bytes", C.c_void_p), ("stdin", W.HANDLE),
                ("stdout", W.HANDLE), ("stderr", W.HANDLE)]


class StartupEx(C.Structure):
    """Add the opaque process attribute list to the native startup record."""

    _fields_ = [("startup", Startup), ("attributes", C.c_void_p)]


class ProcessInfo(C.Structure):
    """Own the process and initial-thread handles returned by Windows."""

    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE),
                ("pid", W.DWORD), ("tid", W.DWORD)]


def close_handles(handles: tuple[int | None, ...]) -> None:
    """Attempt every owned close; then raise the first native close error."""
    failure = None
    for handle in handles:
        if handle is None:
            continue
        try:
            check(Close(handle))
        except OSError as exc:
            if failure is None:
                failure = exc
    if failure is not None:
        raise failure


def api(name: str, arguments: list[Any], result: Any) -> Any:
    """Bind exact native types so 64-bit handles are not truncated."""
    function = getattr(K, name)
    function.argtypes, function.restype = arguments, result
    return function


CreateJob = api("CreateJobObjectW", [C.c_void_p, W.LPCWSTR], W.HANDLE)
SetJob = api("SetInformationJobObject",
             [W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL)
QueryJob = api("QueryInformationJobObject",
               [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL)
Close = api("CloseHandle", [W.HANDLE], W.BOOL)
InitAttrs = api("InitializeProcThreadAttributeList",
                [C.c_void_p, W.DWORD, W.DWORD, C.POINTER(SIZE)], W.BOOL)
UpdateAttrs = api("UpdateProcThreadAttribute",
                  [C.c_void_p, W.DWORD, SIZE, C.c_void_p, SIZE,
                   C.c_void_p, C.c_void_p], W.BOOL)
DeleteAttrs = api("DeleteProcThreadAttributeList", [C.c_void_p], None)
CreateProcess = api("CreateProcessW",
                    [W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p, W.BOOL,
                     W.DWORD, C.c_void_p, W.LPCWSTR,
                     C.POINTER(StartupEx), C.POINTER(ProcessInfo)], W.BOOL)
IsInJob = api("IsProcessInJob", [W.HANDLE, W.HANDLE, C.POINTER(W.BOOL)],
              W.BOOL)
Wait = api("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD)
ExitCode = api("GetExitCodeProcess", [W.HANDLE, C.POINTER(W.DWORD)], W.BOOL)
TerminateJob = api("TerminateJobObject", [W.HANDLE, W.UINT], W.BOOL)
OpenProcess = api("OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)


@dataclass(frozen=True)
class WorkerLimits:
    """Experimental budgets, not tuned production defaults."""

    timeout_seconds: float = 30
    cleanup_seconds: float = 5
    memory_bytes: int = 256 * 1024 * 1024
    job_memory_bytes: int = 256 * 1024 * 1024
    result_bytes: int = 65_536
    active_limit: int = 2


@dataclass(frozen=True)
class ProbeResult:
    """Record observations; never infer memory exhaustion from a crash."""

    status: str
    exit_code: int
    pid: int
    in_job: bool
    configured: dict[str, int | bool]
    active_after_cleanup: int
    elapsed_seconds: float
    launch_seconds: float
    facts: dict[str, object] = field(default_factory=dict)
    terminated_members: tuple[int, ...] = ()


def check(ok: object) -> None:
    """Translate a failed Win32 return using the saved thread-local error."""
    if not ok:
        raise C.WinError(C.get_last_error())


def query(job: int, record: Any, information_class: int) -> Any:
    """Read actual kernel state, not merely the requested configuration."""
    check(QueryJob(job, information_class, C.byref(record),
                   C.sizeof(record), None))
    return record


def open_job(limits: WorkerLimits) -> int:
    """Create a non-inheritable unnamed job; close it if setup fails."""
    handle = CreateJob(None, None)
    check(handle)
    try:
        record = ExtendedLimits()
        record.basic.flags = FLAGS
        record.basic.active = limits.active_limit
        record.process_memory = limits.memory_bytes
        record.job_memory = limits.job_memory_bytes
        check(SetJob(handle, 9, C.byref(record), C.sizeof(record)))
    except BaseException:
        check(Close(handle))
        raise
    return handle


def launch(job: int, request: Path, output: Path) -> ProcessInfo:
    """Atomically assign the job; never launch an unrestricted fallback.

    CreateProcessW needs a mutable command line. Use a fixed worker and
    explicit interpreter, no shell, inherited handles, or breakaway flag:
    README.md#native-references (CreateProcessW and startup records).
    """
    size = SIZE()
    InitAttrs(None, 1, 0, C.byref(size))
    if C.get_last_error() != 122 or not size.value:
        raise C.WinError(C.get_last_error())
    buffer = C.create_string_buffer(size.value)
    check(InitAttrs(buffer, 1, 0, C.byref(size)))
    try:
        handles = (W.HANDLE * 1)(job)
        check(UpdateAttrs(buffer, 0, JOB_LIST, handles,
                          C.sizeof(handles), None, None))
        startup, info = StartupEx(), ProcessInfo()
        startup.startup.cb = C.sizeof(startup)
        startup.attributes = C.addressof(buffer)
        worker = Path(__file__).with_name("worker.py").resolve()
        # Windows venv executables redirect to another process. Use the
        # same base runtime directly so the two-process ceiling is real.
        interpreter = str(Path(sys.base_prefix) / "python.exe")
        command = C.create_unicode_buffer(subprocess.list2cmdline(
            [interpreter, "-B", str(worker), str(request), str(output)]))
        check(CreateProcess(interpreter, command, None, None, False,
                            0x80000 | 0x08000000, None, str(worker.parent),
                            C.byref(startup), C.byref(info)))
        return info
    finally:
        DeleteAttrs(buffer)


def member_handles(job: int) -> list[tuple[int, int]]:
    """Own handles to current members; recheck membership to avoid PID reuse.

    JobObjectBasicProcessIdList reports active IDs; handles remain tied to
    process objects even after exit:
    README.md#native-references (PID lists and OpenProcess).
    """
    record = query(job, ProcessIds(), 3)
    handles = []
    try:
        for pid in record.pids[:record.listed]:
            handle = OpenProcess(0x100000 | 0x1000, False, pid)
            if not handle and C.get_last_error() == 87:
                continue  # The process exited between enumeration and open.
            check(handle)
            handles.append((pid, handle))
            member = W.BOOL()
            check(IsInJob(handle, job, C.byref(member)))
            if not member.value:
                raise RuntimeError("enumerated process changed membership")
        return handles
    except BaseException:
        close_handles(tuple(handle for _, handle in handles))
        raise


def cleanup(job: int, process: int, seconds: float,
            members: tuple[int, ...] = ()) -> int:
    """Terminate all job members and confirm zero activity, or fail loudly."""
    check(TerminateJob(job, 124))
    deadline = time.monotonic() + seconds
    while True:
        active = query(job, Accounting(), 1).active
        if (active == 0 and Wait(process, 0) == 0
                and all(Wait(handle, 0) == 0 for handle in members)):
            return active
        if time.monotonic() >= deadline:
            raise RuntimeError("job cleanup could not be confirmed")
        time.sleep(0.01)


def validate_limits(limits: WorkerLimits) -> None:
    """Reject unsafe probe budgets before files, jobs, or processes exist."""
    if not isinstance(limits, WorkerLimits):
        raise TypeError("limits must be WorkerLimits")
    for name, maximum in (("timeout_seconds", 60), ("cleanup_seconds", 5)):
        value = getattr(limits, name)
        if (type(value) not in (int, float) or not math.isfinite(value)
                or not 0 < value <= maximum):
            raise ValueError(f"invalid {name}")
    for name, minimum, maximum in (
        ("memory_bytes", 16 * 1024 * 1024, 256 * 1024 * 1024),
        ("job_memory_bytes", 16 * 1024 * 1024, 256 * 1024 * 1024),
        ("result_bytes", 1, 65_536), ("active_limit", 1, 2),
    ):
        value = getattr(limits, name)
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"invalid {name}")


def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON keys before a dictionary hides them.

    object_pairs_hook receives each object as pairs:
    https://docs.python.org/3.11/library/json.html#json.loads
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate result key")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    """Reject JSON's nonstandard NaN and Infinity extensions."""
    raise ValueError("invalid numeric result constant")


def validate_facts(mode: str, status: str, facts: dict[str, Any]) -> None:
    """Check worker.py#worker_main facts for the mode or raise ValueError."""
    errors = {"parser_error": "PdfInspectionError",
              "storage_error": "StorageIntegrityError",
              "input_error": "invalid_storage_input",
              "memory_error": "worker_reported_MemoryError"}
    if status in errors:
        if mode != "inspect" or facts != {"error_code": errors[status]}:
            raise ValueError("invalid reported error")
        return
    shapes = {"inspect": {"sha256", "page_count", "is_encrypted"},
              "allocate": {"small_allocation", "large_allocation",
                           "allocation_error"},
              "process_limit": {"third_refused", "creation_error"},
              "spawn_child": {"worker_pid", "child_pid"}}
    empty_modes = {"hello", "hang", "crash", "bad_json", "oversized",
                   "missing", "wrong_version", "wrong_id", "bad_types",
                   "duplicate_key"}
    if mode not in shapes and mode not in empty_modes:
        raise ValueError("unknown result workload")
    if set(facts) != shapes.get(mode, set()):
        raise ValueError("facts do not match selected workload")
    if not facts:
        return
    elif set(facts) == {"sha256", "page_count", "is_encrypted"}:
        digest, pages, encrypted = (facts["sha256"], facts["page_count"],
                                    facts["is_encrypted"])
        if (not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or type(encrypted) is not bool):
            raise ValueError("invalid PDF identity or encryption flag")
        if ((encrypted and pages is not None) or
                (not encrypted and (type(pages) is not int or pages < 0))):
            raise ValueError("invalid PDF page count")
    elif set(facts) == {"small_allocation", "large_allocation",
                        "allocation_error"}:
        if (type(facts["small_allocation"]) is not bool or
                type(facts["large_allocation"]) is not bool or
                type(facts["allocation_error"]) is not int or
                not 0 <= facts["allocation_error"] <= 0xFFFFFFFF or
                facts["large_allocation"] != (facts["allocation_error"] == 0)):
            raise ValueError("invalid allocation observations")
    elif set(facts) == {"third_refused", "creation_error"}:
        if (type(facts["third_refused"]) is not bool or
                type(facts["creation_error"]) is not int or
                not 0 <= facts["creation_error"] <= 0xFFFFFFFF or
                facts["third_refused"] != (facts["creation_error"] != 0)):
            raise ValueError("invalid process creation observations")
    elif set(facts) == {"worker_pid", "child_pid"}:
        if (any(type(pid) is not int or not 0 < pid <= 0xFFFFFFFF
                for pid in facts.values()) or
                facts["worker_pid"] == facts["child_pid"]):
            raise ValueError("invalid lifecycle PIDs")
    else:
        raise ValueError("unknown fact shape")


def read_result(path: Path, limit: int, retrieval_id: str,
                mode: str) -> dict[str, Any]:
    """Return bounded, mode-checked JSON or invalid_result on bad output.

    win_job.py#validate_facts binds facts to the selected fixed workload.
    """
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("result exceeds read budget")
        value = json.loads(data.decode("utf-8"),
                           object_pairs_hook=unique_pairs,
                           parse_constant=reject_constant)
        if (not isinstance(value, dict) or set(value) != {
                "schema_version", "status", "retrieval_id", "facts"}):
            raise ValueError("invalid result envelope")
        if (type(value["schema_version"]) is not int
                or value["schema_version"] != 1):
            raise ValueError("invalid result version")
        if value["retrieval_id"] != retrieval_id:
            raise ValueError("result belongs to another retrieval")
        if (value["status"] not in {"ok", "parser_error", "storage_error",
                                    "input_error", "memory_error"}
                or not isinstance(value["facts"], dict)):
            raise ValueError("invalid result fields")
        validate_facts(mode, value["status"], value["facts"])
        return value
    except (OSError, ValueError, TypeError, RecursionError):
        return {"status": "invalid_result", "facts": {}}


def reconcile_lifecycle(payload: dict[str, Any], worker_pid: int,
                        members: list[tuple[int, int]]) -> dict[str, Any]:
    """Return the payload, or invalid_result for unconfirmed lifecycle IDs.

    win_job.py#member_handles checks membership and retains owned handles;
    compare launch and member IDs before copying facts, even after exit.
    """
    if payload["status"] == "ok":
        facts = payload["facts"]
        pids = {pid for pid, _ in members}
        if (facts["worker_pid"] != worker_pid or worker_pid not in pids or
                facts["child_pid"] not in pids):
            return {"status": "invalid_result", "facts": {}}
    return payload


def run_probe(mode: str, *, limits: WorkerLimits = WorkerLimits(),
              retrieval_id: str = "1234567890abcdef1234567890abcdef",
              root: Path | None = None, max_bytes: int = 10_000_000
              ) -> ProbeResult:
    """Run a fixed kernel-limited probe; close owned handles even on errors."""
    validate_limits(limits)
    if not isinstance(retrieval_id, str):
        raise TypeError("retrieval_id must be a string")
    if not re.fullmatch(r"[0-9a-f]{32}", retrieval_id):
        raise ValueError("invalid retrieval_id")
    if mode not in {"hello", "hang", "allocate", "crash", "bad_json",
                    "oversized", "missing", "wrong_version", "wrong_id",
                    "bad_types", "duplicate_key", "spawn_child", "inspect",
                    "process_limit"}:
        raise ValueError("unknown probe mode")
    if mode == "inspect" and not isinstance(root, Path):
        raise TypeError("inspection root must be a Path")
    if type(max_bytes) is not int or not 0 < max_bytes <= 10_000_000:
        raise ValueError("invalid saved-original limit")
    with TemporaryDirectory() as directory:
        request = Path(directory) / "request.json"
        output = Path(directory) / "out.json"
        packages = Path(sys.prefix) / "Lib" / "site-packages"
        request.write_text(json.dumps({"mode": mode,
                                       "retrieval_id": retrieval_id,
                                       "root": str(root) if root else None,
                                       "max_bytes": max_bytes,
                                       "site_packages": str(packages)}),
                           encoding="utf-8")
        job = open_job(limits)
        info = None
        members = []
        cleanup_started = False
        try:
            actual = query(job, ExtendedLimits(), 9)
            launch_start = time.monotonic()
            info = launch(job, request, output)
            started = time.monotonic()
            launch_time = started - launch_start
            check(Close(info.thread))
            info.thread = None
            member = W.BOOL()
            check(IsInJob(info.process, job, C.byref(member)))
            if not member.value:
                raise RuntimeError("worker is not in the intended job")
            remaining = max(0, limits.timeout_seconds
                            - (time.monotonic() - started))
            waited = Wait(info.process, math.ceil(remaining * 1000))
            if waited == 0xFFFFFFFF:
                raise C.WinError(C.get_last_error())
            if waited not in (0, 258):
                raise RuntimeError("unexpected process wait result")
            timed_out = waited == 258
            code = W.DWORD()
            check(ExitCode(info.process, C.byref(code)))
            if timed_out:
                payload = {"status": "timeout"}
            elif code.value != 0:
                payload = {"status": "crash"}
            else:
                payload = read_result(output, limits.result_bytes,
                                      retrieval_id, mode)
            members = member_handles(job)
            if mode == "spawn_child":
                payload = reconcile_lifecycle(payload, info.pid, members)
            cleanup_started = True
            active = cleanup(job, info.process, limits.cleanup_seconds,
                             tuple(handle for _, handle in members))
            check(ExitCode(info.process, C.byref(code)))
            if timed_out and mode == "spawn_child":
                observed = read_result(output, limits.result_bytes,
                                       retrieval_id, mode)
                observed = reconcile_lifecycle(observed, info.pid, members)
                if observed["status"] == "ok":
                    payload["facts"] = observed["facts"]
            return ProbeResult(
                payload["status"], code.value, info.pid, bool(member.value),
                {"process_memory": actual.process_memory,
                 "job_memory": actual.job_memory,
                 "active_limit": actual.basic.active,
                 "kill_on_close": bool(actual.basic.flags & 0x2000)},
                active, time.monotonic() - started, launch_time,
                payload.get("facts", {}),
                tuple(pid for pid, _ in members))
        finally:
            try:
                if info is not None and not cleanup_started:
                    cleanup(job, info.process, limits.cleanup_seconds)
            finally:
                owned = tuple(handle for _, handle in members)
                if info is not None:
                    owned += (info.thread, info.process)
                close_handles(owned + (job,))


def abandon_probe(directory: Path) -> None:
    """Exit a disposable supervisor only after observers hold member handles.

    os._exit bypasses Python finally blocks. Windows must close the last
    non-inherited job handle and stop the workers without cleanup assistance:
    https://docs.python.org/3.11/library/os.html#os._exit
    """
    import os

    limits = WorkerLimits()
    request, output = directory / "request.json", directory / "out.json"
    retrieval_id = "1234567890abcdef1234567890abcdef"
    request.write_text(json.dumps({"mode": "spawn_child",
                                   "retrieval_id": retrieval_id}),
                       encoding="utf-8")
    job, info, members = open_job(limits), None, []
    try:
        info = launch(job, request, output)
        deadline = time.monotonic() + 10
        while not output.exists():
            if Wait(info.process, 0) == 0 or time.monotonic() >= deadline:
                raise RuntimeError("lifecycle worker did not become ready")
            time.sleep(0.01)
        # The worker writes before sleeping; wait for a complete envelope.
        while True:
            observed = read_result(output, 65_536, retrieval_id, "spawn_child")
            if observed["status"] == "ok":
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("lifecycle worker has invalid output")
            time.sleep(0.01)
        members = member_handles(job)
        observed = reconcile_lifecycle(observed, info.pid, members)
        if observed["status"] != "ok":
            raise RuntimeError("lifecycle facts lack native confirmation")
        evidence = directory / "ready.tmp"
        evidence.write_text(json.dumps({"pids": [pid for pid, _ in members]}),
                            encoding="utf-8")
        evidence.replace(directory / "ready.json")
        while not (directory / "ack").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("lifecycle observer did not acknowledge")
            time.sleep(0.01)
        os._exit(23)  # Intentional only in this disposable test supervisor.
    finally:
        try:
            if info is not None:
                cleanup(job, info.process, limits.cleanup_seconds,
                        tuple(handle for _, handle in members))
        finally:
            owned = tuple(handle for _, handle in members)
            if info is not None:
                owned += (info.thread, info.process)
            close_handles(owned + (job,))


def main() -> None:
    """Run a fixed CLI probe, or the explicitly selected lifecycle harness."""
    import argparse
    from dataclasses import asdict

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--probe", default="hello")
    parser.add_argument("--abandon", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--retrieval-id",
                        default="1234567890abcdef1234567890abcdef")
    arguments = parser.parse_args()
    if arguments.abandon is not None:
        abandon_probe(arguments.abandon)
    else:
        result = run_probe(arguments.probe, root=arguments.root,
                           retrieval_id=arguments.retrieval_id)
        print(json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    main()


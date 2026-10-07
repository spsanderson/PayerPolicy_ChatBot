"""Own a Windows resource-limited process group; no permission sandbox.

Job objects configure commitment caps and last-handle termination:
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
JOB_LIST assigns membership during creation; its value must outlive the list:
https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/
nf-processthreadsapi-updateprocthreadattribute
Native records follow the Windows SDK's default x64 alignment:
https://learn.microsoft.com/en-us/windows/win32/api/winnt/
ns-winnt-jobobject_extended_limit_information
ctypes signatures keep pointers and handles pointer-sized:
https://docs.python.org/3.11/library/ctypes.html
Command quoting is for CreateProcessW, never a shell:
https://docs.python.org/3.11/library/subprocess.html
"""
import ctypes as C
import math
import subprocess
import time
from ctypes import wintypes as W
from pathlib import Path
from types import TracebackType
from typing import Any

SIZE = C.c_size_t
LIMIT_FLAGS = 0x2000 | 0x100 | 0x200 | 0x8
JOB_LIST = 0x2000D


class BasicLimits(C.Structure):
    """Mirror JOBOBJECT_BASIC_LIMIT_INFORMATION in SDK field order."""

    _fields_ = [("process_time", C.c_longlong), ("job_time", C.c_longlong),
                ("flags", W.DWORD), ("min_ws", SIZE), ("max_ws", SIZE),
                ("active", W.DWORD), ("affinity", SIZE),
                ("priority", W.DWORD), ("scheduling", W.DWORD)]


class ExtendedLimits(C.Structure):
    """Hold basic limits, IO counters and committed-memory caps."""

    _fields_ = [("basic", BasicLimits), ("io", C.c_ulonglong * 6),
                ("process_memory", SIZE), ("job_memory", SIZE),
                ("peak_process", SIZE), ("peak_job", SIZE)]


class Accounting(C.Structure):
    """Read actual active-process accounting from the kernel."""

    _fields_ = [("times", C.c_longlong * 4), ("faults", W.DWORD),
                ("total", W.DWORD), ("active", W.DWORD),
                ("terminated", W.DWORD)]


class ProcessIds(C.Structure):
    """Bound enumeration to 16 members, including console helpers."""

    _fields_ = [("assigned", W.DWORD), ("listed", W.DWORD),
                ("pids", SIZE * 16)]


class Startup(C.Structure):
    """Mirror STARTUPINFOW with wide strings and pointer-sized handles."""

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
    """Append the attribute-list pointer to STARTUPINFOW."""

    _fields_ = [("startup", Startup), ("attributes", C.c_void_p)]


class ProcessInfo(C.Structure):
    """Own the process and thread handles returned by CreateProcessW."""

    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE),
                ("pid", W.DWORD), ("tid", W.DWORD)]


class CleanupError(OSError):
    """Native shutdown or handle release could not be confirmed."""


class NativeApi:
    """Bind Windows only when an operation actually needs the library."""

    def __init__(self) -> None:
        """Load kernel32 and assign exact signatures; propagate setup errors."""
        library = C.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJob": ("CreateJobObjectW", [C.c_void_p, W.LPCWSTR],
                          W.HANDLE),
            "SetJob": ("SetInformationJobObject", [W.HANDLE, C.c_int,
                       C.c_void_p, W.DWORD], W.BOOL),
            "QueryJob": ("QueryInformationJobObject", [W.HANDLE, C.c_int,
                         C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
            "Close": ("CloseHandle", [W.HANDLE], W.BOOL),
            "InitAttrs": ("InitializeProcThreadAttributeList",
                          [C.c_void_p, W.DWORD, W.DWORD, C.POINTER(SIZE)],
                          W.BOOL),
            "UpdateAttrs": ("UpdateProcThreadAttribute", [C.c_void_p,
                            W.DWORD, SIZE, C.c_void_p, SIZE, C.c_void_p,
                            C.c_void_p], W.BOOL),
            "DeleteAttrs": ("DeleteProcThreadAttributeList", [C.c_void_p],
                            None),
            "CreateProcess": ("CreateProcessW", [W.LPCWSTR, W.LPWSTR,
                              C.c_void_p, C.c_void_p, W.BOOL, W.DWORD,
                              C.c_void_p, W.LPCWSTR, C.POINTER(StartupEx),
                              C.POINTER(ProcessInfo)], W.BOOL),
            "IsInJob": ("IsProcessInJob", [W.HANDLE, W.HANDLE,
                        C.POINTER(W.BOOL)], W.BOOL),
            "Wait": ("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD),
            "ExitCode": ("GetExitCodeProcess", [W.HANDLE,
                         C.POINTER(W.DWORD)], W.BOOL),
            "TerminateJob": ("TerminateJobObject", [W.HANDLE, W.UINT],
                             W.BOOL),
            "OpenProcess": ("OpenProcess", [W.DWORD, W.BOOL, W.DWORD],
                            W.HANDLE),
        }
        for alias, (name, arguments, result) in signatures.items():
            function = getattr(library, name)
            function.argtypes, function.restype = arguments, result
            setattr(self, alias, function)


def check(ok: object) -> None:
    """Raise the saved Win32 error when a BOOL or handle indicates failure."""
    if not ok:
        raise C.WinError(C.get_last_error())


class Job:
    """Own every native handle for one worker and verify shutdown on exit."""

    def __init__(self, memory_bytes: int) -> None:
        """Remember the cap; do not create any native objects yet."""
        self.memory_bytes = memory_bytes
        self.api = NativeApi()
        self.handle: int | None = None
        self.process = ProcessInfo()
        self.configured = ExtendedLimits()
        self.active_after_cleanup: int | None = None
        self.closed = False

    def query(self, record: Any, information_class: int) -> Any:
        """Return actual kernel state, failing rather than guessing limits."""
        check(self.api.QueryJob(self.handle, information_class,
                               C.byref(record), C.sizeof(record), None))
        return record

    def __enter__(self) -> "Job":
        """Create, configure and read back caps before any process exists."""
        self.handle = self.api.CreateJob(None, None)
        check(self.handle)
        try:
            record = ExtendedLimits()
            record.basic.flags = LIMIT_FLAGS
            record.basic.active = 1
            record.process_memory = self.memory_bytes
            record.job_memory = self.memory_bytes
            check(self.api.SetJob(self.handle, 9, C.byref(record),
                                  C.sizeof(record)))
            actual = self.query(ExtendedLimits(), 9)
            if (actual.basic.flags != LIMIT_FLAGS or actual.basic.active != 1
                    or actual.process_memory != self.memory_bytes
                    or actual.job_memory != self.memory_bytes):
                raise OSError("job limits did not match")
            self.configured = actual
            return self
        except BaseException as exc:
            self.__exit__(type(exc), exc, exc.__traceback__)
            raise

    def launch(
        self, interpreter: Path, script: Path, arguments: list[str],
    ) -> None:
        """Assign this configured job during creation, with no fallback.

        Only the public supervisor chooses the production child. Tests may
        use this private helper with fixed synthetic scripts. The attribute
        value stays alive until DeleteAttrs; no handles are inherited.
        """
        if self.process.process or not self.handle:
            raise OSError("job is absent or already launched")
        size = SIZE()
        self.api.InitAttrs(None, 1, 0, C.byref(size))
        if C.get_last_error() != 122 or not size.value:
            raise C.WinError(C.get_last_error())
        buffer = C.create_string_buffer(size.value)
        check(self.api.InitAttrs(buffer, 1, 0, C.byref(size)))
        handles = (W.HANDLE * 1)(self.handle)
        try:
            check(self.api.UpdateAttrs(buffer, 0, JOB_LIST, handles,
                                       C.sizeof(handles), None, None))
            startup = StartupEx()
            startup.startup.cb = C.sizeof(startup)
            startup.attributes = C.addressof(buffer)
            command = C.create_unicode_buffer(subprocess.list2cmdline([
                str(interpreter), "-I", "-S", "-B", str(script), *arguments,
            ]))
            check(self.api.CreateProcess(
                str(interpreter), command, None, None, False,
                0x80000 | 0x08000000, None, str(script.parent),
                C.byref(startup), C.byref(self.process)))
        finally:
            self.api.DeleteAttrs(buffer)
        if not self.in_job():
            raise OSError("worker membership not confirmed")

    def in_job(self, handle: int | None = None) -> bool:
        """Check a process object, not a potentially reused PID number."""
        member = W.BOOL()
        check(self.api.IsInJob(handle or self.process.process, self.handle,
                               C.byref(member)))
        return bool(member.value)

    def wait(self, seconds: float) -> int:
        """Wait only for worker exit; return its code or raise TimeoutError."""
        result = self.api.Wait(self.process.process, math.ceil(seconds * 1000))
        if result == 258:
            raise TimeoutError("worker wait expired")
        if result != 0:
            raise C.WinError(C.get_last_error())
        code = W.DWORD()
        check(self.api.ExitCode(self.process.process, C.byref(code)))
        return code.value

    def _capture_members(self, owned: list[int]) -> None:
        """Hold and recheck up to 16 members; never truncate PID overflow."""
        record = self.query(ProcessIds(), 3)
        if record.assigned > 16 or record.listed > 16:
            raise OSError("job member enumeration overflow")
        for pid in record.pids[:record.listed]:
            handle = self.api.OpenProcess(0x100000 | 0x1000, False, pid)
            if not handle and C.get_last_error() == 87:
                continue
            check(handle)
            owned.append(handle)
            if not self.in_job(handle):
                raise OSError("enumerated process changed membership")

    def _close(self, handles: list[int]) -> None:
        """Attempt every close even if an earlier close reports failure."""
        errors = []
        for handle in handles:
            try:
                check(self.api.Close(handle))
            except OSError as exc:
                errors.append(exc)
        if errors:
            failure = CleanupError("native handle close failed")
            for error in errors:
                failure.add_note(str(error))
            raise failure from errors[0]

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop members and confirm active zero within one five-second budget.

        Native calls and filesystem work are not whole-call deadlines.
        Interrupts are re-raised after cleanup with cleanup evidence attached.
        """
        deadline = time.monotonic() + 5
        members: list[int] = []
        failures: list[Exception] = []
        if self.handle:
            try:
                self._capture_members(members)
            except Exception as exc:
                failures.append(exc)
            try:
                check(self.api.TerminateJob(self.handle, 124))
                observed = members + ([self.process.process]
                                      if self.process.process else [])
                while True:
                    active = self.query(Accounting(), 1).active
                    states = [self.api.Wait(handle, 0) for handle in observed]
                    if any(state not in (0, 258) for state in states):
                        raise OSError("member wait failed")
                    if active == 0 and all(state == 0 for state in states):
                        self.active_after_cleanup = 0
                        break
                    if time.monotonic() >= deadline:
                        raise OSError("job shutdown not confirmed")
                    time.sleep(0.01)
            except Exception as exc:
                failures.append(exc)
        handles = members + [handle for handle in (
            self.process.thread, self.process.process, self.handle) if handle]
        try:
            self._close(handles)
        except Exception as exc:
            failures.append(exc)
        self.closed = not failures
        self.handle = None
        self.process = ProcessInfo()
        if failures:
            cleanup = CleanupError("native cleanup failed")
            for failure in failures:
                cleanup.add_note(repr(failure))
            if error is not None and not isinstance(error, Exception):
                error.add_note(str(cleanup) + "; " + repr(failures))
                return
            raise cleanup from (error or failures[0])

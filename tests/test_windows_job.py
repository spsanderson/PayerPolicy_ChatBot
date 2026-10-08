"""Native production-helper tests using only fixed synthetic workloads."""
import ctypes
import importlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import subprocess
import time


@unittest.skipUnless(sys.platform == "win32", "Windows native jobs")
class NativeJobTests(unittest.TestCase):
    """Exercise real configured jobs, not the disposable experiment."""

    def test_committed_allocation_refusal_has_positive_control(self) -> None:
        """A fixed 64 MiB commit fails at 48 MiB and succeeds at 128 MiB."""
        from payer_policy._windows_job import Job

        fixture = Path(__file__).parent / "worker_fixtures"
        base = Path(sys.base_prefix).resolve() / "python.exe"
        with TemporaryDirectory() as directory:
            output = Path(directory) / "allocation.json"
            for cap, expected in ((48, False), (128, True)):
                with self.subTest(cap=cap):
                    with Job(cap * 1024 * 1024) as job:
                        job.launch(base, fixture / "allocate_worker.py",
                                   [str(output)])
                        self.assertEqual(job.wait(5), 0)
                    result = json.loads(output.read_text())
                    self.assertIs(result["allocated"], expected)
                    self.assertEqual(result["error"] == 0, expected)
                    self.assertEqual(job.active_after_cleanup, 0)
                    self.assertTrue(job.closed)

    def test_ordinary_extra_child_is_refused(self) -> None:
        """Try an ordinary CreateProcess inside active limit one."""
        from payer_policy._windows_job import Job

        fixture = Path(__file__).parent / "worker_fixtures" / "spawn_worker.py"
        with TemporaryDirectory() as directory:
            output = Path(directory) / "spawn.json"
            with Job(128 * 1024 * 1024) as job:
                job.launch(Path(sys.base_prefix).resolve() / "python.exe",
                           fixture, [str(output)])
                self.assertEqual(job.wait(5), 0)
            result = json.loads(output.read_text())
            self.assertTrue(result["refused"])
            self.assertEqual(result["error"], 1816)
            self.assertEqual(job.active_after_cleanup, 0)
            self.assertTrue(job.closed)

    def test_supervisor_death_kills_observed_members(self) -> None:
        """Hold process objects before acknowledging an abrupt owner exit."""
        from payer_policy._windows_job import NativeApi, check

        api = NativeApi()
        fixture = (Path(__file__).parent / "worker_fixtures"
                   / "abrupt_supervisor.py")
        base = Path(sys.base_prefix).resolve() / "python.exe"
        handles = []
        with TemporaryDirectory() as directory:
            output = Path(directory) / "members.json"
            ack = Path(directory) / "observer-ready"
            supervisor = subprocess.Popen(
                [str(base), "-I", "-S", "-B", str(fixture),
                 str(output), str(ack)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            try:
                deadline = time.monotonic() + 10
                while not output.with_suffix(".ready").exists():
                    self.assertIsNone(supervisor.poll())
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.01)
                report = json.loads(output.read_text())
                self.assertIn(report["worker"], report["members"])
                self.assertLessEqual(len(report["members"]), 16)
                for pid in report["members"]:
                    handle = api.OpenProcess(0x100000 | 0x1000, False, pid)
                    check(handle)
                    handles.append(handle)
                    self.assertEqual(api.Wait(handle, 0), 258)
                ack.write_bytes(b"handles held")
                _, stderr = supervisor.communicate(timeout=10)
                self.assertEqual(supervisor.returncode, 23, stderr)
                for handle in handles:
                    self.assertEqual(api.Wait(handle, 5000), 0)
            finally:
                if supervisor.poll() is None:
                    supervisor.kill()
                supervisor.communicate(timeout=10)
                for handle in handles:
                    check(api.Close(handle))

    def test_all_closes_attempted_after_native_close_error(self) -> None:
        """Actually close each handle, then inject one failed-close report."""
        from payer_policy._windows_job import CleanupError, Job

        job = Job(128 * 1024 * 1024)
        closed = []
        close = job.api.Close

        def close_report(handle: int) -> int:
            """Record physical closes; fail only the first report."""
            result = close(handle)
            closed.append(handle)
            if len(closed) == 1:
                ctypes.set_last_error(6)
                return 0
            return result

        with self.assertRaises(CleanupError):
            with job:
                job.launch(Path(sys.base_prefix).resolve() / "python.exe",
                           Path(__file__).parent / "worker_fixtures"
                           / "sleep_worker.py", [])
                owned = {job.handle, job.process.process, job.process.thread}
                job.api.Close = close_report
        self.assertTrue(owned.issubset(set(closed)))
        self.assertEqual(len(closed), len(set(closed)))
        self.assertEqual(job.active_after_cleanup, 0)
        self.assertFalse(job.closed)

    def test_local_memory_failure_survives_native_cleanup_failure(
        self,
    ) -> None:
        """Never label a parent MemoryError as an explicit child report."""
        from payer_policy._windows_job import CleanupError, Job

        job = Job(128 * 1024 * 1024)
        close = job._close
        failure = MemoryError("local")

        def close_report(handles: list[int]) -> None:
            """Close owned handles before reporting a simulated OS failure."""
            close(handles)
            raise CleanupError("simulated report")

        with self.assertRaises(MemoryError) as got:
            with job:
                job._close = close_report
                raise failure
        self.assertIs(got.exception, failure)
        self.assertTrue(failure.__notes__)

    def test_interrupt_during_cleanup_still_attempts_all_closes(self) -> None:
        """A stop while capturing or closing must not abandon owned handles."""
        from payer_policy._windows_job import Job

        for seam in ("capture", "close"):
            with self.subTest(seam=seam):
                job = Job(128 * 1024 * 1024)
                closed = []
                close = job.api.Close
                failure = KeyboardInterrupt()

                def close_report(handle: int) -> int:
                    """Physically close and optionally interrupt the report."""
                    result = close(handle)
                    closed.append(handle)
                    if seam == "close" and len(closed) == 1:
                        raise failure
                    return result

                with self.assertRaises(KeyboardInterrupt) as got:
                    with job:
                        job.api.Close = close_report
                        owned = job.handle
                        if seam == "capture":
                            job._capture_members = unittest.mock.Mock(
                                side_effect=failure)
                self.assertIs(got.exception, failure)
                self.assertIn(owned, closed)
                self.assertIsNone(job.handle)
                self.assertFalse(job.closed)

    def test_native_setup_faults_fail_closed(self) -> None:
        """Inject failed API reports; setup never starts a fallback child."""
        from payer_policy._windows_job import Job

        for seam in ("CreateJob", "SetJob", "InitAttrs", "UpdateAttrs",
                     "CreateProcess"):
            with self.subTest(seam=seam):
                job = Job(128 * 1024 * 1024)
                with patch.object(job.api, seam, return_value=0):
                    with self.assertRaises(OSError):
                        with job:
                            job.launch(
                                Path(sys.base_prefix).resolve() / "python.exe",
                                Path(__file__).parent / "worker_fixtures"
                                / "hello.py", [])
                self.assertFalse(job.process.process)
                self.assertFalse(job.handle)

    def test_overflow_and_membership_change_fail_cleanup(self) -> None:
        """Reject too many PIDs or a reused PID, yet kill and close the job."""
        from payer_policy._windows_job import CleanupError, Job, ProcessIds

        for seam in ("overflow", "membership"):
            with self.subTest(seam=seam):
                job = Job(128 * 1024 * 1024)
                with self.assertRaises(CleanupError):
                    with job:
                        job.launch(
                            Path(sys.base_prefix).resolve() / "python.exe",
                            Path(__file__).parent / "worker_fixtures"
                            / "sleep_worker.py", [])
                        if seam == "overflow":
                            query = job.query

                            def overflow(record: object, kind: int) -> object:
                                """Simulate excess membership only."""
                                if isinstance(record, ProcessIds):
                                    record.assigned = 17
                                    return record
                                return query(record, kind)

                            job.query = overflow
                        else:
                            job.in_job = unittest.mock.Mock(return_value=False)
                self.assertEqual(job.active_after_cleanup, 0)
                self.assertIsNone(job.handle)
                self.assertFalse(job.closed)

    def test_cleanup_observation_uses_one_shared_deadline(self) -> None:
        """Fail closed when accounting still lags after five seconds."""
        from payer_policy._windows_job import Accounting, CleanupError, Job

        job = Job(128 * 1024 * 1024)
        query = job.query

        def active(record: object, kind: int) -> object:
            """Keep accounting nonzero without leaving a real child alive."""
            if isinstance(record, Accounting):
                record.active = 1
                return record
            return query(record, kind)

        with self.assertRaises(CleanupError):
            with patch("payer_policy._windows_job.time.monotonic",
                       side_effect=[10, 16]):
                with job:
                    job.query = active
        self.assertIsNone(job.active_after_cleanup)
        self.assertIsNone(job.handle)
        self.assertFalse(job.closed)

    def test_creation_flags_and_attribute_lifetime(self) -> None:
        """Check runtime, no inheritance/breakaway, and live JOB_LIST."""
        from payer_policy import _windows_job as native

        job = native.Job(128 * 1024 * 1024)
        update, delete = job.api.UpdateAttrs, job.api.DeleteAttrs
        create = job.api.CreateProcess
        values = []
        seen = []
        base = Path(sys.base_prefix).resolve() / "python.exe"

        def update_attribute(*arguments: object) -> int:
            """Retain only the native address, not the Python value owner."""
            self.assertEqual(arguments[2], native.JOB_LIST)
            self.assertEqual(arguments[4], ctypes.sizeof(native.W.HANDLE))
            values.append(ctypes.addressof(arguments[3]))
            return update(*arguments)

        def delete_attribute(buffer: object) -> None:
            """Read the attribute value while Windows still owns the list."""
            value = native.W.HANDLE.from_address(values[0]).value
            self.assertEqual(value, job.handle)
            seen.append("delete")
            delete(buffer)

        def create_process(*arguments: object) -> int:
            """Check native launch flags before calling Windows."""
            self.assertEqual(arguments[0], str(base))
            self.assertFalse(arguments[4])
            self.assertEqual(arguments[5], 0x80000 | 0x08000000)
            self.assertIn("-I -S -B", arguments[1].value)
            seen.append("create")
            return create(*arguments)

        with job:
            job.api.UpdateAttrs = update_attribute
            job.api.DeleteAttrs = delete_attribute
            job.api.CreateProcess = create_process
            job.launch(base, Path(__file__).parent / "worker_fixtures"
                       / "hello.py", [])
            self.assertEqual(job.wait(5), 0)
        self.assertEqual(seen, ["create", "delete"])
        self.assertEqual(native.BasicLimits.flags.offset, 16)
        self.assertEqual(native.BasicLimits.min_ws.offset, 24)
        self.assertEqual(native.ExtendedLimits.process_memory.offset, 112)
        self.assertIs(native.NativeApi().OpenProcess.restype, native.W.HANDLE)
        self.assertEqual(native.NativeApi().CreateProcess.argtypes[-1],
                         ctypes.POINTER(native.ProcessInfo))

    def test_limit_mismatch_and_cleanup_api_failures_are_not_success(
        self,
    ) -> None:
        """Fail closed on mismatched caps or failed shutdown observations."""
        from payer_policy import _windows_job as native

        job = native.Job(128 * 1024 * 1024)
        query = job.query

        def mismatch(record: object, kind: int) -> object:
            """Read real limits, then simulate a differing active cap."""
            result = query(record, kind)
            if isinstance(result, native.ExtendedLimits):
                result.basic.active = 2
            return result

        with patch.object(job, "query", mismatch):
            with self.assertRaises(OSError):
                with job:
                    self.fail("mismatched cap accepted")
        self.assertTrue(job.closed)
        for seam in ("TerminateJob", "QueryJob", "Wait"):
            with self.subTest(seam=seam):
                job = native.Job(128 * 1024 * 1024)
                observer = native.NativeApi()
                held = None
                try:
                    with self.assertRaises(native.CleanupError):
                        with job:
                            job.launch(
                                Path(sys.base_prefix).resolve() / "python.exe",
                                Path(__file__).parent / "worker_fixtures"
                                / "sleep_worker.py", [])
                            held = observer.OpenProcess(
                                0x100000 | 0x1000, False, job.process.pid)
                            native.check(held)
                            setattr(job.api, seam, unittest.mock.Mock(
                                return_value=0xFFFFFFFF if seam == "Wait"
                                else 0))
                    self.assertIsNone(job.handle)
                    self.assertFalse(job.closed)
                    self.assertEqual(observer.Wait(held, 5000), 0)
                finally:
                    if held:
                        native.check(observer.Close(held))

    def test_job_is_configured_before_launch_and_cleaned(self) -> None:
        """Read actual caps/membership and confirm exit before closing."""
        try:
            native = importlib.import_module("payer_policy._windows_job")
        except ModuleNotFoundError:
            self.fail("production native helper is missing")
        expected_sizes = {
            "BasicLimits": 64, "ExtendedLimits": 144, "Accounting": 48,
            "ProcessIds": 136, "Startup": 104, "StartupEx": 112,
            "ProcessInfo": 24,
        }
        for name, size in expected_sizes.items():
            self.assertEqual(ctypes.sizeof(getattr(native, name)), size)
        with native.Job(128 * 1024 * 1024) as job:
            limits = job.configured
            self.assertEqual(limits.basic.active, 1)
            self.assertEqual(limits.basic.flags, native.LIMIT_FLAGS)
            self.assertEqual(limits.process_memory, 128 * 1024 * 1024)
            self.assertEqual(limits.job_memory, 128 * 1024 * 1024)
            base = Path(sys.base_prefix) / "python.exe"
            fixture = Path(__file__).parent / "worker_fixtures" / "hello.py"
            job.launch(base, fixture, [])
            self.assertTrue(job.in_job())
            self.assertEqual(job.wait(5), 0)
        self.assertEqual(job.active_after_cleanup, 0)
        self.assertTrue(job.closed)


if __name__ == "__main__":
    unittest.main()

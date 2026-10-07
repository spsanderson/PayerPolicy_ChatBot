"""Native production-helper tests using only fixed synthetic workloads."""
import ctypes
import importlib
import sys
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == "win32", "Windows native jobs")
class NativeJobTests(unittest.TestCase):
    """Exercise real configured jobs, not the disposable experiment."""

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

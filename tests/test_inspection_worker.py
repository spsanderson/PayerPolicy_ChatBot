"""Offline caller and real-process tests for the contained PDF API."""
import importlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Windows storage contract")
class WorkerExecutionTests(unittest.TestCase):
    """Inspect real saved synthetic PDFs in the production worker."""

    def test_child_parser_error_has_stable_category(self) -> None:
        """Reject a real malformed PDF without leaking a remote traceback."""
        from test_document_inspection import RETRIEVAL_ID, save_fixture
        from payer_policy.inspection_worker import (
            WorkerInspectionError, inspect_saved_pdf_in_worker,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, b"%PDF-")
            record = root / "records" / RETRIEVAL_ID
            before = {p: p.read_bytes() for p in record.iterdir()}
            with self.assertRaises(WorkerInspectionError) as caught:
                inspect_saved_pdf_in_worker(root, RETRIEVAL_ID)
            self.assertEqual(caught.exception.code, "parser_error")
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_storage_failures_keep_snapshots_unchanged(self) -> None:
        """Classify damaged, missing and over-budget saved bytes as storage."""
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        from payer_policy.inspection_worker import (
            WorkerInspectionError, inspect_saved_pdf_in_worker,
        )

        for damage in ("original", "receipt", "missing", "size"):
            with self.subTest(damage=damage), TemporaryDirectory() as name:
                root = Path(name)
                save_fixture(root, pdf_with_pages(1))
                record = root / "records" / RETRIEVAL_ID
                if damage == "original":
                    (record / "original.bin").write_bytes(b"%PDF-changed")
                elif damage == "receipt":
                    (record / "receipt.json").write_bytes(b"{}")
                elif damage == "missing":
                    (record / "original.bin").unlink()
                before = {p.name: p.read_bytes() for p in record.iterdir()}
                with self.assertRaises(WorkerInspectionError) as caught:
                    inspect_saved_pdf_in_worker(
                        root, RETRIEVAL_ID,
                        max_bytes=1 if damage == "size" else 10_000_000,
                    )
                self.assertEqual(caught.exception.code, "storage_error")
                self.assertEqual(before, {
                    p.name: p.read_bytes() for p in record.iterdir()})

    def test_simulated_child_reports_reach_public_api(self) -> None:
        """Distinguish explicit simulated memory/input reports from crashes."""
        from payer_policy import inspection_worker as worker
        from payer_policy._windows_job import Job
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        launch = Job.launch
        fixture = Path(__file__).parent / "worker_fixtures"

        def substitute(job: Job, interpreter: Path, script: Path,
                       arguments: list[str]) -> None:
            """Run a fixed injected-error fixture through real native code."""
            launch(job, interpreter, fixture / name, arguments)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(1))
            for name, code in (("memory_report_worker.py", "memory_error"),
                               ("input_report_worker.py", "input_error")):
                with self.subTest(code=code):
                    with patch.object(Job, "launch", substitute):
                        with self.assertRaises(
                                worker.WorkerInspectionError) as got:
                            worker.inspect_saved_pdf_in_worker(
                                root, RETRIEVAL_ID)
                    self.assertEqual(got.exception.code, code)
                    self.assertEqual(str(got.exception), code)
                    self.assertIsNone(got.exception.__cause__)

    def test_concurrent_calls_have_unique_requests_and_storage(self) -> None:
        """Inspect zero, multipage and encrypted PDFs in separate live jobs."""
        from concurrent.futures import ThreadPoolExecutor
        from threading import Lock
        from payer_policy import inspection_worker as worker
        from payer_policy import _inspection_protocol as protocol
        from payer_policy.document_inspection import inspect_saved_pdf
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        publish = protocol.publish
        requests = []
        lock = Lock()

        def record(path: Path, request: dict[str, object]) -> None:
            """Record parent identities while preserving actual publication."""
            with lock:
                requests.append((path.parent, request["request_id"]))
            publish(path, request)

        with TemporaryDirectory(prefix="concurrent é ") as directory:
            roots, expected, before = [], [], []
            for index, (pages, encrypted) in enumerate(
                    ((0, False), (3, False), (2, True))):
                root = Path(directory) / str(index)
                root.mkdir()
                save_fixture(root, pdf_with_pages(pages, encrypted=encrypted))
                roots.append(root)
                expected.append(inspect_saved_pdf(root, RETRIEVAL_ID))
                before.append({p: p.read_bytes() for p in root.rglob("*")
                               if p.is_file()})
            with patch.object(protocol, "publish", record):
                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(
                        worker.inspect_saved_pdf_in_worker, root, RETRIEVAL_ID,
                    ) for root in roots]
                    results = [future.result(timeout=15) for future in futures]
            self.assertEqual(results, expected)
            self.assertEqual(len(requests), 3)
            self.assertEqual(len({path for path, _ in requests}), 3)
            self.assertEqual(len({key for _, key in requests}), 3)
            for path, key in requests:
                self.assertFalse(path.exists())
                self.assertRegex(key, r"^[0-9a-f]{32}$")
            for snapshot in before:
                self.assertEqual(snapshot, {
                    p: p.read_bytes() for p in snapshot})

    def test_copied_unicode_runtime_checkout_and_poisoned_environment(
        self,
    ) -> None:
        """Use Unicode/space paths without trusting PATH, cwd or PYTHONPATH."""
        import json
        import os
        import shutil
        import subprocess
        import pypdf
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        from payer_policy.document_inspection import inspect_saved_pdf
        from dataclasses import asdict

        base = Path(sys.base_prefix).resolve()
        source = Path(__file__).absolute().parent.parent
        with TemporaryDirectory(prefix="copied runtime é ") as directory:
            folder = Path(directory)
            runtime = folder / "Python space ü"
            checkout = folder / "Source space é"
            runtime.mkdir()
            checkout.mkdir()
            ignored = shutil.ignore_patterns("__pycache__", "site-packages")
            for name in ("Lib", "DLLs"):
                shutil.copytree(base / name, runtime / name, ignore=ignored)
            for pattern in ("python.exe", "*.dll"):
                for path in base.glob(pattern):
                    shutil.copy2(path, runtime / path.name)
            packages = runtime / "Lib" / "site-packages"
            shutil.copytree(Path(pypdf.__file__).parent, packages / "pypdf",
                            ignore=ignored)
            shutil.copytree(source / "payer_policy", checkout / "payer_policy",
                            ignore=ignored)
            shutil.copy2(source / "requirements.txt", checkout)
            fixture = checkout / "tests" / "worker_fixtures"
            fixture.mkdir(parents=True)
            shutil.copy2(source / "tests" / "worker_fixtures"
                         / "runtime_probe.py", fixture)
            storage = folder / "Storage space ñ"
            storage.mkdir()
            save_fixture(storage, pdf_with_pages(2))
            expected = asdict(inspect_saved_pdf(storage, RETRIEVAL_ID))
            poison = folder / "unrelated cwd"
            poison.mkdir()
            for name in ("pypdf.py", "sitecustomize.py", "usercustomize.py"):
                (poison / name).write_text(
                    "raise RuntimeError('poison imported')", encoding="utf-8")
            (packages / "poison.pth").write_text(
                "import sys; raise RuntimeError('pth executed')",
                encoding="utf-8")
            environment = dict(os.environ, PYTHONPATH=str(poison),
                               PYTHONHOME=str(poison), PATH=str(poison))
            process = subprocess.run(
                [str(runtime / "python.exe"), "-I", "-S", "-B",
                 str(fixture / "runtime_probe.py"), str(storage),
                 RETRIEVAL_ID],
                cwd=poison, env=environment, capture_output=True,
                text=True, timeout=30,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(process.stdout), expected)
            self.assertFalse(list(checkout.rglob("__pycache__")))

    def test_saved_pdf_is_parsed_only_in_child(self) -> None:
        """Match original facts and leave original/receipt bytes unchanged."""
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        from payer_policy.document_inspection import inspect_saved_pdf
        from payer_policy.inspection_worker import inspect_saved_pdf_in_worker

        with TemporaryDirectory(prefix="worker unicode é ") as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(2))
            original = root / "records" / RETRIEVAL_ID / "original.bin"
            receipt = original.with_name("receipt.json")
            before = original.read_bytes(), receipt.read_bytes()
            expected = inspect_saved_pdf(root, RETRIEVAL_ID)
            with (patch("payer_policy.document_inspection.PdfReader",
                        side_effect=AssertionError("parent parsed PDF")),
                  patch("payer_policy.document_inspection."
                        "load_saved_candidate",
                        side_effect=AssertionError("parent read snapshot"))):
                result = inspect_saved_pdf_in_worker(root, RETRIEVAL_ID)
            self.assertEqual(result, expected)
            self.assertEqual((original.read_bytes(), receipt.read_bytes()),
                             before)


class SupervisorFailureTests(unittest.TestCase):
    """Inject local failures at real supervisor boundaries."""

    def test_real_timeout_and_crash_allow_later_success(self) -> None:
        """Kill a sleeping child, reject a crash, then inspect normally."""
        from payer_policy import inspection_worker as worker
        from payer_policy._windows_job import Job
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )

        launch = Job.launch
        jobs = []
        fixture = Path(__file__).parent / "worker_fixtures"

        def substitute(job: Job, interpreter: Path, script: Path,
                       arguments: list[str]) -> None:
            """Launch only the fixed fixture and retain cleanup evidence."""
            jobs.append(job)
            launch(job, interpreter, fixture / name, arguments)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(1))
            for name, code in (("sleep_worker.py", "timeout"),
                               ("crash_worker.py", "crash")):
                with self.subTest(code=code):
                    with patch.object(Job, "launch", substitute):
                        with self.assertRaises(
                                worker.WorkerInspectionError) as caught:
                            worker.inspect_saved_pdf_in_worker(
                                root, RETRIEVAL_ID,
                                limits=worker.InspectionLimits(0.2))
                    self.assertEqual(caught.exception.code, code)
                    self.assertTrue(jobs[-1].closed)
                    self.assertEqual(jobs[-1].active_after_cleanup, 0)
            self.assertEqual(worker.inspect_saved_pdf_in_worker(
                root, RETRIEVAL_ID).page_count, 1)

    def test_invalid_output_and_real_io_are_distinct(self) -> None:
        """Reject bad output while preserving real IO causes."""
        from payer_policy import inspection_worker as worker
        from payer_policy import _inspection_protocol as protocol
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        failures = ((protocol.ProtocolError("missing"), "invalid_result"),
                    (PermissionError("read denied"), "ipc_error"))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(1))
            for failure, code in failures:
                with self.subTest(code=code):
                    with patch.object(protocol, "read_result",
                                      side_effect=failure):
                        with self.assertRaises(
                                worker.WorkerInspectionError) as caught:
                            worker.inspect_saved_pdf_in_worker(
                                root, RETRIEVAL_ID)
                    self.assertEqual(caught.exception.code, code)
                    self.assertIs(caught.exception.__cause__, failure)
            failure = OSError("write denied")
            with patch.object(protocol, "publish", side_effect=failure):
                with self.assertRaises(worker.WorkerInspectionError) as got:
                    worker.inspect_saved_pdf_in_worker(root, RETRIEVAL_ID)
                self.assertEqual(got.exception.code, "ipc_error")
                self.assertIs(got.exception.__cause__, failure)

    def test_cleanup_failure_never_returns_success(self) -> None:
        """Native and temporary cleanup errors override success with causes."""
        from payer_policy import inspection_worker as worker
        from payer_policy._windows_job import CleanupError, Job
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )

        real_close = Job._close

        def failed_close(job: Job, handles: list[int]) -> None:
            """Close real handles, then simulate a reported close failure."""
            real_close(job, handles)
            raise CleanupError("simulated close report")

        real_cleanup = TemporaryDirectory.cleanup

        def failed_cleanup(temporary: TemporaryDirectory) -> None:
            """Remove real files, then simulate an OS cleanup failure."""
            real_cleanup(temporary)
            raise OSError("simulated remove report")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(1))
            for target, attribute, replacement in (
                    (Job, "_close", failed_close),
                    (TemporaryDirectory, "cleanup", failed_cleanup)):
                with self.subTest(attribute=attribute):
                    with patch.object(target, attribute, replacement):
                        with self.assertRaises(
                                worker.WorkerInspectionError) as got:
                            worker.inspect_saved_pdf_in_worker(
                                root, RETRIEVAL_ID)
                    self.assertEqual(got.exception.code, "cleanup_error")
                    self.assertIsInstance(got.exception.__cause__, OSError)

    def test_interrupts_survive_cleanup_failures(self) -> None:
        """Clean actual children before re-raising stops if removal fails."""
        from payer_policy import inspection_worker as worker
        from payer_policy._windows_job import Job
        cleanup = TemporaryDirectory.cleanup
        jobs = []
        failure: BaseException = KeyboardInterrupt()

        def stop(job: Job, seconds: float) -> int:
            """Interrupt after creation so native shutdown must still run."""
            jobs.append(job)
            raise failure

        def remove(temporary: TemporaryDirectory) -> None:
            """Remove the directory before injecting a cleanup report."""
            cleanup(temporary)
            raise OSError("simulated remove failure")

        with TemporaryDirectory() as directory:
            for failure in (KeyboardInterrupt(), SystemExit(3), MemoryError()):
                with self.subTest(failure=type(failure)):
                    with (patch.object(Job, "wait", stop),
                          patch.object(TemporaryDirectory, "cleanup", remove)):
                        with self.assertRaises(type(failure)) as got:
                            worker.inspect_saved_pdf_in_worker(
                                Path(directory), "a" * 32)
                    self.assertIs(got.exception, failure)
                    self.assertTrue(got.exception.__notes__)
                    self.assertTrue(jobs[-1].closed)
                    self.assertEqual(jobs[-1].active_after_cleanup, 0)

    def test_runtime_and_temporary_creation_failures(self) -> None:
        """Normalize OS discovery/setup errors, not local memory failures."""
        from payer_policy import inspection_worker as worker

        failure = OSError("synthetic filesystem failure")
        with patch.object(Path, "resolve", side_effect=failure):
            with self.assertRaises(worker.WorkerInspectionError) as got:
                worker._runtime()
            self.assertEqual(got.exception.code, "unsupported_runtime")
            self.assertIs(got.exception.__cause__, failure)
        with TemporaryDirectory() as directory:
            with patch.object(worker, "TemporaryDirectory",
                              side_effect=failure):
                with self.assertRaises(worker.WorkerInspectionError) as got:
                    worker.inspect_saved_pdf_in_worker(
                        Path(directory), "a" * 32)
                self.assertEqual(got.exception.code, "setup_error")
                self.assertIs(got.exception.__cause__, failure)
            for target in ("_runtime", "TemporaryDirectory"):
                memory = MemoryError("local, not a child report")
                with patch.object(worker, target, side_effect=memory):
                    with self.assertRaises(MemoryError) as got:
                        worker.inspect_saved_pdf_in_worker(
                            Path(directory), "a" * 32)
                    self.assertIs(got.exception, memory)

    def test_real_result_files_must_match_this_request(self) -> None:
        """Reject missing, corrupt, wrong-ID and unrelated on-disk results."""
        import json
        from payer_policy import inspection_worker as worker
        from payer_policy import _inspection_protocol as protocol
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        read = protocol.read_result
        folders = []

        def corrupt(path: Path, request_id: str,
                    retrieval_id: str) -> dict[str, object]:
            """Alter the actual result after process cleanup, then validate."""
            folders.append(path.parent)
            if damage == "missing":
                path.unlink()
            elif damage == "malformed":
                path.write_bytes(b"not JSON")
            elif damage == "unrelated":
                path.write_bytes(b'{"status": "ok", "probe": true}')
            elif damage == "oversized":
                path.write_bytes(b" " * 65_537)
            else:
                message = json.loads(path.read_text())
                message[damage] = "f" * 32
                path.write_text(json.dumps(message), encoding="utf-8")
            return read(path, request_id, retrieval_id)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(1))
            for damage in ("missing", "malformed", "unrelated", "oversized",
                           "request_id", "retrieval_id"):
                with self.subTest(damage=damage):
                    with patch.object(protocol, "read_result", corrupt):
                        with self.assertRaises(
                                worker.WorkerInspectionError) as got:
                            worker.inspect_saved_pdf_in_worker(
                                root, RETRIEVAL_ID)
                    self.assertEqual(got.exception.code, "invalid_result")
            self.assertTrue(all(not path.exists() for path in folders))

    def test_request_encoding_failure_is_ipc_error(self) -> None:
        """An oversized outbound message cannot leak a protocol exception."""
        from payer_policy import inspection_worker as worker
        from payer_policy import _inspection_protocol as protocol

        failure = protocol.ProtocolError("oversized message")
        with TemporaryDirectory() as directory:
            with patch.object(protocol, "publish", side_effect=failure):
                with self.assertRaises(worker.WorkerInspectionError) as got:
                    worker.inspect_saved_pdf_in_worker(
                        Path(directory), "a" * 32)
                self.assertEqual(got.exception.code, "ipc_error")
                self.assertIs(got.exception.__cause__, failure)

    def test_root_io_and_native_wait_errors_have_stable_codes(self) -> None:
        """Classify root IO as input failure and native wait IO as IPC."""
        from payer_policy import inspection_worker as worker
        from payer_policy._windows_job import Job

        with TemporaryDirectory() as directory:
            root = Path(directory)
            for target, attribute, code in (
                    (worker, "_check_root", "input_error"),
                    (Job, "wait", "ipc_error")):
                with self.subTest(code=code):
                    failure = OSError("simulated IO")
                    with patch.object(target, attribute, side_effect=failure):
                        with self.assertRaises(
                                worker.WorkerInspectionError) as got:
                            worker.inspect_saved_pdf_in_worker(root, "a" * 32)
                    self.assertEqual(got.exception.code, code)
                    self.assertIs(got.exception.__cause__, failure)

    def test_setup_failure_is_classified_without_retry(self) -> None:
        """Keep the OS cause and never fall back to an uncontained child."""
        from payer_policy import inspection_worker as worker
        failure = OSError("synthetic setup failure")
        with TemporaryDirectory() as directory:
            with patch("payer_policy._windows_job.Job.launch",
                       side_effect=failure) as launch:
                with self.assertRaises(worker.WorkerInspectionError) as got:
                    worker.inspect_saved_pdf_in_worker(
                        Path(directory), "a" * 32)
                self.assertEqual(got.exception.code, "setup_error")
                self.assertIs(got.exception.__cause__, failure)
                launch.assert_called_once()


class ChildBoundaryTests(unittest.TestCase):
    """Simulate defined failures, not real parser memory exhaustion."""

    def test_unexpected_parser_value_error_escapes_unchanged(self) -> None:
        """Keep unknown parser bugs out of the input-error report.

        Exercise ../payer_policy/document_inspection.py and its real loader.
        Only the parser failure is simulated.
        """
        from payer_policy._inspection_child import inspect_request
        from payer_policy.document_inspection import inspect_saved_pdf
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_fixture(root, pdf_with_pages(1))
            request = {"root": str(root), "retrieval_id": RETRIEVAL_ID,
                       "request_id": "a" * 32, "max_bytes": 10_000_000}
            failure = ValueError("unexpected parser failure")
            with patch("payer_policy.document_inspection.PdfReader",
                       side_effect=failure):
                with self.assertRaises(ValueError) as original:
                    inspect_saved_pdf(root, RETRIEVAL_ID)
                self.assertIs(original.exception, failure)
                with self.assertRaises(ValueError) as child:
                    inspect_request(request)
                self.assertIs(child.exception, failure)

    def test_missing_root_is_input_error_before_inspection(self) -> None:
        """Reject a vanished root before the inspector can read bytes.

        Reuse the path-only check in ../payer_policy/document_storage.py.
        """
        from payer_policy._inspection_child import inspect_request

        with TemporaryDirectory() as directory:
            request = {"root": str(Path(directory) / "missing"),
                       "retrieval_id": "b" * 32, "request_id": "a" * 32,
                       "max_bytes": 1}
            target = "payer_policy.document_inspection.inspect_saved_pdf"
            with patch(target) as inspector:
                result = inspect_request(request)
                self.assertEqual(result["status"], "input_error")
                self.assertIsNone(result["facts"])
                inspector.assert_not_called()

    def test_only_defined_inspection_failures_are_serialized(self) -> None:
        """Return no facts or exception text; unknown errors still escape."""
        from payer_policy._inspection_child import inspect_request
        from payer_policy.document_inspection import PdfInspectionError
        from payer_policy.document_storage import StorageIntegrityError

        request = {"root": str(Path.cwd()), "retrieval_id": "b" * 32,
                   "request_id": "a" * 32, "max_bytes": 1}
        target = "payer_policy.document_inspection.inspect_saved_pdf"
        for failure, code in (
                (PdfInspectionError("private"), "parser_error"),
                (StorageIntegrityError("private"), "storage_error"),
                (MemoryError("private"), "memory_error")):
            with self.subTest(code=code), patch(target, side_effect=failure):
                result = inspect_request(request)
                self.assertEqual(result["status"], code)
                self.assertIsNone(result["facts"])
                self.assertNotIn("private", str(result))
        for failure in (TypeError(), ValueError(), RuntimeError(), OSError(),
                        KeyboardInterrupt(), SystemExit()):
            with self.subTest(failure=type(failure)):
                with patch(target, side_effect=failure):
                    with self.assertRaises(type(failure)) as caught:
                        inspect_request(request)
                    self.assertIs(caught.exception, failure)


class WorkerValidationTests(unittest.TestCase):
    """Reject caller mistakes before making files or native objects."""

    def test_unsupported_layouts_and_parser_pin_fail_before_setup(
        self,
    ) -> None:
        """Do not search PATH, loosen bounds, or run an unverified parser."""
        from payer_policy import inspection_worker as worker
        from contextlib import ExitStack

        cases = ((worker.sys, "frozen", True),
                 (worker.sys, "platform", "linux"),
                 (worker.sys, "version_info", (3, 10)),
                 (worker.sys, "executable", "C:/unapproved/python.exe"),
                 (worker.pypdf, "__version__", "0.0.0"),
                 (worker.pypdf, "__file__", "C:/unapproved/pypdf/__init__.py"))
        for target, attribute, value in cases:
            with self.subTest(attribute=attribute), ExitStack() as stack:
                stack.enter_context(patch.object(target, attribute, value,
                                                 create=True))
                temporary = stack.enter_context(patch.object(
                    worker, "TemporaryDirectory"))
                with self.assertRaises(worker.WorkerInspectionError) as got:
                    worker._runtime()
                self.assertEqual(got.exception.code, "unsupported_runtime")
                temporary.assert_not_called()
        interpreter, _ = worker._runtime()
        self.assertEqual(interpreter,
                         Path(sys.base_prefix).resolve() / "python.exe")

    def test_imports_do_not_bind_windows_library(self) -> None:
        """Simulate non-Windows imports without binding WinDLL."""
        from payer_policy import inspection_worker, _inspection_protocol
        from payer_policy import _windows_job

        with (patch.object(sys, "platform", "linux"),
              patch("ctypes.WinDLL", side_effect=AssertionError("bound"))):
            for module in (inspection_worker, _inspection_protocol,
                           _windows_job):
                importlib.reload(module)
        # Restore class identities for any other tests holding references.
        for module in (inspection_worker, _inspection_protocol, _windows_job):
            importlib.reload(module)

    def test_error_codes_are_allowlisted(self) -> None:
        """Reject misspelled or arbitrary categories at the public boundary."""
        from payer_policy.inspection_worker import WorkerInspectionError

        codes = ("unsupported_runtime", "setup_error", "input_error",
                 "storage_error", "parser_error", "memory_error", "timeout",
                 "crash", "invalid_result", "ipc_error", "cleanup_error")
        for code in codes:
            self.assertEqual(WorkerInspectionError(code).code, code)
        for code in ("unknown", "", None, [], True):
            with self.subTest(code=code):
                with self.assertRaises((TypeError, ValueError)):
                    WorkerInspectionError(code)

    def test_storage_junction_is_not_canonicalized(self) -> None:
        """Reject a real junction and descendants before temporary setup."""
        import _winapi
        from payer_policy import inspection_worker as worker

        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir()
            (target / "nested").mkdir()
            junction = root / "junction"
            _winapi.CreateJunction(str(target), str(junction))
            try:
                with patch.object(worker, "TemporaryDirectory") as temporary:
                    for path in (junction, junction / "nested"):
                        with self.subTest(path=path):
                            with self.assertRaises(ValueError):
                                worker.inspect_saved_pdf_in_worker(
                                    path, "a" * 32)
                    temporary.assert_not_called()
            finally:
                junction.rmdir()

    def test_invalid_inputs_have_no_launch_side_effects(self) -> None:
        """Validate exact budgets, identifiers and roots before setup."""
        try:
            worker = importlib.import_module("payer_policy.inspection_worker")
        except ModuleNotFoundError:
            self.fail("contained inspection API is missing")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [
                ({"root": str(root)}, TypeError),
                ({"root": Path("relative")}, ValueError),
                ({"root": Path("//server/share/root")}, ValueError),
                ({"root": root / "missing"}, ValueError),
                ({"retrieval_id": 123}, TypeError),
                ({"retrieval_id": "A" * 32}, ValueError),
                ({"retrieval_id": "a" * 31}, ValueError),
                ({"max_bytes": True}, ValueError),
                ({"max_bytes": 10_000_001}, ValueError),
                ({"max_bytes": 0}, ValueError),
                ({"max_bytes": 1.0}, ValueError),
                ({"limits": object()}, TypeError),
            ]
            for value in (True, 0, -1, 61, float("nan"), float("inf")):
                cases.append(({"limits": worker.InspectionLimits(
                    timeout_seconds=value)}, ValueError))
            for value in (True, 0, 16_777_215, 268_435_457, 16_777_216.0):
                cases.append(({"limits": worker.InspectionLimits(
                    memory_bytes=value)}, ValueError))
            with (patch("tempfile.mkdtemp") as temporary,
                  patch("ctypes.WinDLL", create=True) as native):
                for changes, error in cases:
                    with self.subTest(changes=changes):
                        arguments = {"root": root, "retrieval_id": "a" * 32}
                        arguments.update(changes)
                        with self.assertRaises(error):
                            worker.inspect_saved_pdf_in_worker(**arguments)
                temporary.assert_not_called()
                native.assert_not_called()


if __name__ == "__main__":
    unittest.main()

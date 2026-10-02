"""Real Windows process tests for the disposable job-worker experiment."""
import sys
import unittest


@unittest.skipUnless(sys.platform == "win32", "Windows job experiment")
class WorkerTests(unittest.TestCase):
    """Check actual containment, rather than mocked process success."""

    def test_limits_are_rejected_before_launch(self) -> None:
        """Bad budgets cannot start even a hello worker."""
        from dataclasses import replace
        from unittest.mock import patch
        import win_job

        cases = ({"timeout_seconds": 0}, {"timeout_seconds": float("nan")},
                 {"timeout_seconds": True}, {"memory_bytes": 0},
                 {"memory_bytes": True}, {"job_memory_bytes": -1},
                 {"result_bytes": 65_537}, {"active_limit": 3},
                 {"cleanup_seconds": float("inf")})
        for change in cases:
            with self.subTest(change=change):
                with patch.object(
                        win_job, "open_job",
                        side_effect=AssertionError("setup reached")) as job:
                    with self.assertRaises((TypeError, ValueError)):
                        win_job.run_probe(
                            "hello", limits=replace(win_job.WorkerLimits(),
                                                    **change))
                    job.assert_not_called()

    def test_committed_memory_limit_refuses_large_allocation(self) -> None:
        """A small allocation works; a ceiling-sized one is refused."""
        from win_job import WorkerLimits, run_probe

        for process_mib, job_mib, accepted in (
                (64, 256, False), (128, 256, True), (128, 64, False)):
            with self.subTest(process=process_mib, job=job_mib):
                result = run_probe("allocate", limits=WorkerLimits(
                    memory_bytes=process_mib * 1024 * 1024,
                    job_memory_bytes=job_mib * 1024 * 1024))
                self.assertEqual(result.status, "ok")
                self.assertTrue(result.facts["small_allocation"])
                self.assertEqual(result.facts["large_allocation"], accepted)
                if not accepted:
                    self.assertGreater(result.facts["allocation_error"], 0)
                self.assertEqual(result.active_after_cleanup, 0)

    def test_invalid_worker_results_are_rejected(self) -> None:
        """Bad bounded output never becomes a successful PDF fact."""
        from win_job import run_probe

        for mode in ("bad_json", "oversized", "missing", "wrong_version",
                     "wrong_id", "bad_types", "duplicate_key"):
            with self.subTest(mode=mode):
                result = run_probe(mode)
                self.assertEqual(result.status, "invalid_result")
                self.assertEqual(result.facts, {})
                self.assertEqual(result.active_after_cleanup, 0)

    def test_inspection_uses_real_verified_snapshots(self) -> None:
        """Inspect real verified snapshots without altering stored files."""
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from win_job import run_probe

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
        from test_document_inspection import (
            RETRIEVAL_ID, pdf_with_pages, save_fixture,
        )
        cases = ((pdf_with_pages(2), "ok", 2, False),
                 (pdf_with_pages(0), "ok", 0, False),
                 (pdf_with_pages(1, encrypted=True), "ok", None, True),
                 (b"%PDF-", "parser_error", None, None))
        for body, expected, pages, encrypted in cases:
            with self.subTest(expected=expected, pages=pages):
                with TemporaryDirectory() as folder:
                    root = Path(folder)
                    save_fixture(root, body)
                    original = root / "records" / RETRIEVAL_ID / "original.bin"
                    receipt = original.with_name("receipt.json")
                    before = (original.read_bytes(), receipt.read_bytes())
                    result = run_probe("inspect", root=root,
                                       retrieval_id=RETRIEVAL_ID)
                    self.assertEqual(result.status, expected)
                    self.assertEqual(result.exit_code, 0)
                    if expected == "ok":
                        self.assertEqual(result.facts["page_count"], pages)
                        self.assertEqual(result.facts["is_encrypted"],
                                         encrypted)
                        self.assertEqual(result.facts["sha256"],
                                         json.loads(before[1])["sha256"])
                    self.assertEqual(
                        (original.read_bytes(), receipt.read_bytes()), before)
                    original.write_bytes(b"%PDF-changed")
                    damaged = (original.read_bytes(), receipt.read_bytes())
                    result = run_probe("inspect", root=root,
                                       retrieval_id=RETRIEVAL_ID)
                    self.assertEqual(result.status, "storage_error")
                    self.assertEqual(
                        (original.read_bytes(), receipt.read_bytes()), damaged)

    def test_response_facts_have_exact_types(self) -> None:
        """Reject wrong fact shapes, types, counts, and file fingerprints."""
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from win_job import read_result

        retrieval_id = "a" * 32
        good = {"sha256": "b" * 64, "page_count": 1, "is_encrypted": False}
        cases = ({**good, "page_count": True},
                 {**good, "page_count": -1}, {**good, "sha256": "B" * 64},
                 {**good, "is_encrypted": 0},
                 {**good, "is_encrypted": True},
                 {**good, "extra": 1}, {"invented": 1})
        with TemporaryDirectory() as folder:
            output = Path(folder) / "out.json"
            for facts in cases:
                with self.subTest(facts=facts):
                    output.write_text(json.dumps({"schema_version": 1,
                        "retrieval_id": retrieval_id, "status": "ok",
                        "facts": facts}), encoding="utf-8")
                    self.assertEqual(read_result(
                        output, 65_536, retrieval_id, "inspect")["status"],
                        "invalid_result")

    def test_response_facts_belong_to_selected_workload(self) -> None:
        """Simulated JSON faults cannot borrow another workload's facts.

        Exercise win_job.py#read_result, not native containment evidence.
        """
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from win_job import read_result

        retrieval_id = "a" * 32
        shapes = {
            "inspect": {"sha256": "b" * 64, "page_count": 1,
                        "is_encrypted": False},
            "allocate": {"small_allocation": True,
                         "large_allocation": False, "allocation_error": 8},
            "process_limit": {"third_refused": True, "creation_error": 5},
            "spawn_child": {"worker_pid": 101, "child_pid": 102},
            "hello": {},
        }
        empty_modes = ("hang", "crash", "bad_json", "oversized", "missing",
                       "wrong_version", "wrong_id", "bad_types",
                       "duplicate_key")
        shapes.update({mode: {} for mode in empty_modes})
        errors = {"parser_error": "PdfInspectionError",
                  "storage_error": "StorageIntegrityError",
                  "input_error": "invalid_storage_input",
                  "memory_error": "worker_reported_MemoryError"}
        with TemporaryDirectory() as folder:
            output = Path(folder) / "out.json"
            for mode, expected in shapes.items():
                responses = [("ok", facts) for facts in shapes.values()]
                responses += [(status, {"error_code": code})
                              for status, code in errors.items()]
                for status, facts in responses:
                    with self.subTest(mode=mode, status=status, facts=facts):
                        output.write_text(json.dumps({"schema_version": 1,
                            "retrieval_id": retrieval_id, "status": status,
                            "facts": facts}), encoding="utf-8")
                        accepted = (facts == expected if status == "ok"
                                    else mode == "inspect")
                        wanted = status if accepted else "invalid_result"
                        self.assertEqual(read_result(
                            output, 65_536, retrieval_id, mode)["status"],
                            wanted)

    def test_response_booleans_agree_with_native_error_codes(self) -> None:
        """Simulated JSON contradictions are rejected in both directions.

        Exercise win_job.py#read_result, not resource-limit enforcement.
        """
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from win_job import read_result

        retrieval_id = "a" * 32
        with TemporaryDirectory() as folder:
            output = Path(folder) / "out.json"
            for flag in (False, True):
                for error in (0, 8):
                    cases = (
                        ("allocate", {"small_allocation": True,
                            "large_allocation": flag,
                            "allocation_error": error}, flag == (error == 0)),
                        ("process_limit", {"third_refused": flag,
                            "creation_error": error}, flag == (error != 0)),
                    )
                    for mode, facts, valid in cases:
                        with self.subTest(mode=mode, facts=facts):
                            output.write_text(json.dumps({"schema_version": 1,
                                "retrieval_id": retrieval_id, "status": "ok",
                                "facts": facts}), encoding="utf-8")
                            wanted = "ok" if valid else "invalid_result"
                            self.assertEqual(read_result(
                                output, 65_536, retrieval_id, mode)["status"],
                                wanted)

    def test_response_lifecycle_pids_are_distinct(self) -> None:
        """Simulated JSON cannot identify a worker as its own child.

        Exercise win_job.py#read_result, not process membership evidence.
        """
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from win_job import read_result

        retrieval_id = "a" * 32
        with TemporaryDirectory() as folder:
            output = Path(folder) / "out.json"
            output.write_text(json.dumps({"schema_version": 1,
                "retrieval_id": retrieval_id, "status": "ok",
                "facts": {"worker_pid": 101, "child_pid": 101}}),
                encoding="utf-8")
            self.assertEqual(read_result(
                output, 65_536, retrieval_id, "spawn_child")["status"],
                "invalid_result")

    def test_lifecycle_facts_match_launched_native_members(self) -> None:
        """Simulated response faults cannot copy unconfirmed lifecycle IDs.

        Keep win_job.py#run_probe's real launch, membership, and cleanup.
        """
        from unittest.mock import patch
        import win_job

        reader = win_job.read_result
        for fault in ("wrong_worker", "absent_child"):
            with self.subTest(fault=fault):
                def faulty_response(*args: object) -> dict[str, object]:
                    """Corrupt only JSON facts returned by the real reader."""
                    payload = reader(*args)
                    if payload["status"] == "ok":
                        facts = payload["facts"]
                        if fault == "wrong_worker":
                            facts["worker_pid"], facts["child_pid"] = (
                                facts["child_pid"], facts["worker_pid"])
                        else:
                            facts["child_pid"] = 0xFFFFFFFF
                    return payload

                with patch.object(win_job, "read_result", faulty_response):
                    result = win_job.run_probe("spawn_child", limits=
                        win_job.WorkerLimits(timeout_seconds=2))
                self.assertEqual(result.status, "timeout")
                self.assertEqual(result.facts, {})
                self.assertIn(result.pid, result.terminated_members)
                self.assertEqual(result.active_after_cleanup, 0)

    def test_supervisor_rejects_unconfirmed_lifecycle_evidence(self) -> None:
        """Simulated response faults cannot publish ready evidence.

        Keep win_job.py#abandon_probe's real native membership and cleanup;
        intercept only the deliberate os._exit to protect the test process.
        """
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        import win_job

        reader = win_job.read_result
        for fault in ("wrong_worker", "absent_child"):
            with self.subTest(fault=fault), TemporaryDirectory() as folder:
                directory = Path(folder)
                (directory / "ack").write_bytes(b"")

                def faulty_response(*args: object) -> dict[str, object]:
                    """Corrupt only JSON facts returned by the real reader."""
                    payload = reader(*args)
                    if payload["status"] == "ok":
                        facts = payload["facts"]
                        if fault == "wrong_worker":
                            facts["worker_pid"], facts["child_pid"] = (
                                facts["child_pid"], facts["worker_pid"])
                        else:
                            facts["child_pid"] = 0xFFFFFFFF
                    return payload

                with (patch.object(win_job, "read_result", faulty_response),
                      patch("os._exit", side_effect=RuntimeError(
                          "simulated supervisor exit"))):
                    with self.assertRaises(RuntimeError):
                        win_job.abandon_probe(directory)
                self.assertFalse((directory / "ready.json").exists())
                self.assertFalse((directory / "ready.tmp").exists())

    def test_native_setup_failures_never_launch_a_fallback(self) -> None:
        """Simulated native setup failures close the job and remain errors."""
        from unittest.mock import patch
        import win_job

        for operation in ("SetJob", "UpdateAttrs", "CreateProcess"):
            with self.subTest(operation=operation):
                with (patch.object(win_job, operation, return_value=0),
                      patch.object(win_job, "Close",
                                   wraps=win_job.Close) as close):
                    with self.assertRaises(OSError):
                        win_job.run_probe("hello")
                    self.assertEqual(close.call_count, 1)

    def test_small_result_budget_rejects_even_valid_output(self) -> None:
        """A real hello response cannot exceed a smaller parent read budget."""
        from win_job import WorkerLimits, run_probe

        result = run_probe("hello", limits=WorkerLimits(result_bytes=32))
        self.assertEqual(result.status, "invalid_result")
        self.assertEqual(result.active_after_cleanup, 0)

    def test_process_ceiling_refuses_an_extra_ordinary_child(self) -> None:
        """A two-process job allows one ordinary child, not two children."""
        from win_job import run_probe

        result = run_probe("process_limit")
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.facts["third_refused"])
        self.assertGreater(result.facts["creation_error"], 0)
        self.assertEqual(result.active_after_cleanup, 0)

    def test_close_failure_still_attempts_other_owned_handles(self) -> None:
        """Simulate one close failure; still attempt all remaining handles."""
        from unittest.mock import call, patch
        import win_job

        with patch.object(win_job, "Close", side_effect=[0, 1]) as close:
            with self.assertRaises(OSError):
                win_job.close_handles((77, 88))
            self.assertEqual(close.call_args_list, [call(77), call(88)])

    def test_crash_is_not_a_successful_result(self) -> None:
        """An abrupt worker exit stays distinct from timeout and memory."""
        from win_job import run_probe

        result = run_probe("crash")
        self.assertEqual(result.status, "crash")
        self.assertEqual(result.exit_code, 37)
        self.assertEqual(result.facts, {})
        self.assertEqual(result.active_after_cleanup, 0)

    def test_deadline_stops_the_worker_and_its_descendant(self) -> None:
        """Hold handles to both real job members and confirm both exit."""
        from win_job import WorkerLimits, run_probe

        result = run_probe("spawn_child", limits=WorkerLimits(
            timeout_seconds=2))
        self.assertEqual(result.status, "timeout")
        self.assertIn(result.pid, result.terminated_members)
        self.assertIn(result.facts["child_pid"], result.terminated_members)
        self.assertEqual(result.active_after_cleanup, 0)

    def test_supervisor_exit_closes_job_and_stops_members(self) -> None:
        """Open member handles before the disposable supervisor exits."""
        import json
        import math
        import subprocess
        import time
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import win_job

        with TemporaryDirectory() as folder:
            directory = Path(folder)
            supervisor = subprocess.Popen(
                [sys.executable, "-B", win_job.__file__, "--abandon", folder],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            handles = []
            try:
                ready = directory / "ready.json"
                deadline = time.monotonic() + 10
                while not ready.exists() and supervisor.poll() is None:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.01)
                self.assertTrue(ready.exists(), "supervisor probe missing")
                pids = json.loads(ready.read_text("utf-8"))["pids"]
                self.assertGreaterEqual(len(pids), 2)
                for pid in pids:
                    handle = win_job.OpenProcess(0x100000 | 0x1000, False, pid)
                    win_job.check(handle)
                    handles.append(handle)
                    self.assertEqual(win_job.Wait(handle, 0), 258)
                (directory / "ack").write_bytes(b"")
                self.assertEqual(supervisor.wait(timeout=10), 23)
                deadline = time.monotonic() + 5
                for handle in handles:
                    remaining = max(0, deadline - time.monotonic())
                    self.assertEqual(win_job.Wait(
                        handle, math.ceil(remaining * 1000)), 0)
            finally:
                if supervisor.poll() is None:
                    supervisor.terminate()
                    supervisor.wait(timeout=5)
                for handle in handles:
                    win_job.check(win_job.Close(handle))

    def test_deadline_stops_a_hung_worker(self) -> None:
        """A real hang times out, exits, and does not poison the next run."""
        from win_job import WorkerLimits, run_probe

        result = run_probe("hang", limits=WorkerLimits(timeout_seconds=0.5))
        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.exit_code, 124)
        self.assertEqual(result.active_after_cleanup, 0)
        self.assertLess(result.elapsed_seconds, 5.5)
        self.assertEqual(run_probe("hello").status, "ok")

    def test_launch_is_contained_before_work(self) -> None:
        """A real worker belongs to the configured job and exits cleanly."""
        try:
            from win_job import WorkerLimits, run_probe
        except ModuleNotFoundError as exc:
            if exc.name != "win_job":
                raise
            self.fail("contained worker runner is not implemented")
        limits = WorkerLimits()
        result = run_probe("hello", limits=limits)
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.in_job)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.configured["process_memory"],
                         limits.memory_bytes)
        self.assertEqual(result.configured["job_memory"],
                         limits.job_memory_bytes)
        self.assertEqual(result.configured["active_limit"], 2)
        self.assertTrue(result.configured["kill_on_close"])
        self.assertEqual(result.active_after_cleanup, 0)


if __name__ == "__main__":
    unittest.main()

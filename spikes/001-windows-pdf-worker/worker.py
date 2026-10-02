"""Fixed disposable workloads; launched only by the experiment's job runner."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def allocation_probe(size: int) -> dict[str, object]:
    """Request real committed memory, then release it even on failure.

    VirtualAlloc returns NULL on failure; VirtualFree with MEM_RELEASE
    releases the whole reservation. The fixture requests 4 MiB and 64 MiB
    under externally enforced limits, not arbitrary machine-sized blocks:
    README.md#native-references (VirtualAlloc and VirtualFree).
    """
    import ctypes as C
    from ctypes import wintypes as W
    from win_job import api, check

    allocate = api("VirtualAlloc", [C.c_void_p, C.c_size_t, W.DWORD, W.DWORD],
                   C.c_void_p)
    free = api("VirtualFree", [C.c_void_p, C.c_size_t, W.DWORD], W.BOOL)
    small = allocate(None, 4 * 1024 * 1024, 0x3000, 4)
    large = None
    try:
        large = allocate(None, size, 0x3000, 4)
        error = C.get_last_error() if not large else 0
        return {"small_allocation": bool(small),
                "large_allocation": bool(large), "allocation_error": error}
    finally:
        for address in (large, small):
            if address:
                check(free(address, 0, 0x8000))


def inspect_probe(arguments: dict[str, object]
                  ) -> tuple[str, dict[str, object]]:
    """Reuse the existing verifier/inspector inside the resource-limited job.

    inspect_saved_pdf verifies storage before parsing the returned bytes:
    ../../payer_policy/document_inspection.py
    Only error classifications cross JSON, not native exception objects.
    """
    from dataclasses import asdict

    sys.path.insert(0, str(arguments["site_packages"]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from payer_policy.document_inspection import (
        PdfInspectionError, inspect_saved_pdf,
    )
    from payer_policy.document_storage import StorageIntegrityError

    try:
        facts = asdict(inspect_saved_pdf(
            Path(str(arguments["root"])), str(arguments["retrieval_id"]),
            max_bytes=arguments["max_bytes"]))
        facts.pop("retrieval_id")
        return "ok", facts
    except StorageIntegrityError:
        return "storage_error", {"error_code": "StorageIntegrityError"}
    except PdfInspectionError:
        return "parser_error", {"error_code": "PdfInspectionError"}
    except (TypeError, ValueError):
        return "input_error", {"error_code": "invalid_storage_input"}
    except MemoryError:
        return "memory_error", {"error_code": "worker_reported_MemoryError"}


def worker_main(request: Path, output: Path) -> None:
    """Run a fixed probe; write observations rather than log streams."""
    arguments = json.loads(request.read_text("utf-8"))
    mode = arguments["mode"]
    facts, status = {}, "ok"
    if mode == "crash":
        os._exit(37)
    if mode == "hang":
        time.sleep(60)
    elif mode == "allocate":
        facts = allocation_probe(64 * 1024 * 1024)
    elif mode == "inspect":
        status, facts = inspect_probe(arguments)
    elif mode == "process_limit":
        command = [sys.executable, "-c", "import time; time.sleep(60)"]
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, close_fds=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            extra = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, close_fds=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as exc:
            facts = {"third_refused": True, "creation_error": exc.winerror}
        else:
            facts = {"third_refused": False, "creation_error": 0}
            extra.terminate()
            extra.wait(timeout=5)
        finally:
            child.terminate()
            child.wait(timeout=5)
    elif mode == "spawn_child":
        child_request = output.with_name("child-request.json")
        child_request.write_text(json.dumps({"mode": "hang",
                                 "retrieval_id": arguments["retrieval_id"]}),
                                 encoding="utf-8")
        child = subprocess.Popen(
            [sys.executable, "-B", __file__, str(child_request),
             str(output.with_name("child-output.json"))],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        facts = {"worker_pid": os.getpid(), "child_pid": child.pid}
    elif mode not in {"hello", "bad_json", "oversized", "missing",
                      "wrong_version", "wrong_id", "bad_types",
                      "duplicate_key"}:
        raise ValueError("unknown probe mode")
    payload = {"schema_version": 1, "status": status,
               "retrieval_id": arguments["retrieval_id"], "facts": facts}
    if mode == "missing":
        return
    if mode in {"bad_json", "oversized", "duplicate_key"}:
        data = {"bad_json": b"{", "oversized": b" " * 65_537,
                "duplicate_key": json.dumps(payload).replace(
                    '"schema_version": 1',
                    '"schema_version": 1, "schema_version": 1').encode()}
        output.write_bytes(data[mode])
        return
    if mode == "wrong_version":
        payload["schema_version"] = 2
    elif mode == "wrong_id":
        payload["retrieval_id"] = "f" * 32
    elif mode == "bad_types":
        payload["schema_version"] = True
    output.write_text(json.dumps(payload), encoding="utf-8")
    if mode == "spawn_child":
        time.sleep(60)


if __name__ == "__main__":
    worker_main(Path(sys.argv[1]), Path(sys.argv[2]))

"""Fixed child entry point: inspect one saved PDF, never run probe modes.

The supervisor launches the base CPython with -I -S -B. Only this source
checkout and the verified environment package folder are added to sys.path;
no site initialization, .pth, PYTHONPATH or user-site code is run:
https://docs.python.org/3.11/using/cmdline.html
The original inspector alone loads stored bytes and invokes pypdf:
../payer_policy/document_inspection.py
"""
import sys
from pathlib import Path
from typing import Any

# Under -I the script directory is absent. This fixed, trusted checkout is
# derived from the entry script itself, never supplied by a request.
_APP = Path(__file__).absolute().parent.parent
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from payer_policy import _inspection_protocol as protocol


def bootstrap(runtime: dict[str, Any]) -> None:
    """Add only the approved package directory and verify the parser pin."""
    packages = Path(runtime["packages"])
    if (Path(runtime["base_prefix"]) != Path(sys.base_prefix)
            or packages.name != "site-packages"
            or packages.parent.name != "Lib"
            or not packages.is_dir()):
        raise RuntimeError("unsupported child runtime")
    sys.path.append(str(packages))
    import pypdf
    if (pypdf.__version__ != "6.19.0"
            or Path(pypdf.__file__).parent != packages / "pypdf"):
        raise RuntimeError("unexpected parser installation")


def inspect_request(request: dict[str, Any]) -> dict[str, Any]:
    """Return facts or a defined inspector/storage/input failure code.

    Recheck the root with document_storage.py before reading any bytes.
    _inspection_protocol.py already checks the identifier and byte limit.
    Only that preflight may label plain errors as bad input. The unchanged
    document_inspection.py owns loading and parsing; later unknown failures
    escape, including a root race after preflight. Never guess from messages.
    """
    from payer_policy.document_inspection import (
        PdfInspectionError, inspect_saved_pdf,
    )
    from payer_policy.document_storage import (
        StorageIntegrityError, _check_root,
    )

    result: dict[str, Any] = {
        "schema_version": 1, "operation": "inspect",
        "request_id": request["request_id"],
        "retrieval_id": request["retrieval_id"], "status": "ok",
        "facts": None,
    }
    try:
        try:
            root = Path(request["root"])
            _check_root(root)
        except (TypeError, ValueError, OSError):
            result["status"] = "input_error"
            return result
        inspected = inspect_saved_pdf(root, request["retrieval_id"],
                                      max_bytes=request["max_bytes"])
    except PdfInspectionError:
        result["status"] = "parser_error"
    except StorageIntegrityError:
        result["status"] = "storage_error"
    except MemoryError:
        result["status"] = "memory_error"
    else:
        result["facts"] = {"sha256": inspected.sha256,
                           "is_encrypted": inspected.is_encrypted,
                           "page_count": inspected.page_count}
    return result


def main() -> int:
    """Read one request and publish a complete result; bugs exit nonzero."""
    if len(sys.argv) != 3:
        return 2
    request = protocol.read_request(Path(sys.argv[1]))
    bootstrap(request["runtime"])
    result = inspect_request(request)
    protocol.publish(Path(sys.argv[2]), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

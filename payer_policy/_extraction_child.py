"""Fixed isolated extraction child; no password, fallback or probe modes.

Trusted bootstrap is shared unchanged with _inspection_child.py.
Only the fixed source directory is inserted before request processing.
"""
import sys
from pathlib import Path

_APP = Path(__file__).absolute().parent.parent
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from payer_policy import _extraction_protocol as protocol
from payer_policy._inspection_child import bootstrap
from payer_policy.text_extraction import (
    ExtractionError, _extract_saved_pages, limits_from_facts,
)


def extract_request(request: dict) -> dict:
    """Extract a complete batch; unknown parser bugs escape to a crash."""
    from payer_policy.document_storage import (
        StorageIntegrityError, _check_root,
    )

    try:
        try:
            root = Path(request["root"])
            _check_root(root)
            limits = limits_from_facts(request["limits"])
        except (TypeError, ValueError, OSError):
            return protocol.result_message(request, status="input_error")
        result = _extract_saved_pages(
            root, request["retrieval_id"], tuple(request["requested_pages"]),
            limits,
        )
        message = protocol.result_message(request, result)
        try:
            protocol.encode(message, limits.max_result_bytes)
        except protocol.ProtocolError:
            return protocol.result_message(request, status="output_limit")
        return message
    except ExtractionError as exc:
        return protocol.result_message(request, status=exc.code)
    except StorageIntegrityError:
        return protocol.result_message(request, status="storage_error")
    except MemoryError:
        return protocol.result_message(request, status="memory_error")


def main() -> int:
    """Read one bounded request and publish one complete response."""
    if len(sys.argv) != 3:
        return 2
    request = protocol.read_request(Path(sys.argv[1]))
    bootstrap(request["runtime"])
    result = extract_request(request)
    protocol.publish(Path(sys.argv[2]), result, protocol.RESULT_BYTES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

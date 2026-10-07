"""Strict JSON message tests; these do not demonstrate native containment."""
import copy
import importlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REQUEST_ID = "a" * 32
RETRIEVAL_ID = "b" * 32


def result_message() -> dict[str, object]:
    """Return a complete synthetic successful inspection message."""
    return {
        "schema_version": 1, "operation": "inspect",
        "request_id": REQUEST_ID, "retrieval_id": RETRIEVAL_ID,
        "status": "ok", "facts": {
            "sha256": "c" * 64, "is_encrypted": False, "page_count": 0,
        },
    }


class ProtocolTests(unittest.TestCase):
    """Only fixed, correctly bound inspection facts cross the boundary."""

    def test_result_schema_is_exact_and_bounded(self) -> None:
        """Reject ambiguous JSON and results from another request."""
        try:
            protocol = importlib.import_module(
                "payer_policy._inspection_protocol")
        except ModuleNotFoundError:
            self.fail("inspection protocol is missing")
        good = result_message()
        invalid = [b"", b"{}", b"[]", b"null", b"x" * 65_537,
                   b'{"x":1,"x":2}', b'{"x":NaN}',
                   b"[" * 1200 + b"0" + b"]" * 1200, b"\xff"]
        for key, values in {
            "schema_version": [True, 2, 1.0],
            "operation": ["hello", None],
            "request_id": ["d" * 32, "A" * 32],
            "retrieval_id": ["d" * 32, 0],
            "status": ["memory", "crash", None],
            "facts": [{}, None, {"unrelated": True}],
        }.items():
            for value in values:
                item = copy.deepcopy(good)
                item[key] = value
                invalid.append(json.dumps(item).encode())
        for key, values in {
            "sha256": ["C" * 64, "c" * 63, None],
            "is_encrypted": [0, 1, None],
            "page_count": [True, -1, 1.0, None],
        }.items():
            for value in values:
                item = copy.deepcopy(good)
                item["facts"][key] = value
                invalid.append(json.dumps(item).encode())
        extra = copy.deepcopy(good)
        extra["extra"] = 1
        invalid.append(json.dumps(extra).encode())
        with TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            for raw in invalid:
                with self.subTest(raw=raw[:90]):
                    output.write_bytes(raw)
                    with self.assertRaises(protocol.ProtocolError):
                        protocol.read_result(output, REQUEST_ID, RETRIEVAL_ID)
            output.write_text(json.dumps(good), encoding="utf-8")
            self.assertEqual(protocol.read_result(
                output, REQUEST_ID, RETRIEVAL_ID), good)
            for code in ("input_error", "storage_error", "parser_error",
                         "memory_error"):
                item = dict(good, status=code, facts=None)
                output.write_text(json.dumps(item), encoding="utf-8")
                self.assertEqual(protocol.read_result(
                    output, REQUEST_ID, RETRIEVAL_ID), item)
            encrypted = copy.deepcopy(good)
            encrypted["facts"].update(is_encrypted=True, page_count=None)
            output.write_text(json.dumps(encrypted), encoding="utf-8")
            self.assertEqual(protocol.read_result(
                output, REQUEST_ID, RETRIEVAL_ID), encrypted)


if __name__ == "__main__":
    unittest.main()

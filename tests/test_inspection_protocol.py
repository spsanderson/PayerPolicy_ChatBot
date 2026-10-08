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

    def test_request_schema_and_atomic_publication(self) -> None:
        """Only fixed inspect requests with bounded budgets are published."""
        from payer_policy import _inspection_protocol as protocol

        self.assertTrue(hasattr(protocol, "read_request"),
                        "request validation is missing")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            request = {
                "schema_version": 1, "operation": "inspect",
                "request_id": REQUEST_ID, "retrieval_id": RETRIEVAL_ID,
                "root": str(root), "max_bytes": 10_000_000,
                "runtime": {"base_prefix": str(root),
                            "packages": str(root)},
            }
            target = root / "request.json"
            protocol.publish(target, request)
            self.assertEqual(protocol.read_request(target), request)
            self.assertFalse(target.with_suffix(".tmp").exists())
            cases = [("extra", 0), ("operation", "probe"),
                     ("max_bytes", True), ("max_bytes", 10_000_001),
                     ("max_bytes", 0), ("root", "relative"),
                     ("root", 5), ("runtime", {}),
                     ("runtime", {"packages": "relative",
                                  "base_prefix": str(root)}),
                     ("schema_version", True),
                     ("request_id", "A" * 32)]
            for key, value in cases:
                with self.subTest(key=key, value=value):
                    bad = dict(request)
                    bad[key] = value
                    target.write_text(json.dumps(bad), encoding="utf-8")
                    with self.assertRaises(protocol.ProtocolError):
                        protocol.read_request(target)
            with self.assertRaises(protocol.ProtocolError):
                protocol.publish(target, {"huge": "x" * 65_536})
            self.assertFalse(target.with_suffix(".tmp").exists())

    def test_exact_read_budget_and_io_distinction(self) -> None:
        """Read limit plus one, reject missing messages, preserve real IO."""
        from io import BytesIO
        from unittest.mock import patch
        from payer_policy import _inspection_protocol as protocol

        raw = b'{}' + b' ' * (protocol.MESSAGE_BYTES - 2)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "message.json"
            path.write_bytes(raw)
            self.assertEqual(protocol.read_message(path), {})
            path.write_bytes(raw + b" ")
            with self.assertRaises(protocol.ProtocolError):
                protocol.read_message(path)
            path.unlink()
            with self.assertRaises(protocol.ProtocolError):
                protocol.read_message(path)
            with patch.object(Path, "open", side_effect=PermissionError()):
                with self.assertRaises(PermissionError):
                    protocol.read_message(path)
            stream = BytesIO(raw)
            with (patch.object(Path, "open", return_value=stream),
                  patch.object(stream, "read", wraps=stream.read) as read):
                self.assertEqual(protocol.read_message(path), {})
                read.assert_called_once_with(65_537)

    def test_contradictory_errors_and_nested_json_are_rejected(self) -> None:
        """No facts on errors, no encrypted count, duplicates or extra keys."""
        from payer_policy import _inspection_protocol as protocol

        invalid = []
        for code in protocol.CHILD_ERRORS:
            invalid.append(json.dumps(dict(result_message(), status=code)))
        message = result_message()
        message["facts"]["is_encrypted"] = True
        invalid.append(json.dumps(message))
        message = result_message()
        message["facts"]["extra"] = None
        invalid.append(json.dumps(message))
        text = json.dumps(result_message())
        invalid.extend((text.replace('"page_count": 0',
                                     '"page_count": 0, "page_count": 1'),
                        text + "{}", text.replace("0}", "Infinity}"),
                        text.replace("0}", "-Infinity}")))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            for raw in invalid:
                with self.subTest(raw=raw):
                    path.write_text(raw, encoding="utf-8")
                    with self.assertRaises(protocol.ProtocolError):
                        protocol.read_result(path, REQUEST_ID, RETRIEVAL_ID)

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

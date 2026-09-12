"""Offline behavior tests for registry parsing and loading."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from payer_policy import source_registry as registry
from test_source_registry import valid_source


class RegistryLoadingTests(unittest.TestCase):
    """Exercise complete registries rather than isolated definitions."""

    def test_checked_in_registry(self) -> None:
        """Load the reviewed reference entry without contacting its URL."""
        root = Path(__file__).resolve().parents[1]
        path = root / "sources" / "registry.json"
        self.assertTrue(path.is_file(), "reviewed registry missing")
        sources = registry.load_source_registry(path)
        self.assertEqual(list(sources), ["anthem-empire-plan-overview"])
        source = sources["anthem-empire-plan-overview"]
        self.assertEqual(source["url"], "https://www.anthembluecross.com/nys")
        self.assertEqual(source["applicability_status"], "reference")
        self.assertTrue((root / source["review_note"]).is_file())

    def test_load_local_utf8_and_file_errors(self) -> None:
        """Load real files; never mask missing, unreadable, or bad data."""
        loader = getattr(registry, "load_source_registry", None)
        self.assertTrue(callable(loader), "loader missing")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            with self.assertRaises(FileNotFoundError):
                loader(path)
            with self.assertRaises(OSError):
                loader(Path(directory))
            source = valid_source()
            source["name"] = "Reference café"
            path.write_text(json.dumps({"schema_version": 1, "sources": [
                source]}, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(loader(path), {source["source_id"]: source})
            path.write_bytes(b"\xff")
            with self.assertRaises(UnicodeDecodeError):
                loader(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(registry.RegistryValidationError):
                loader(path)

    def test_duplicate_keys_and_non_json_numbers(self) -> None:
        """Do not silently overwrite keys or accept nonstandard numbers."""
        for text, message in (
            ('{"schema_version":1,"sources":[],"sources":[]}',
             "duplicate JSON key"),
            ('{"schema_version":1,"sources":[],"extra":{"a":1,"a":2}}',
             "duplicate JSON key"),
            ('{"schema_version":1,"sources":[],"extra":NaN}', "JSON"),
            ('{"schema_version":1,"sources":[],"extra":Infinity}', "JSON"),
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(
                    registry.RegistryValidationError, message
                ):
                    registry.parse_source_registry(text)

    def test_invalid_registry_is_rejected(self) -> None:
        """Reject bad structure and entries rather than partial results."""
        error = getattr(registry, "RegistryValidationError", None)
        self.assertTrue(isinstance(error, type), "registry error missing")
        invalid_source = valid_source()
        invalid_source["url"] = "https://example.org/" + chr(0x7F)
        cases = [
            ("{", "JSON"),
            ("[]", "object"),
            ('{"sources":[]}', "schema_version"),
            ('{"schema_version":true,"sources":[]}', "schema_version"),
            ('{"schema_version":1.0,"sources":[]}', "schema_version"),
            ('{"schema_version":2,"sources":[]}', "schema_version"),
            ('{"schema_version":1}', "sources"),
            ('{"schema_version":1,"sources":{}}', "sources"),
            (json.dumps({"schema_version": 1, "sources": [
                valid_source(), invalid_source]}), r"sources\[1\].*url"),
            (json.dumps({"schema_version": 1, "sources": [
                valid_source(), valid_source()]}), "duplicate source_id"),
            ('{"schema_version":1,"sources":[null]}', r"sources\[0\]"),
        ]
        for text, message in cases:
            with self.subTest(text=text):
                with self.assertRaisesRegex(error, message):
                    registry.parse_source_registry(text)

    def test_parse_preserves_values_and_order(self) -> None:
        """Index valid entries by exact IDs without changing metadata."""
        parser = getattr(registry, "parse_source_registry", None)
        self.assertTrue(callable(parser), "parser missing")
        first = valid_source()
        first["source_id"] = "z-first"
        second = valid_source()
        second["source_id"] = "a-second"
        second["name"] = "Reference café"
        entries = [first, second]
        text = json.dumps({"schema_version": 1, "sources": entries})
        result = parser(text)
        self.assertEqual(list(result), ["z-first", "a-second"])
        self.assertEqual(list(result.values()), entries)
        self.assertEqual(parser('{"schema_version":1,"sources":[]}'), {})

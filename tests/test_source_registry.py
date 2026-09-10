"""Behavior tests for source definitions; all URLs are offline fixtures."""
import unittest

from payer_policy import source_registry


def valid_source() -> dict:
    """Return a fresh, explicitly unverified source fixture."""
    return {
        "source_id": "example-source",
        "name": "Example source",
        "url": "https://example.org/policies?year=2026",
        "publisher": "Example publisher",
        "category": "plan_resources",
        "plan": "Empire Plan",
        "program": "Hospital Program",
        "applicability_status": "unknown",
        "evidence_url": "",
        "access_restrictions": "Not yet reviewed",
    }


class SourceDefinitionTests(unittest.TestCase):
    """Validate metadata without inferring authority or mutating inputs."""

    def test_required_metadata(self) -> None:
        """Reject missing, blank, and incorrectly typed required fields."""
        for field in valid_source():
            for bad in (None, 123, [], "   "):
                source = valid_source()
                source[field] = bad
                with self.subTest(field=field, bad=bad):
                    errors = source_registry.validate_source_definition(source)
                    self.assertTrue(any(field in error for error in errors))
            source = valid_source()
            del source[field]
            errors = source_registry.validate_source_definition(source)
            self.assertTrue(any(field in error for error in errors))

    def test_non_mapping_input(self) -> None:
        """Report invalid containers rather than crashing."""
        for source in (None, [], "source", 42):
            self.assertEqual(
                source_registry.validate_source_definition(source),
                ["source: expected a mapping"],
            )

    def test_identifier_status_and_evidence(self) -> None:
        """Reject malformed IDs, unsupported statuses, and bare claims."""
        for field, value in (
            ("source_id", " bad-id "),
            ("source_id", "Bad ID"),
            ("applicability_status", "official"),
            ("applicability_status", "confirmed_applicable"),
        ):
            source = valid_source()
            source[field] = value
            with self.subTest(field=field, value=value):
                self.assertTrue(
                    source_registry.validate_source_definition(source)
                )
        for status in (
            "unknown", "needs_review", "reference", "outside_scope",
            "confirmed_applicable",
        ):
            source = valid_source()
            source["applicability_status"] = status
            source["evidence_url"] = "https://example.org/evidence"
            self.assertEqual(
                source_registry.validate_source_definition(source), []
            )

    def test_url_structure(self) -> None:
        """Reject unsafe schemes and malformed URLs without network access."""
        invalid = (
            "example.org/path", "ftp://example.org/a", "file:///C:/policy",
            "https:///missing-host", "https://user:secret@example.org",
            " https://example.org", "https://example.org/a b",
            "https://example.org/\npath", "https://example.org:99999",
            "https://example.org:abc", "https://[broken",
            "https://exa_mple.org", "https://example.org/%zz",
            "https://example.org\\evil", "https://-example.org",
        )
        for field in ("url", "evidence_url"):
            for value in invalid:
                source = valid_source()
                source[field] = value
                original = source.copy()
                with self.subTest(field=field, value=value):
                    errors = source_registry.validate_source_definition(source)
                    self.assertTrue(any(field in error for error in errors))
                    self.assertEqual(source, original)
        for value in (
            "http://example.org/path", "https://EXAMPLE.org:443/a%20b?q=1#s",
        ):
            source = valid_source()
            source["url"] = value
            self.assertEqual(
                source_registry.validate_source_definition(source), []
            )
            self.assertEqual(source["url"], value)

    def test_rejects_del_and_c1_controls(self) -> None:
        """Reject every DEL/C1 code point in both URL fields unchanged."""
        for field in ("url", "evidence_url"):
            for codepoint in range(0x7F, 0xA0):
                source = valid_source()
                source[field] = "https://example.org/" + chr(codepoint)
                original = source.copy()
                with self.subTest(field=field, codepoint=hex(codepoint)):
                    errors = source_registry.validate_source_definition(source)
                    self.assertTrue(any(field in error for error in errors))
                    self.assertEqual(source, original)

    def test_valid_unknown_source_is_unchanged(self) -> None:
        """Accept explicit uncertainty without upgrading applicability."""
        source = valid_source()
        original = source.copy()
        function = getattr(source_registry, "validate_source_definition", None)
        self.assertTrue(callable(function), "validator missing")
        self.assertEqual(function(source), [])
        self.assertEqual(source, original)

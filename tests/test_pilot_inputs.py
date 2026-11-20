"""Tests for the bounded pilot input contract."""
import unittest


def approved_manifest() -> list[dict[str, object]]:
    """Return one complete metadata record for every approved pilot page."""
    pages = {
        "pa-certificate-2025": (1, 56, 110, 165),
        "pa-amendments-2025": (1, 6, 11, 16),
        "pa-empire-plan-report-2026": (1, 5, 8, 12),
    }
    records = []
    for source_id, numbers in pages.items():
        for page_number in numbers:
            records.append({
                "source_id": source_id,
                "retrieval_id": "a" * 32,
                "sha256": "b" * 64,
                "page_number": page_number,
                "raw_artifact": (
                    f"page-text/{source_id}/page-{page_number:03d}.txt"
                ),
                "selected_artifact": "raw",
                "quality_verdict": "usable",
            })
    return records


class PilotPageRecordTests(unittest.TestCase):
    """Validate reviewed-page metadata before chunking."""

    def test_accepts_one_approved_page_record(self) -> None:
        """Accept a complete record for an approved physical page."""
        from payer_policy.pilot_inputs import validate_pilot_page_record

        record = {
            "source_id": "pa-certificate-2025",
            "retrieval_id": "a" * 32,
            "sha256": "b" * 64,
            "page_number": 1,
            "raw_artifact": "page-text/pa-certificate-2025/page-001.txt",
            "selected_artifact": "raw",
            "quality_verdict": "usable",
        }
        self.assertEqual(validate_pilot_page_record(record), [])

    def test_rejects_unapproved_physical_page(self) -> None:
        """Reject a valid-looking page outside the reviewed sample."""
        from payer_policy.pilot_inputs import validate_pilot_page_record

        record = {
            "source_id": "pa-certificate-2025",
            "retrieval_id": "a" * 32,
            "sha256": "b" * 64,
            "page_number": 2,
            "raw_artifact": "page-text/pa-certificate-2025/page-002.txt",
            "selected_artifact": "raw",
            "quality_verdict": "usable",
        }
        errors = validate_pilot_page_record(record)
        self.assertTrue(any("page_number" in error for error in errors))

    def test_rejects_boolean_page_number(self) -> None:
        """Reject bool because it must not act as integer page one."""
        from payer_policy.pilot_inputs import validate_pilot_page_record

        record = {
            "source_id": "pa-certificate-2025",
            "retrieval_id": "a" * 32,
            "sha256": "b" * 64,
            "page_number": True,
            "raw_artifact": "page-text/pa-certificate-2025/page-001.txt",
            "selected_artifact": "raw",
            "quality_verdict": "usable",
        }
        errors = validate_pilot_page_record(record)
        self.assertTrue(any("page_number" in error for error in errors))


class PilotManifestTests(unittest.TestCase):
    """Validate the complete reviewed-page collection before chunking."""

    def test_accepts_complete_approved_manifest(self) -> None:
        """Accept exactly the twelve reviewed physical pages."""
        from payer_policy.pilot_inputs import validate_pilot_manifest

        records = approved_manifest()
        self.assertEqual(validate_pilot_manifest(records), [])

    def test_rejects_missing_approved_page(self) -> None:
        """Reject a partial manifest and name the missing page."""
        from payer_policy.pilot_inputs import validate_pilot_manifest

        records = approved_manifest()
        records.pop()
        errors = validate_pilot_manifest(records)
        self.assertTrue(any("pa-empire-plan-report-2026" in error
                            and "page 12" in error for error in errors))

    def test_rejects_duplicate_page_identity(self) -> None:
        """Reject two records for the same document and physical page."""
        from payer_policy.pilot_inputs import validate_pilot_manifest

        records = approved_manifest()
        records.append(records[0].copy())
        errors = validate_pilot_manifest(records)
        self.assertTrue(any("duplicate" in error and "page 1" in error
                            for error in errors))

    def test_rejects_unexpected_page_identity(self) -> None:
        """Reject a page outside the approved twelve-page set."""
        from payer_policy.pilot_inputs import validate_pilot_manifest

        records = approved_manifest()
        records[-1]["page_number"] = 13
        errors = validate_pilot_manifest(records)
        self.assertTrue(any("records[11]" in error for error in errors))

    def test_prefixes_nested_record_errors(self) -> None:
        """Identify which manifest record contains invalid metadata."""
        from payer_policy.pilot_inputs import validate_pilot_manifest

        records = approved_manifest()
        records[4]["retrieval_id"] = "bad"
        errors = validate_pilot_manifest(records)
        self.assertTrue(any("records[4]" in error and "retrieval_id" in error
                            for error in errors))

    def test_rejects_non_sequence_manifest(self) -> None:
        """Reject mappings and null instead of iterating ambiguous values."""
        from payer_policy.pilot_inputs import validate_pilot_manifest

        for value in ({}, None, "records"):
            with self.subTest(value=value):
                errors = validate_pilot_manifest(value)
                self.assertTrue(any("records" in error for error in errors))

    def test_does_not_mutate_manifest(self) -> None:
        """Leave order and record values unchanged after validation."""
        from copy import deepcopy
        from payer_policy.pilot_inputs import validate_pilot_manifest

        records = approved_manifest()
        original = deepcopy(records)
        validate_pilot_manifest(records)
        self.assertEqual(records, original)


if __name__ == "__main__":
    unittest.main()

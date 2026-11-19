"""Tests for the bounded pilot input contract."""
import unittest


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


if __name__ == "__main__":
    unittest.main()

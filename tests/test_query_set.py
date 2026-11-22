"""Tests for the bounded human-reviewed pilot query contract."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


APPROVED_CHUNKS = {
    "chunk-a": ("source-a", 1),
    "chunk-b": ("source-b", 2),
}


def answerable_record(**overrides):
    """Return one valid draft answerable query record."""
    record = {
        "query_id": "q-coverage-001",
        "category": "coverage",
        "text": "What services are covered?",
        "answerable": True,
        "expected_chunk_ids": ["chunk-a"],
        "expected_source_id": "source-a",
        "expected_page_number": 1,
        "review_status": "draft",
        "review_note": "Candidate for human review.",
    }
    record.update(overrides)
    return record


class QuerySetValidationTests(unittest.TestCase):
    """Validate query metadata before retrieval evaluation."""

    def test_accepts_valid_draft_and_converts_to_evaluation_query(
        self,
    ) -> None:
        """Preserve a valid query as immutable evaluation input."""
        from payer_policy.query_set import (
            ValidatedPilotQuery,
            as_evaluation_queries,
            validate_query_set,
        )

        validated = validate_query_set(
            [answerable_record()], APPROVED_CHUNKS
        )
        self.assertEqual(len(validated), 1)
        self.assertIsInstance(validated[0], ValidatedPilotQuery)
        evaluation = as_evaluation_queries(validated)
        self.assertEqual(evaluation[0].expected_chunk_ids, ("chunk-a",))
        self.assertEqual(evaluation[0].expected_source_id, "source-a")

    def test_accepts_valid_no_evidence_query(self) -> None:
        """Allow a deliberate absence query without a citation target."""
        from payer_policy.query_set import validate_query_set

        record = {
            "query_id": "q-no-evidence-001",
            "category": "no_evidence",
            "text": "Which page contains the dental implant benefit?",
            "answerable": False,
            "expected_chunk_ids": [],
            "expected_source_id": None,
            "expected_page_number": None,
            "review_status": "draft",
            "review_note": "Not present in the selected pages.",
        }
        validated = validate_query_set([record], APPROVED_CHUNKS)
        self.assertFalse(validated[0].answerable)

    def test_rejects_duplicate_ids_and_unknown_chunks(self) -> None:
        """Reject duplicate identities and citations outside the artifact."""
        from payer_policy.query_set import validate_query_set

        duplicate = answerable_record()
        duplicate["text"] = "Second question."
        with self.assertRaises(ValueError):
            validate_query_set(
                [answerable_record(), duplicate], APPROVED_CHUNKS
            )

        unknown = answerable_record(expected_chunk_ids=["missing"])
        with self.assertRaises(ValueError):
            validate_query_set([unknown], APPROVED_CHUNKS)

    def test_rejects_source_page_mismatch(self) -> None:
        """Require expected citation identity to match every expected chunk."""
        from payer_policy.query_set import validate_query_set

        record = answerable_record(expected_source_id="source-b")
        with self.assertRaises(ValueError):
            validate_query_set([record], APPROVED_CHUNKS)

    def test_rejects_inconsistent_answerability(self) -> None:
        """Keep answerable and no-evidence contracts mutually exclusive."""
        from payer_policy.query_set import validate_query_set

        missing_target = answerable_record(expected_chunk_ids=[])
        with self.assertRaises(ValueError):
            validate_query_set([missing_target], APPROVED_CHUNKS)

        cited_absence = answerable_record(
            category="no_evidence",
            answerable=False,
            expected_chunk_ids=["chunk-a"],
            expected_source_id=None,
            expected_page_number=None,
        )
        with self.assertRaises(ValueError):
            validate_query_set([cited_absence], APPROVED_CHUNKS)

    def test_rejects_invalid_text_category_and_status(self) -> None:
        """Reject malformed text and unsupported review metadata."""
        from payer_policy.query_set import validate_query_set

        for field, value in (
            ("text", ""),
            ("category", "unrecognized"),
            ("review_status", "approved_by_ai"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    validate_query_set(
                        [answerable_record(**{field: value})],
                        APPROVED_CHUNKS,
                    )

    def test_final_gate_requires_human_approval(self) -> None:
        """Prevent draft queries from entering final evaluation."""
        from payer_policy.query_set import validate_query_set

        with self.assertRaises(ValueError):
            validate_query_set(
                [answerable_record()],
                APPROVED_CHUNKS,
                require_human_approval=True,
            )

        approved = answerable_record(review_status="human_approved")
        validated = validate_query_set(
            [approved],
            APPROVED_CHUNKS,
            require_human_approval=True,
        )
        self.assertEqual(validated[0].review_status, "human_approved")

    def test_validation_does_not_mutate_records(self) -> None:
        """Leave caller-owned query dictionaries unchanged."""
        from copy import deepcopy
        from payer_policy.query_set import validate_query_set

        records = [answerable_record()]
        original = deepcopy(records)
        validate_query_set(records, APPROVED_CHUNKS)
        self.assertEqual(records, original)

    def test_loads_file_and_binds_expected_sha256(self) -> None:
        """Reject a query file whose bytes differ from the reviewed digest."""
        from payer_policy.query_set import load_query_set_file

        records = [answerable_record()]
        body = (json.dumps(records, indent=2) + "\n").encode("utf-8")
        expected = hashlib.sha256(body).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queries.json"
            path.write_bytes(body)
            loaded = load_query_set_file(
                path,
                APPROVED_CHUNKS,
                expected_sha256=expected,
            )
            self.assertEqual(loaded[0].query_id, "q-coverage-001")
            path.write_bytes(body + b" ")
            with self.assertRaises(ValueError):
                load_query_set_file(
                    path,
                    APPROVED_CHUNKS,
                    expected_sha256=expected,
                )

    def test_file_loader_enforces_human_approval(self) -> None:
        """Do not load draft queries into the final evaluation path."""
        from payer_policy.query_set import load_query_set_file

        body = (json.dumps([answerable_record()]) + "\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queries.json"
            path.write_bytes(body)
            with self.assertRaises(ValueError):
                load_query_set_file(
                    path,
                    APPROVED_CHUNKS,
                    require_human_approval=True,
                )

    def test_file_loader_rejects_invalid_json_and_relative_paths(self) -> None:
        """Fail closed on unreadable query artifacts and unsafe path inputs."""
        from payer_policy.query_set import load_query_set_file

        with self.assertRaises(ValueError):
            load_query_set_file(
                Path("relative.json"),
                APPROVED_CHUNKS,
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queries.json"
            path.write_bytes(b"not-json")
            with self.assertRaises(ValueError):
                load_query_set_file(path, APPROVED_CHUNKS)


if __name__ == "__main__":
    unittest.main()

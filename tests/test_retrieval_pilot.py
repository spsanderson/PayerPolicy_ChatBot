"""Tests for the deterministic lexical retrieval baseline."""
import unittest


class LexicalRetrievalTests(unittest.TestCase):
    """Rank exact pilot chunks without changing their evidence."""

    @staticmethod
    def chunk(chunk_id: str, page: int, text: str):
        """Build a small immutable chunk fixture."""
        from payer_policy.chunk_packing import PageChunk

        return PageChunk(
            chunk_id=chunk_id,
            source_id="source",
            retrieval_id="a" * 32,
            pdf_sha256="b" * 64,
            raw_text_sha256="c" * 64,
            selected_text_sha256="d" * 64,
            artifact_kind="raw",
            quality_verdict="usable",
            parser_name="pypdf",
            parser_version="6.19.0",
            extraction_mode="text",
            page_number=page,
            ordinal=1,
            start_offset=0,
            end_offset=len(text),
            line_start=1,
            line_end=1,
            text=text,
            word_count=len(text.split()),
            block_kinds=("paragraph",),
        )

    def test_query_returns_exact_chunk_and_stable_order(self) -> None:
        """Return complete chunks with deterministic ranking and ties."""
        from payer_policy.retrieval_pilot import (
            build_lexical_index, retrieve_lexical,
        )

        chunks = (
            self.chunk("b", 2, "hospital deductible and coinsurance"),
            self.chunk("a", 1, "hospital deductible"),
        )
        index = build_lexical_index(chunks)
        first = retrieve_lexical(index, "hospital deductible", limit=2)
        second = retrieve_lexical(index, "hospital deductible", limit=2)
        self.assertEqual(first, second)
        self.assertEqual([hit.chunk.chunk_id for hit in first], ["a", "b"])
        self.assertEqual(first[0].chunk.text, "hospital deductible")
        self.assertGreater(first[0].score, 0)

    def test_absent_evidence_returns_no_hits(self) -> None:
        """Do not invent a citation when no indexed term overlaps."""
        from payer_policy.retrieval_pilot import (
            build_lexical_index, retrieve_lexical,
        )

        index = build_lexical_index((self.chunk("a", 1, "deductible"),))
        self.assertEqual(retrieve_lexical(index, "orthodontia"), ())
        self.assertEqual(retrieve_lexical(index, "   "), ())

    def test_rejects_duplicate_ids_and_invalid_limits(self) -> None:
        """Reject ambiguous indexes and malformed query limits."""
        from payer_policy.retrieval_pilot import (
            build_lexical_index, retrieve_lexical,
        )

        duplicate = self.chunk("a", 1, "deductible")
        with self.assertRaises(ValueError):
            build_lexical_index((duplicate, duplicate))
        index = build_lexical_index((duplicate,))
        with self.assertRaises(ValueError):
            retrieve_lexical(index, "deductible", limit=0)
        with self.assertRaises(TypeError):
            retrieve_lexical(index, 1)  # type: ignore[arg-type]

    def test_index_rejects_non_chunk_values(self) -> None:
        """Reject arbitrary objects rather than guessing their text field."""
        from payer_policy.retrieval_pilot import build_lexical_index

        with self.assertRaises(TypeError):
            build_lexical_index(("text",))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

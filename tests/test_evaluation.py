"""Tests for retrieval evaluation metrics."""
import json
import unittest

try:
    from .test_retrieval_pilot import LexicalRetrievalTests
except ImportError:
    from test_retrieval_pilot import LexicalRetrievalTests


class EvaluationTests(unittest.TestCase):
    """Measure retrieval without generating or judging answers."""

    def test_reports_recall_citation_and_no_evidence(self) -> None:
        """Compute per-query results and declared aggregate metrics."""
        from payer_policy.evaluation import EvaluationQuery, evaluate_queries
        from payer_policy.retrieval_pilot import build_lexical_index

        helper = LexicalRetrievalTests()
        chunks = (
            helper.chunk("a", 1, "hospital deductible"),
            helper.chunk("b", 2, "covered services"),
        )
        index = build_lexical_index(chunks)
        queries = (
            EvaluationQuery(
                "q1", "deductible", ("a",), True, "source", 1
            ),
            EvaluationQuery("q2", "never-present-term", (), False),
        )
        report = evaluate_queries(index, queries)
        self.assertEqual(report.recall_at_1, 1.0)
        self.assertEqual(report.recall_at_3, 1.0)
        self.assertEqual(report.citation_accuracy, 1.0)
        self.assertEqual(report.no_evidence_accuracy, 1.0)
        self.assertEqual(report.results[0].retrieved_chunk_ids, ("a",))

    def test_rejects_inconsistent_query_contracts(self) -> None:
        """Reject duplicate IDs and answerability contradictions."""
        from payer_policy.evaluation import EvaluationQuery, evaluate_queries
        from payer_policy.retrieval_pilot import build_lexical_index

        helper = LexicalRetrievalTests()
        index = build_lexical_index((helper.chunk("a", 1, "text"),))
        cases = (
            (
                EvaluationQuery("q", "text", (), True),
                EvaluationQuery("q", "text", (), False),
            ),
            (EvaluationQuery("q", "text", (), True),),
            (EvaluationQuery("q", "text", ("a",), False),),
        )
        for queries in cases:
            with self.subTest(queries=queries):
                with self.assertRaises(ValueError):
                    evaluate_queries(index, queries)


if __name__ == "__main__":
    unittest.main()

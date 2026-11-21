"""Tests for deterministic page-block segmentation."""
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


class PageBlockSegmentationTests(unittest.TestCase):
    """Segment validated page text without changing its contents."""

    @staticmethod
    def page(text: str):
        """Build validated page metadata around synthetic text."""
        from payer_policy.pilot_inputs import ValidatedPilotPage

        return ValidatedPilotPage(
            source_id="pa-certificate-2025",
            retrieval_id="a" * 32,
            pdf_sha256="b" * 64,
            page_number=1,
            raw_artifact=Path("raw.txt"),
            selected_artifact=Path("raw.txt"),
            raw_text_sha256="c" * 64,
            selected_text_sha256="c" * 64,
            text=text,
            artifact_kind="raw",
            quality_verdict="usable",
        )

    def test_empty_text_returns_no_blocks(self) -> None:
        """Return no blocks for an empty page."""
        from payer_policy.chunking import segment_page_blocks

        self.assertEqual(segment_page_blocks(self.page("")), ())

    def test_single_paragraph_preserves_exact_text(self) -> None:
        """Keep one paragraph as one exact source slice."""
        from payer_policy.chunking import segment_page_blocks

        text = "A paragraph with exact spacing.\nSecond line.\n"
        blocks = segment_page_blocks(self.page(text))
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].text, text)
        self.assertEqual(blocks[0].kind, "paragraph")
        self.assertEqual((blocks[0].start_offset, blocks[0].end_offset),
                         (0, len(text)))

    def test_blank_lines_create_reconstructible_blocks(self) -> None:
        """Split likely sections while retaining separator bytes."""
        from payer_policy.chunking import segment_page_blocks

        text = "SECTION 1\n\nBody line one.\nBody line two.\n\nTail."
        blocks = segment_page_blocks(self.page(text))
        self.assertEqual("".join(block.text for block in blocks), text)
        self.assertEqual([block.kind for block in blocks], [
            "heading", "paragraph", "paragraph",
        ])
        self.assertEqual(blocks[0].text, "SECTION 1\n\n")

    def test_list_items_remain_one_list_block(self) -> None:
        """Keep contiguous bullet items together."""
        from payer_policy.chunking import segment_page_blocks

        text = "- First item\n- Second item\nContinuation."
        blocks = segment_page_blocks(self.page(text))
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].kind, "list")
        self.assertEqual(blocks[0].text, text)

    def test_table_like_rows_are_labeled_conservatively(self) -> None:
        """Recognize repeated pipe-delimited rows as table-like text."""
        from payer_policy.chunking import segment_page_blocks

        text = "Name | Value\n--- | ---\nA | 1"
        blocks = segment_page_blocks(self.page(text))
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].kind, "table")

    def test_whitespace_only_text_is_unknown_and_preserved(self) -> None:
        """Retain nonempty whitespace without claiming a structure."""
        from payer_policy.chunking import segment_page_blocks

        text = " \n\t\n"
        blocks = segment_page_blocks(self.page(text))
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].kind, "unknown")
        self.assertEqual(blocks[0].text, text)
        self.assertIsNotNone(blocks[0].boundary_note)

    def test_blocks_have_increasing_line_and_character_ranges(self) -> None:
        """Expose usable one-based line and zero-based text provenance."""
        from payer_policy.chunking import segment_page_blocks

        text = "Heading\n\nBody.\n\nLast."
        blocks = segment_page_blocks(self.page(text))
        previous_end = 0
        previous_line = 0
        for block in blocks:
            self.assertGreaterEqual(block.start_offset, previous_end)
            self.assertGreater(block.end_offset, block.start_offset)
            self.assertGreater(block.line_start, previous_line)
            self.assertGreaterEqual(block.line_end, block.line_start)
            self.assertEqual(block.text,
                             text[block.start_offset:block.end_offset])
            previous_end = block.end_offset
            previous_line = block.line_end
        self.assertEqual(previous_end, len(text))

    def test_rejects_non_page_input(self) -> None:
        """Reject arbitrary objects instead of guessing their text field."""
        from payer_policy.chunking import segment_page_blocks

        with self.assertRaises(TypeError):
            segment_page_blocks("text")

    def test_blocks_are_immutable(self) -> None:
        """Prevent downstream code from changing block provenance."""
        from payer_policy.chunking import segment_page_blocks

        block = segment_page_blocks(self.page("Text."))[0]
        with self.assertRaises(FrozenInstanceError):
            block.text = "changed"


if __name__ == "__main__":
    unittest.main()

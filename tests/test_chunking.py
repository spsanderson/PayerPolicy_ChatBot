"""Tests for deterministic page-block segmentation."""
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory


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
            parser_name="pypdf",
            parser_version="6.19.0",
            extraction_mode="text",
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


class PageChunkPackingTests(unittest.TestCase):
    """Pack whole page blocks into deterministic provenance-rich chunks."""

    @staticmethod
    def page(text: str):
        """Build validated page metadata around synthetic text."""
        from payer_policy.pilot_inputs import ValidatedPilotPage

        return ValidatedPilotPage(
            source_id="pa-certificate-2025",
            retrieval_id="a" * 32,
            pdf_sha256="b" * 64,
            page_number=56,
            raw_artifact=Path("raw.txt"),
            selected_artifact=Path("raw.txt"),
            raw_text_sha256="c" * 64,
            selected_text_sha256="c" * 64,
            text=text,
            artifact_kind="raw",
            quality_verdict="usable",
            parser_name="pypdf",
            parser_version="6.19.0",
            extraction_mode="text",
        )

    @staticmethod
    def blocks(page):
        """Segment synthetic page text into the packer's input blocks."""
        from payer_policy.chunking import segment_page_blocks

        return segment_page_blocks(page)

    def test_one_block_produces_provenance_complete_chunk(self) -> None:
        """Carry exact text and page identity into one chunk."""
        from payer_policy.chunk_packing import pack_page_blocks

        page = self.page("One short paragraph.")
        chunks = pack_page_blocks(page, self.blocks(page))
        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertEqual(chunk.text, page.text)
        self.assertEqual(chunk.word_count, 3)
        self.assertEqual(chunk.source_id, page.source_id)
        self.assertEqual(chunk.retrieval_id, page.retrieval_id)
        self.assertEqual(chunk.pdf_sha256, page.pdf_sha256)
        self.assertEqual(chunk.raw_text_sha256, page.raw_text_sha256)
        self.assertEqual(
            chunk.selected_text_sha256, page.selected_text_sha256)
        self.assertEqual(chunk.artifact_kind, page.artifact_kind)
        self.assertEqual(chunk.quality_verdict, page.quality_verdict)
        self.assertEqual(chunk.page_number, page.page_number)
        self.assertEqual(chunk.ordinal, 1)
        self.assertEqual(
            chunk.chunk_id,
            f"{page.retrieval_id}:p{page.page_number:04d}:c0001",
        )

    def test_packing_keeps_whole_blocks_and_respects_maximum(self) -> None:
        """Close chunks before adding a block would exceed the maximum."""
        from payer_policy.chunk_packing import pack_page_blocks

        text = "one two three four five\n\n" "six seven eight nine ten"
        page = self.page(text)
        chunks = pack_page_blocks(
            page,
            self.blocks(page),
            target_words=5,
            max_words=7,
        )
        self.assertEqual([chunk.word_count for chunk in chunks], [5, 5])
        self.assertEqual("".join(chunk.text for chunk in chunks), text)
        self.assertEqual([chunk.ordinal for chunk in chunks], [1, 2])

    def test_heading_attaches_to_following_block_when_it_fits(self) -> None:
        """Prefer keeping a heading with the content it introduces."""
        from payer_policy.chunking import PageBlock
        from payer_policy.chunk_packing import pack_page_blocks

        page = self.page("TITLE\n\nBody text.")
        blocks = (
            PageBlock(0, 7, 1, 2, "TITLE\n\n", "heading", "medium"),
            PageBlock(
                7,
                len(page.text),
                3,
                3,
                "Body text.",
                "paragraph",
                "medium",
            ),
        )
        chunks = pack_page_blocks(page, blocks, target_words=1, max_words=5)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].block_kinds, ("heading", "paragraph"))
        self.assertEqual(chunks[0].text, page.text)

    def test_oversized_block_is_preserved_and_marked(self) -> None:
        """Never split one indivisible block just to meet the size limit."""
        from payer_policy.chunking import PageBlock
        from payer_policy.chunk_packing import pack_page_blocks

        text = " ".join(f"word{index}" for index in range(8))
        page = self.page(text)
        blocks = (PageBlock(0, len(text), 1, 1, text, "table", "medium"),)
        chunks = pack_page_blocks(page, blocks, target_words=3, max_words=5)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].word_count, 8)
        self.assertIn("oversized", chunks[0].boundary_note or "")

    def test_rejects_non_reconstructing_blocks(self) -> None:
        """Reject fabricated or overlapping provenance before packing."""
        from payer_policy.chunking import PageBlock
        from payer_policy.chunk_packing import pack_page_blocks

        page = self.page("One two.")
        blocks = (PageBlock(0, 3, 1, 1, "One", "paragraph", "medium"),)
        with self.assertRaises(ValueError):
            pack_page_blocks(page, blocks)

    def test_rejects_invalid_size_settings(self) -> None:
        """Reject zero, boolean, and inverted word-size settings."""
        from payer_policy.chunk_packing import pack_page_blocks

        page = self.page("One two.")
        blocks = self.blocks(page)
        invalid = [(0, 5), (True, 5), (6, 5)]
        for target_words, max_words in invalid:
            with self.subTest(target_words=target_words, max_words=max_words):
                with self.assertRaises(ValueError):
                    pack_page_blocks(
                        page,
                        blocks,
                        target_words=target_words,
                        max_words=max_words,
                    )

    def test_chunks_are_immutable_and_repeatable(self) -> None:
        """Keep chunk facts immutable and stable across repeated runs."""
        from payer_policy.chunk_packing import pack_page_blocks

        page = self.page("One two three.")
        first = pack_page_blocks(page, self.blocks(page))
        second = pack_page_blocks(page, self.blocks(page))
        self.assertEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            first[0].text = "changed"




class ChunkArtifactTests(unittest.TestCase):
    """Serialize chunks without losing exact text or provenance."""

    def test_artifact_contains_complete_chunk_provenance(self) -> None:
        """Expose every source and boundary field in the JSON record."""
        from payer_policy.chunk_artifacts import (
            build_chunk_artifact, chunk_to_record,
        )
        from payer_policy.chunk_packing import PageChunk

        chunk = PageChunk(
            chunk_id="r:p0001:c0001",
            source_id="source",
            retrieval_id="r" * 32,
            pdf_sha256="a" * 64,
            raw_text_sha256="b" * 64,
            selected_text_sha256="c" * 64,
            artifact_kind="corrected",
            quality_verdict="usable",
            parser_name="pypdf",
            parser_version="6.19.0",
            extraction_mode="text",
            page_number=1,
            ordinal=1,
            start_offset=0,
            end_offset=5,
            line_start=1,
            line_end=1,
            text="Hello",
            word_count=1,
            block_kinds=("paragraph",),
        )
        artifact = build_chunk_artifact(
            (chunk,), input_manifest_sha256="d" * 64)
        self.assertEqual(artifact["chunk_count"], 1)
        self.assertEqual(artifact["chunks"], [chunk_to_record(chunk)])

    def test_writer_is_readable_and_does_not_overwrite(self) -> None:
        """Write stable UTF-8 JSON once and reject a second write."""
        from payer_policy.chunk_artifacts import (
            load_chunk_artifact, write_chunk_artifact,
        )

        with TemporaryDirectory() as name:
            path = Path(name) / "chunks.json"
            artifact = {
                "schema_version": 1,
                "input_manifest_sha256": "a" * 64,
                "chunk_count": 0,
                "chunks": [],
            }
            write_chunk_artifact(path, artifact)
            first = path.read_bytes()
            self.assertEqual(load_chunk_artifact(path), artifact)
            with self.assertRaises(FileExistsError):
                write_chunk_artifact(path, artifact)
            self.assertEqual(path.read_bytes(), first)

    def test_artifact_rejects_bad_manifest_digest(self) -> None:
        """Require a complete SHA-256 identity for the input manifest."""
        from payer_policy.chunk_artifacts import build_chunk_artifact

        with self.assertRaises(ValueError):
            build_chunk_artifact((), input_manifest_sha256="bad")

    def test_loader_rejects_malformed_chunk_record(self) -> None:
        """Reject missing provenance and duplicate chunk identities."""
        from payer_policy.chunk_artifacts import (
            build_chunk_artifact, chunk_to_record, load_chunk_artifact,
        )
        from payer_policy.chunk_packing import PageChunk

        chunk = PageChunk(
            chunk_id="r:p0001:c0001",
            source_id="source",
            retrieval_id="r" * 32,
            pdf_sha256="a" * 64,
            raw_text_sha256="b" * 64,
            selected_text_sha256="c" * 64,
            artifact_kind="raw",
            quality_verdict="usable",
            parser_name="pypdf",
            parser_version="6.19.0",
            extraction_mode="text",
            page_number=1,
            ordinal=1,
            start_offset=0,
            end_offset=5,
            line_start=1,
            line_end=1,
            text="Hello",
            word_count=1,
            block_kinds=("paragraph",),
        )
        artifact = build_chunk_artifact(
            (chunk,), input_manifest_sha256="d" * 64)
        with TemporaryDirectory() as name:
            path = Path(name) / "bad.json"
            record = chunk_to_record(chunk)
            del record["source_id"]
            artifact["chunks"] = [record]
            path.write_text(json.dumps(artifact), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_chunk_artifact(path)

    def test_loader_rejects_wrong_chunk_count(self) -> None:
        """Reject artifact metadata that does not match its records."""
        from payer_policy.chunk_artifacts import load_chunk_artifact

        with TemporaryDirectory() as name:
            path = Path(name) / "bad.json"
            path.write_text(
                '{"schema_version": 1, "chunk_count": 1, "chunks": []}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_chunk_artifact(path)


if __name__ == "__main__":
    unittest.main()

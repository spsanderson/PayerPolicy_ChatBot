"""Tests for the bounded pilot input contract."""
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


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


def artifact_record(
    *, text: str = "Approved page text.\n", corrected: bool = False,
) -> tuple[dict[str, object], bytes, bytes]:
    """Return one artifact record and its raw/selected bytes."""
    raw = text.encode("utf-8")
    selected_text = text.replace("raw", "corrected") if corrected else text
    selected = selected_text.encode("utf-8")
    raw_path = "page-text/pa-certificate-2025/page-001.txt"
    selected_path = (
        "corrected/page-001.txt" if corrected else raw_path
    )
    record: dict[str, object] = {
        "source_id": "pa-certificate-2025",
        "retrieval_id": "a" * 32,
        "sha256": "b" * 64,
        "page_number": 1,
        "raw_artifact": raw_path,
        "raw_text_sha256": hashlib.sha256(raw).hexdigest(),
        "selected_artifact": "corrected" if corrected else "raw",
        "selected_text_artifact": selected_path,
        "selected_text_sha256": hashlib.sha256(selected).hexdigest(),
        "quality_verdict": "usable",
    }
    if corrected:
        record.update({
            "correction_manifest": "corrected/manifest.json",
            "corrected_from_raw_sha256": hashlib.sha256(raw).hexdigest(),
        })
    return record, raw, selected


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


class PilotArtifactTests(unittest.TestCase):
    """Verify selected text artifacts without changing local evidence."""

    @staticmethod
    def write_artifact(root: Path, relative: str, body: bytes) -> Path:
        """Write a temporary artifact fixture and return its path."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    def approved_artifact_manifest(
        self, root: Path,
    ) -> list[dict[str, object]]:
        """Write and describe all twelve synthetic approved page artifacts."""
        records = []
        pages = {
            "pa-certificate-2025": (1, 56, 110, 165),
            "pa-amendments-2025": (1, 6, 11, 16),
            "pa-empire-plan-report-2026": (1, 5, 8, 12),
        }
        for source_id, numbers in pages.items():
            for page_number in numbers:
                text = f"{source_id} page {page_number}\n"
                body = text.encode("utf-8")
                relative = (
                    f"page-text/{source_id}/page-{page_number:03d}.txt"
                )
                self.write_artifact(root, relative, body)
                digest = hashlib.sha256(body).hexdigest()
                records.append({
                    "source_id": source_id,
                    "retrieval_id": "a" * 32,
                    "sha256": "b" * 64,
                    "page_number": page_number,
                    "raw_artifact": relative,
                    "raw_text_sha256": digest,
                    "selected_artifact": "raw",
                    "selected_text_artifact": relative,
                    "selected_text_sha256": digest,
                    "quality_verdict": "usable",
                })
        return records

    def test_accepts_complete_raw_artifact_metadata(self) -> None:
        """Accept explicit raw and selected text provenance fields."""
        from payer_policy.pilot_inputs import validate_pilot_artifact_record

        record, _, _ = artifact_record()
        self.assertEqual(validate_pilot_artifact_record(record), [])

    def test_rejects_missing_text_provenance(self) -> None:
        """Require hashes and a selected text path before reading files."""
        from payer_policy.pilot_inputs import validate_pilot_artifact_record

        record, _, _ = artifact_record()
        del record["raw_text_sha256"]
        del record["selected_text_sha256"]
        errors = validate_pilot_artifact_record(record)
        self.assertTrue(any("raw_text_sha256" in error for error in errors))
        self.assertTrue(
            any("selected_text_sha256" in error for error in errors)
        )

    def test_rejects_relative_path_escape(self) -> None:
        """Reject artifact paths that can escape the selected root."""
        from payer_policy.pilot_inputs import validate_pilot_artifact_record

        record, _, _ = artifact_record()
        record["raw_artifact"] = "../outside.txt"
        errors = validate_pilot_artifact_record(record)
        self.assertTrue(any("raw_artifact" in error for error in errors))

    def test_loads_matching_raw_artifact(self) -> None:
        """Return immutable page facts when raw bytes match the manifest."""
        from payer_policy.pilot_inputs import load_validated_pilot_page

        record, raw, _ = artifact_record()
        with TemporaryDirectory() as name:
            root = Path(name)
            path = self.write_artifact(root, str(record["raw_artifact"]), raw)
            page = load_validated_pilot_page(root, record)
        self.assertEqual(page.text, raw.decode("utf-8"))
        self.assertEqual(page.raw_artifact, path)
        self.assertEqual(page.selected_artifact, path)
        self.assertEqual(page.artifact_kind, "raw")

    def test_rejects_changed_artifact(self) -> None:
        """Reject bytes whose hash differs from the declared text artifact."""
        from payer_policy.pilot_inputs import (
            PilotArtifactError, load_validated_pilot_page,
        )

        record, _, _ = artifact_record()
        with TemporaryDirectory() as name:
            root = Path(name)
            self.write_artifact(
                root, str(record["raw_artifact"]), b"changed text\n")
            with self.assertRaises(PilotArtifactError) as caught:
                load_validated_pilot_page(root, record)
        self.assertEqual(caught.exception.code, "artifact_hash_mismatch")

    def test_rejects_missing_artifact(self) -> None:
        """Report a missing selected text file distinctly."""
        from payer_policy.pilot_inputs import (
            PilotArtifactError, load_validated_pilot_page,
        )

        record, _, _ = artifact_record()
        with TemporaryDirectory() as name:
            with self.assertRaises(PilotArtifactError) as caught:
                load_validated_pilot_page(Path(name), record)
        self.assertEqual(caught.exception.code, "artifact_missing")

    def test_rejects_directory_artifact(self) -> None:
        """Reject a directory at the selected artifact path."""
        from payer_policy.pilot_inputs import (
            PilotArtifactError, load_validated_pilot_page,
        )

        record, _, _ = artifact_record()
        with TemporaryDirectory() as name:
            root = Path(name)
            (root / str(record["raw_artifact"])).mkdir(parents=True)
            with self.assertRaises(PilotArtifactError) as caught:
                load_validated_pilot_page(root, record)
        self.assertEqual(caught.exception.code, "artifact_is_directory")

    def test_rejects_oversized_artifact(self) -> None:
        """Reject a page artifact larger than the bounded text limit."""
        from payer_policy.pilot_inputs import (
            PilotArtifactError, load_validated_pilot_page,
        )

        record, _, _ = artifact_record()
        with TemporaryDirectory() as name:
            root = Path(name)
            self.write_artifact(
                root, str(record["raw_artifact"]), b"x" * 65_537)
            with self.assertRaises(PilotArtifactError) as caught:
                load_validated_pilot_page(root, record)
        self.assertEqual(caught.exception.code, "artifact_too_large")

    def test_rejects_invalid_utf8(self) -> None:
        """Reject text bytes that cannot be decoded as UTF-8."""
        from payer_policy.pilot_inputs import (
            PilotArtifactError, load_validated_pilot_page,
        )

        record, _, _ = artifact_record()
        with TemporaryDirectory() as name:
            root = Path(name)
            self.write_artifact(root, str(record["raw_artifact"]), b"\xff")
            with self.assertRaises(PilotArtifactError) as caught:
                load_validated_pilot_page(root, record)
        self.assertEqual(caught.exception.code, "artifact_decode_error")

    def test_corrected_artifact_requires_matching_provenance(self) -> None:
        """Accept a corrected view only when its manifest matches the page."""
        from payer_policy.pilot_inputs import load_validated_pilot_page

        record, raw, selected = artifact_record(corrected=True)
        with TemporaryDirectory() as name:
            root = Path(name)
            self.write_artifact(
                root, str(record["raw_artifact"]), raw)
            self.write_artifact(
                root, str(record["selected_text_artifact"]), selected)
            manifest = {
                "retrieval_id": record["retrieval_id"],
                "sha256": record["sha256"],
                "page_number": record["page_number"],
                "raw_text_sha256": record["raw_text_sha256"],
                "selected_text_sha256": record["selected_text_sha256"],
            }
            self.write_artifact(
                root, str(record["correction_manifest"]),
                json.dumps(manifest).encode("utf-8"),
            )
            page = load_validated_pilot_page(root, record)
        self.assertEqual(page.artifact_kind, "corrected")
        self.assertEqual(page.text, selected.decode("utf-8"))

    def test_rejects_mismatched_correction_manifest(self) -> None:
        """Reject a correction manifest tied to another physical page."""
        from payer_policy.pilot_inputs import (
            PilotArtifactError, load_validated_pilot_page,
        )

        record, raw, selected = artifact_record(corrected=True)
        with TemporaryDirectory() as name:
            root = Path(name)
            self.write_artifact(root, str(record["raw_artifact"]), raw)
            self.write_artifact(
                root, str(record["selected_text_artifact"]), selected)
            manifest = {
                "retrieval_id": record["retrieval_id"],
                "sha256": record["sha256"],
                "page_number": 2,
                "raw_text_sha256": record["raw_text_sha256"],
                "selected_text_sha256": record["selected_text_sha256"],
            }
            self.write_artifact(
                root, str(record["correction_manifest"]),
                json.dumps(manifest).encode("utf-8"),
            )
            with self.assertRaises(PilotArtifactError) as caught:
                load_validated_pilot_page(root, record)
        self.assertEqual(
            caught.exception.code, "correction_provenance_mismatch")

    def test_loads_complete_validated_batch(self) -> None:
        """Return all twelve pages only after every artifact is verified."""
        from payer_policy.pilot_inputs import load_validated_pilot_pages

        with TemporaryDirectory() as name:
            root = Path(name)
            records = self.approved_artifact_manifest(root)
            pages = load_validated_pilot_pages(root, records)
        self.assertEqual(len(pages), 12)
        self.assertEqual(pages[0].page_number, 1)
        self.assertEqual(pages[-1].page_number, 12)

    def test_rejects_incomplete_batch_before_loading_files(self) -> None:
        """Reject a partial page set instead of returning partial facts."""
        from payer_policy.pilot_inputs import (
            PilotArtifactError, load_validated_pilot_pages,
        )

        record, _, _ = artifact_record()
        with TemporaryDirectory() as name:
            with self.assertRaises(PilotArtifactError) as caught:
                load_validated_pilot_pages(Path(name), [record])
        self.assertEqual(caught.exception.code, "pilot_batch_incomplete")


if __name__ == "__main__":
    unittest.main()

"""Validate the fixed reviewed-page boundary for the retrieval pilot."""
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


APPROVED_PAGES = {
    "pa-certificate-2025": frozenset({1, 56, 110, 165}),
    "pa-amendments-2025": frozenset({1, 6, 11, 16}),
    "pa-empire-plan-report-2026": frozenset({1, 5, 8, 12}),
}

_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_QUALITY_VERDICTS = frozenset({"usable", "usable_with_caveats"})
_SELECTED_ARTIFACTS = frozenset({"raw", "corrected"})
_MAX_TEXT_BYTES = 65_536
_ARTIFACT_ERROR_CODES = frozenset({
    "invalid_artifact_metadata", "artifact_path_escape", "artifact_missing",
    "artifact_is_directory", "artifact_too_large", "artifact_decode_error",
    "artifact_hash_mismatch", "correction_provenance_mismatch",
    "pilot_batch_incomplete",
})


class PilotArtifactError(ValueError):
    """Report a bounded pilot artifact failure with a stable category."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Store an allowlisted failure code and optional diagnostic detail."""
        if code not in _ARTIFACT_ERROR_CODES:
            raise ValueError("unknown pilot artifact error code")
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class ValidatedPilotPage:
    """Hold selected page text and immutable source/artifact provenance."""

    source_id: str
    retrieval_id: str
    pdf_sha256: str
    page_number: int
    raw_artifact: Path
    selected_artifact: Path
    raw_text_sha256: str
    selected_text_sha256: str
    text: str
    artifact_kind: str
    quality_verdict: str
    correction_manifest: Path | None = None


def validate_pilot_page_record(record: object) -> list[str]:
    """Return errors for one reviewed pilot-page metadata record.

    The validator checks the fixed twelve-page pilot boundary and leaves the
    supplied mapping unchanged. An empty result means the metadata is
    structurally acceptable; it does not verify files or hashes on disk.
    """
    if not isinstance(record, Mapping):
        return ["record: expected a mapping"]

    errors: list[str] = []
    source_id = record.get("source_id")
    if not isinstance(source_id, str) or source_id not in APPROVED_PAGES:
        errors.append("source_id: unapproved pilot document")

    retrieval_id = record.get("retrieval_id")
    if (
        not isinstance(retrieval_id, str)
        or _ID_PATTERN.fullmatch(retrieval_id) is None
    ):
        errors.append(
            "retrieval_id: expected 32 lowercase hexadecimal characters"
        )

    sha256 = record.get("sha256")
    if (
        not isinstance(sha256, str)
        or _SHA256_PATTERN.fullmatch(sha256) is None
    ):
        errors.append("sha256: expected 64 lowercase hexadecimal characters")

    page_number = record.get("page_number")
    if type(page_number) is not int or page_number < 1:
        errors.append("page_number: expected a positive integer")
    elif (
        source_id in APPROVED_PAGES
        and page_number not in APPROVED_PAGES[source_id]
    ):
        errors.append("page_number: not in the approved twelve-page sample")

    raw_artifact = record.get("raw_artifact")
    if not isinstance(raw_artifact, str) or not raw_artifact.strip():
        errors.append("raw_artifact: required nonblank path")

    selected_artifact = record.get("selected_artifact")
    if selected_artifact not in _SELECTED_ARTIFACTS:
        errors.append("selected_artifact: expected raw or corrected")

    quality_verdict = record.get("quality_verdict")
    if quality_verdict not in _QUALITY_VERDICTS:
        errors.append("quality_verdict: expected an approved usable verdict")

    return errors


def validate_pilot_manifest(records: object) -> list[str]:
    """Return errors for the complete twelve-page pilot manifest.

    The function delegates field checks to ``validate_pilot_page_record`` and
    then checks collection identity: every approved document/page pair must
    occur exactly once. It inspects records without sorting, removing, or
    modifying them; it does not read artifact paths or hash files on disk.
    """
    if not isinstance(records, (list, tuple)):
        return ["records: expected a list or tuple"]

    errors: list[str] = []
    expected = {
        (source_id, page_number)
        for source_id, pages in APPROVED_PAGES.items()
        for page_number in pages
    }
    observed: set[tuple[str, int]] = set()

    for index, record in enumerate(records):
        record_errors = validate_pilot_page_record(record)
        for error in record_errors:
            if error.startswith("record:"):
                errors.append(f"records[{index}]: {error}")
            elif ":" in error:
                errors.append(f"records[{index}].{error}")
            else:
                errors.append(f"records[{index}]: {error}")
        if not isinstance(record, Mapping):
            continue
        source_id = record.get("source_id")
        page_number = record.get("page_number")
        if (
            isinstance(source_id, str)
            and source_id in APPROVED_PAGES
            and type(page_number) is int
        ):
            identity = (source_id, page_number)
            if identity in observed:
                errors.append(
                    f"records[{index}]: duplicate page identity "
                    f"{source_id} page {page_number}"
                )
            observed.add(identity)
            if identity not in expected:
                errors.append(
                    f"records[{index}]: unexpected page identity "
                    f"{source_id} page {page_number}"
                )

    for source_id, page_number in sorted(expected - observed):
        errors.append(
            f"manifest: missing approved page {source_id} page {page_number}"
        )
    return errors


def validate_pilot_artifact_record(record: object) -> list[str]:
    """Return metadata errors before any pilot artifact file is opened.

    The original PDF hash and the selected text hashes are separate evidence:
    the former identifies the saved source PDF, while the latter identifies the
    exact derived text bytes supplied to the chunker.
    """
    errors = validate_pilot_page_record(record)
    if not isinstance(record, Mapping):
        return errors

    for field in (
        "raw_text_sha256", "selected_text_sha256",
    ):
        value = record.get(field)
        if (
            not isinstance(value, str)
            or _SHA256_PATTERN.fullmatch(value) is None
        ):
            errors.append(
                f"{field}: expected 64 lowercase hexadecimal characters"
            )

    paths: dict[str, object] = {
        "raw_artifact": record.get("raw_artifact"),
        "selected_text_artifact": record.get("selected_text_artifact"),
    }
    if record.get("selected_artifact") == "corrected":
        paths["correction_manifest"] = record.get("correction_manifest")
    for field, value in paths.items():
        if not isinstance(value, str) or not value.strip():
            if field != "raw_artifact":
                errors.append(f"{field}: required nonblank relative path")
            continue
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"{field}: must be a relative path within the root")

    selected = record.get("selected_artifact")
    if selected == "raw":
        if (
            record.get("selected_text_artifact")
            != record.get("raw_artifact")
        ):
            errors.append(
                "selected_text_artifact: raw selection must use raw_artifact"
            )
        if (
            record.get("selected_text_sha256")
            != record.get("raw_text_sha256")
        ):
            errors.append(
                "selected_text_sha256: raw selection must match "
                "raw_text_sha256"
            )
    elif selected == "corrected":
        raw_hash = record.get("raw_text_sha256")
        if record.get("corrected_from_raw_sha256") != raw_hash:
            errors.append(
                "corrected_from_raw_sha256: must match raw_text_sha256"
            )
    return errors


def _resolve_pilot_artifact(root: Path, value: object, field: str) -> Path:
    """Resolve one existing file under root without allowing path escape."""
    if not isinstance(root, Path):
        raise PilotArtifactError("invalid_artifact_metadata", "root")
    try:
        root_path = root.resolve(strict=True)
    except (TypeError, ValueError) as exc:
        raise PilotArtifactError("invalid_artifact_metadata", "root") from exc
    if not isinstance(value, str):
        raise PilotArtifactError("invalid_artifact_metadata", field)
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise PilotArtifactError("artifact_path_escape", field)
    try:
        candidate = (root / relative).resolve(strict=True)
    except FileNotFoundError as exc:
        raise PilotArtifactError("artifact_missing", field) from exc
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise PilotArtifactError("artifact_path_escape", field) from exc
    if not candidate.is_file():
        raise PilotArtifactError("artifact_is_directory", field)
    return candidate


def _read_pilot_text(path: Path, field: str) -> tuple[bytes, str]:
    """Read one bounded UTF-8 artifact without normalizing its contents."""
    try:
        if path.stat().st_size > _MAX_TEXT_BYTES:
            raise PilotArtifactError("artifact_too_large", field)
        body = path.read_bytes()
    except PilotArtifactError:
        raise
    except OSError as exc:
        raise PilotArtifactError("artifact_missing", field) from exc
    if len(body) > _MAX_TEXT_BYTES:
        raise PilotArtifactError("artifact_too_large", field)
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PilotArtifactError("artifact_decode_error", field) from exc
    return body, text


def _verify_text_hash(body: bytes, expected: object, field: str) -> None:
    """Require exact SHA-256 bytes for one derived text artifact."""
    observed = hashlib.sha256(body).hexdigest()
    if observed != expected:
        raise PilotArtifactError("artifact_hash_mismatch", field)


def _verify_correction_manifest(
    root: Path, record: Mapping[str, object],
) -> Path:
    """Verify corrected-view provenance against the selected page record."""
    path = _resolve_pilot_artifact(
        root, record.get("correction_manifest"), "correction_manifest")
    body, _ = _read_pilot_text(path, "correction_manifest")
    try:
        manifest = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotArtifactError(
            "correction_provenance_mismatch", "invalid correction manifest"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise PilotArtifactError(
            "correction_provenance_mismatch", "manifest must be an object")
    required = {
        "retrieval_id", "sha256", "page_number", "raw_text_sha256",
        "selected_text_sha256",
    }
    if any(manifest.get(field) != record.get(field) for field in required):
        raise PilotArtifactError(
            "correction_provenance_mismatch", "manifest identity mismatch")
    return path


def load_validated_pilot_page(
    root: Path, record: object,
) -> ValidatedPilotPage:
    """Load one page only after metadata, path, bytes and hashes agree."""
    errors = validate_pilot_artifact_record(record)
    if errors:
        raise PilotArtifactError(
            "invalid_artifact_metadata", "; ".join(errors)
        )
    assert isinstance(record, Mapping)
    raw_path = _resolve_pilot_artifact(
        root, record["raw_artifact"], "raw_artifact")
    raw_body, _ = _read_pilot_text(raw_path, "raw_artifact")
    _verify_text_hash(raw_body, record["raw_text_sha256"], "raw_artifact")
    selected_path = _resolve_pilot_artifact(
        root, record["selected_text_artifact"], "selected_text_artifact")
    selected_body, text = _read_pilot_text(
        selected_path, "selected_text_artifact")
    _verify_text_hash(
        selected_body, record["selected_text_sha256"],
        "selected_text_artifact")
    correction_manifest = None
    if record["selected_artifact"] == "corrected":
        correction_manifest = _verify_correction_manifest(root, record)
    return ValidatedPilotPage(
        source_id=record["source_id"],
        retrieval_id=record["retrieval_id"],
        pdf_sha256=record["sha256"],
        page_number=record["page_number"],
        raw_artifact=raw_path,
        selected_artifact=selected_path,
        raw_text_sha256=record["raw_text_sha256"],
        selected_text_sha256=record["selected_text_sha256"],
        text=text,
        artifact_kind=record["selected_artifact"],
        quality_verdict=record["quality_verdict"],
        correction_manifest=correction_manifest,
    )


def load_validated_pilot_pages(
    root: Path, records: object,
) -> tuple[ValidatedPilotPage, ...]:
    """Return all twelve validated pages or raise without partial results."""
    errors = validate_pilot_manifest(records)
    if errors:
        raise PilotArtifactError("pilot_batch_incomplete", "; ".join(errors))
    assert isinstance(records, (list, tuple))
    return tuple(load_validated_pilot_page(root, record) for record in records)

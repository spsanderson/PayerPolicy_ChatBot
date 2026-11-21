"""Validate the fixed reviewed-page boundary for the retrieval pilot."""
import re
from collections.abc import Mapping


APPROVED_PAGES = {
    "pa-certificate-2025": frozenset({1, 56, 110, 165}),
    "pa-amendments-2025": frozenset({1, 6, 11, 16}),
    "pa-empire-plan-report-2026": frozenset({1, 5, 8, 12}),
}

_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_QUALITY_VERDICTS = frozenset({"usable", "usable_with_caveats"})
_SELECTED_ARTIFACTS = frozenset({"raw", "corrected"})


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
    if not isinstance(retrieval_id, str) or _ID_PATTERN.fullmatch(retrieval_id) is None:
        errors.append("retrieval_id: expected 32 lowercase hexadecimal characters")

    sha256 = record.get("sha256")
    if not isinstance(sha256, str) or _SHA256_PATTERN.fullmatch(sha256) is None:
        errors.append("sha256: expected 64 lowercase hexadecimal characters")

    page_number = record.get("page_number")
    if type(page_number) is not int or page_number < 1:
        errors.append("page_number: expected a positive integer")
    elif source_id in APPROVED_PAGES and page_number not in APPROVED_PAGES[source_id]:
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
        for error in validate_pilot_page_record(record):
            if error.startswith("record:"):
                errors.append(f"records[{index}]: {error}")
            elif ":" in error:
                errors.append(f"records[{index}].{error}")
            else:
                errors.append(f"records[{index}]: {error}")
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

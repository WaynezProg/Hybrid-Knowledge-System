"""Parser fingerprint computation for re-ingest judgment.

FR-033 / FR-044: a manifest entry is considered idempotent-compatible only
when both the content SHA256 and the parser fingerprint match. Parser
library upgrades or ingest-time flag changes (e.g. `--pptx-notes`) must
bump the fingerprint so the pipeline re-emits derived artifacts.

Fingerprint format: `"{format}:v{library_version}:{flags_digest}"`.

`are_fingerprints_compatible` treats a stored `"*"` as wildcard for
Phase 1 manifests that predate the field.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from hks.core.manifest import SourceFormat
from hks.ingest.ocr import ocr_engine_signature, preprocess_signature

_FORMAT_TO_PACKAGE: dict[SourceFormat, str | None] = {
    "txt": None,
    "md": "markdown-it-py",
    "pdf": "pypdf",
    "docx": "python-docx",
    "xlsx": "openpyxl",
    "pptx": "python-pptx",
    "png": "pillow",
    "jpg": "pillow",
    "jpeg": "pillow",
}


@dataclass(frozen=True, slots=True)
class ParserFlags:
    """Flags that influence parser output for a given format."""

    pptx_notes: bool = True  # include by default


def _library_version(format_: SourceFormat) -> str:
    package = _FORMAT_TO_PACKAGE.get(format_)
    if package is None:
        return "builtin"
    try:
        return version(package)
    except PackageNotFoundError:  # pragma: no cover - install guarantees
        return "unknown"


def _flags_digest(format_: SourceFormat, flags: ParserFlags) -> str:
    if format_ == "pptx" and not flags.pptx_notes:
        return "notes_exclude"
    return ""


def compute_parser_fingerprint(format_: SourceFormat, flags: ParserFlags) -> str:
    lib = _library_version(format_)
    if format_ in {"png", "jpg", "jpeg"}:
        return (
            f"{format_}:v{lib}:{preprocess_signature()}:{ocr_engine_signature()}:off"
        )
    return f"{format_}:v{lib}:{_flags_digest(format_, flags)}"


def are_fingerprints_compatible(entry_fp: str, current_fp: str) -> bool:
    """Return True iff the manifest entry can be reused without re-ingest.

    `"*"` on the entry side is treated as wildcard (Phase 1 legacy entries).
    """

    return entry_fp == "*" or entry_fp == current_fp

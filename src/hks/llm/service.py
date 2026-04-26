"""Service orchestration for LLM extraction."""

from __future__ import annotations

from pathlib import Path

from hks.core.manifest import ManifestEntry, load_manifest
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import ExitCode, KSError
from hks.llm.models import LlmExtractionRequest, LlmExtractionResult, SourceProvenance
from hks.llm.prompts import build_prompt
from hks.llm.providers import provider_for
from hks.llm.store import store_or_reuse
from hks.llm.validation import validate_provider_output


def classify(request: LlmExtractionRequest) -> LlmExtractionResult:
    paths = runtime_paths()
    entry = resolve_manifest_entry(request.source_relpath, paths)
    source_file = paths.raw_sources / entry.relpath
    content = _content_for_provider(source_file)
    _ = build_prompt(source_relpath=entry.relpath, content=content)
    source = SourceProvenance(
        source_relpath=entry.relpath,
        source_fingerprint=entry.sha256,
        parser_fingerprint=entry.parser_fingerprint,
    )
    raw_payload = provider_for(request).extract(request, content=content)
    result = validate_provider_output(raw_payload, request=request, source=source)
    if request.mode == "preview":
        return result
    idempotency_key = request.idempotency_key(
        source_fingerprint=entry.sha256,
        parser_fingerprint=entry.parser_fingerprint,
    )
    stored, _ = store_or_reuse(request, result, idempotency_key=idempotency_key, paths=paths)
    return stored


def resolve_manifest_entry(source_relpath: str, paths: RuntimePaths | None = None) -> ManifestEntry:
    resolved = paths or runtime_paths()
    if not resolved.root.exists() or not resolved.manifest.exists():
        raise KSError(
            "/ks/ 尚未初始化，請先執行 ks ingest <path>",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks ingest <path>`",
        )
    normalized = source_relpath.strip().lstrip("/")
    if not normalized or ".." in Path(normalized).parts:
        raise KSError(
            "source_relpath 不合法",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    manifest = load_manifest(resolved.manifest)
    entry = manifest.entries.get(normalized)
    if entry is None:
        raise KSError(
            f"source `{normalized}` 不存在於 manifest",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            details=[f"source_relpath: {normalized}"],
        )
    source_file = resolved.raw_sources / entry.relpath
    if not source_file.exists():
        raise KSError(
            f"raw source `{entry.relpath}` 不存在",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            details=[f"path: {source_file}"],
        )
    return entry


def _content_for_provider(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise KSError(
            f"source `{path.name}` 無法讀取",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            details=[str(exc)],
        ) from exc

"""Resolve upstream 008 extraction artifacts for wiki synthesis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from hks.adapters.contracts import validate_llm_artifact
from hks.core.manifest import load_manifest
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import ExitCode, KSError
from hks.llm.store import artifact_path, extractions_dir


def resolve_extraction_artifact(
    *,
    source_relpath: str | None,
    extraction_artifact_id: str | None,
    paths: RuntimePaths | None = None,
) -> tuple[str, dict[str, Any], Path]:
    resolved = paths or runtime_paths()
    _assert_runtime_ready(resolved)
    if extraction_artifact_id:
        path = artifact_path(extraction_artifact_id, resolved)
        if not path.exists():
            raise _missing_artifact(extraction_artifact_id)
        return _load_artifact(path, resolved)
    normalized = (source_relpath or "").strip().lstrip("/")
    if not normalized:
        raise _missing_artifact("<unset>")
    matches: list[tuple[str, dict[str, Any], Path]] = []
    for path in sorted(extractions_dir(resolved).glob("*.json")):
        artifact_id, payload, artifact_file = _read_artifact(path)
        source = payload["result"]["source"]
        if source.get("source_relpath") == normalized:
            matches.append((artifact_id, payload, artifact_file))
    if not matches:
        raise KSError(
            f"source `{normalized}` 沒有 stored 008 extraction artifact",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint=f"run `ks llm classify {normalized} --mode store`",
        )
    stale_error: KSError | None = None
    newest_first = sorted(matches, key=lambda item: str(item[1]["created_at"]), reverse=True)
    for artifact_id, payload, artifact_file in newest_first:
        try:
            _assert_not_stale(payload, resolved)
        except KSError as exc:
            if exc.code == "ARTIFACT_STALE":
                stale_error = exc
                continue
            raise
        return artifact_id, payload, artifact_file
    if stale_error:
        raise stale_error
    raise _missing_artifact(normalized)


def _assert_runtime_ready(paths: RuntimePaths) -> None:
    if not paths.root.exists() or not paths.manifest.exists():
        raise KSError(
            "/ks/ 尚未初始化，請先執行 ks ingest <path>",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks ingest <path>`",
        )


def _missing_artifact(artifact_id: str) -> KSError:
    return KSError(
        f"extraction artifact `{artifact_id}` 不存在",
        exit_code=ExitCode.NOINPUT,
        code="NOINPUT",
        hint="run `ks llm classify <source-relpath> --mode store`",
    )


def _load_artifact(path: Path, paths: RuntimePaths) -> tuple[str, dict[str, Any], Path]:
    artifact_id, payload, artifact_file = _read_artifact(path)
    _assert_not_stale(payload, paths)
    return artifact_id, payload, artifact_file


def _read_artifact(path: Path) -> tuple[str, dict[str, Any], Path]:
    try:
        payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        validate_llm_artifact(payload)
    except Exception as exc:
        raise KSError(
            f"extraction artifact `{path.name}` 無效",
            exit_code=ExitCode.DATAERR,
            code="ARTIFACT_INVALID",
            details=[str(exc)],
        ) from exc
    return str(payload["artifact_id"]), payload, path


def _assert_not_stale(payload: dict[str, Any], paths: RuntimePaths) -> None:
    manifest = load_manifest(paths.manifest)
    source = payload["result"]["source"]
    relpath = str(source["source_relpath"])
    entry = manifest.entries.get(relpath)
    if entry is None:
        raise KSError(
            f"source `{relpath}` 不存在於 manifest",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
        )
    if (
        entry.sha256 != source["source_fingerprint"]
        or entry.parser_fingerprint != source["parser_fingerprint"]
    ):
        raise KSError(
            f"extraction artifact `{payload['artifact_id']}` 已 stale",
            exit_code=ExitCode.DATAERR,
            code="ARTIFACT_STALE",
            details=[f"source_relpath: {relpath}"],
        )

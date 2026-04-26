"""Artifact storage for 008 LLM extraction."""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from hks.adapters.contracts import validate_llm_artifact
from hks.core.manifest import atomic_write, utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.llm.models import (
    SCHEMA_VERSION,
    ExtractionArtifact,
    LlmExtractionRequest,
    LlmExtractionResult,
)


def extractions_dir(paths: RuntimePaths | None = None) -> Path:
    resolved = paths or runtime_paths()
    return resolved.root / "llm" / "extractions"


def artifact_path(artifact_id: str, paths: RuntimePaths | None = None) -> Path:
    return extractions_dir(paths) / f"{artifact_id}.json"


def artifact_reference(artifact_id: str, path: Path, *, status: str = "valid") -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_path": path.as_posix(),
        "schema_version": SCHEMA_VERSION,
        "status": status,
    }


def store_or_reuse(
    request: LlmExtractionRequest,
    result: LlmExtractionResult,
    *,
    idempotency_key: str,
    paths: RuntimePaths | None = None,
) -> tuple[LlmExtractionResult, bool]:
    resolved = paths or runtime_paths()
    base_id = idempotency_key[:24]
    with _blocking_file_lock(resolved.root / "llm" / ".lock"):
        if not request.force_new_run:
            path = artifact_path(base_id, resolved)
            if path.exists():
                payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
                existing_ref = artifact_reference(
                    str(payload["artifact_id"]),
                    path,
                    status=str(payload.get("status", "valid")),
                )
                existing_ref["idempotent_reuse"] = True
                return result.with_artifact(existing_ref), True
            artifact_id = base_id
        else:
            artifact_id = f"{base_id}-{utc_now_iso().replace(':', '').replace('+', 'z')}"
            path = artifact_path(artifact_id, resolved)

        ref = artifact_reference(artifact_id, path)
        stored_result = result.with_artifact(ref)
        artifact = ExtractionArtifact(
            artifact_id=artifact_id,
            schema_version=SCHEMA_VERSION,
            idempotency_key=idempotency_key,
            created_at=utc_now_iso(),
            status="valid",
            request=request,
            result=stored_result,
        )
        payload = artifact.to_dict()
        validate_llm_artifact(payload)
        atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))
        return stored_result, False


@contextmanager
def _blocking_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

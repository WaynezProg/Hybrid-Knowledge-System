"""Candidate artifact storage for 009 wiki synthesis."""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from hks.adapters.contracts import validate_wiki_artifact
from hks.core.manifest import atomic_write, utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import ExitCode, KSError
from hks.wiki_synthesis.models import (
    SCHEMA_VERSION,
    WikiSynthesisArtifact,
    WikiSynthesisCandidate,
    WikiSynthesisRequest,
    WikiSynthesisResult,
)


def candidates_dir(paths: RuntimePaths | None = None) -> Path:
    resolved = paths or runtime_paths()
    return resolved.root / "llm" / "wiki-candidates"


def candidate_path(artifact_id: str, paths: RuntimePaths | None = None) -> Path:
    return candidates_dir(paths) / f"{artifact_id}.json"


def artifact_reference(artifact_id: str, path: Path, *, status: str = "valid") -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_path": path.as_posix(),
        "schema_version": SCHEMA_VERSION,
        "status": status,
    }


def store_or_reuse(
    request: WikiSynthesisRequest,
    result: WikiSynthesisResult,
    *,
    idempotency_key: str,
    paths: RuntimePaths | None = None,
) -> tuple[WikiSynthesisResult, bool]:
    resolved = paths or runtime_paths()
    base_id = idempotency_key[:24]
    with blocking_file_lock(resolved.root / "llm" / ".wiki-synthesis.lock"):
        if not request.force_new_run:
            path = candidate_path(base_id, resolved)
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
            path = candidate_path(artifact_id, resolved)
        ref = artifact_reference(artifact_id, path)
        stored_result = result.with_artifact(ref)
        artifact = WikiSynthesisArtifact(
            artifact_id=artifact_id,
            schema_version=SCHEMA_VERSION,
            idempotency_key=idempotency_key,
            created_at=utc_now_iso(),
            status="valid",
            request=request,
            candidate=result.candidate,
        )
        payload = artifact.to_dict()
        validate_wiki_artifact(payload)
        atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))
        return stored_result, False


def load_candidate_artifact(
    candidate_artifact_id: str,
    paths: RuntimePaths | None = None,
) -> tuple[str, WikiSynthesisCandidate, dict[str, Any], Path]:
    resolved = paths or runtime_paths()
    path = candidate_path(candidate_artifact_id, resolved)
    if not path.exists():
        raise KSError(
            f"wiki synthesis candidate artifact `{candidate_artifact_id}` 不存在",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks wiki synthesize --mode store` first",
        )
    try:
        payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        validate_wiki_artifact(payload)
        candidate = WikiSynthesisCandidate.from_dict(cast(dict[str, Any], payload["candidate"]))
    except Exception as exc:
        raise KSError(
            f"wiki synthesis candidate artifact `{candidate_artifact_id}` 無效",
            exit_code=ExitCode.DATAERR,
            code="WIKI_CANDIDATE_INVALID",
            details=[str(exc)],
        ) from exc
    return str(payload["artifact_id"]), candidate, payload, path


@contextmanager
def blocking_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

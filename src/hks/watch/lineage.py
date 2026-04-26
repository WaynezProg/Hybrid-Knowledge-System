"""Derived artifact lineage checks for watch planning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hks.core.paths import RuntimePaths
from hks.watch.models import WatchIssue, WatchSource, zero_artifact_counts


def inspect_lineage(
    *,
    paths: RuntimePaths,
    sources: list[WatchSource],
) -> tuple[dict[str, int], list[WatchIssue]]:
    stale_relpaths = {source.relpath for source in sources if source.state in {"stale", "missing"}}
    manifest_relpaths = {source.relpath for source in sources if source.state != "unsupported"}
    counts = zero_artifact_counts()
    issues: list[WatchIssue] = []
    if not stale_relpaths:
        return counts, issues

    for path in sorted((paths.root / "llm" / "extractions").glob("*.json")):
        payload = _load_json(path)
        relpath = _source_relpath(payload)
        if relpath in stale_relpaths:
            counts["llm_extraction_stale"] += 1
            issues.append(_issue("llm_extraction_stale", path, relpath))
        elif relpath and relpath not in manifest_relpaths:
            counts["orphaned"] += 1
            issues.append(_issue("llm_extraction_orphaned", path, relpath))

    for path in sorted((paths.root / "llm" / "wiki-candidates").glob("*.json")):
        payload = _load_json(path)
        relpath = _source_relpath(payload)
        if relpath in stale_relpaths:
            counts["wiki_candidate_stale"] += 1
            issues.append(_issue("wiki_candidate_stale", path, relpath))
        elif relpath and relpath not in manifest_relpaths:
            counts["orphaned"] += 1
            issues.append(_issue("wiki_candidate_orphaned", path, relpath))

    latest = paths.root / "graphify" / "latest.json"
    if latest.exists() and stale_relpaths:
        counts["graphify_stale"] = 1
        issues.append(
            WatchIssue(
                severity="info",
                code="graphify_stale",
                message="graphify latest output may be stale because source lineage changed",
                source_ref=latest.relative_to(paths.root).as_posix(),
            )
        )
    return counts, issues


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_relpath(payload: dict[str, Any]) -> str | None:
    direct = payload.get("source_relpath")
    if isinstance(direct, str):
        return direct
    for key in ("summary", "result", "candidate", "input"):
        nested = payload.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("source_relpath"), str):
            return str(nested["source_relpath"])
    return None


def _issue(code: str, path: Path, source_relpath: str) -> WatchIssue:
    return WatchIssue(
        severity="info",
        code=code,
        message=f"{path.name} references stale or orphaned source `{source_relpath}`",
        source_ref=path.as_posix(),
    )

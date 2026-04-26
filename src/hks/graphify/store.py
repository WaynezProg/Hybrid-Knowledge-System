"""Graphify run storage."""

from __future__ import annotations

import fcntl
import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from hks.adapters.contracts import validate_graphify_graph, validate_graphify_run
from hks.core.manifest import atomic_write, utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.graphify.export import render_html, render_report
from hks.graphify.models import GraphifyGraph, GraphifyRequest, GraphifyResult, GraphifyRun
from hks.graphify.validation import validate_run


def graphify_dir(paths: RuntimePaths | None = None) -> Path:
    resolved = paths or runtime_paths()
    return resolved.root / "graphify"


def runs_dir(paths: RuntimePaths | None = None) -> Path:
    return graphify_dir(paths) / "runs"


def run_dir(run_id: str, paths: RuntimePaths | None = None) -> Path:
    return runs_dir(paths) / run_id


def latest_path(paths: RuntimePaths | None = None) -> Path:
    return graphify_dir(paths) / "latest.json"


def store_or_reuse(
    request: GraphifyRequest,
    graph: GraphifyGraph,
    *,
    input_fingerprint: str,
    source: list[str],
    paths: RuntimePaths | None = None,
) -> tuple[GraphifyResult, bool]:
    resolved = paths or runtime_paths()
    created_at = utc_now_iso()
    idempotency_key = request.idempotency_key(
        input_fingerprint=input_fingerprint,
        created_at_iso=created_at if request.force_new_run else None,
    )
    base_id = idempotency_key[:24]
    with blocking_file_lock(resolved.root / "graphify" / ".lock"):
        if not request.force_new_run:
            existing_dir = run_dir(base_id, resolved)
            manifest_path = existing_dir / "manifest.json"
            if manifest_path.exists():
                artifacts = _summary_artifacts(base_id, existing_dir)
                _write_latest(resolved, base_id, input_fingerprint, manifest_path)
                return (
                    GraphifyResult(
                        mode="store",
                        graph=graph,
                        input_fingerprint=input_fingerprint,
                        source=cast(list[Any], source),
                        artifacts=artifacts,
                        idempotent_reuse=True,
                    ),
                    True,
                )
            run_id = base_id
        else:
            suffix = created_at.replace(":", "").replace("+", "z")
            run_id = f"{base_id}-{suffix}"
        destination = run_dir(run_id, resolved)
        _write_run(
            request,
            graph,
            run_id,
            destination,
            input_fingerprint,
            idempotency_key,
            created_at,
        )
        manifest_path = destination / "manifest.json"
        _write_latest(resolved, run_id, input_fingerprint, manifest_path)
        return (
            GraphifyResult(
                mode="store",
                graph=graph,
                input_fingerprint=input_fingerprint,
                source=cast(list[Any], source),
                artifacts=_summary_artifacts(run_id, destination),
            ),
            False,
        )


def _write_run(
    request: GraphifyRequest,
    graph: GraphifyGraph,
    run_id: str,
    destination: Path,
    input_fingerprint: str,
    idempotency_key: str,
    created_at: str,
) -> None:
    temp = destination.with_name(f".{destination.name}.tmp")
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)
    artifacts = {
        "graph": "graphify.json",
        "communities": "communities.json",
        "audit": "audit.json",
        "manifest": "manifest.json",
        "html": "graph.html" if request.include_html else None,
        "report": "GRAPH_REPORT.md" if request.include_report else None,
    }
    validate_graphify_graph(graph.to_dict())
    (temp / "graphify.json").write_text(
        json.dumps(graph.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (temp / "communities.json").write_text(
        json.dumps([item.to_dict() for item in graph.communities], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (temp / "audit.json").write_text(
        json.dumps([item.to_dict() for item in graph.audit_findings], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if request.include_html:
        (temp / "graph.html").write_text(render_html(graph), encoding="utf-8")
    if request.include_report:
        (temp / "GRAPH_REPORT.md").write_text(render_report(graph), encoding="utf-8")
    run = validate_run(
        GraphifyRun(
            run_id=run_id,
            created_at=created_at,
            status="valid",
            idempotency_key=idempotency_key,
            input_fingerprint=input_fingerprint,
            algorithm_version=request.algorithm_version,
            request=request,
            artifacts=artifacts,
        )
    )
    (temp / "manifest.json").write_text(
        json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    validate_graphify_run(json.loads((temp / "manifest.json").read_text(encoding="utf-8")))
    if destination.exists():
        shutil.rmtree(destination)
    temp.replace(destination)


def _write_latest(
    paths: RuntimePaths,
    run_id: str,
    input_fingerprint: str,
    manifest_path: Path,
) -> None:
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "run_manifest_path": manifest_path.as_posix(),
        "updated_at": utc_now_iso(),
        "input_fingerprint": input_fingerprint,
    }
    atomic_write(latest_path(paths), json.dumps(payload, ensure_ascii=False, indent=2))


def _summary_artifacts(run_id: str, base: Path) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "run_path": base.as_posix(),
        "graph": (base / "graphify.json").as_posix(),
        "communities": (base / "communities.json").as_posix(),
        "audit": (base / "audit.json").as_posix(),
        "manifest": (base / "manifest.json").as_posix(),
        "html": (base / "graph.html").as_posix() if (base / "graph.html").exists() else None,
        "report": (
            (base / "GRAPH_REPORT.md").as_posix()
            if (base / "GRAPH_REPORT.md").exists()
            else None
        ),
    }


def load_run_manifest(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


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

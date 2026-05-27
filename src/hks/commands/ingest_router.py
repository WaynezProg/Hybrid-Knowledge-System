"""Workspace-routing ingest: reads frontmatter workspace_id, splits files by workspace."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from hks.commands import ingest as ingest_command
from hks.core.runtime_context import scoped_ks_root
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.ingest.parsers.md import _split_frontmatter
from hks.workspace.service import ensure_workspace


def _read_workspace_id(file_path: Path) -> str | None:
    if file_path.suffix.lower() not in (".md", ".markdown"):
        return None
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    metadata, _ = _split_frontmatter(text)
    return metadata.get("workspace_id") or None


def run_routed_ingest(
    path: Path,
    *,
    prune: bool = False,
    pptx_notes: bool = True,
    registry_path_value: str | Path | None = None,
) -> QueryResponse:
    source_dir = path.resolve()
    if source_dir.is_file():
        files = [source_dir]
    else:
        files = sorted(f for f in source_dir.rglob("*") if f.is_file())

    groups: dict[str | None, list[Path]] = defaultdict(list)
    for file in files:
        wid = _read_workspace_id(file)
        groups[wid].append(file)

    results: list[dict[str, Any]] = []

    for wid in sorted(groups, key=lambda k: (k is None, k or "")):
        group_files = groups[wid]
        if wid is not None:
            record = ensure_workspace(wid, registry_path_value=registry_path_value)
            with scoped_ks_root(record.ks_root):
                for file in group_files:
                    ingest_command.run(
                        file,
                        prune=prune,
                        pptx_notes=pptx_notes,
                        source_root_override=file.parent,
                    )
            results.append({"workspace_id": wid, "files": len(group_files), "ks_root": record.ks_root})
        else:
            for file in group_files:
                ingest_command.run(
                    file,
                    prune=prune,
                    pptx_notes=pptx_notes,
                    source_root_override=file.parent,
                )
            results.append({"workspace_id": None, "files": len(group_files), "ks_root": "default"})

    total = sum(r["files"] for r in results)
    ws_count = sum(1 for r in results if r["workspace_id"] is not None)
    return QueryResponse(
        answer=f"workspace-route ingest 完成：{total} 檔案分配到 {ws_count} 個 workspace",
        source=[],
        confidence=1.0,
        trace=Trace(
            route="wiki",
            steps=[TraceStep(kind="workspace_route_summary", detail={"groups": results})],
        ),
    )

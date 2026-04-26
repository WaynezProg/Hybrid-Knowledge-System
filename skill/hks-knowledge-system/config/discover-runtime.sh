#!/usr/bin/env sh

# List repo-local HKS runtime candidates, including ignored local data.
# This is for agents that otherwise inspect only tracked repo files.

if command -v git >/dev/null 2>&1; then
  HKS_REPO_ROOT="${HKS_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
else
  HKS_REPO_ROOT="${HKS_REPO_ROOT:-$(pwd)}"
fi

cd "$HKS_REPO_ROOT" || exit 1

if [ -f "skill/hks-knowledge-system/config/shared-runtime.sh" ]; then
  # shellcheck disable=SC1091
  . "skill/hks-knowledge-system/config/shared-runtime.sh" >/dev/null
fi

set -- "$KS_ROOT" "./ks" ./.hks-runs/*/ks
export HKS_ACTIVE_RUNTIME="$KS_ROOT"

printf 'HKS runtime candidates under %s\n' "$HKS_REPO_ROOT"

seen=""
for candidate in "$@"; do
  [ -n "$candidate" ] || continue
  case "$candidate" in
    ./.hks-runs/\*/ks) continue ;;
  esac

  if [ -d "$candidate" ]; then
    abs_candidate="$(cd "$candidate" && pwd)"
  else
    continue
  fi

  case "$seen" in
    *"|$abs_candidate|"*) continue ;;
  esac
  seen="${seen}|${abs_candidate}|"

  uv run python - "$abs_candidate" <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = root / "manifest.json"
wiki_pages = root / "wiki" / "pages"
graph = root / "graph" / "graph.json"

manifest_entries = 0
if manifest.exists():
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("entries"), (dict, list)):
        manifest_entries = len(payload["entries"])
    elif isinstance(payload, list):
        manifest_entries = len(payload)

wiki_count = len(list(wiki_pages.glob("*.md"))) if wiki_pages.exists() else 0
graph_nodes = 0
graph_edges = 0
if graph.exists():
    payload = json.loads(graph.read_text(encoding="utf-8"))
    graph_nodes = len(payload.get("nodes", []))
    graph_edges = len(payload.get("edges", []))

active_runtime = os.environ.get("HKS_ACTIVE_RUNTIME")
marker = "candidate"
if active_runtime and root.resolve() == Path(active_runtime).resolve():
    marker = "active"
print(
    json.dumps(
        {
            "runtime": str(root),
            "marker": marker,
            "manifest_entries": manifest_entries,
            "wiki_pages": wiki_count,
            "graph_nodes": graph_nodes,
            "graph_edges": graph_edges,
        },
        ensure_ascii=False,
    )
)
PY
done

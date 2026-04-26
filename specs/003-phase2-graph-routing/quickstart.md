# Quickstart: Phase 2 階段二 — Graph / Routing / Auto Write-back

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Audience**: reviewer、QA、後續維護者
**Prerequisite**: `001` 與 `002` 已完成

```bash
git checkout 003-phase2-graph-routing
mise install
uv sync
make fixtures

export KS_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/hks.XXXXXX")
export HKS_EMBEDDING_MODEL=simple

uv run ks ingest tests/fixtures/valid
uv run ks query "A 專案延遲影響哪些系統" --writeback=no | jq .
cat "$KS_ROOT/graph/graph.json" | jq '.nodes | length, .edges | length'
uv run ks query "summary Atlas" | jq .
tail -n 20 "$KS_ROOT/wiki/log.md"
```

預期：

- relation query 回 `trace.route="graph"`
- `graph/graph.json` 存在
- summary query 預設觸發 `auto-committed`
- 新 write-back page 含 `## Related`

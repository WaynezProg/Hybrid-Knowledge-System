# Multi-Agent Coordination Workflow

用途：多個 local agents 共用同一個 `KS_ROOT` 時，避免互相踩 shared resources。

```bash
export KS_ROOT="/path/to/hks-runtime"
uv run ks coord session start agent-a
uv run ks coord lease claim agent-a wiki:project-atlas --ttl-seconds 1800
uv run ks coord status --agent-id agent-a
```

交接：

```bash
uv run ks coord handoff add agent-a \
  --summary "完成 ingest/query/lint 檢查" \
  --next-action "請複核 wiki synthesis candidate"
```

收尾：

```bash
uv run ks coord lease release agent-a wiki:project-atlas
uv run ks coord session close agent-a
uv run ks coord lint
```

邊界：coordination 是 local ledger，不是權限系統。

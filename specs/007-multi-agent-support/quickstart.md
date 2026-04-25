# Quickstart: Phase 3 階段三 — Multi-agent support

## 1. 準備 runtime

```bash
uv sync
make fixtures
export KS_ROOT=$(mktemp -d /tmp/hks-agents.XXXXXX)
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid/project-atlas.txt
```

## 2. 建立 agent session

```bash
uv run ks coord session start --agent-id codex-a | jq .
uv run ks coord session start --agent-id codex-b | jq .
uv run ks coord status | jq .
```

預期：
- response 是 HKS `QueryResponse` shape
- `trace.steps[kind="coordination_summary"].detail.sessions` 包含兩個 active sessions
- ledger 出現在 `$KS_ROOT/coordination/state.json`

## 3. Claim resource lease

```bash
uv run ks coord lease claim \
  --agent-id codex-a \
  --resource-key task:reingest-project-atlas \
  --ttl-seconds 1800 | jq .
```

同一 resource 的第二個 claim：

```bash
uv run ks coord lease claim \
  --agent-id codex-b \
  --resource-key task:reingest-project-atlas \
  --ttl-seconds 1800 | jq .
```

預期：
- codex-a 取得 active lease
- codex-b 收到 structured conflict
- 不會產生兩個 active owners

## 4. Handoff note

```bash
uv run ks coord handoff add \
  --agent-id codex-a \
  --resource-key task:reingest-project-atlas \
  --summary "Project Atlas 已完成查詢與 lint。" \
  --next-action "請檢查是否需要 re-ingest 更新來源。" \
  --reference wiki_page:project-atlas | jq .

uv run ks coord handoff list --resource-key task:reingest-project-atlas | jq .
```

預期：
- handoff note 可由 codex-b 查到
- missing references 由 coordination lint 標示，不阻擋 note 寫入

## 5. MCP coordination tools

```bash
uv run hks-mcp --transport stdio
```

預期 tools：
- `hks_coord_session`
- `hks_coord_lease`
- `hks_coord_handoff`
- `hks_coord_status`

Example tool call：

```json
{
  "tool": "hks_coord_lease",
  "arguments": {
    "action": "claim",
    "agent_id": "codex-a",
    "resource_key": "task:reingest-project-atlas",
    "ttl_seconds": 1800
  }
}
```

## 6. Coordination lint

```bash
uv run ks coord lint | jq .
```

預期：
- stale leases、missing references、ledger schema drift 會出現在 `findings`
- ledger 壞檔回 `DATAERR` (`65`)

## 7. 合併前驗證

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

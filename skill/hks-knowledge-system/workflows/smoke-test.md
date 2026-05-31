# Smoke Test Workflow

用途：確認 HKS CLI runtime 可用，且不碰使用者真實知識庫。

```bash
cd "$(git rev-parse --show-toplevel)"
export KS_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hks-smoke.XXXXXX")"
export HKS_EMBEDDING_MODEL=simple
uv run ks --help
uv run ks ingest tests/fixtures/valid
uv run ks source list
uv run ks query "這批資料的重點是什麼？" --writeback=no
uv run ks lint --strict
```

完成標準：

- `ks --help` 顯示 command list。
- ingest 成功建立 `manifest.json`、`wiki/`、`graph/`、`vector/`。
- query 回傳 schema-valid JSON。
- lint strict 沒有 error exit。

## Agent profile MCP smoke

用途：確認 `hks-mcp --profile agent` 只註冊 session2memory / workspace 安全工具，不含 `hks_ingest`。

```bash
cd "$(git rev-parse --show-toplevel)"
export HKS_SESSION2MEMORY_EXPORT_ROOT="${HKS_SESSION2MEMORY_EXPORT_ROOT:-$HOME/session2memory/export}"
export HKS_KS_ROOT_BASE="${HKS_KS_ROOT_BASE:-$HOME/.local/share/hks/workspaces}"
mkdir -p "$HKS_SESSION2MEMORY_EXPORT_ROOT" "$HKS_KS_ROOT_BASE"

# 可選：確認 stdio server 能啟動（Ctrl+C 結束）
# uv run hks-mcp --profile agent --transport stdio

uv run python -c "
from hks.adapters.agent_config import AGENT_TOOL_NAMES
from hks.adapters.mcp_server import create_agent_server
names = set(create_agent_server()._tool_manager._tools.keys())
assert names == set(AGENT_TOOL_NAMES), (sorted(names), sorted(AGENT_TOOL_NAMES))
assert 'hks_ingest' not in names
print('agent tools:', sorted(names))
"

uv run pytest tests/contract/test_agent_profile_contract.py::test_agent_profile_exposes_only_allowlisted_tools -q
```

完成標準：

- Python 印出 `agent tools:` 且為 7 個名稱，與 `AGENT_TOOL_NAMES` 一致。
- pytest 單測 PASS。
- 輸出中 **沒有** `hks_ingest`。

參考：`mcp/README.md` → Agent profile / Validation。

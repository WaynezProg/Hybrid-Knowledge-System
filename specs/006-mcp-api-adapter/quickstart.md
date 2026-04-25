# Quickstart: Phase 3 階段三 — MCP / API adapter

## 1. 安裝與準備

```bash
uv sync
make fixtures
export KS_ROOT=$(mktemp -d /tmp/hks-mcp.XXXXXX)
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid
```

## 2. 啟動 MCP stdio server

```bash
uv run hks-mcp --transport stdio
```

預期：
- server 透過 stdio 等待 MCP client 連線
- tools 清單包含 `hks_query`、`hks_ingest`、`hks_lint`

## 3. 使用 MCP Inspector 驗證

```bash
npx -y @modelcontextprotocol/inspector
```

連線到本機 server 後呼叫：

```json
{
  "tool": "hks_query",
  "arguments": {
    "question": "summary Atlas"
  }
}
```

預期：
- 回傳 HKS `QueryResponse` shape
- `trace.route` 為 `wiki|graph|vector`
- default 不產生 write-back page，因為 adapter query 預設 `writeback=no`

## 4. 啟動 Streamable HTTP MCP server

```bash
uv run hks-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

預期：
- MCP endpoint 綁定 loopback
- 非 loopback host 預設拒絕，除非使用者明確 opt-in

## 5. 驗證 ingest / lint tools

呼叫 `hks_ingest`：

```json
{
  "path": "tests/fixtures/valid",
  "prune": false,
  "pptx_notes": "include"
}
```

呼叫 `hks_lint`：

```json
{
  "strict": false,
  "severity_threshold": "error",
  "fix": "none"
}
```

預期：
- ingest 回傳 `trace.steps[0].kind == "ingest_summary"`
- lint 回傳 `trace.steps[0].kind == "lint_summary"`
- 成功 payload 均通過 `specs/005-phase3-lint-impl/contracts/query-response.schema.json`

## 6. Optional HTTP facade

```bash
uv run hks-api --host 127.0.0.1 --port 8766
```

呼叫 endpoints：

```bash
curl -s http://127.0.0.1:8766/query \
  -H 'content-type: application/json' \
  -d '{"question":"summary Atlas"}' | jq .

curl -s http://127.0.0.1:8766/lint \
  -H 'content-type: application/json' \
  -d '{}' | jq .
```

預期：
- 成功 response 與 MCP / CLI 使用同一 `QueryResponse` shape
- 錯誤 response 使用 adapter error envelope
- 非 loopback host 預設拒絕，除非明確使用 `--allow-non-loopback`

## 7. 錯誤路徑

未初始化 `KS_ROOT`：

```bash
export KS_ROOT=$(mktemp -d /tmp/hks-mcp-empty.XXXXXX)
```

呼叫 `hks_query` 應回 adapter error envelope：

```json
{
  "ok": false,
  "error": {
    "code": "NOINPUT",
    "exit_code": 66,
    "message": "...",
    "details": []
  },
  "response": {
    "answer": "...",
    "source": [],
    "confidence": 0.0,
    "trace": {"route": "wiki", "steps": [{"kind": "error", "detail": {}}]}
  }
}
```

## 8. 合併前驗證

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

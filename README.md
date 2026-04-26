# Hybrid Knowledge System (HKS)

[English](./README.en.md)

Hybrid Knowledge System 是一個 CLI-first、domain-agnostic 的知識系統。目前 runtime 已完成 Phase 1-3：ingest 支援 `txt / md / pdf / docx / xlsx / pptx / png / jpg / jpeg`，query 會在 `wiki / graph / vector` 三層間切換，relation 類問題優先走 graph，高 confidence 答案預設自動 write-back，並提供 image ingest、lint system、multi-agent coordination 與 local MCP / HTTP adapter。

## 這個專案怎麼運作

HKS 預設不是常駐服務。一般使用方式是需要時執行 `uv run ks ...` 指令，指令完成後結束；資料會保存在 `$KS_ROOT`。

- 一般使用者 / shell / Codex / Claude Code / OpenClaw：直接呼叫 `ks ingest`、`ks query`、`ks lint`、`ks coord`
- MCP agent integration：啟動 `hks-mcp`；stdio 模式通常由 agent client 啟動並跟著 session 存活
- HTTP client integration：啟動 `hks-api` 或 `hks-mcp --transport streamable-http`；有 client 要連線時才需要保持該 process running

## 目前能做什麼

- `ks ingest <file|dir> [--pptx-notes include|exclude]`：建立 `raw_sources/`、`wiki/`、`graph/graph.json`、`vector/db/`、`manifest.json`
- `ks query "<question>" [--writeback auto|yes|no|ask]`：回傳穩定 JSON，summary 優先 wiki、relation 優先 graph、detail 優先 vector
- `ks lint [--strict] [--severity-threshold error|warning|info] [--fix|--fix=apply]`：檢查 `wiki / graph / vector / manifest / raw_sources` 跨層一致性
- `ks coord session|lease|handoff|status|lint`：提供 agent presence、resource lease、handoff notes 與 coordination ledger lint
- `hks-mcp --transport stdio|streamable-http`：以本機 MCP tools 暴露 query / ingest / lint / coordination tools
- `hks-api`：optional loopback HTTP facade，提供 `/query`、`/ingest`、`/lint`、`/coord/*`
- 獨立圖片檔 ingest 已支援 `png / jpg / jpeg`，以本機 `tesseract` OCR 處理；`.heic / .webp` 與 VLM 仍未納入

## 安裝

前置需求：

- macOS 建議使用 Homebrew 安裝系統工具
- Python runtime 由 `mise` 管理，套件由 `uv` 安裝
- image ingest 需要本機 `tesseract` 與語言包
- `jq` 非必要，但方便檢查 JSON output

```bash
git clone https://github.com/WaynezProg/Hybrid-Knowledge-System.git
cd Hybrid-Knowledge-System
brew install tesseract tesseract-lang jq
mise install
uv sync
make fixtures
```

如果只要跑文字 / Office ingest，可以先不裝 `tesseract`；遇到 `png / jpg / jpeg` ingest 再補。

## 5 分鐘上手

```bash
export KS_ROOT=$(mktemp -d /tmp/hks.XXXXXX)
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid
uv run ks query "這批文件的重點是什麼" --writeback=no | jq .
uv run ks query "A 專案延遲會影響哪些系統" --writeback=no | jq .
uv run ks coord session start agent-a | jq .
uv run ks coord lease claim agent-a wiki:atlas | jq .
uv run hks-mcp --help
cat "$KS_ROOT/graph/graph.json" | jq '.nodes | length, .edges | length'
```

`HKS_EMBEDDING_MODEL=simple` 適合 CI、demo 與 agent smoke test。正式使用可移除此設定，改用預設 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，或把 `HKS_EMBEDDING_MODEL` 指向本機模型目錄。

## 怎麼使用

### Ingest

```bash
uv run ks ingest <file-or-dir>
```

- 支援 `txt`、`md`、`pdf`、`docx`、`xlsx`、`pptx`、`png`、`jpg`、`jpeg`
- 以 `SHA256 + parser_fingerprint` 做 idempotency
- `--pptx-notes=exclude` 會改變 parser fingerprint，觸發 pptx re-ingest
- image ingest 需要本機 `tesseract` + `tesseract-lang`
- `.heic` / `.webp` / gif / tiff / svg 仍未承諾支援

### Query

```bash
uv run ks query "<question>" [--writeback auto|yes|no|ask]
```

- summary / overview 類：優先 wiki
- relation / impact / dependency / why 類：優先 graph，miss 才 fallback vector
- detail / clause 類：優先 vector
- 無命中仍 exit `0`，只是 `source=[]`

### Write-back

- `auto`：預設模式；`confidence >= HKS_WRITEBACK_AUTO_THRESHOLD` 時自動寫回 wiki
- `yes`：強制寫回
- `no`：永不寫回
- `ask`：保留舊互動模式；TTY 才詢問，非 TTY 會 skip

自動 write-back 產生的新頁面會帶 `## Related`，連回這次答案涉及的既有 wiki pages。  
automation / agent workflow 仍建議顯式帶 `--writeback=no`，避免測試或批次流程產生多餘頁面。

### Lint

```bash
uv run ks lint
```

會輸出 `trace.steps[kind="lint_summary"].detail`，列出 `findings`、severity/category counters，以及 fix plan/apply 結果。

- 預設 read-only；有 findings 仍 exit `0`
- `--strict`：達到 `--severity-threshold` 的 finding 會 exit `1`
- `--fix`：只列出可安全修復的動作，不寫入
- `--fix=apply`：只執行 allowlist 動作：rebuild `wiki/index.md`、prune orphan vector chunks、prune orphan graph nodes/edges，並寫入 `wiki/log.md`

### Coordination

```bash
uv run ks coord session start agent-a
uv run ks coord session heartbeat agent-a
uv run ks coord lease claim agent-a wiki:atlas --ttl-seconds 1800
uv run ks coord handoff add agent-a --summary "完成檢查" --next-action "請複核"
uv run ks coord status --agent-id agent-a
uv run ks coord lint
```

coordination state 寫在 `$KS_ROOT/coordination/state.json`，events 以 JSONL append 到 `$KS_ROOT/coordination/events.jsonl`。

- `session`：宣告 agent presence，避免同一 agent 重複建立 active session
- `lease`：對 logical `resource_key` 取得 ownership；衝突時 exit `1`，stdout 仍是 schema-valid JSON，`trace.steps[kind="coordination_summary"].detail.conflicts` 會列出 owner
- `handoff`：記錄交接摘要、下一步、blocked_by 與 references
- `coord lint`：檢查 missing references 與 stale active leases

### Agent 接法

Codex、Claude Code、OpenClaw 或其他 local agent 可以用三種方式接 HKS：

```bash
# 1. 最簡單：agent 直接執行 CLI
export KS_ROOT=/path/to/hks-runtime
uv run ks query "Project Atlas 目前風險是什麼？" --writeback=no
uv run ks lint --strict

# 2. MCP stdio：讓支援 MCP 的 agent client 啟動這個 server
uv run hks-mcp --transport stdio

# 3. HTTP：給不支援 MCP、但能呼叫 loopback HTTP 的工具
uv run hks-api --host 127.0.0.1 --port 8766
```

agent read path 建議一律顯式使用 `--writeback=no` 或 MCP `hks_query` 預設值，避免背景查詢產生 wiki page。多個 agent 共用同一個 `$KS_ROOT` 時，用 `ks coord lease` 先 claim logical resource，再寫 handoff note。

### MCP / HTTP Adapter

```bash
uv run hks-mcp --transport stdio
uv run hks-mcp --transport streamable-http --host 127.0.0.1 --port 8765
uv run hks-api --host 127.0.0.1 --port 8766
```

- MCP tools：`hks_query`、`hks_ingest`、`hks_lint`、`hks_coord_session`、`hks_coord_lease`、`hks_coord_handoff`、`hks_coord_status`
- HTTP endpoints：`/query`、`/ingest`、`/lint`、`/coord/session`、`/coord/lease`、`/coord/handoff`、`/coord/status`
- 成功 payload 直接沿用 `ks` 的 top-level JSON shape，不包 adapter envelope
- 錯誤 payload 使用 `{ok:false,error:{code,exit_code,message,details},response?}`
- adapter 預設 local-first；Streamable HTTP 與 HTTP facade 預設只允許 loopback host
- agent workflow 建議讓 `hks_query` 維持預設 `writeback=no`

## 輸出格式

```json
{
  "answer": "...",
  "source": ["graph"],
  "confidence": 0.88,
  "trace": {
    "route": "graph",
    "steps": [
      {"kind": "routing_model", "detail": {}},
      {"kind": "graph_lookup", "detail": {}}
    ]
  }
}
```

`ks ingest`、`ks query`、`ks lint`、`ks coord` 共用同一 top-level JSON shape。

## Exit Code

- `0`：成功，包含 query 無命中
- `1`：一般錯誤
- `2`：CLI usage error
- `65`：ingest data error
- `66`：輸入不存在，或 `KS_ROOT` 尚未初始化

## 常用環境變數

- `KS_ROOT`：runtime 資料根，預設 `./ks`
- `HKS_EMBEDDING_MODEL`：embedding backend；`simple` 適合離線 smoke / CI
- `HKS_ROUTING_MODEL`：routing backend 標記與未來接本機 model 的入口；預設 `simple`
- `HKS_WRITEBACK_AUTO_THRESHOLD`：auto write-back 門檻，預設 `0.75`
- `HKS_MAX_FILE_MB`：`txt / md / pdf` 單檔 ingest 上限，預設 `200`；Office 與 Image 使用各自上限
- `HKS_OFFICE_MAX_FILE_MB`：Office 單檔 ingest 上限，預設 `200`
- `HKS_OFFICE_TIMEOUT_SEC`：Office parser timeout，預設 `60`
- `HKS_IMAGE_MAX_FILE_MB`：Image 單檔 ingest 上限，預設 `20`
- `HKS_IMAGE_TIMEOUT_SEC`：Image OCR timeout，預設 `30`
- `HKS_IMAGE_MAX_PIXELS`：Image decode 後像素上限，預設 `100000000`
- `HKS_OCR_LANGS`：tesseract language set，預設 `eng+chi_tra`
- `HKS_ROUTING_RULES`：覆寫 routing rules 檔案路徑

## 進一步文件

- Phase 1 基線：[specs/001-phase1-cli-mvp/spec.md](./specs/001-phase1-cli-mvp/spec.md)
- Office ingest 擴充：[specs/002-phase2-ingest-office/spec.md](./specs/002-phase2-ingest-office/spec.md)
- Phase 2 graph / routing / write-back：[specs/003-phase2-graph-routing/spec.md](./specs/003-phase2-graph-routing/spec.md)
- Phase 3 image ingest：[specs/004-phase3-image-ingest/spec.md](./specs/004-phase3-image-ingest/spec.md)
- 目前 response contract：[specs/005-phase3-lint-impl/contracts/query-response.schema.json](./specs/005-phase3-lint-impl/contracts/query-response.schema.json)
- Spec archive index：[specs/ARCHIVE.md](./specs/ARCHIVE.md)
- Phase 3 lint system：[specs/005-phase3-lint-impl/spec.md](./specs/005-phase3-lint-impl/spec.md)
- Phase 3 MCP / API adapter：[specs/006-mcp-api-adapter/spec.md](./specs/006-mcp-api-adapter/spec.md)
- Phase 3 multi-agent support：[specs/007-multi-agent-support/spec.md](./specs/007-multi-agent-support/spec.md)

## 開發檢查

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

## License

MIT

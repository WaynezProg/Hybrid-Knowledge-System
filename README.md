# Hybrid Knowledge System (HKS)

[English](./README.en.md)

Hybrid Knowledge System 是一個 CLI-first、domain-agnostic 的知識系統。目前 runtime 已完成 Phase 1-3 與 008-012：ingest 支援 `txt / md / pdf / docx / xlsx / pptx / png / jpg / jpeg`，query 會在 `wiki / graph / vector` 三層間切換，relation 類問題優先走 graph，高 confidence 答案預設自動 write-back，並提供 image ingest、lint system、multi-agent coordination、local MCP / HTTP adapter、LLM-assisted classification/extraction、LLM-assisted wiki synthesis、derived Graphify artifacts、bounded watch/re-ingest workflow，以及 source catalog / workspace selection。

## 這個專案怎麼運作

HKS 預設不是常駐服務。一般使用方式是需要時執行 `uv run ks ...` 指令，指令完成後結束；資料會保存在 `$KS_ROOT`。

- 一般使用者 / shell / Codex / Claude Code / OpenClaw：直接呼叫 `ks ingest`、`ks query`、`ks source`、`ks workspace`、`ks lint`、`ks coord`、`ks llm classify`、`ks wiki synthesize`、`ks graphify build`、`ks watch scan|run|status`
- MCP agent integration：啟動 `hks-mcp`；stdio 模式通常由 agent client 啟動並跟著 session 存活
- HTTP client integration：啟動 `hks-api` 或 `hks-mcp --transport streamable-http`；有 client 要連線時才需要保持該 process running

## 目前能做什麼

- `ks ingest <file|dir> [--pptx-notes include|exclude]`：建立 `raw_sources/`、`wiki/`、`graph/graph.json`、`vector/db/`、`manifest.json`
- `ks query "<question>" [--writeback auto|yes|no|ask]`：回傳穩定 JSON，summary 優先 wiki、relation 優先 graph、detail 優先 vector
- `ks source list|show`：查看目前 `KS_ROOT` 已 ingest 的資料與單筆 source 的 derived artifacts；read-only
- `ks workspace register|list|show|remove|use|query`：管理多個 named `KS_ROOT`，並對指定 workspace query
- `ks lint [--strict] [--severity-threshold error|warning|info] [--fix|--fix=apply]`：檢查 `wiki / graph / vector / manifest / raw_sources` 跨層一致性
- `ks coord session|lease|handoff|status|lint`：提供 agent presence、resource lease、handoff notes 與 coordination ledger lint
- `ks llm classify <source-relpath> [--mode preview|store] [--provider fake]`：對已 ingest source 產生 LLM classification / summary / fact / entity / relation candidates；preview 預設不改 wiki / graph / vector，store 只寫 `$KS_ROOT/llm/extractions/`
- `ks wiki synthesize --mode preview|store|apply`：consume 008 extraction artifact，產生 / 儲存 / 明確套用 wiki synthesis candidate；`apply` 只吃 stored candidate artifact
- `ks graphify build --mode preview|store`：從既有 wiki / graph / 008 / 009 lineage 產生 derived graphify JSON、communities、audit、static HTML、Markdown report；不改 authoritative graph
- `ks watch scan|run|status`：對明確 source root 或 saved watch config 產生 refresh plan、執行 bounded refresh、查詢 watch state；scan / dry-run 不改 authoritative layers
- `hks-mcp --transport stdio|streamable-http`：以本機 MCP tools 暴露 query / ingest / source catalog / workspace / lint / coordination / LLM extraction / wiki synthesis / graphify / watch tools
- `hks-api`：optional loopback HTTP facade，提供 `/query`、`/ingest`、`/catalog/*`、`/workspaces/*`、`/lint`、`/llm/classify`、`/wiki/synthesize`、`/graphify/build`、`/watch/*`、`/coord/*`
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
mkdir -p .hks-runs/demo
export KS_ROOT="$PWD/.hks-runs/demo/ks"
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid
uv run ks source list | jq .
uv run ks source show project-atlas.txt | jq .
uv run ks query "這批文件的重點是什麼" --writeback=no | jq .
uv run ks query "A 專案延遲會影響哪些系統" --writeback=no | jq .
uv run ks llm classify project-atlas.txt --provider fake --mode preview | jq .
uv run ks llm classify project-atlas.txt --provider fake --mode store | jq .
uv run ks wiki synthesize --source-relpath project-atlas.txt --target-slug project-atlas-synthesis --mode store --provider fake | jq .
uv run ks graphify build --mode store --provider fake | jq .
uv run ks watch scan --source-root tests/fixtures/valid | jq .
export HKS_WORKSPACE_REGISTRY="$PWD/.hks-runs/demo/workspaces.json"
uv run ks workspace register demo --ks-root "$KS_ROOT" --label "Demo" | jq .
uv run ks workspace query demo "Project Atlas 目前風險是什麼？" --writeback=no | jq .
uv run ks coord session start agent-a | jq .
uv run ks coord lease claim agent-a wiki:atlas | jq .
uv run hks-mcp --help
cat "$KS_ROOT/graph/graph.json" | jq '.nodes | length, .edges | length'
```

`.hks-runs/` 是 repo-local runtime 目錄，已被 `.gitignore` 忽略；這比 `/tmp` 更適合跨平台與長期保留測試輸出。

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

### Source Catalog / Workspace

```bash
uv run ks source list
uv run ks source show project-atlas.txt

export HKS_WORKSPACE_REGISTRY="$PWD/.hks-runs/workspaces.json"
uv run ks workspace register atlas --ks-root "$PWD/.hks-runs/atlas/ks" --label "Atlas"
uv run ks workspace list
uv run ks workspace use atlas
uv run ks workspace query atlas "這個專案有哪些風險？" --writeback=no
```

- `ks source list|show` 只讀 `manifest.json` 與既有 artifact references，不改 `wiki/`、`graph/`、`vector/`、`manifest.json` 或 `watch/`
- workspace registry 是獨立 local JSON，預設由 `HKS_WORKSPACE_REGISTRY` 覆寫；registry 只記錄 workspace id 到 `KS_ROOT` 的對應
- `workspace use` 回傳 shell-safe `export KS_ROOT=...`，不假裝能改變 parent shell
- `workspace query` 會把 query 導向指定 workspace 的 `KS_ROOT`，response shape 與 `ks query` 相同

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

### LLM Classification / Extraction

```bash
uv run ks llm classify <source-relpath> --provider fake --mode preview
uv run ks llm classify <source-relpath> --provider fake --mode store
```

- 只處理已由 `ks ingest` 建立 manifest 的 source relpath，例如 `project-atlas.txt`
- 成功 response 仍是 HKS top-level JSON；`trace.route="wiki"`、`source=[]`、`trace.steps[kind="llm_extraction_summary"]`
- `preview` 是預設模式，不寫 `wiki/`、`graph/graph.json`、`vector/db/` 或 `manifest.json`
- `store` 只寫 versioned candidate artifact 到 `$KS_ROOT/llm/extractions/`，供後續 009 Wiki synthesis、010 Graphify、011 watch/re-ingest 使用
- 目前內建 deterministic `fake` provider，測試與 agent smoke 不需要 network 或 API key
- hosted/network provider 預設拒絕；必須用環境變數 opt-in，不能用 CLI/MCP/HTTP request body 打開

### LLM Wiki Synthesis

```bash
uv run ks llm classify project-atlas.txt --provider fake --mode store
uv run ks wiki synthesize --source-relpath project-atlas.txt --target-slug project-atlas-synthesis --mode preview --provider fake
uv run ks wiki synthesize --source-relpath project-atlas.txt --target-slug project-atlas-synthesis --mode store --provider fake
uv run ks wiki synthesize --candidate-artifact-id <candidate-id> --mode apply --provider fake
```

- `preview` 只回傳 wiki page candidate，不改 `wiki/`、`graph/`、`vector/`、`manifest.json`
- `store` 寫 versioned candidate artifact 到 `$KS_ROOT/llm/wiki-candidates/`
- `apply` 必須使用 stored `candidate_artifact_id`，只寫 `wiki/pages/`、`wiki/index.md`、`wiki/log.md`
- 若 target slug 已有非 `origin=llm_wiki` 頁面，會 fail closed，exit `1` 且 stdout 仍是 HKS JSON
- 成功 response 使用 `trace.steps[kind="wiki_synthesis_summary"]`

### Graphify

```bash
uv run ks graphify build --mode preview --provider fake
uv run ks graphify build --mode store --provider fake
uv run ks graphify build --mode store --no-html --provider fake
```

- `preview` 只回傳 `graphify_summary`，不寫任何 runtime layer
- `store` 只寫 `$KS_ROOT/graphify/runs/<run-id>/` 與 `$KS_ROOT/graphify/latest.json`
- output 包含 `graphify.json`、`communities.json`、`audit.json`、`manifest.json`、`graph.html`、`GRAPH_REPORT.md`
- Graphify 是 derived analysis layer，不會修改 authoritative `graph/graph.json`、`wiki/`、`vector/` 或 `manifest.json`
- 成功 response 使用 `trace.route="graph"`、`trace.steps[kind="graphify_summary"]`，`source` 只列實際讀取的穩定 layer，例如 `["wiki","graph"]`

### Watch / Refresh

```bash
uv run ks watch scan --source-root <source-dir>
uv run ks watch run --source-root <source-dir> --mode dry-run --profile ingest-only
uv run ks watch run --source-root <source-dir> --mode execute --profile ingest-only
uv run ks watch status
```

- `scan` 產生 watch plan，寫入 `$KS_ROOT/watch/` operational state，但不改 `wiki/`、`graph/`、`vector/`、`manifest.json`
- `run --mode dry-run` 只規劃 refresh action；`run --mode execute` 才會透過既有 ingest / graphify service 執行
- external source 變更偵測需要 `--source-root` 或 saved watch config；未提供時只掃 `$KS_ROOT/raw_sources` 做 internal consistency fallback
- 成功 response 使用 `trace.route="wiki"`、`trace.steps[kind="watch_summary"]`；scan / dry-run / status 的 `source=[]`，execute ingest refresh 成功後 `source=["wiki","graph","vector"]`

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
export KS_ROOT="$PWD/.hks-runs/my-runtime/ks"
uv run ks query "Project Atlas 目前風險是什麼？" --writeback=no
uv run ks llm classify project-atlas.txt --provider fake --mode preview
uv run ks wiki synthesize --source-relpath project-atlas.txt --mode preview --provider fake
uv run ks graphify build --mode preview --provider fake
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

- MCP tools：`hks_query`、`hks_ingest`、`hks_source_list`、`hks_source_show`、`hks_workspace_list`、`hks_workspace_register`、`hks_workspace_show`、`hks_workspace_remove`、`hks_workspace_use`、`hks_workspace_query`、`hks_lint`、`hks_llm_classify`、`hks_wiki_synthesize`、`hks_graphify_build`、`hks_watch_scan`、`hks_watch_run`、`hks_watch_status`、`hks_coord_session`、`hks_coord_lease`、`hks_coord_handoff`、`hks_coord_status`
- HTTP endpoints：`/query`、`/ingest`、`/catalog/sources`、`/catalog/sources/{relpath}`、`/workspaces`、`/workspaces/{workspace_id}`、`/workspaces/{workspace_id}/query`、`/lint`、`/llm/classify`、`/wiki/synthesize`、`/graphify/build`、`/watch/scan`、`/watch/run`、`/watch/status`、`/coord/session`、`/coord/lease`、`/coord/handoff`、`/coord/status`
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

`ks ingest`、`ks query`、`ks source`、`ks workspace`、`ks lint`、`ks coord`、`ks llm classify`、`ks wiki synthesize`、`ks graphify build`、`ks watch scan|run|status` 共用同一 top-level JSON shape。`ks source` 與 workspace management commands 使用 `trace.route="wiki"`、`source=[]`、`trace.steps[kind="catalog_summary"]`；`ks workspace query` 則回傳既有 `ks query` 語意。`ks llm classify` 與 `ks wiki synthesize --mode preview|store` 使用 `source=[]`，語意由 trace step kind 區分；`ks wiki synthesize --mode apply` 成功後使用 `source=["wiki"]`。`ks graphify build` 使用 `trace.route="graph"`，`source` 表示實際讀取的穩定 HKS layer，不能出現 `"graphify"`。`ks watch scan|run --mode dry-run|status` 使用 `trace.route="wiki"`、`source=[]`；`ks watch run --mode execute --profile ingest-only` 成功後使用 `source=["wiki","graph","vector"]`。

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
- `HKS_LLM_PROVIDER`：LLM extraction provider，預設 `fake`
- `HKS_LLM_MODEL`：LLM extraction model id，預設 `fake-llm-extractor-v1`
- `HKS_LLM_NETWORK_OPT_IN`：hosted/network provider opt-in；必須為 `1` 才允許非 fake provider 繼續檢查 credential
- `HKS_LLM_PROVIDER_<ID>_API_KEY`：hosted provider credential，例如 provider id `openai` 對應 `HKS_LLM_PROVIDER_OPENAI_API_KEY`
- `HKS_LLM_PROVIDER_<ID>_ENDPOINT`：hosted provider optional endpoint
- `HKS_WORKSPACE_REGISTRY`：workspace registry JSON path；預設為使用者 config path

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
- LLM-assisted classification / extraction：[specs/008-llm-classification-extraction/spec.md](./specs/008-llm-classification-extraction/spec.md)
- LLM-assisted wiki synthesis：[specs/009-llm-wiki-synthesis/spec.md](./specs/009-llm-wiki-synthesis/spec.md)
- Graphify pipeline：[specs/010-graphify-pipeline/spec.md](./specs/010-graphify-pipeline/spec.md)
- Watch / re-ingest workflow：[specs/011-continuous-watch/spec.md](./specs/011-continuous-watch/spec.md)
- Source catalog / workspace selection：[specs/012-source-catalog/spec.md](./specs/012-source-catalog/spec.md)

## 開發檢查

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

## License

MIT

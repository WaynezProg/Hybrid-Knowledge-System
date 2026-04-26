# PRD — Hybrid Knowledge System (HKS)

## 1. 產品目標

提供一個可被 AI agent 調用的知識系統，讓使用者可以：

* 查 summary，不只拿到片段
* 查 relation / impact，不只做純文字檢索
* 讓 query 結果持續沉澱成 wiki

---

## 2. Persona

* 工程師：查專案、文件、規範
* PM / 管理層：問風險、依賴、影響
* 個人使用者：做筆記、研究、閱讀整理

---

## 3. Top Scenarios

1. 「A 專案延遲會影響哪些系統？」
2. 「這份規範的重點是什麼？」
3. 「條款 3.2 的原文是？」

---

## 4. 核心能力

### 4.0 Current runtime boundary

目前已完成的是 local-first HKS runtime，已包含 LLM-assisted wiki synthesis、derived Graphify artifacts、bounded watch/re-ingest workflow，以及 source catalog / workspace selection；常駐 daemon 仍未完成。

* HKS 負責 ingest、wiki / graph / vector 同步、query routing、write-back、lint、coordination。
* 外部 agent（Codex / Claude Code / OpenClaw 等）負責 LLM reasoning、任務拆解與是否呼叫 HKS。
* 008 已提供 LLM-assisted classification / extraction candidate artifacts；009 已提供 explicit wiki synthesis apply，但不自動 apply 到 graph / vector / manifest。
* 010 已提供 derived Graphify community clustering、HTML visualization、JSON export、audit report；它不修改 authoritative `graph/graph.json`。
* 011 已提供 bounded `ks watch scan|run|status`；它不是常駐 daemon，scan / dry-run 不改 authoritative layers。
* 012 已提供 `ks source` 與 `ks workspace`，讓使用者或 agent 可以查看已 ingest sources、管理多個 named `KS_ROOT`，並對指定 workspace query。

### 4.1 Ingest

* Phase 1：`txt / md / pdf`
* Phase 2：`docx / xlsx / pptx`
* Phase 3：圖片 ingest（`png / jpg / jpeg`；OCR-only，VLM 與其他 raster formats 延後）

輸出三層：

* wiki
* graph
* vector

### 4.2 Query

* `ks query "<q>" [--writeback auto|yes|no|ask]`
* summary → wiki
* relation / impact / dependency / why → graph
* detail / clause → vector
* graph miss / wiki miss → vector fallback

### 4.3 Write-back

* 高 confidence 答案預設自動 write-back
* `--writeback=no` 可關閉
* 新頁面要帶 related cross-links

### 4.4 Lint

* `ks lint` 檢查 wiki / graph / vector / manifest / raw_sources 跨層一致性
* 預設 read-only；`--strict` 提供 CI exit code；`--fix=apply` 只做 allowlist 安全修復

### 4.5 MCP / API Adapter

* `hks-mcp` 以 local MCP server 暴露 query / ingest / lint / coordination / LLM tools
* 支援 stdio 與 loopback Streamable HTTP transport
* `hks-api` 是 optional loopback HTTP facade，提供 `/query`、`/ingest`、`/lint`、`/coord/*`、`/llm/classify`、`/wiki/synthesize`、`/graphify/build`
* 成功 payload 沿用現有 top-level JSON contract；錯誤 payload 使用 adapter error envelope

### 4.6 Multi-agent Coordination

* `ks coord session` 宣告 agent presence 與 heartbeat
* `ks coord lease` 對 logical resource 取得 claim / renew / release
* `ks coord handoff` 記錄交接摘要、下一步、references、blocked_by
* `ks coord status` 與 `ks coord lint` 提供 runtime visibility 與 missing reference / stale lease 檢查

### 4.7 LLM Classification / Extraction

* `ks llm classify <source-relpath> [--mode preview|store]`
* 只處理已 ingest 並存在於 manifest 的 source
* `preview` 預設 read-only，不改 wiki / graph / vector / manifest
* `store` 只寫 `$KS_ROOT/llm/extractions/` candidate artifact
* 成功 response 使用 `trace.steps[kind="llm_extraction_summary"]`
* MCP tool：`hks_llm_classify`
* HTTP endpoint：`/llm/classify`

### 4.8 LLM Wiki Synthesis

* `ks wiki synthesize --mode preview|store|apply`
* `preview` 與 `store` 只產生或儲存 wiki synthesis candidate，不改 authoritative wiki / graph / vector / manifest
* `apply` 只接受 stored candidate artifact，成功後寫入 `origin=llm_wiki` wiki page、重建 index、append log
* 成功 response 使用 `trace.steps[kind="wiki_synthesis_summary"]`
* MCP tool：`hks_wiki_synthesize`
* HTTP endpoint：`/wiki/synthesize`

### 4.9 Graphify Pipeline

* `ks graphify build --mode preview|store`
* 產生 derived graphify artifacts，不改 authoritative `graph/graph.json`
* output 包含 community clustering、JSON export、static HTML visualization、audit report
* 成功 response 使用 `trace.steps[kind="graphify_summary"]`
* MCP tool：`hks_graphify_build`
* HTTP endpoint：`/graphify/build`

### 4.10 Watch / Refresh Workflow

* `ks watch scan|run|status`
* `scan` 與 `run --mode=dry-run` 只寫 `$KS_ROOT/watch/` operational state，不改 authoritative layers
* `run --mode=execute --profile=ingest-only` 透過既有 ingest 更新 `wiki / graph / vector / manifest`
* 成功 response 使用 `trace.steps[kind="watch_summary"]`
* MCP tools：`hks_watch_scan`、`hks_watch_run`、`hks_watch_status`
* HTTP endpoints：`/watch/scan`、`/watch/run`、`/watch/status`

### 4.11 Source Catalog / Workspace Selection

* `ks source list|show` 提供 read-only source catalog，從 `manifest.json` 顯示 relpath、format、size、ingested time 與 derived artifact references
* `ks workspace register|list|show|remove|use|query` 管理多個 named `KS_ROOT`
* `workspace use` 回傳 shell-safe export command，不假裝修改 parent shell
* `workspace query` 委派既有 query，維持相同 response contract
* MCP tools：`hks_source_list`、`hks_source_show`、`hks_workspace_list`、`hks_workspace_register`、`hks_workspace_show`、`hks_workspace_remove`、`hks_workspace_use`、`hks_workspace_query`
* HTTP endpoints：`/catalog/sources`、`/catalog/sources/{relpath}`、`/workspaces`、`/workspaces/{workspace_id}`、`/workspaces/{workspace_id}/query`

---

## 5. 非功能需求

* local-first
* CLI-first
* 輸出穩定（JSON schema）
* query p95 < 3s（本地 fixture 尺度）

---

## 6. In Scope

* CLI 工具
* 本地知識管理
* wiki / graph / vector 三層同步

## 7. Out of Scope

* UI
* 多使用者 / RBAC
* 雲端部署
* microservice
* 非文字素材（影片、音訊）

---

## 8. Roadmap

### Phase 1

* [x] CLI（query / ingest / lint；Phase 1 初始 lint 介面已由 Phase 3 取代）
* [x] wiki + vector
* [x] rule-based routing
* [x] ingest：`txt / md / pdf`
* [x] 半自動 write-back

### Phase 2

* [x] graph（entity / relation）
* [x] routing backend 升級
* [x] 全自動 write-back
* [x] ingest：`docx / xlsx / pptx`

### Phase 3

* [x] lint system
* [x] 多 agent
* [x] API / MCP adapter
* [x] 圖片 ingest（`png / jpg / jpeg`；OCR-only）

### Candidate Phase 4

* [x] 008 LLM-assisted classification / extraction candidate artifacts
* [x] 009 LLM-assisted wiki rewriting / summarization
* [x] Graphify pipeline：community clustering、HTML visualization、audit report
* [x] Watch / re-ingest workflow for continuously updated personal knowledge roots
* [x] Source catalog / workspace selection

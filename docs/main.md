# Hybrid Knowledge System（Wiki + Graph + Vector）

## 1. 定位

HKS 是一個 local-first、CLI-first、domain-agnostic 的知識系統。  
現在的 runtime 狀態：

* Phase 1：完成
* Phase 2：完成
* Phase 3：完成（`004` image ingest、`005` lint system、`006` MCP / API adapter、`007` multi-agent support）
* 008：完成（LLM-assisted classification / extraction candidate artifacts）
* 009：完成（LLM-assisted wiki synthesis candidate preview / store / explicit apply）
* 010：完成（derived Graphify artifacts、community clustering、static HTML、audit report）
* 011：完成（bounded watch scan / run / status；非 daemon）
* 012：完成（source catalog / workspace selection）

---

## 2. 架構

* Data Layer
  * `raw_sources/`：immutable 原始檔
  * `wiki/`：人可讀摘要與 write-back pages
  * `graph/graph.json`：entity / relation
  * `vector/db/`：embedding retrieval
* Processing Layer
  * ingestion pipeline：parse → normalize → extract → update
  * query pipeline：routing backend → wiki / graph / vector → fallback / write-back
* Tool Layer
  * `ks ingest`
  * `ks query`
  * `ks source`
  * `ks workspace`
  * `ks lint`
  * `ks coord`
  * `ks llm classify`
  * `ks wiki synthesize`
  * `ks graphify build`
  * `ks watch scan|run|status`
  * `hks-mcp`
  * `hks-api`（optional loopback facade）

![LLM Wiki 概念示意](LLM%20wiki.png)

![Graphify 流程](graphify.png)

![LLM Wiki + Graphify 結合](LLM%20wiki%20Graphify.png)

### 2.1 Vision vs current runtime

原始產品願景是 **LLM Wiki + Graphify + Vector**：由 agent / LLM 協助整理個人資料庫，產生可讀 wiki、可分析 graph、可檢索 vector，並讓後續 query 持續沉澱回知識庫。

目前 runtime 已完成可執行的本地知識系統與 derived Graphify pipeline：

* 已完成：來源 ingest 後同步更新 `wiki / graph / vector / manifest`；修改來源後重跑 `ks ingest` 可依 hash / parser fingerprint 更新資料庫。
* 已完成：query 會依問題類型走 wiki、graph 或 vector；高 confidence 結果可 write-back 成 wiki page。
* 已完成：008 可對已 ingest source 產生 schema-validated LLM classification / summary / fact / entity / relation candidates，並可 explicit store 到 `$KS_ROOT/llm/extractions/`。
* 已完成：009 可從 008 stored artifact 產生 wiki synthesis candidate，preview / store 預設不改 authoritative layers，只有 caller-explicit `apply` 會寫入 `wiki/` page、index 與 log。
* 已完成：010 可從既有 wiki / graph / 008 / 009 lineage 產生 derived Graphify artifacts、community clustering、static HTML 與 audit report。
* 已完成：011 提供 bounded watch scan / run / status，處理明確 source roots 或 saved watch config 的 refresh plan 與 re-ingest。
* 已完成：012 提供 read-only source catalog 與 named workspace registry，讓使用者或 agent 可以查看已 ingest sources、選擇 `KS_ROOT`，並對指定 workspace query。
* 尚未完成：常駐 daemon / OS filesystem watcher。

換句話說，HKS 現在是 agent 可調用的 local knowledge runtime；LLM-assisted extraction、wiki synthesis、Graphify、watch 與 source catalog 已由 008-012 交付，剩餘產品願景主要是常駐 daemon / OS watcher 與更高階操作體驗。

---

## 3. CLI Contract

```bash
ks ingest <file|dir>
ks query "<question>" [--writeback auto|yes|no|ask]
ks source list|show
ks workspace register|list|show|remove|use|query
ks lint
ks coord session|lease|handoff|status|lint
ks llm classify <source-relpath> [--mode preview|store] [--provider fake]
ks wiki synthesize --mode preview|store|apply [--source-relpath <relpath>|--candidate-artifact-id <id>]
ks graphify build [--mode preview|store] [--provider fake]
hks-mcp --transport stdio|streamable-http
hks-api
```

stdout 契約統一：

```json
{
  "answer": "...",
  "source": ["wiki", "graph", "vector"],
  "confidence": 0.0,
  "trace": {
    "route": "wiki|graph|vector",
    "steps": []
  }
}
```

`ks ingest`、`ks query`、`ks source`、`ks workspace`、`ks lint`、`ks coord`、`ks llm classify`、`ks wiki synthesize`、`ks graphify build`、`ks watch scan|run|status` 共用同一 top-level JSON shape。
`hks-mcp` 與 `hks-api` 的成功 payload 也共用此 shape；adapter 錯誤才使用 `{ok:false,error:{code,exit_code,message,details},response?}` envelope。

`ks llm classify` 的 successful extraction 使用 `trace.route="wiki"`、`source=[]`、`trace.steps[kind="llm_extraction_summary"]`。這是 008 為避免擴 route/source enum 做出的 contract choice；consumer 不得把它解讀成 `ks query` no-hit。

Source / route 語意對照：

`source` 不是跨 feature 單一動詞；consumer 必須依 command/mode 解讀。`ks query` 的 `source` 表示讀取層；008/009 preview/store 使用 `source=[]` 表示產生 candidate artifact、不是 no-hit；009 apply success 的 `source=["wiki"]` 表示 caller-explicit mutation 成功寫入 wiki；010 Graphify 使用 `source` 表示 Graphify build 實際讀取到的穩定 HKS layer；011 watch 的 scan/dry-run/status 使用 `source=[]` 表示 operational plan/status；012 catalog/workspace management 使用 `source=[]` 表示 operational catalog response。不得新增 `"graphify"`、`"watch"`、`"catalog"` 或 `"workspace"` enum。

| Command / mode | `trace.route` | `source` | 語意 |
|---|---|---|---|
| `ks query` 命中 wiki | `wiki` | `["wiki"]` | 讀取既有 wiki 作答 |
| `ks query` 命中 graph | `graph` | `["graph"]` 或含 fallback source | 讀取 graph，必要時可 fallback / merge |
| `ks query` 命中 vector | `vector` | `["vector"]` | 讀取 vector 作答 |
| `ks query` no-hit | `wiki\|graph\|vector` | `[]` | 查詢流程正常但沒有可用命中；exit code 仍為 `0` |
| `ks llm classify --mode preview\|store` | `wiki` | `[]` | 產生或儲存 LLM extraction artifact；不代表查詢 no-hit，也未讀取 runtime knowledge layer 作答 |
| `ks wiki synthesize --mode preview\|store` | `wiki` | `[]` | 產生或儲存 wiki synthesis candidate；不修改 authoritative wiki |
| `ks wiki synthesize --mode apply` success | `wiki` | `["wiki"]` | caller-explicit wiki mutation 成功後，response 指向被寫入的 wiki layer |
| `ks wiki synthesize --mode apply` conflict/error | `wiki` | `[]` | apply 未成功寫入 wiki；若走 adapter error envelope，錯誤語意由 `error` 承擔 |
| `ks graphify build --mode preview\|store` | `graph` | `["wiki","graph"]` 或實際讀取到的穩定 source layer | 產生 derived Graphify artifacts；不得把 `"graphify"` 放入 top-level `source` |
| `ks watch scan` / `ks watch run --mode dry-run` / `ks watch status` | `wiki` | `[]` | 產生或讀取 `$KS_ROOT/watch/` operational state；不代表 query no-hit |
| `ks watch run --mode execute --profile ingest-only` | `wiki` | `["wiki","graph","vector"]` | caller-explicit refresh 透過既有 ingest 更新穩定 runtime layers |
| `ks source list|show` | `wiki` | `[]` | 讀取 manifest-derived catalog；不代表 query no-hit |
| `ks workspace register|list|show|remove|use` | `wiki` | `[]` | 管理 local workspace registry；不讀取 knowledge layer 作答 |
| `ks workspace query` | `wiki\|graph\|vector` | `ks query` semantics | 先解析 workspace id 到 `KS_ROOT`，再委派既有 query |

---

## 4. Ingestion Pipeline

1. parse
   * Phase 1：`txt / md / pdf`
   * Phase 2：`docx / xlsx / pptx`
   * Phase 3：圖片 ingest（`png / jpg / jpeg`；OCR-only，VLM / `.heic` / `.webp` 延後）
2. normalize
3. extract
   * key facts
   * entities
   * relations
4. update
   * wiki
   * graph
   * vector

目前 graph extraction 是 pattern-based，目的不是做最強 NLP，而是穩定支撐離線 relation query 與 regression tests。
目前 `004` 已把獨立圖片 ingest 凍結為 `png / jpg / jpeg` + local OCR。VLM、`.heic` / `.webp` 與更泛化的 normalize/轉檔策略仍留待後續 spec。

---

## 5. Query Routing

### 5.1 Route 偏好

* summary / overview → wiki
* relation / impact / dependency / why → graph
* detail / clause / excerpt → vector

### 5.2 Routing backend

* 現在的 routing 是 model-driven，不再直接走單純 keyword if/else
* repo 預設 backend 是本機 deterministic semantic router
* `HKS_ROUTING_MODEL` 保留為未來接本機 prompt model 的入口

### 5.3 Fallback

* wiki miss → vector
* graph miss → vector
* no hit → `source=[]`, `confidence=0.0`, exit code 仍為 `0`

---

## 6. Write-back

### 目前行為

* 預設模式：`auto`
* `confidence >= HKS_WRITEBACK_AUTO_THRESHOLD`（預設 `0.75`）→ 自動回寫 wiki
* `--writeback=no` → 禁用
* `--writeback=yes` → 強制回寫
* `--writeback=ask` → 舊互動模式，相容保留

自動 write-back page 會帶 `## Related`，連回本次答案涉及的既有 wiki pages。

---

## 7. Graph Schema

### Entity types

* `Person`
* `Project`
* `Document`
* `Event`
* `Concept`

### Relations

* `owns`
* `depends_on`
* `impacts`
* `references`
* `belongs_to`

graph persistence 位於 `/ks/graph/graph.json`。

---

## 8. Runtime Layout

```text
/ks
  /raw_sources
  /wiki
    index.md
    log.md
    /pages
      <slug>.md
  /graph
    graph.json
  /vector
    db/
  /coordination
    state.json
    events.jsonl
  /llm
    /extractions
      <artifact-id>.json
    /wiki-candidates
      <candidate-artifact-id>.json
  /graphify
    latest.json
    /runs
      <run-id>/
        graphify.json
        communities.json
        audit.json
        manifest.json
        graph.html
        GRAPH_REPORT.md
  /manifest.json
```

`manifest.json` 以 `relpath + sha256 + parser_fingerprint` 對應 derived artifacts，現在包含：

* `wiki_pages`
* `graph_nodes`
* `graph_edges`
* `vector_ids`

`coordination/state.json` 存 agent sessions、resource leases、handoff notes；`events.jsonl` 是 append-only coordination event log。
`llm/extractions/*.json` 存 008 extraction candidate artifact；`llm/wiki-candidates/*.json` 存 009 wiki synthesis candidate artifact。兩者都不是 authoritative wiki / graph / vector state；只有 `ks wiki synthesize --mode apply` 成功後寫入的 `origin=llm_wiki` page 才是 applied wiki state。

Workspace registry 不屬於任何單一 `$KS_ROOT`，預設位於使用者 config path，可用 `HKS_WORKSPACE_REGISTRY` 指向 explicit JSON。Registry 只保存 workspace id 到 `KS_ROOT` 的 mapping；不修改任何 registered runtime 的 `wiki / graph / vector / manifest`。

---

## 9. Multi-agent Coordination

`ks coord` 是 local-first coordination layer，不提供 RBAC 或多使用者隔離。

* `session`：agent 宣告 presence、heartbeat、close；同一 agent 不重複建立 active session
* `lease`：對 logical `resource_key` 取得 ownership；claim / renew / release 在 coordination lock 內完成
* `handoff`：記錄 summary、next_action、references、blocked_by
* `status`：查 sessions / leases / handoffs
* `lint`：檢查 missing references 與 stale active leases

MCP 暴露 `hks_coord_session`、`hks_coord_lease`、`hks_coord_handoff`、`hks_coord_status`；HTTP facade 暴露 `/coord/session`、`/coord/lease`、`/coord/handoff`、`/coord/status`。

## 10. LLM Classification / Extraction

008 提供 `ks llm classify <source-relpath>`，只接受已由 `ks ingest` 登錄在 `manifest.json` 的 source relpath。

* `--mode=preview`：預設，read-only，不改 `wiki/`、`graph/graph.json`、`vector/db/` 或 `manifest.json`
* `--mode=store`：只寫 `$KS_ROOT/llm/extractions/<artifact-id>.json`
* provider 預設 `fake`，用於 deterministic tests / agent smoke
* hosted/network provider 必須由 `HKS_LLM_NETWORK_OPT_IN=1` 與 provider-specific credential gate 開啟，CLI/MCP/HTTP request body 不提供 opt-in toggle
* entity candidates 限定 `Person / Project / Document / Event / Concept`
* relation candidates 限定 `owns / depends_on / impacts / references / belongs_to`

MCP 暴露 `hks_llm_classify`；HTTP facade 暴露 `/llm/classify`。

008 不做 wiki synthesis、Graphify clustering / visualization / audit report，也不做 watch / daemon。wiki synthesis 由 009 提供；Graphify 由 010 提供；watch / daemon 留給 011。

---

## 11. LLM Wiki Synthesis

009 提供 `ks wiki synthesize --mode preview|store|apply`，只消費 008 stored extraction artifact，不重新做 extraction。

* `--mode=preview`：read-only，回傳 wiki page candidate；`source=[]`
* `--mode=store`：只寫 `$KS_ROOT/llm/wiki-candidates/<candidate-artifact-id>.json`；`source=[]`
* `--mode=apply`：只接受 stored candidate artifact，成功時寫入 `wiki/pages/<slug>.md`、重建 `wiki/index.md`、append `wiki/log.md`；`source=["wiki"]`
* apply 是 caller-explicit mutation，不是 query write-back auto mode；它不得修改 graph、vector、manifest 或 008 extraction artifact
* `origin=llm_wiki` page 必須保留 lineage frontmatter，lint 會檢查 candidate artifact 與 applied page provenance

MCP 暴露 `hks_wiki_synthesize`；HTTP facade 暴露 `/wiki/synthesize`。

---

## 12. Graphify

010 提供 `ks graphify build --mode preview|store`，產生 derived Graphify artifacts，而不是修改 authoritative `graph/graph.json`。

* `--mode=preview`：read-only，回傳 `graphify_summary`；不寫任何 runtime layer
* `--mode=store`：只寫 `$KS_ROOT/graphify/runs/<run-id>/` 與 `$KS_ROOT/graphify/latest.json`
* output 包含 graph JSON、communities JSON、audit JSON、static HTML、Markdown report
* `trace.route="graph"`；top-level `source` 只使用既有 `wiki / graph / vector` enum，不能新增 `"graphify"`
* 010 不做 watch / daemon；011 才處理 continuous update orchestration

---

## 13. Watch / Refresh

011 提供 bounded `ks watch scan|run|status`，處理 continuously updated personal knowledge roots，但不是常駐 daemon。

* `scan`：讀取 manifest、明確 source roots 或 saved watch config、derived lineage，產生 refresh plan；不改 authoritative layers
* `run --mode=dry-run`：只規劃 action，最多寫 `$KS_ROOT/watch/` operational state
* `run --mode=execute --profile=ingest-only`：透過既有 ingest pipeline 更新 `wiki / graph / vector / manifest`
* `status`：讀取 latest watch plan / run summary
* watch state 位於 `$KS_ROOT/watch/{plans,runs,latest.json,events.jsonl,config.json}`
* trace 使用 `trace.steps[kind="watch_summary"]`；top-level `source` 不新增 `"watch"`

---

## 14. Source Catalog / Workspace Selection

012 提供 `ks source list|show` 與 `ks workspace register|list|show|remove|use|query`。

* `source list|show`：read-only 讀取 `manifest.json`、`raw_sources/` 與 manifest 的 derived artifact references，回傳 `trace.steps[kind="catalog_summary"]`
* `workspace register|list|show|remove|use`：只寫 workspace registry JSON，不寫 registered `KS_ROOT`
* `workspace use`：回傳 shell-safe `export KS_ROOT=...`，不假裝修改 parent shell
* `workspace query`：解析 workspace id 後委派既有 `ks query`
* MCP 暴露 `hks_source_list`、`hks_source_show`、`hks_workspace_*`；HTTP facade 暴露 `/catalog/*` 與 `/workspaces/*`

---

## 15. Phase Status

### Phase 1

* [x] CLI
* [x] wiki + vector
* [x] rule-based baseline
* [x] ingest：`txt / md / pdf`
* [x] 半自動 write-back
* [x] `ks lint` 初始介面（已由 Phase 3 lint system 取代）

### Phase 2

* [x] ingest：`docx / xlsx / pptx`
* [x] graph extraction
* [x] graph query
* [x] model-driven routing
* [x] 全自動 write-back

### Phase 3

* [x] lint system
* [x] 多 agent 支援
* [x] API / MCP adapter
* [x] 圖片 ingest（`png / jpg / jpeg`；OCR-only）

---

### Post-Phase Specs

* [x] 008 LLM-assisted classification / extraction candidate artifacts
* [x] 009 LLM Wiki synthesis
* [x] 010 Graphify clustering / visualization / audit report
* [x] 011 continuous update / watch workflow
* [x] 012 source catalog / workspace selection

---

## 16. Runtime configuration

常用環境變數不在本文件重複列完整清單，避免 drift。請以 [README.md#常用環境變數](../README.md#常用環境變數) 與 [README.en.md#useful-environment-variables](../README.en.md#useful-environment-variables) 為準。

檔案大小上限分三組：`HKS_MAX_FILE_MB` 管 `txt / md / pdf`，`HKS_OFFICE_MAX_FILE_MB` 管 Office，`HKS_IMAGE_MAX_FILE_MB` 管 image。

---

## 17. 非目標

目前仍不做：

* UI
* 多使用者 / RBAC
* 雲端部署
* microservice
* 非文字素材（影片、音訊）

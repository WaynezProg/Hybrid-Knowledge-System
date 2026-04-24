# Hybrid Knowledge System（Wiki + Graph + Vector）

## 1. 定位

HKS 是一個 local-first、CLI-first、domain-agnostic 的知識系統。  
現在的 runtime 狀態：

* Phase 1：完成
* Phase 2：完成
* Phase 3：未開始

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
  * `ks lint`

![LLM Wiki 概念示意](LLM%20wiki.png)

![LLM Wiki + Graphify 結合](LLM%20wiki%20Graphify.png)

![Graphify 流程](graphify.png)

---

## 3. CLI Contract

```bash
ks ingest <file|dir>
ks query "<question>" [--writeback auto|yes|no|ask]
ks lint
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

`ks ingest`、`ks query`、`ks lint` 共用同一 top-level JSON shape。

---

## 4. Ingestion Pipeline

1. parse
   * Phase 1：`txt / md / pdf`
   * Phase 2：`docx / xlsx / pptx`
   * Phase 3：圖片 ingest（still raster images；實際接受格式與 normalize / 轉檔策略待後續 spec 凍結）
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
圖片 ingest 目前只確定會晚於 Phase 2；未來不應把產品邊界寫死成只吃 `png / jpg`，而應以「接受 still raster images → normalize → OCR / VLM」另立 spec。

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

### 現在的 Phase 2 行為

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
  /manifest.json
```

`manifest.json` 以 `relpath + sha256 + parser_fingerprint` 對應 derived artifacts，現在包含：

* `wiki_pages`
* `graph_nodes`
* `graph_edges`
* `vector_ids`

---

## 9. Phase Status

### Phase 1

* [x] CLI
* [x] wiki + vector
* [x] rule-based baseline
* [x] ingest：`txt / md / pdf`
* [x] 半自動 write-back
* [x] `ks lint` stub

### Phase 2

* [x] ingest：`docx / xlsx / pptx`
* [x] graph extraction
* [x] graph query
* [x] model-driven routing
* [x] 全自動 write-back

### Phase 3

* [ ] lint system
* [ ] 多 agent 支援
* [ ] API / MCP adapter
* [ ] 圖片 ingest（still raster images；exact format set / normalize pipeline / OCR / VLM 待 spec）

---

## 10. 非目標

Phase 2 仍不做：

* UI
* 多使用者 / RBAC
* 雲端部署
* microservice
* 非文字素材（影片、音訊）
* API / MCP adapter

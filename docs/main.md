# Hybrid Knowledge System（LLM Wiki + Graph + Vector）

## 0. 定位

一個 **domain-agnostic knowledge system**

* 可用於 personal / team / enterprise
* 以 CLI 為入口
* 由 agent（OpenClaw / Codex / Claude Code）調用

---

## 1. 系統目標

建立一套：

* 可持續累積（persistent）
* 可結構推理（graph-based reasoning）
* 可高效檢索（vector retrieval）
* 可被多 agent 共用（tool interface）

---

## 2. 系統架構

### 2.1 分層

* Data Layer
  * raw_sources（immutable）
  * wiki（markdown）
  * graph（entity-relation）
  * vector（embedding）
* Processing Layer
  * ingestion pipeline
  * update engine（同步三層）
* Tool Layer
  * CLI（ks）
  * （未來）API / MCP adapter
* Agent Layer
  * routing
  * reasoning
  * tool orchestration

### 2.2 視覺參照

![LLM Wiki 概念示意](LLM%20wiki.png)

![LLM Wiki + Graphify 結合](LLM%20wiki%20Graphify.png)

![Graphify 流程](graphify.png)

---

## 3. CLI 設計（Phase 1 必做）

### 3.1 指令

```bash
ks ingest <file|dir>
ks query "<question>"
ks lint                # Phase 1 為 stub，Phase 3 才實作
```

### 3.2 輸出（統一 JSON）

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

---

## 4. Ingestion Pipeline（核心）

### 4.1 流程

1. parse
   * Phase 1：**txt / md / pdf**
   * Phase 2：docx / xlsx / pptx
   * Phase 3：png / jpg（OCR / VLM）
2. normalize（clean / chunk）
3. extract
   * entities（Phase 2）
   * relations（Phase 2）
   * key facts
4. update
   * wiki（新增 / 修改 / cross-link）
   * graph（Phase 2，新增節點與邊）
   * vector（embedding）

---

## 5. Query Routing（最重要）

### 5.1 Phase 1（rule-based，僅 wiki / vector 兩路）

* 「總結 / 說明 / 報告」→ wiki
* 「影響 / 關係 / 依賴 / 為什麼」→ vector（fallback，答案附註「深度關係推理將於 Phase 2 支援」）
* 「原文 / 細節 / 條款」→ vector

### 5.2 Phase 2（加入 graph，升級為 LLM-based）

* 「影響 / 關係 / 依賴 / 為什麼」→ graph
* routing 決策改由 LLM 判定

### 5.3 fallback

* 查不到 → vector
* 多來源 → merge

### 5.4 Route / Source 語意（JSON 輸出對應）

`trace.route` 表示**最終採用的主要路徑**；`source` 表示**實際取用到的知識層**（可為複數，反映 merge）。Phase 1 組合表：

| 情境 | `trace.route` | `source` |
|---|---|---|
| wiki 命中 | `wiki` | `["wiki"]` |
| wiki 空 → fallback vector | `vector` | `["vector"]` |
| wiki + vector 合併（wiki 主） | `wiki` | `["wiki","vector"]` |
| 純 vector（detail / 關係 fallback） | `vector` | `["vector"]` |

fallback 過程（rule 判定、wiki 未命中、切換 vector 等）一律寫入 `trace.steps`，供 agent 與除錯追蹤。Phase 1 `source` 與 `trace.route` **MUST NOT** 出現 `"graph"`。

---

## 6. Write-back

### Phase 1（半自動，預設開啟）

* query 結束後，若產生新知識 → **詢問使用者**是否回寫 wiki
* 使用者確認後，更新 index.md、記錄 log.md

### Phase 2（全自動）

* 高 confidence 答案自動回寫
* 自動建立 cross-link
* 使用者可關閉

---

## 7. Graph Schema（Phase 2）

先定義最小集合：

* Entity types：
  * Person
  * Project
  * Document
  * Event
  * Concept
* Relations：
  * owns
  * depends_on
  * impacts
  * references
  * belongs_to

---

## 8. 資料結構

```text
/ks
  /raw_sources                # immutable 原始檔
  /wiki
    index.md                  # TOC（所有 wiki 頁面索引）
    log.md                    # append-only query / write-back 紀錄
    /pages
      <slug>.md               # 實際 wiki 頁面（一檔一主題）
  /graph
    graph.json                # Phase 2 才建立；Phase 1 禁止寫入
  /vector
    db/                       # embedding store
  /manifest.json              # ingest idempotency 索引（path + sha256 → derived artifacts）
```

### 8.1 `wiki/index.md` 格式（Phase 1 最小版本）

純 TOC，每行一個 wiki 頁面：

```markdown
# Wiki Index

- [Page Title](pages/<slug>.md) — one-line summary
- [Another Page](pages/another.md) — one-line summary
```

### 8.2 `wiki/log.md` 格式（Phase 1 最小版本）

Append-only。每次 write-back 追加一筆：

```markdown
## 2026-04-23 14:32 | 專案A目前風險是什麼
- route: wiki
- source: [wiki, vector]
- pages touched: pages/project-a.md
- confidence: 0.87
```

### 8.3 Ingest idempotency

`manifest.json` 以 `raw_sources` 相對路徑為 key、內容 SHA256 為版本；重複 `ks ingest` 時：

* hash 未變 → 跳過
* hash 變更 → 覆寫該檔衍生的 wiki chunk 與 vector rows，並於 `log.md` 追加紀錄
* 檔案消失 → 可選 `--prune` 清除遺留 artifacts（Phase 1 預設不動）

---

## 9. 開發階段（必照順序）

### Phase 1（現在）

* [ ] 建 CLI（typer）
* [ ] 實作 `ks query`（rule-based routing，wiki / vector 兩路）
* [ ] 實作 `ks ingest`（支援 **txt / md / pdf**）
* [ ] wiki（markdown 寫入）
* [ ] vector（basic embedding）
* [ ] 半自動 write-back（詢問後回寫）
* [ ] `ks lint` stub（回「尚未實作」）

👉 不做 graph

---

### Phase 2

* [ ] graph extraction（entity / relation）
* [ ] graph query
* [ ] routing 升級（LLM-based）
* [ ] 全自動 write-back
* [ ] ingest 擴充：**docx / xlsx / pptx**

---

### Phase 3

* [ ] lint system 實作
* [ ] 多 agent 支援
* [ ] API / MCP adapter
* [ ] ingest 擴充：**png / jpg**（OCR / VLM）

---

## 10. 不做清單（MVP 及 Phase 2 一律不做）

* 不做 UI（CLI-only）
* 不做 多使用者 / RBAC
* 不做 雲端部署
* 不做 Microservice
* 不做 MCP adapter（Phase 3 再評估）
* 不做 非文字素材（影片、音訊）

---

## 11. 驗收標準（MVP）

完成以下才算成功：

* 能 ingest 10 份文件
* 能回答：
  * summary 類問題（wiki）
  * detail 類問題（vector）
* CLI 可被 agent 調用
* wiki 有持續成長（>20 pages）

---

## 12. 下一步（立即執行）

1. 建 repo（ks）
2. 實作 CLI skeleton
3. 寫第一版 routing（rule-based）
4. ingest 3 份文件測試
5. 調整輸出 JSON

---

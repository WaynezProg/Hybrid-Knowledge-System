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

* 仍是 Phase 3 stub

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

## 7. Out of Scope（直到 Phase 3 前都不做）

* UI
* 多使用者 / RBAC
* 雲端部署
* microservice
* API / MCP adapter
* 非文字素材（影片、音訊）

---

## 8. Roadmap

### Phase 1

* [x] CLI（query / ingest / lint-stub）
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

* [ ] lint system
* [ ] 多 agent
* [ ] API / MCP adapter
* [x] 圖片 ingest（`png / jpg / jpeg`；OCR-only）

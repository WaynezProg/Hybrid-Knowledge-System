# PRD — Hybrid Knowledge System (HKS)

## 1. 產品目標

提供一個可被 AI agent 使用的知識系統，讓使用者能：

* 快速得到穩定答案（非臨時拼湊）
* 查詢關係與影響（非純文字檢索）
* 隨使用逐步累積知識（非一次性回覆）

---

## 2. 使用者（Persona）

* 工程師：查專案/文件/規範
* PM / 管理層：問關係、風險、影響
* 個人使用者：筆記、研究、閱讀

---

## 3. 使用場景（Top 3）

1. 專案分析：
   「A 專案延遲會影響哪些系統？」
2. 文件理解：
   「這份規範的重點是什麼？」
3. 細節查詢：
   「條款 3.2 的原文是？」

---

## 4. 核心功能

### 4.1 Ingestion

* 支援格式（分階段）：
  * Phase 1：**txt / md / pdf**
  * Phase 2：docx / xlsx / pptx
  * Phase 3：png / jpg（OCR / VLM）
* 輸出：
  * wiki 更新
  * graph 建立（Phase 2）
  * vector embedding

### 4.2 Query

* CLI：`ks query "<q>"`
* routing（Phase 1，rule-based，**僅 wiki / vector 兩路**）：
  * summary → wiki
  * relation → vector（fallback，答案附註「深度關係推理將於 Phase 2 支援」）
  * detail → vector
* routing（Phase 2，加入 graph，升級為 LLM-based）：
  * relation → graph
  * routing 決策改由 LLM 判定

### 4.3 Write-back

* Phase 1（半自動，預設開啟）：
  * query 結束後詢問使用者是否回寫 wiki
  * 使用者確認後更新 index / log
* Phase 2（全自動）：
  * 高 confidence 答案自動回寫
  * 自動建立 cross-link
  * 使用者可關閉

### 4.4 Lint（Phase 3）

* 偵測：
  * 矛盾
  * 過時
  * orphan page
* 建議補資料
* Phase 1 僅提供 `ks lint` CLI stub（回「尚未實作」）

---

## 5. 非功能需求

* 本地優先（local-first）
* CLI-first（可被 agent 調用）
* 輸出穩定（JSON schema）

---

## 6. 成功指標（KPI）

* 查詢正確率（主觀評估 ≥ 80%）
* 平均查詢時間 < 3s（本地）
* wiki 成長速度（pages / week）
* 重複問題回答一致性

---

## 7. 範圍界定

### In Scope

* CLI 工具
* 本地知識管理
* 三層知識（wiki / graph / vector）

### Out of Scope（MVP 及 Phase 2 一律不做）

* UI（CLI-only）
* 多使用者 / RBAC
* 雲端部署
* Microservice
* MCP adapter（Phase 3 再評估）
* 非文字素材（影片、音訊）

---

## 8. 風險

* ingestion 品質不足 → 知識污染
* routing 錯誤 → 體驗下降
* graph schema 設計錯 → 無法推理

---

## 9. Roadmap

### Phase 1（MVP）

* CLI（query / ingest / lint-stub）
* wiki + vector
* rule-based routing（wiki / vector 兩路）
* ingest：txt / md / pdf
* 半自動 write-back

### Phase 2

* graph（entity / relation）
* LLM routing
* 全自動 write-back
* ingest 擴充：docx / xlsx / pptx

### Phase 3

* lint 實作
* 多 agent 整合
* API / MCP adapter
* ingest 擴充：png / jpg（OCR / VLM）

---

## 10. 驗收標準

* 可 ingest ≥ 10 份文件
* 可回答 summary / detail 問題
* CLI 可被 agent 調用
* wiki 持續成長（≥ 20 pages）

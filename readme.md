# README.md

## Hybrid Knowledge System (HKS)

一個 CLI-first、domain-agnostic 的知識系統，整合 **LLM Wiki（整理）+ Knowledge Graph（推理）+ Vector（搜尋）**，可被多種 agent（OpenClaw / Codex / Claude Code / Qwen Code）透過 CLI 使用。

---

## 為什麼要做

傳統 RAG 每次查詢都重新拼湊；HKS 在 **ingest 時就完成整理與關聯**，查詢時直接利用已累積的知識，穩定且可持續成長。

---

## 核心能力

* **Persistent Wiki**：自動摘要、cross-link、持續更新
* **Graph Reasoning**：entity / relation，支援依賴與影響分析
* **Vector Retrieval**：細節與原文補充
* **Write-back**：有價值的答案回寫成知識

---

## 架構概覽

```
Agent (OpenClaw / Codex / Claude)
        ↓ shell
       ks (CLI)
        ↓
--------------------------------
Core
- wiki (markdown)
- graph (entity-relation)
- vector (embedding)
- ingestion pipeline
--------------------------------
```

---

## 安裝（本地）

```bash
git clone <repo>
cd ks
uv sync
uv run ks --help
```

---

## CLI 使用

### Ingest

```bash
ks ingest ./docs
```

### Query

```bash
ks query "專案A目前風險是什麼"
```

### Lint（Phase 3 規劃中）

```bash
ks lint   # Phase 1 為 stub，尚未實作
```

---

## 輸出格式（JSON）

```json
{
  "answer": "...",
  "source": ["wiki","graph"],
  "confidence": 0.87,
  "trace": {
    "route": "wiki",
    "steps": []
  }
}
```

---

## 查詢路由

### Phase 1（rule-based，僅 wiki / vector 兩路）

* 總結/說明 → wiki
* 關係/影響 → vector（fallback，答案附註「深度關係推理將於 Phase 2 支援」）
* 細節/原文 → vector

### Phase 2（加入 graph，升級為 LLM-based）

* 關係/影響 → graph
* routing 決策改由 LLM 判定

---

## 專案結構

```
/ks
  /raw_sources
  /wiki
    index.md
    log.md
  /graph
    graph.json
  /vector
    db/
```

---

## 開發路線

* Phase 1：CLI + wiki + vector + rule routing + ingest(txt/md/pdf) + 半自動 write-back
* Phase 2：graph + LLM routing + 全自動 write-back + ingest(docx/xlsx/pptx)
* Phase 3：lint + multi-agent + API/MCP adapter + ingest(png/jpg)

---

## 非目標（MVP 及 Phase 2 一律不做）

* 不做 UI（CLI-only）
* 不做 多使用者 / RBAC
* 不做 雲端部署
* 不做 Microservice
* 不做 MCP adapter（Phase 3 再評估）
* 不做 非文字素材（影片、音訊）

---

## 貢獻

歡迎 PR，請先跑：

```bash
uv run pytest
```

---

## License

MIT

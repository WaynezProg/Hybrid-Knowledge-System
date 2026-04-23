# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

此 repo 目前**尚未有程式碼**，僅有設計文件。權威來源：

- [readme.md](readme.md) — 使用者面文件（CLI 概觀、安裝、路線圖）
- [docs/main.md](docs/main.md) — 系統設計（架構、routing、資料結構、phase）
- [docs/PRD.md](docs/PRD.md) — 產品規格（persona、場景、KPI、範圍）

開始實作前，請先對齊以上三份文件的 Phase 定義；三者敘述不一致時以 [docs/main.md](docs/main.md) 為準。

## Intended stack & commands

設計文件指定以 **Python + uv + typer** 實作 CLI 名為 `ks`。尚未 scaffold，但將來的標準指令為：

```bash
uv sync                   # 安裝依賴
uv run ks --help          # CLI 入口
uv run ks ingest <path>   # 索引文件
uv run ks query "<q>"     # 查詢
uv run ks lint            # Phase 1 為 stub
uv run pytest             # 測試（PR 前必跑，見 readme）
```

建立 `pyproject.toml` 時，entry point 應為 `ks = "<package>.cli:app"`（typer）。

## Architecture（big picture）

系統是 **CLI-first、domain-agnostic** 的知識系統，三層知識儲存以 ingestion pipeline 同步：

```
Agent ──shell──▶ ks (CLI) ──▶ Core
                               ├── wiki   (markdown,  /ks/wiki/{index.md,log.md})
                               ├── graph  (entity-rel, /ks/graph/graph.json)     [Phase 2]
                               └── vector (embedding,  /ks/vector/db/)
raw_sources (immutable) ──ingestion──▶ 三層同步更新
```

幾個跨檔案才看得懂的重點：

- **Ingestion 是「寫入時就整理」**：與傳統 RAG 差異在於 ingest 階段就做 parse → normalize → extract → update 三層，不是查詢時拼湊。修改 ingestion 必須同時考慮三層的同步。
- **Query routing 是分 phase 演進的契約**，不要跨 phase 實作：
  - Phase 1：**rule-based**，只有 wiki / vector 兩條路。關係/影響類問題走 vector fallback，並於輸出 `answer` 附註「深度關係推理將於 Phase 2 支援」。
  - Phase 2：加入 graph，routing 改由 LLM 判斷。
  - 未實作的路徑不要偷跑 —— Phase 1 出現 graph 程式碼屬於越界。
- **輸出 JSON schema 是穩定介面**（agent 會解析）：
  ```json
  {"answer": "...", "source": ["wiki","graph","vector"], "confidence": 0.0,
   "trace": {"route": "wiki|graph|vector", "steps": []}}
  ```
  任何變更都是對外 API 變更。
- **Write-back**：Phase 1 半自動（query 後詢問使用者是否回寫 wiki，更新 `index.md` + `log.md`），Phase 2 才自動。不要在 Phase 1 自動寫入。

## Phase discipline（重要）

路線嚴格分 Phase，不可跳做（[docs/main.md §9](docs/main.md) 明訂「必照順序」）：

| Phase | Ingest 格式 | Routing | Graph | Write-back |
|---|---|---|---|---|
| 1 (MVP) | txt / md / pdf | rule-based, wiki+vector | 無 | 半自動 |
| 2 | +docx / xlsx / pptx | LLM-based, +graph | 有 | 全自動 |
| 3 | +png / jpg (OCR/VLM) | — | — | — |

Phase 3 才做：`lint` 實作、多 agent、API / MCP adapter。

## Non-goals（MVP 與 Phase 2 一律不做）

收到涉及以下範圍的需求時，先指出與非目標衝突再處理：

- UI（CLI-only）
- 多使用者 / RBAC
- 雲端部署、Microservice
- MCP adapter（Phase 3 再評估）
- 非文字素材（影片、音訊）

## Graph schema（Phase 2 實作前確認）

最小集合，擴充前需更新 [docs/main.md §7](docs/main.md)：

- Entity：Person / Project / Document / Event / Concept
- Relation：owns / depends_on / impacts / references / belongs_to

## Language

文件與 commit message 使用 **Traditional Chinese (zh-TW)**；程式碼、識別字、技術術語維持英文。

# Hybrid Knowledge System (HKS)

[![ci](https://github.com/WaynezProg/Hybrid-Knowledge-System/actions/workflows/ci.yml/badge.svg)](https://github.com/WaynezProg/Hybrid-Knowledge-System/actions/workflows/ci.yml)

[English](./README.en.md)

CLI-first 的知識系統：把文件 ingest 成結構化 wiki / graph / vector，用 fused retrieval 回答問題。不是常駐服務，每次跑完就結束。

## 安裝

```bash
git clone https://github.com/WaynezProg/Hybrid-Knowledge-System.git
cd Hybrid-Knowledge-System

# 系統工具（macOS）
brew install tesseract tesseract-lang jq

# Python runtime（mise 管理）+ 套件（uv 管理）
mise install
uv sync

# 測試用 fixtures
make fixtures
```

> 只做文字 / Office ingest 可以先不裝 `tesseract`，遇到圖片 ingest 再補。

## Quick Start

```bash
# 1. 建立 runtime 目錄，設定環境
export KS_ROOT="$PWD/.hks-runs/demo/ks"
export HKS_EMBEDDING_MODEL=simple          # demo / CI 用；正式移除改用預設模型

# 2. Ingest 文件
uv run ks ingest tests/fixtures/valid

# 3. 查詢
uv run ks query "這批文件的重點是什麼" --writeback=no | jq .

# 4. 瀏覽已 ingest 的 source
uv run ks source list | jq .
```

`HKS_EMBEDDING_MODEL=simple` 適合 demo 與 CI。正式使用移除此設定，改用預設 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，或設 `HKS_EMBEDDING_MODEL=openai:text-embedding-3-small` 使用 OpenAI API。

## 使用方式

### Ingest

```bash
uv run ks ingest <file-or-dir>
```

支援 `txt`、`md`、`pdf`、`docx`、`xlsx`、`pptx`、`png`、`jpg`、`jpeg`。以 SHA256 + parser fingerprint 做 idempotency，重複 ingest 不會產生重複 artifact。圖片 ingest 需要本機 `tesseract`。

### Daily update workflow

```bash
# initial build
uv run ks ingest ./docs

# daily update
uv run ks update ./docs

# preview changes first
uv run ks update ./docs --dry-run

# update and rebuild derived graph
uv run ks update ./docs --profile derived-refresh

# remove deleted sources
uv run ks update ./docs --prune
```

`ingest` 是第一次建立 runtime；`update` 是日常同步。Authoritative source 仍是 `source-root` / raw files，update 會根據 manifest fingerprint 判斷 stale / new / missing。`watch` 是底層規劃與自動化 API；memory / agent event-sourcing 是未來功能，不在目前 scope。

### Query

```bash
uv run ks query "<question>" [--writeback auto|yes|no|ask]
```

所有 query 走 fused retrieval：同時從 wiki / graph / vector / page_tree 收集 candidates，以 LLM reranker 排序（無 API key 時 fallback RRF）。Response 包含 `evidence[]` 溯源。

Write-back 模式：
- `auto`（預設）：`writeback_eligible=true` 且 `calibrated_confidence >= 0.75` 時自動寫回 wiki
- `yes` / `no`：強制 / 禁止
- `ask`：TTY 互動詢問

> Agent / automation 建議一律帶 `--writeback=no`。

### Source Catalog & Workspace

```bash
uv run ks source list                         # 列出已 ingest 的 source
uv run ks source show project-atlas.txt       # 單筆 source 詳情

# 多 workspace 管理
export HKS_WORKSPACE_REGISTRY="$PWD/.hks-runs/workspaces.json"
uv run ks workspace register atlas --ks-root "$PWD/.hks-runs/atlas/ks" --label "Atlas"
uv run ks workspace query atlas "風險有哪些？" --writeback=no
```

### LLM Classification & Wiki Synthesis

```bash
# 對已 ingest source 產生 LLM extraction
uv run ks llm classify project-atlas.txt --provider fake --mode preview | jq .
uv run ks llm classify project-atlas.txt --provider fake --mode store

# 從 extraction 產生 wiki page
uv run ks wiki synthesize --source-relpath project-atlas.txt \
  --target-slug project-atlas-synthesis --mode store --provider fake
```

- `preview`：預覽，不寫入任何 layer
- `store`：寫 versioned artifact 到 `$KS_ROOT/llm/`
- 內建 `fake` provider 不需要 network；hosted provider 需要環境變數 opt-in

### Graphify

```bash
uv run ks graphify build --mode store --provider fake | jq .
```

從 wiki / graph 產生 derived knowledge graph、communities、互動式 HTML 儀表板、Markdown report。寫入 `$KS_ROOT/graphify/runs/`，不改 authoritative layers。

### Watch / Refresh

```bash
uv run ks watch scan --source-root <dir>                                    # 掃描變更
uv run ks watch run --source-root <dir> --mode execute --profile ingest-only # 執行 refresh
uv run ks watch status                                                       # 查看狀態
```

### Coordination（多 Agent）

```bash
uv run ks coord session start agent-a
uv run ks coord lease claim agent-a wiki:atlas --ttl-seconds 1800
uv run ks coord handoff add agent-a --summary "完成檢查" --next-action "請複核"
```

多 agent 共用同一 `$KS_ROOT` 時，先 claim lease 再寫入，用 handoff 記錄交接。

### Lint

```bash
uv run ks lint                    # read-only 檢查
uv run ks lint --strict           # 有 finding 則 exit 1
uv run ks lint --fix=apply        # 自動修復（rebuild index、prune orphans）
```

## Agent 接法

三種方式：

```bash
# 1. CLI（最簡單）
export KS_ROOT="$PWD/.hks-runs/my-runtime/ks"
uv run ks query "Project Atlas 風險？" --writeback=no

# 2. MCP stdio（支援 MCP 的 agent client 啟動）
uv run hks-mcp --transport stdio

# 3. HTTP（不支援 MCP 的工具）
uv run hks-api --host 127.0.0.1 --port 8766
```

<details>
<summary>MCP tools 清單</summary>

`hks_query`、`hks_ingest`、`hks_source_list`、`hks_source_show`、`hks_workspace_list`、`hks_workspace_register`、`hks_workspace_show`、`hks_workspace_remove`、`hks_workspace_use`、`hks_workspace_query`、`hks_lint`、`hks_llm_classify`、`hks_wiki_synthesize`、`hks_graphify_build`、`hks_pageindex_show`、`hks_pageindex_enrich`、`hks_watch_scan`、`hks_watch_run`、`hks_watch_status`、`hks_coord_session`、`hks_coord_lease`、`hks_coord_handoff`、`hks_coord_status`

</details>

<details>
<summary>HTTP endpoints 清單</summary>

`/query`、`/ingest`、`/catalog/sources`、`/catalog/sources/{relpath}`、`/workspaces`、`/workspaces/{workspace_id}`、`/workspaces/{workspace_id}/query`、`/lint`、`/llm/classify`、`/wiki/synthesize`、`/graphify/build`、`/pageindex/{relpath}`、`/pageindex/enrich`、`/watch/scan`、`/watch/run`、`/watch/status`、`/coord/session`、`/coord/lease`、`/coord/handoff`、`/coord/status`

</details>

## 輸出格式

所有指令共用同一 JSON shape：

```json
{
  "answer": "...",
  "source": ["graph"],
  "confidence": 0.88,
  "retrieval_score": 0.88,
  "calibrated_confidence": 0.88,
  "writeback_eligible": true,
  "evidence": [
    {"source_relpath": "atlas.txt", "route": "graph", "quote": "Atlas depends on Mobile Gateway..."}
  ],
  "trace": {
    "route": "graph",
    "steps": [
      {"kind": "routing_model", "detail": {}},
      {"kind": "wiki_lookup", "detail": {"hit": false}},
      {"kind": "graph_lookup", "detail": {"hit": true, "relpaths": ["atlas.txt"]}},
      {"kind": "vector_lookup", "detail": {}},
      {"kind": "rerank", "detail": {"strategy": "rrf", "status": "primary"}},
      {"kind": "merge", "detail": {"strategy": "rrf", "candidate_count": 3}}
    ]
  }
}
```

- `confidence`：raw retrieval score；`retrieval_score` 等值保留給未來遷移
- `calibrated_confidence` + `writeback_eligible`：`auto` write-back 的實際 gate
- `evidence[]`：溯源資訊，含 `source_relpath`、`route`、`quote`
- `trace.steps`：pipeline 每一步的記錄
- 無命中時 `source=[]`，仍 exit `0`

## Exit Code

| Code | 意義 |
|------|------|
| `0` | 成功（含 query 無命中） |
| `1` | 一般錯誤 |
| `2` | CLI usage error |
| `65` | Ingest data error |
| `66` | 輸入不存在或 `KS_ROOT` 未初始化 |

## 設定

完整設定見 [docs/configuration.md](./docs/configuration.md)。

**常用環境變數：**

| 變數 | 預設 | 說明 |
|------|------|------|
| `KS_ROOT` | `./ks` | Runtime 資料根目錄 |
| `HKS_EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Embedding backend；CI 用 `simple` |
| `HKS_LLM_PROVIDER` | `fake` | LLM provider；`openai` 需另設 API key |
| `HKS_LLM_NETWORK_OPT_IN` | — | 設為 `1` 才允許非 fake provider |
| `HKS_LLM_PROVIDER_OPENAI_API_KEY` | — | OpenAI API key |
| `HKS_WRITEBACK_AUTO_THRESHOLD` | `0.75` | Auto write-back calibrated confidence floor；仍需 `writeback_eligible=true` |
| `HKS_WORKSPACE_REGISTRY` | user config path | Workspace registry JSON 路徑 |

結構化設定檔用 `config/hks.yaml`（從 `config/hks.yaml.example` 複製）。讀取優先序：process env > `config/hks.env` > `config/hks.yaml` / `config/hks.json` > default。

## Using with Obsidian

`$KS_ROOT/wiki/` 可直接用 Obsidian 的 `Open folder as vault` 開啟，不需要 plugin。人工筆記不要放進 `wiki/pages/`（HKS 會讀取並解析該目錄所有 `*.md`），建議放在 `$KS_ROOT/wiki/manual/`、`$KS_ROOT/wiki/notes/`，或使用獨立 vault。

完整說明見 [docs/obsidian.md](./docs/obsidian.md)。

## 開發

```bash
uv run pytest --tb=short -q
uv run pytest tests/eval/test_golden_retrieval_quality.py -q
uv run ruff check .
uv run mypy src/hks
```

## 進一步文件

<details>
<summary>Spec 目錄</summary>

- [specs/001-phase1-cli-mvp/spec.md](./specs/001-phase1-cli-mvp/spec.md) — Phase 1 基線
- [specs/002-phase2-ingest-office/spec.md](./specs/002-phase2-ingest-office/spec.md) — Office ingest
- [specs/003-phase2-graph-routing/spec.md](./specs/003-phase2-graph-routing/spec.md) — Graph / routing / write-back
- [specs/004-phase3-image-ingest/spec.md](./specs/004-phase3-image-ingest/spec.md) — Image ingest
- [specs/005-phase3-lint-impl/spec.md](./specs/005-phase3-lint-impl/spec.md) — Lint system
- [specs/006-mcp-api-adapter/spec.md](./specs/006-mcp-api-adapter/spec.md) — MCP / API adapter
- [specs/007-multi-agent-support/spec.md](./specs/007-multi-agent-support/spec.md) — Multi-agent support
- [specs/008-llm-classification-extraction/spec.md](./specs/008-llm-classification-extraction/spec.md) — LLM classification / extraction
- [specs/009-llm-wiki-synthesis/spec.md](./specs/009-llm-wiki-synthesis/spec.md) — Wiki synthesis
- [specs/010-graphify-pipeline/spec.md](./specs/010-graphify-pipeline/spec.md) — Graphify pipeline
- [specs/011-continuous-watch/spec.md](./specs/011-continuous-watch/spec.md) — Watch / re-ingest
- [specs/012-source-catalog/spec.md](./specs/012-source-catalog/spec.md) — Source catalog / workspace
- [specs/005-phase3-lint-impl/contracts/query-response.schema.json](./specs/005-phase3-lint-impl/contracts/query-response.schema.json) — Response contract
- [specs/ARCHIVE.md](./specs/ARCHIVE.md) — Archive index

</details>

## License

MIT

# Hybrid Knowledge System (HKS)

[![ci](https://github.com/WaynezProg/Hybrid-Knowledge-System/actions/workflows/ci.yml/badge.svg)](https://github.com/WaynezProg/Hybrid-Knowledge-System/actions/workflows/ci.yml)

[English](./README.en.md)

CLI-first 的知識系統：把文件 ingest 成結構化 wiki / graph / vector，用 fused retrieval 回答問題。不是常駐服務，每次跑完就結束。

## 需求

| 需要 | 用途 | 說明 |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 安裝與執行 | 會自動下載 Python 3.12，不必自己裝 |
| Python 3.12 | 只有用 pip 而不用 uv 時 | 3.13 以上會被 `requires-python` 拒絕 |
| 約 1 GB 磁碟空間 | 套件（含 torch） | |
| `tesseract` 與 `eng`、`chi_tra` 語言包（選用） | 只有 ingest 圖片（png／jpg）時 | macOS：`brew install tesseract tesseract-lang`；Ubuntu：`sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-tra` |
| 預設 embedding model（選用） | 不設 `HKS_EMBEDDING_MODEL` 時 | 第一次使用會下載約 450 MB |
| OpenAI API key（選用） | `openai:text-embedding-3-small`、LLM reranker | |

pdf、docx、xlsx、pptx 不需要 LibreOffice 或 poppler。範例用到的 `jq` 只是排版用。

## 安裝

當成指令安裝（套件名是 `hks`，指令是 `ks`、`hks-mcp`、`hks-api`）：

```bash
uv tool install git+https://github.com/WaynezProg/Hybrid-Knowledge-System
ks --help
```

從 checkout 執行（開發、跑測試）：

```bash
git clone https://github.com/WaynezProg/Hybrid-Knowledge-System.git
cd Hybrid-Knowledge-System
uv sync
uv run ks --help
```

以下範例以 checkout 為準（`uv run ks …`）；用安裝好的指令時去掉 `uv run`。離線重建環境（套件已在 uv cache）：`uv sync --offline`。

## Quick Start

不需要 API key，也不需要 `tesseract`：

```bash
# 1. runtime 輸出目錄（不要和來源文件放在一起），以及試用的 embedding
export KS_ROOT="$PWD/.hks-runs/demo/ks"
export HKS_EMBEDDING_MODEL=simple

# 2. Ingest 範例文件
uv run ks ingest examples/quickstart

# 3. 查詢
uv run ks query "Atlas 有哪些風險？" --writeback=no | jq '{answer, source, confidence, evidence}'
uv run ks query "ERR-4012 怎麼修" --writeback=no | jq '{answer, source, confidence}'

# 4. 看已 ingest 的 source，並檢查知識庫是否一致
uv run ks source list | jq '[.trace.steps[0].detail.sources[].relpath]'
uv run ks lint | jq -r .answer
```

怎麼讀輸出：

- stdout 一律是 JSON；出錯時 stderr 另有一行說明。
- `ks query`：`answer` 是命中的原文片段（不是 LLM 生成的回答），`source` 是作答的 route（`wiki`／`graph`／`vector`／`lexical`／`page_tree`），`evidence[]` 是出處。沒有命中時 `source` 為 `[]`、exit code 仍是 0。
- `ks ingest`、`ks lint`、`ks source`：摘要在 `answer`，明細在 `trace.steps[0].detail`。

換成正式的 embedding：

- 本機 model：不設 `HKS_EMBEDDING_MODEL`，使用預設的 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`。
- OpenAI：`HKS_EMBEDDING_MODEL=openai:text-embedding-3-small` 加上 `HKS_OPENAI_API_KEY`。
- **一個 `KS_ROOT` 只用一種 embedding model。** 換 model 要換一個新的 `KS_ROOT` 重新 ingest；沿用舊的不會報錯，但 vector 查詢會查不到。
- 設定檔：`cp config/hks.yaml.example config/hks.yaml`，只在 repo 根目錄執行時會被讀到；`uv run python -m hks.core.config --shell` 可以確認實際生效的設定。細節見 `docs/configuration.md`。
- Keyword 檢索的模式：`HKS_HYBRID_SEARCH=route|fused|off`（預設 `route`）。

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

所有 query 走 fused retrieval：同時從 wiki / graph / vector / lexical / page_tree 收集 candidates，以 LLM reranker 排序（無 API key 時 fallback RRF）。Response 包含 `evidence[]` 溯源。

除了 embedding，query 也做 BM25 keyword 檢索：embedding 沒帶出、但逐字含有問句關鍵詞（名稱、ID、錯誤碼）的內容會以 `lexical` route 成為候選，所以 `source` 可能是 `lexical`。
含 `今天` / `昨天` / `today` / `yesterday` / `YYYY-MM-DD` 的 session-memory 查詢會優先命中對應 date 的 session daily source，避免被一般 graph/vector 內容搶答。

> LLM reranker 僅在 `HKS_LLM_NETWORK_OPT_IN=1` 且 OpenAI key 齊備時啟用；啟用時會將 question 與候選 snippet（每筆截斷 200 字，含 wiki / graph / vector 命中內容）送至 hosted endpoint。未 opt-in 一律走 local RRF，不外送任何內容。

Write-back 模式：
- `no`（預設）：不回寫
- `auto`：顯式 opt-in；`writeback_eligible=true` 且 route-specific `auto_threshold` 通過時自動寫回 wiki
- `yes` / `no`：強制 / 禁止
- `ask`：TTY 互動詢問

> Agent / automation 可省略 `--writeback`；需要自動沉澱時才顯式帶 `--writeback=auto`。

### Source Catalog & Workspace

```bash
uv run ks source list                         # 列出已 ingest 的 source
uv run ks source show project-atlas.txt       # 單筆 source 詳情

# 多 workspace 管理
export HKS_WORKSPACE_REGISTRY="$PWD/.hks-runs/workspaces.json"
uv run ks workspace register atlas --ks-root "$PWD/.hks-runs/atlas/ks" --label "Atlas"
uv run ks workspace query atlas "風險有哪些？" --writeback=no
```

多知識庫路徑擺放原則：每個知識庫一個獨立 `$KS_ROOT`，source files 不要放進 `$KS_ROOT`，workspace registry 放在所有 runtime 外面。

```text
project/
  sources/
    atlas/
    borealis/
  .hks-runs/
    atlas/ks/
    borealis/ks/
    workspaces.json
```

```bash
export HKS_WORKSPACE_REGISTRY="$PWD/.hks-runs/workspaces.json"
KS_ROOT="$PWD/.hks-runs/atlas/ks" uv run ks ingest "$PWD/sources/atlas"
KS_ROOT="$PWD/.hks-runs/borealis/ks" uv run ks ingest "$PWD/sources/borealis"
uv run ks workspace register atlas --ks-root "$PWD/.hks-runs/atlas/ks" --label "Atlas" --force
uv run ks workspace register borealis --ks-root "$PWD/.hks-runs/borealis/ks" --label "Borealis" --force
```

`ks workspace use <id>` 只回傳 shell-safe `export KS_ROOT=...`，不會改 parent shell；agent automation 建議直接用 `ks workspace query <id> ...`。

### PageIndex

```bash
uv run ks pageindex show project-atlas.txt | jq .
uv run ks pageindex enrich --source-relpath project-atlas.txt --mode preview --provider fake | jq .
```

Ingest 會產生 `$KS_ROOT/page_trees/*.json`；query 會把 page_tree summary 納入 fused retrieval，回傳 evidence 時可帶 `section_path` / `page_range`。

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

# 3. HTTP（不支援 MCP 的工具）；除了 /catalog/* 以外的 endpoint 都要 token，全部是 POST
export HKS_API_TOKEN='replace-with-local-token'
uv run hks-api --host 127.0.0.1 --port 8766
curl -sS http://127.0.0.1:8766/query \
  -H "Authorization: Bearer $HKS_API_TOKEN" -H 'content-type: application/json' \
  -d '{"question":"Project Atlas 風險？","writeback":"no","ks_root":null}'
```

MCP client 的設定檔（`mcp/config/stdio.mcp.json`）裡的 `cwd` 與 `KS_ROOT` 要改成絕對路徑。

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

- `confidence`：query 命中時取自 `calibrated_confidence`；top-level shape 相容欄位
- `retrieval_score`：raw retrieval score（未經 clamp）
- `calibrated_confidence` + `writeback_eligible`：`auto` write-back 的實際 gate；`calibrated_confidence` 目前為 `retrieval_score` clamp 至 `[0,1]`
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
| `HKS_WRITEBACK_AUTO_THRESHOLD` | `0.75` | Legacy auto write-back fallback；有 `ConfidenceAssessment` 時以 route-specific `auto_threshold` 為準，且仍需 `writeback_eligible=true` |
| `HKS_HYBRID_SEARCH` | `route` | Keyword 檢索模式：`route` 讓 embedding 沒帶出的 keyword 命中自成 `lexical` route；`fused` 把 BM25 併入 vector route；`off` 只用 dense |
| `HKS_HYBRID_MAX_CHUNKS` | `20000` | chunk 數超過此值時略過 keyword 檢索（query 時即時計算，無落地索引） |
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

- [docs/architecture.md](./docs/architecture.md) — 架構圖、ingest / query 流程圖、query 時序圖

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
- [specs/013-pageindex-integration/spec.md](./specs/013-pageindex-integration/spec.md) — PageIndex / page_tree
- [specs/019-writeback-review-queue/spec.md](./specs/019-writeback-review-queue/spec.md) — Write-back review queue 設計（待實作）
- [specs/005-phase3-lint-impl/contracts/query-response.schema.json](./specs/005-phase3-lint-impl/contracts/query-response.schema.json) — Response contract
- [specs/ARCHIVE.md](./specs/ARCHIVE.md) — Archive index

</details>

## License

MIT

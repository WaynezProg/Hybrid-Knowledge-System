# Implementation Plan: HKS Phase 1 MVP — CLI 骨架與核心知識流程

**Branch**: `001-phase1-cli-mvp` | **Date**: 2026-04-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-phase1-cli-mvp/spec.md`

## Summary

交付 `ks` CLI 的 MVP：以 `typer` 為入口實作 `ingest / query / lint-stub` 三指令；ingestion pipeline 在寫入階段以 `pypdf` / `markdown-it-py` 解析 txt·md·pdf，產出 `wiki/pages/<slug>.md`（`python-slugify` 處理非 ASCII + 後綴碰撞）與 `chromadb` 向量（`sentence-transformers` 多語 MiniLM 模型，local-first），以 `manifest.json` 搭 SHA256 做 idempotency；query 走 `ruamel.yaml` 讀取的 `config/routing_rules.yaml`，rule-based 選 wiki / vector；write-back 以 `isatty` + `--writeback=yes|no|ask` 雙軌決策；所有對外 JSON 透過 `jsonschema` 執行時驗證；exit code 採 BSD sysexits 子集。Phase 1 實作範圍嚴格排除 graph 相關 code paths 與 dependencies。

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`（mise 管理；`pyproject.toml` 宣告 `requires-python`）
**Primary Dependencies**:
- CLI: `typer`
- Parsers: `pypdf`（PDF）、`markdown-it-py`（md）、stdlib（txt）
- Embedding: `sentence-transformers`（預設模型 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，CPU-only）
- Vector DB: `chromadb`（PersistentClient，檔案型）
- YAML: `ruamel.yaml`（保留註解 / 順序）
- Slug: `python-slugify`
- Schema 驗證: `jsonschema`
- Test: `pytest` + `pytest-cov`
- Lint / format: `ruff`
- Type check: `mypy` strict
**Storage**:
- 檔案系統 `/ks/` 為 runtime 資料根（`raw_sources/`、`wiki/`、`vector/db/`、`manifest.json`）
- `/ks/graph/` **禁止建立**（憲法 §I）
- `config/routing_rules.yaml` 在 repo 內、`/ks/config/routing_rules.yaml` 於 runtime 可覆寫
**Testing**: `pytest`（unit / integration / contract）；契約測試用 `jsonschema` 對 CLI stdout 做 schema 驗證；覆蓋率 ≥ 80%（由 `pyproject.toml [tool.coverage]` 門檻把關）
**Target Platform**: macOS / Linux CLI（本 feature 主機測試平台為 macOS 15 arm64、Linux x86_64）；離線可執行
**Project Type**: CLI（單一 package，非 web / mobile）
**Performance Goals**:
- 查詢 p95 延遲 < 3s（已 ingest 50 份文件、commodity laptop）
- 重複 ingest 至少比首次快 ≥ 50%（idempotent skip）
- 首次啟動允許下載 embedding 模型（~ 118 MB，由 `sentence-transformers` 自動快取至 `~/.cache`）
**Constraints**:
- Local-first；無網路環境下除首次下載 embedding 模型外必須可跑（允許預打包模型；`HKS_EMBEDDING_MODEL` 可指向本機路徑）
- 單進程（lock 檔拒絕並發）
- 單檔 200 MB 上限（`HKS_MAX_FILE_MB` 可調）
- JSON 輸出 100% 符合憲法 §II schema
- `source` / `trace.route` **MUST NOT** 含 `"graph"`
**Scale/Scope**:
- MVP 驗收：≥ 10 份 ingest、≥ 20 wiki pages（ingest + write-back 合計）
- Phase 1 預期語料規模 ≤ 數百份文件（個人 / 小團隊使用）
- Chunking：512 token / 64 token overlap（以 MiniLM tokenizer 計）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

本 feature 對憲法 1.1.0 §I–§V 的遵守方式如下。初檢於 Phase 0 前完成；Phase 1 設計產出後再檢（見文末 Post-Design Re-Check）。

### §I Phase Discipline — ✅ PASS

- `hks/` package 下無 `graph/` 子套件；dependencies 清單無任何 graph DB（neo4j / nebula / networkx 皆不引入）。
- `routing/router.py` 為 rule-based，**不做** LLM routing；`writeback/gate.py` 為半自動，**不做** 自動寫入。
- 資料層禁止 `/ks/graph/` 目錄建立，由 `core/paths.py` 常數定義白名單。
- `chromadb` 為 vector-only，與 graph 無涉（驗證於 `research.md` §Vector DB）。

### §II Stable Output Contract — ✅ PASS

- JSON schema 由 [`contracts/query-response.schema.json`](./contracts/query-response.schema.json) 固化；`core/schema.py` 提供 `QueryResponse` dataclass + `to_json()` 序列化。
- 所有 CLI 指令返回路徑在 `cli.py` 統一經過 `jsonschema.validate()` 閘門（契約測試與 runtime assert 共用同一份 schema）。
- Exit code 由 `errors.py` 的 `ExitCode` IntEnum 提供，對應表於 [`contracts/cli-exit-codes.md`](./contracts/cli-exit-codes.md)。
- `source` 與 `trace.route` 的 enum 值在 schema 中限制為 `"wiki" | "vector"`（Phase 1），graph 不在允許集合。

### §III CLI-First & Domain-Agnostic — ✅ PASS

- 僅 `ks` CLI 入口；無 web / TUI / REST server。
- 無雲端依賴；`sentence-transformers` 模型首次執行下載後可 offline。
- 領域詞彙外部化於 `config/routing_rules.yaml`；程式碼不 hard-code 關鍵字（FR-020）。

### §IV Ingest-Time Organization — ✅ PASS

- `ingest/pipeline.py` 單一 orchestrator，內部序列 `parse → normalize → extract → update(wiki, vector)` 四階段。
- `query` path 僅讀取 wiki / vector；不得重新 parse / chunk / extract 來源文件。若走 vector route，僅允許對 query 本身做一次 embedding（驗證於 pytest `tests/integration/test_query_no_reparse.py`）。
- 三層一致性由 `manifest.json` 承擔；中斷回復於 `ingest/pipeline.py` 的 `resume_or_rebuild()`。

### §V Write-back Safety — ✅ PASS

- `writeback/gate.py` 的 `decide()` 函式依 `--writeback` flag + `sys.stdout.isatty()` 決策，無任何 confidence-based 自動分支。
- 每筆回寫落在 `wiki/log.md` 與 `trace.steps`，提供可追溯紀錄（FR-033）。
- `--writeback=yes` 屬顯式使用者意圖，非自動；仍符合 §V「使用者明確確認」語意。

**Gate 結果**：全數 PASS，無需 Complexity Tracking 豁免。

## Project Structure

### Documentation (this feature)

```text
specs/001-phase1-cli-mvp/
├── plan.md                   # 本文件（/speckit.plan 產出）
├── spec.md                   # /speckit.specify 產出
├── research.md               # Phase 0 產出（選型短評）
├── data-model.md             # Phase 1 產出（資料模型）
├── quickstart.md             # Phase 1 產出（本機 setup）
├── contracts/
│   ├── query-response.schema.json   # §II JSON schema（jsonschema 可驗證）
│   └── cli-exit-codes.md            # exit code 契約
├── checklists/
│   └── requirements.md       # /speckit.specify 產出
└── tasks.md                  # Phase 2 產出（/speckit.tasks，本指令不建立）
```

### Source Code (repository root)

```text
.
├── pyproject.toml            # requires-python, dependencies, ruff/mypy/pytest config
├── uv.lock                   # uv 鎖定（由 uv 產出、commit）
├── .python-version           # mise / pyenv 讀取
├── .mise.toml                # 指定 python 版本
├── src/
│   └── hks/                  # package root（src-layout）
│       ├── __init__.py
│       ├── cli.py            # typer app, 綁定 sub-commands
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── ingest.py
│       │   ├── query.py
│       │   └── lint.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── schema.py     # QueryResponse / TraceStep dataclass + JSON codec
│       │   ├── manifest.py   # manifest.json I/O + SHA256 idempotency
│       │   └── paths.py      # /ks/ 路徑常數與初始化（含 graph 路徑黑名單 assert）
│       ├── ingest/
│       │   ├── __init__.py
│       │   ├── parsers/
│       │   │   ├── __init__.py
│       │   │   ├── txt.py
│       │   │   ├── md.py
│       │   │   └── pdf.py
│       │   ├── normalizer.py
│       │   ├── extractor.py  # 產出 wiki page + vector chunk（ingest-time organization）
│       │   └── pipeline.py   # orchestration + resume_or_rebuild
│       ├── routing/
│       │   ├── __init__.py
│       │   ├── rules.py      # routing_rules.yaml 載入（ruamel.yaml）
│       │   └── router.py     # Phase 1 rule-based；Phase 2 會整個換掉
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── wiki.py       # index.md, log.md, pages/ 寫入
│       │   └── vector.py     # chromadb PersistentClient 封裝
│       ├── writeback/
│       │   ├── __init__.py
│       │   ├── gate.py       # TTY 偵測 + --writeback flag 決策
│       │   └── writer.py
│       └── errors.py         # ExitCode IntEnum + KSError 階層
├── config/
│   └── routing_rules.yaml    # rule-based routing 關鍵字表（中 / 英）
├── tests/
│   ├── fixtures/             # valid/ 10 份合法樣本；broken/ + oversized/ + skip cases
│   ├── unit/
│   │   ├── core/
│   │   ├── ingest/
│   │   ├── routing/
│   │   └── writeback/
│   ├── integration/
│   │   ├── test_ingest_basic.py
│   │   ├── test_ingest_edge_cases.py
│   │   ├── test_query_summary.py
│   │   ├── test_query_no_reparse.py
│   │   ├── test_writeback_non_tty.py
│   │   └── ...
│   └── contract/
│       ├── test_json_schema.py    # 以 contracts/query-response.schema.json 驗 stdout
│       └── test_exit_codes.py
├── readme.md
├── CLAUDE.md
├── LICENSE
├── .gitignore
├── docs/                     # 設計文件（既存）
└── specs/001-phase1-cli-mvp/ # 本 feature 之 spec / plan / artifacts
```

**Structure Decision**：採 **src-layout 單一 package**（`src/hks/`）。理由：

1. **src-layout** 隔離 import 污染（測試時必經安裝，避免 import to cwd 的假陽性）；這對 CLI 套件尤重要，因為 `ks` 指令會以已安裝的方式執行。
2. **單一 package** 而非 monorepo：spec 範圍限 CLI，無 web / mobile / 多語言；Project Type 為 `cli`。
3. **子套件依領域切分**（commands / core / ingest / routing / storage / writeback），對應 §IV 的 pipeline 分層與憲法 §III 的 domain-agnostic 配置點。
4. `config/routing_rules.yaml` 置於 repo 根下（而非 `src/hks/` 內）是為了讓使用者能以 `/ks/config/routing_rules.yaml` 在 runtime 覆寫；`routing/rules.py` 依序查找：`/ks/config/` → env `HKS_ROUTING_RULES` → package 內建 `config/`。

## Complexity Tracking

無違反。Constitution Check 全數 PASS，毋須列舉豁免。

---

## Post-Design Re-Check（Phase 1 設計產出後）

Phase 1 交付 [research.md](./research.md)、[data-model.md](./data-model.md)、[contracts/query-response.schema.json](./contracts/query-response.schema.json)、[contracts/cli-exit-codes.md](./contracts/cli-exit-codes.md)、[quickstart.md](./quickstart.md) 後，再次核驗憲法 §I–§V：

- **§I**：確認 `data-model.md` 無 Entity 涉及 graph 概念；`research.md` §Vector DB 驗證 chromadb 單純為 embedding store。**PASS**。
- **§II**：`contracts/query-response.schema.json` 使用 JSON Schema Draft 2020-12；`source` items 以 `enum: ["wiki","vector"]` 限制；`trace.route` 同。`contracts/cli-exit-codes.md` 列出 0/1/2/65/66 完整契約。**PASS**。
- **§III**：`research.md` 所有選型皆為 pure-Python 或提供 offline 模式；`routing_rules.yaml` 樣板不含任何領域關鍵字。**PASS**。
- **§IV**：`data-model.md` 的 Manifest Entry 定義 `derived.wiki_pages[]` 與 `derived.vector_ids[]`，ingestion 同步更新；查詢模型無 parse 欄位。**PASS**。
- **§V**：`data-model.md` 的 Log Entry 強制 `route`/`source`/`confidence`/`pages_touched`，成為 write-back 可追溯紀錄。**PASS**。

**Post-Design 結果**：全數 PASS。可進入 `/speckit.tasks`。

## Final Constitution Audit（2026-04-24）

- **§I PASS**：runtime JSON 契約測試與 `tests/contract/test_no_graph_in_src.py` 皆限制 Phase 1 僅有 wiki / vector；`/ks/` 路徑防線改為白名單，避免殘留任何 graph runtime code path。
- **§II PASS**：`uv run pytest --tb=short -q` 仍維持 contract / integration 全綠；錯誤與成功輸出皆為穩定 JSON schema。
- **§III PASS**：quickstart 補上本機模型路徑與 `HKS_EMBEDDING_MODEL=simple` 的 local-first 操作路徑；CLI 仍是唯一入口。
- **§IV PASS**：query walkthrough 仍只讀 wiki / vector，沒有重新 parse 原始文件；ingest idempotency 測試補齊第二次執行的 artifact 與耗時檢查。
- **§V PASS**：TTY / non-TTY / `--writeback` override 依 quickstart 與既有整合測試驗證，沒有 confidence-based 自動回寫分支。

**Complexity Tracking**：無新增豁免。
**Spec Status**：`spec.md` 已為 `Complete`，本輪無需再改。

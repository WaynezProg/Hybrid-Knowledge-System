---
description: "Task list for HKS Phase 1 MVP"
---

# Tasks: HKS Phase 1 MVP — CLI 骨架與核心知識流程

**Input**: [spec.md](./spec.md) · [plan.md](./plan.md) · [research.md](./research.md) · [data-model.md](./data-model.md) · [contracts/](./contracts/) · [quickstart.md](./quickstart.md)

**Tests**: 依使用者要求「測試先行」，TDD 流程於每個 user story 內部先建測試 skeleton、再進實作。

**Organization**: 依 spec.md user story priority 分組（US1/US2=P1, US3=P2, US4=P3）；每組內先測試、再實作、最後 checkpoint。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可平行（不同檔案且無未完成前置依賴）
- **[Story]**: 僅用於 user story 階段（US1 / US2 / US3 / US4）；Setup / Foundational / Polish 不帶 story label
- 任務尾端附 **FR / SC / 憲法 § 編號**以利追溯

## Path Conventions

CLI 單一 package（`cli`）+ src-layout：
- 程式碼：`src/hks/`
- 測試：`tests/{unit,integration,contract,fixtures}/`
- 配置：`config/`、`pyproject.toml`、`.mise.toml`、`.python-version`
- 設計文件：`specs/001-phase1-cli-mvp/`

---

## Phase 1: Setup（腳手架）

**Purpose**: 專案初始化、依賴鎖定、pytest marker、fixtures 語料

- [x] T001 [P] 建立 `.mise.toml` 指定 `python = "3.12"`（sec: mise 管理）
- [x] T002 [P] 建立 `.python-version` 內容為 `3.12`（sec: pyenv / mise 相容）
- [x] T003 建立 `pyproject.toml`：宣告 package metadata、`requires-python = ">=3.12,<3.13"`、entry point `ks = "hks.cli:app"`、runtime deps（`typer`, `pypdf`, `markdown-it-py`, `sentence-transformers`, `chromadb`, `ruamel.yaml`, `python-slugify`, `jsonschema`）、dev deps（`pytest`, `pytest-cov`, `ruff`, `mypy`）、`[tool.ruff]` / `[tool.mypy] strict = true` / `[tool.pytest.ini_options] markers = ["us1","us2","us3","us4","unit","integration","contract"]` / `[tool.coverage.report] fail_under = 80` —（FR-061, SC-009, research §1/§3/§10/§11）
- [x] T004 執行 `uv sync` 產生 `uv.lock` 並 commit（依賴 T003）—（FR-061, research §1）
- [x] T005 [P] 建立 `src/hks/` package 骨架：`__init__.py`、`cli.py`（最小 typer app）、空子套件 `commands/`、`core/`、`ingest/`、`ingest/parsers/`、`routing/`、`storage/`、`writeback/` 各帶 `__init__.py` —（plan §Project Structure）
- [x] T006 [P] 建立 `config/routing_rules.yaml` 樣板：依 [data-model.md §7](./data-model.md) 放 summary / relation / detail 三條 rule、中英 keyword、`default_route: vector`、`version: 1` —（FR-020, FR-052, §III）
- [x] T007 [P] 置入分層 fixtures 目錄（避免合法與異常混在同一集）：
  - `tests/fixtures/valid/` 放 **10 份合法樣本**：3 × txt、3 × md、4 × 正常 PDF（供 T021/T022/T023 等預期全成功情境；對應 SC-001「至少 2 PDF、3 md、3 txt」）
  - `tests/fixtures/broken/broken.pdf` 1 份壞 PDF（供 T024 broken case）
  - `tests/fixtures/oversized/` 1 份超大檔樣本；大小驗證以 `HKS_MAX_FILE_MB=1` + monkeypatch 模擬即可，避免 repo 膨脹（供 T024 oversized case）
  - `tests/fixtures/skip/` 放 unsupported 副檔名與空檔 / whitespace 檔（供 T024 skip cases）
  —（SC-001, US1 Acceptance 4, edge case）
- [x] T008 [P] 建立 `tests/` 目錄結構與 `conftest.py`：提供 `tmp_ks_root` fixture、`cli_runner` fixture、marker 註冊 —（plan §Project Structure, FR-061）
- [x] T009 [P] 建立 `Makefile`（或等效 `scripts/dev.sh`）提供 `make test / lint / typecheck / coverage` 一鍵指令 —（DX）

**Checkpoint**: `uv run ks --help` 可顯示（即使三個 subcommand 為 stub）；`uv run pytest` 零錯誤（未收任何測試）；`uv run ruff check .` 通過。

---

## Phase 2: Foundational（共用基石，阻塞所有 US）

**⚠️ CRITICAL**: 本階段未完成前，US1–US4 任何任務皆不得開工。

- [x] T010 實作 `src/hks/errors.py`：`ExitCode` IntEnum（`OK=0, GENERAL=1, USAGE=2, DATAERR=65, NOINPUT=66`）+ `KSError` 階層 —（FR-003, §II 附屬, [contracts/cli-exit-codes.md](./contracts/cli-exit-codes.md)）
- [x] T011 [P] 實作 `src/hks/core/paths.py`：定義 `KS_ROOT`（讀 env `KS_ROOT`）、`RAW_SOURCES_DIR` / `WIKI_DIR` / `WIKI_PAGES_DIR` / `VECTOR_DB_DIR` / `MANIFEST_PATH` / `LOCK_PATH`，並以 runtime path 白名單拒絕任何 `/ks/graph/` 存取 —（FR-050, FR-051, §I）
- [x] T012 [P] 實作 `src/hks/core/schema.py`：`QueryResponse` / `Trace` / `TraceStep` dataclass + `to_dict()` + `validate(obj)` 以 `jsonschema` 載入 [contracts/query-response.schema.json](./contracts/query-response.schema.json) 驗證 —（FR-002, §II）
- [x] T013 [P] 實作 `src/hks/core/manifest.py`：`Manifest` / `ManifestEntry` / `DerivedArtifacts` dataclass、`load() / save() / atomic_write()`、`compute_sha256(path)`、`resume_or_rebuild()` —（FR-013, FR-014, [data-model.md §2](./data-model.md)）
- [x] T014 [P] 實作 `src/hks/core/lock.py`：`acquire_lock(path)` 以 `fcntl.flock` 互斥；上下文管理器 `with file_lock(LOCK_PATH): ...` —（research §14, concurrency edge case）
- [x] T015 [P] 實作 `src/hks/storage/wiki.py`：`WikiStore`（讀寫 `index.md` TOC、append `log.md` 的 ingest / writeback 事件、寫入 `pages/<slug>.md`、slug 生成 `python-slugify` + 衝突 `-<n>` 後綴、`reconcile()` 一致性檢查）—（FR-016, FR-033, SC-006, [data-model.md §3–§5](./data-model.md)）
- [x] T016 [P] 實作 `src/hks/storage/vector.py`：`VectorStore` 封裝 `chromadb.PersistentClient`（collection `hks_phase1`、cosine 距離、`TextModelBackend(HKS_EMBEDDING_MODEL)`）；`add_chunks()` / `search(query, top_k=5)` 回傳 `SearchHit[]` —（research §5/§6, [data-model.md §6](./data-model.md)）
- [x] T017 [P] 實作 `src/hks/routing/rules.py`：以 `ruamel.yaml` 載入 `routing_rules.yaml`（依序：env `HKS_ROUTING_RULES` → `/ks/config/` → package 內建 `config/`）；解析為 `RoutingRuleSet`；schema 驗證（`target_route` 限 `wiki`/`vector`）—（FR-020, FR-052, [data-model.md §7](./data-model.md)）
- [x] T018 [P] 實作 `src/hks/cli.py`：typer app，提供 `ingest` / `query` / `lint` 三個 subcommand、`query --writeback` option、`--version` —（FR-001）
- [x] T019 [P] 契約測試 `tests/contract/test_json_schema.py`：(a) `jsonschema` 載入 `contracts/query-response.schema.json` 自我驗證；(b) 4 個 example 皆通過；(c) 反例測試（`source` 含 `"graph"` → `ValidationError`、`trace.route="graph"` → `ValidationError`）；(d) 黑名單測試：呼叫 `core/paths.py` 任何試圖建立或寫入 `KS_ROOT/graph/` 的 helper → 觸發 `AssertionError`（§I defense）—（§II, §I, FR-002, FR-051）
- [x] T020 契約測試 `tests/contract/test_exit_codes.py`：subprocess 驅動 CLI，覆蓋 [contracts/cli-exit-codes.md](./contracts/cli-exit-codes.md) 各指令表格的至少 14 個獨立情境（ingest 6、query 6、lint 2）。每個 case 同時 assert exit code 與 stderr 首行格式 `[ks:<command>] <level>: <summary>`；`1`/`65`/`66` 情境額外 assert stdout 仍為合法 JSON（`schema.validate()` 通過）—（FR-003, §II 附屬, SC-007）

**Checkpoint**: `uv run pytest tests/contract/` 全綠；`uv run mypy src/hks` 無錯誤；`uv run ks --help` 列出三個 subcommand；`src/hks/core/paths.py` 常數拒絕建立 `/ks/graph/`。

---

## Phase 3: User Story 1 — Ingest 建立知識基底（P1）🎯 MVP 必要

**Goal**: `ks ingest <path>` 接受 txt/md/pdf，建立 `raw_sources/` 副本、`wiki/pages/`、`vector/db/`、`manifest.json`；重複 ingest 以 SHA256 idempotent。

**Independent Test**: 跑 [spec.md US1 Independent Test](./spec.md)；預期 `uv run pytest -m us1 -v` 全綠。

### Tests for US1（先寫、先 fail）

- [x] T021 [P] [US1] 整合測試 `tests/integration/test_ingest_basic.py`：ingest 10 份 fixtures，assert `raw_sources/` 10 份、`wiki/pages/` ≥ 10 份、`manifest.json` 每筆含 sha256 + derived、exit `0`、stdout JSON 摘要 parseable —（US1 Acceptance 1, FR-010/012/013, SC-001）
- [x] T022 [P] [US1] 整合測試 `tests/integration/test_ingest_idempotent.py`：第二次 ingest 後 artifact 數量不變、耗時 ≤ 首次 × 0.5 —（US1 Acceptance 2, FR-014, SC-002）
- [x] T023 [P] [US1] 整合測試 `tests/integration/test_ingest_update.py`：修改一份 md 後 re-ingest，assert 僅該檔 derived 被更新 + `log.md` 新增一筆 update —（US1 Acceptance 3, FR-014）
- [x] T024 [P] [US1] 整合測試 `tests/integration/test_ingest_edge_cases.py`：(a) `tests/fixtures/broken/broken.pdf` 單獨 ingest → exit `65`、stdout JSON `failures[]` 含該檔；(b) 與 `tests/fixtures/valid/` 合併 ingest → exit `65`、10 份合法檔仍完成；(c) `tests/fixtures/oversized/` 在 `HKS_MAX_FILE_MB=1` 下 ingest → exit `65`、錯誤原因標記 `oversized`；(d) 混入 unsupported 副檔名與空檔 / whitespace 檔 → stdout JSON 分別標記 `unsupported` / `empty`、均列入 `skipped` 不計 `failures`，且 `log.md` 記 skip reason —（US1 Acceptance 4, FR-011, FR-014, ExitCode DATAERR, edge cases）
- [x] T025 [P] [US1] 單元測試 `tests/unit/ingest/test_parsers.py`：txt / md / pdf 解析輸出非空 string；壞 PDF 觸發 `KSError(code="PDF_READ_ERROR")` —（FR-011）
- [x] T026 [P] [US1] 單元測試 `tests/unit/ingest/test_normalizer.py`：512 / 64 token chunking 邊界、段落優先切點、tokenizer counts 一致 —（research §12）
- [x] T027 [P] [US1] 單元測試 `tests/unit/ingest/test_extractor.py`：從 normalized 文本產出 `WikiPage`（title / summary / body）+ `VectorChunk[]` 的正確性與對應關係 —（FR-015, [data-model §3/§6](./data-model.md)）
- [x] T028 [P] [US1] 單元測試 `tests/unit/core/test_manifest.py`：SHA256 一致性、atomic write 不會半成品、`resume_or_rebuild()` 從 `raw_sources/` 重建 manifest 正確 —（FR-013, FR-014）
- [x] T029 [P] [US1] 單元測試 `tests/unit/storage/test_wiki_slug.py`：slugify 對中/英/emoji/重複檔名的行為、衝突 `-<n>` 後綴 —（FR-016, edge case）

### Implementation for US1

- [x] T030 [P] [US1] 實作 `src/hks/ingest/parsers/txt.py`：讀檔（UTF-8、fallback `errors="replace"`）、回傳 `str` —（FR-011）
- [x] T031 [P] [US1] 實作 `src/hks/ingest/parsers/md.py`：`markdown-it-py` tokenize；保留 heading 層級供 extractor 抽 title；回傳 `(title: str, body: str)` —（FR-011, research §4）
- [x] T032 [P] [US1] 實作 `src/hks/ingest/parsers/pdf.py`：`pypdf` 抽文字；catch `PdfReadError` → `raise KSError(ExitCode.DATAERR, ...)`；檔案大小 > `HKS_MAX_FILE_MB` → 同 exit 65 —（FR-011, FR-003, edge case, research §3）
- [x] T033 [P] [US1] 實作 `src/hks/ingest/normalizer.py`：trim / dedupe whitespace；`chunk(text, size=512, overlap=64)` 以 `sentence-transformers` tokenizer 計算、偏好段落與句號切點 —（research §12）
- [x] T034 [US1] 實作 `src/hks/ingest/extractor.py`：輸入 parser 輸出 + normalized chunks；產出 1 份 `WikiPage`（title = 第一個 heading 或檔名、summary = 前 80 字）+ `list[VectorChunk]`（metadata 含 source_relpath / chunk_idx / sha256）—（FR-015, [data-model §3/§6](./data-model.md)）
- [x] T035 [US1] 實作 `src/hks/ingest/pipeline.py`：orchestrator `ingest(path)`：(1) `acquire_lock`；(2) 遍歷 path；(3) 每檔 `compute_sha256` 與 manifest 比對 → skip / update / create；(4) unsupported 與空檔 / whitespace 檔標記 skipped 並 append `log.md`；(5) `copy_to_raw_sources`；(6) parse→normalize→extract；(7) 並行 `wiki_store.write()` + `vector_store.add_chunks()`；(8) 更新 manifest atomic；(9) 回傳摘要 dict `{successes, skipped, updated, failures}`（依賴 T010/T011/T013/T014/T015/T016/T030-T034）—（FR-010/011/012/013/014/015/050）
- [x] T036 [US1] 實作 `src/hks/commands/ingest.py`：接收 CLI 參數（path、`--prune`）、呼叫 `pipeline.ingest()`、將摘要包裝為 `QueryResponse`（`trace.route="wiki"` 佔位、`trace.steps` 加 `ingest_summary`）、`schema.validate()` 後輸出 stdout；錯誤 → ExitCode 映射 —（FR-001, FR-002, §II）
- [x] T037 [US1] 串接 `ingest` 指令進入 `src/hks/cli.py`（替換 T018 的佔位 handler）—（FR-001）

### Checkpoint US1

- [x] T038 [US1] 執行 `uv run pytest -m us1 -v` 全綠；手動走 [quickstart.md §3](./quickstart.md) 與 §5（idempotency）；確認 `/ks/graph/` 未被建立；stdout JSON 全數通過 schema 驗證 —（SC-001, SC-002, §I, §II）

---

## Phase 4: User Story 2 — Query 取得統一格式答案（P1）🎯 MVP 必要

**Goal**: `ks query "<q>"` 依 rule-based routing 選 wiki / vector，回傳憲法 §II schema 的 JSON；無命中亦 exit `0`；未初始化 exit `66`。

**Independent Test**: [spec.md US2 Independent Test](./spec.md)；`uv run pytest -m us2 -v` 全綠。

### Tests for US2

- [x] T039 [P] [US2] 整合測試 `tests/integration/test_query_flows.py::test_query_summary_uses_wiki`：summary 類 query → `trace.route=="wiki"`, `source=["wiki"]`, `confidence==1.0` —（US2 Acc 1, FR-020/023/024）
- [x] T040 [P] [US2] 整合測試 `tests/integration/test_query_flows.py::test_query_detail_uses_vector`：detail 類 query → `trace.route=="vector"`, `source=["vector"]`, `0<confidence<=1` —（US2 Acc 2, FR-024）
- [x] T041 [P] [US2] 整合測試 `tests/integration/test_query_flows.py::test_query_relation_appends_phase2_note`：關係類 query → vector fallback 且 `answer` 結尾含「深度關係推理將於 Phase 2 支援」 —（US2 Acc 3, FR-022）
- [x] T042 [P] [US2] 整合測試 `tests/integration/test_query_flows.py::test_query_no_hit_returns_zero`：完全無命中 → `answer="未能於現有知識中找到答案"`, `source=[]`, `confidence==0.0`, exit `0` —（US2 Acc 4, FR-026）
- [x] T043 [P] [US2] 整合測試 `tests/integration/test_query_flows.py::test_query_uninitialized_returns_noinput` 與 `::test_query_corrupted_runtime_without_manifest_returns_noinput`：空 `/ks/`，以及 `manifest.json` 遺失但 `wiki/`、`vector/db/` 仍在的毀損狀態，皆應 exit `66` + JSON 錯誤說明與 re-ingest 提示 —（US2 Acc 5, FR-003, NOINPUT, edge case）
- [x] T044 [P] [US2] 整合測試 `tests/integration/test_query_flows.py::test_query_does_not_reparse_sources`：monkeypatch `ingest.parsers.*`、`ingest.normalizer.chunk`、`ingest.extractor.*`；query 階段不得重新 parse / chunk / extract 來源文件。若走 vector route，僅允許 embedding backend 對 query text 呼叫一次 —（§IV gate）
- [x] T045 [P] [US2] 單元測試 `tests/unit/routing/test_rules.py`：YAML 讀取、priority 排序、`target_route` graph 拒絕載入 —（FR-020, §III）
- [x] T046 [P] [US2] 單元測試 `tests/unit/routing/test_router.py`：匹配優先序、fallback、`TraceStep` 紀錄完整、`phase2_note` 注入 —（FR-022, FR-025）
- [x] T047 [P] [US2] 單元測試 `tests/unit/storage/test_vector_search.py`：top-1 cosine similarity 回傳、空庫回 `[]` —（FR-024）

### Implementation for US2

- [x] T048 [P] [US2] 實作 `src/hks/routing/router.py`：`route(query: str, rules: RoutingRuleSet) -> (Route, list[TraceStep])`；未命中回 `default_route`；命中 `phase2_note` rule 時另回一個旗標供 command 注入附註 —（FR-020/022/025）
- [x] T049 [P] [US2] 擴充 `src/hks/storage/wiki.py`：`search(query) -> Optional[WikiPage]` 以 title / summary / body 子字串 + 關鍵字權重做 Phase 1 最簡查找（不引入 BM25，Phase 2 可升級）—（FR-023）
- [x] T050 [P] [US2] 擴充 `src/hks/storage/vector.py`：`search(query, top_k=5) -> list[SearchHit]`；返回 cosine similarity ∈ [0,1] —（FR-024）
- [x] T051 [US2] 實作 `src/hks/commands/query.py`：(1) assert manifest 存在，否則 `raise KSError(NOINPUT)`；(2) 載入 routing rules；(3) `router.route()`；(4) 依 route dispatch 至 wiki / vector 查找；(5) wiki 未命中自動 fallback vector（`trace.steps` 加 `fallback`）；(6) 組 `QueryResponse` + `schema.validate()`；(7) 若 rule 含 `phase2_note` 則於 `answer` 結尾附註；(8) 回傳 JSON —（FR-021/022/023/024/025/026, FR-002, §II）
- [x] T052 [US2] 串接 `query` 指令進入 `src/hks/cli.py`（替換 T018 佔位）—（FR-001）

### Checkpoint US2

- [x] T053 [US2] 執行 `uv run pytest -m us2 -v` 全綠；手動跑 [quickstart.md §3](./quickstart.md) 四類 query；用 `jq '.source, .trace.route'` 檢查每筆 stdout JSON 的 `source` / `trace.route` 皆為 `wiki` / `vector`（不為 `graph`）—（§I, §II, SC-003）

---

## Phase 5: User Story 3 — 半自動 Write-back（P2）

**Goal**: query 結束後依 TTY + `--writeback` flag 決策是否回寫 wiki；TTY 詢問、非 TTY 跳過、flag 可覆寫；Phase 1 嚴禁自動寫入。

**Independent Test**: [spec.md US3 Independent Test](./spec.md)；`uv run pytest -m us3 -v` 全綠。

### Tests for US3

- [x] T054 [P] [US3] 整合測試 `tests/integration/test_writeback.py::test_writeback_ask_yes_commits`：commit 路徑新增 `pages/<slug>.md`，並在 `trace.steps` 記 `writeback=committed` —（US3 Acc 1, FR-030/033）
- [x] T055 [P] [US3] 整合測試 `tests/integration/test_writeback.py::test_writeback_ask_no_declines`：decline 路徑不回寫、`writeback=declined` —（US3 Acc 2）
- [x] T056 [P] [US3] 整合測試 `tests/integration/test_writeback.py::test_writeback_skips_non_tty_by_default`：非 TTY 預設 `writeback=skip-non-tty`、exit `0`、指令不阻塞 —（US3 Acc 3, FR-031, SC-004）
- [x] T057 [P] [US3] 整合測試 `tests/integration/test_writeback.py::test_writeback_yes_overrides_non_tty` 與 `::test_writeback_no_overrides_and_skips_commit`：驗證 `--writeback=yes` / `--writeback=no` 兩種 override 行為 —（US3 Acc 4, FR-032）
- [x] T058 [P] [US3] 整合測試 `tests/integration/test_writeback.py::test_writeback_slug_collision_uses_suffix`：預先放既有 slug，回寫同 slug 產出 `-2` 後綴並於 trace 記錄 —（US3 Acc 5, FR-016）
- [x] T059 [P] [US3] 單元測試 `tests/unit/writeback/test_gate.py`：`decide(flag, is_tty)` 矩陣（3 × 2 = 6 組）完整覆蓋；assert 不含任何 confidence 分支 —（FR-030/031/032/034, §V）
- [x] T060 [P] [US3] 單元測試 `tests/unit/writeback/test_writer.py`：`commit(response)` 正確寫入 wiki page / index entry / log entry；寫入失敗回傳錯誤 —（FR-033, edge case 磁碟滿）

### Implementation for US3

- [x] T061 [P] [US3] 實作 `src/hks/writeback/gate.py`：`decide(flag: Literal["yes","no","ask"], is_tty: bool) -> Decision`，搭配 `prompt_user()`；**禁止**任何 `confidence` 輸入 —（FR-030/031/032, §V）
- [x] T062 [US3] 實作 `src/hks/writeback/writer.py`：`commit(query, response, wiki_store=...) -> list[TraceStep]`；呼叫 `WikiStore.write_page()` + `append_log()`，並由 `WikiStore` 內部重建 index —（FR-033, [data-model §3/§4/§5](./data-model.md)）
- [x] T063 [US3] 整合 write-back 進入 `src/hks/commands/query.py`：於組完 `QueryResponse` 後呼叫 `gate.decide()` → 若 commit 則 `writer.commit()` 並將回傳 steps 合併入 `trace.steps`；assert 不存取 `confidence` 欄位做判斷 —（FR-030/031/032/033/034, §V）
- [x] T064 [US3] 為 `ks query` 加上 `--writeback` option（typer `Annotated[Writeback, typer.Option(...)]`，預設 `"ask"`）—（FR-032, FR-001）

### Checkpoint US3

- [x] T065 [US3] 執行 `uv run pytest -m us3 -v` 全綠；手動跑 [quickstart.md §4](./quickstart.md) 四組 writeback 情境；確認 `grep -n "confidence" src/hks/writeback/gate.py` 無匹配 —（§V）

---

## Phase 6: User Story 4 — Lint Stub（P3）

**Goal**: `ks lint` 吐 query 相同 schema 的固定 JSON + exit 0，保留與 Phase 3 相容介面。

**Independent Test**: [spec.md US4 Independent Test](./spec.md)。

### Tests for US4

- [x] T066 [P] [US4] 契約測試 `tests/contract/test_lint_stub.py`：`ks lint` stdout 為 `{answer: "lint 尚未實作，預計於 Phase 3 提供", source: [], confidence: 0.0, trace: {route: "wiki", steps: []}}`、exit `0`、schema 驗證通過 —（US4 Acc 1, FR-040, §II）

### Implementation for US4

- [x] T067 [US4] 實作 `src/hks/commands/lint.py`：固定回應 dataclass → schema.validate → stdout JSON —（FR-040）
- [x] T068 [US4] 串接 `lint` 指令進入 `src/hks/cli.py`（替換 T018 佔位）—（FR-001）

### Checkpoint US4

- [x] T069 [US4] 執行 `uv run pytest -m us4 -v` 全綠 —（FR-040）

---

## Phase 7: Polish & Cross-Cutting

**Purpose**: 憲法 §I 全域閘門、效能驗證、DX、整體 quickstart 走查。

- [x] T070 [P] 契約測試 `tests/contract/test_no_graph_in_runtime.py`：執行 US1–US4 主要情境，蒐集所有 stdout JSON 並 `json.loads`；assert `response["source"]` 不含 `"graph"` 且 `response["trace"]["route"] != "graph"`（精確欄位檢查，不做 string grep）；同時 assert `KS_ROOT/graph/` 目錄不存在 —（SC-008, §I, FR-021, FR-051）
- [x] T071 [P] 靜態檢查 `tests/contract/test_no_graph_in_src.py`：以 `ast` 掃描 `src/hks/` 的 import、常數、enum 值、路徑常數與可執行 string literals；assert 不存在 graph runtime code path。module docstring 與註解不列入違規 —（§I）
- [x] T072 [P] 效能測試 `tests/integration/test_query_performance.py`：ingest 50 份 fixtures（從 10 份擴充或 monkeypatch），以 `pytest-benchmark` 或手測 50 次取 p95 < 3s —（SC-005）
- [x] T073 [P] 覆蓋率設定驗收：在 `pyproject.toml` 鎖定 `[tool.coverage.report] fail_under = 80`、`[tool.coverage.run] source = ["src/hks"]`、`omit = ["src/hks/__init__.py"]`；CI 以 `uv run pytest --cov` 判斷 —（SC-009, FR-061）
- [x] T074 [P] SC-006 一致性測試 `tests/integration/test_wiki_reconcile.py`：ingest + writeback 若干輪後呼叫 `WikiStore.reconcile()` assert 無 orphan / 無 dead link —（SC-006）
- [x] T075 [P] Local-first 離線測試 `tests/integration/test_offline.py`：以 monkeypatch 禁用 `httpx` / `requests` / `urllib` 網路呼叫，僅允許 `HKS_EMBEDDING_MODEL` 指向本機快取（預先於 conftest fixture 下載）；ingest + query 全流程成功 —（FR-060, research §5）
- [x] T076 [P] 更新 [readme.md](../../readme.md)：明示 repo 目前仍以 specification-first 交付，但 Phase 1 CLI runtime 已落地；於「安裝」與「CLI 使用」區塊指向本 feature 的 [quickstart.md](./quickstart.md)；列出 `--writeback` flag 與 exit code 摘要 —（DX）
- [x] T077 [P] 執行 `uv run ruff format .` + `uv run ruff check --fix .` + `uv run mypy src/hks`，全綠並 commit 清理 —（DX, FR-061）
- [x] T078 手動走 [quickstart.md](./quickstart.md) §1–§9 端對端；任何不符合描述處回頭修 code 或修 quickstart —（SC-004, acceptance）
- [x] T079 最終憲法再檢：逐條核對 [plan.md Post-Design Re-Check](./plan.md) 五項 §I–§V 閘門；更新 `Complexity Tracking`（若有豁免）；更新 `spec.md` `Status: Draft → Complete` —（§I–§V）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup** (T001–T009) → 可立刻開始；T003 / T004 為鏈式依賴
- **Phase 2 Foundational** (T010–T020) → 依賴 Phase 1 完成；**阻塞** Phase 3–6
- **Phase 3 US1** (T021–T038) → 依賴 Phase 2；MVP 必要
- **Phase 4 US2** (T039–T053) → 依賴 Phase 2 + US1（查詢必須先有資料）；MVP 必要
- **Phase 5 US3** (T054–T065) → 依賴 US2（write-back 接在 query 後）
- **Phase 6 US4** (T066–T069) → 依賴 Phase 2（可與 US1–US3 並行）
- **Phase 7 Polish** (T070–T079) → 依賴所有 US 完成

### User Story 內部

- Tests MUST fail 後再進 Implementation
- Foundational 的 `schema.py` / `errors.py` / `paths.py` 是所有 US 的前置
- US1 → US2：query 需要 manifest + wiki + vector 已有資料
- US2 → US3：write-back 附掛在 query 流程後段
- US4 獨立：僅需 `schema.py`

### Parallel Opportunities

- **Setup**: T001 / T002 / T005 / T006 / T007 / T008 / T009 可全並行；T003 需先、T004 次之
- **Foundational**: T011 / T012 / T013 / T014 / T015 / T016 / T017 / T018 / T019 皆 [P]；T010 可先、T020 需 T018 完成
- **US1 tests**: T021–T029 全 [P]
- **US1 impl**: T030–T033 parsers / normalizer [P]；T034 → T035 → T036 → T037 鏈式
- **US2 tests**: T039–T047 全 [P]
- **US2 impl**: T048 / T049 / T050 [P]；T051 → T052 鏈式
- **US3 tests**: T054–T060 全 [P]
- **US3 impl**: T061 [P]；T062 → T063 → T064 鏈式
- **US4**: T066 → T067 → T068 短鏈
- **Polish**: T070 / T071 / T072 / T073 / T074 / T075 / T076 / T077 全 [P]；T078 / T079 於最後

---

## Parallel Example — User Story 1

```bash
# 同時啟動 US1 全部測試（失敗狀態正常）
uv run pytest tests/integration/test_ingest_basic.py &
uv run pytest tests/integration/test_ingest_idempotent.py &
uv run pytest tests/integration/test_ingest_update.py &
uv run pytest tests/integration/test_ingest_edge_cases.py &
uv run pytest tests/unit/ingest/ tests/unit/core/test_manifest.py tests/unit/storage/test_wiki_slug.py &
wait

# 實作 parsers 並行
# T030 parsers/txt.py、T031 parsers/md.py、T032 parsers/pdf.py、T033 normalizer.py
```

---

## Implementation Strategy

### MVP First（僅 US1 + US2，可作為第一次 demo）

1. 完成 Phase 1 Setup（T001–T009）
2. 完成 Phase 2 Foundational（T010–T020）— **關鍵阻塞**
3. 完成 Phase 3 US1 Ingest（T021–T038）
4. 完成 Phase 4 US2 Query（T039–T053）
5. 在 Checkpoint US2 暫停、驗收，對 agent 提供結構化查詢能力 — **可交付 demo**

### Incremental Delivery

1. MVP → US1 + US2 → demo
2. 加 US3 Write-back → demo
3. 加 US4 Lint Stub → demo（為 Phase 3 rollout 預留）
4. Polish → 效能、覆蓋率、離線、quickstart 走查

### Parallel Team Strategy

- Dev A：Setup + Foundational
- Dev A + B：US1（A 帶 ingest core、B 帶 storage + tests）
- Dev A + B + C：US1 完成後分工，A → US2、B → US3、C → US4 + Polish

---

## FR → Task 追溯

| FR | Tasks |
|---|---|
| FR-001 CLI 入口 | T018, T037, T052, T064, T068 |
| FR-002 JSON schema 輸出 | T012, T019, T036, T051, T067 |
| FR-003 Exit code | T010, T020, T032, T043, T051 |
| FR-010 ingest 路徑接受 | T021, T035 |
| FR-011 格式支援 + unsupported | T024, T025, T030–T032, T035 |
| FR-012 raw_sources 複製 | T021, T035 |
| FR-013 manifest.json | T013, T028, T035 |
| FR-014 idempotency | T013, T022, T023, T024, T028, T035 |
| FR-015 ingest-time 整理 | T033, T034, T035, T044 |
| FR-016 slug + 碰撞 | T015, T029, T058 |
| FR-020 rule-based + 外部化 | T006, T017, T045, T048 |
| FR-021 Phase 1 禁 graph | T011, T017, T045, T070, T071 |
| FR-022 關係類 fallback + 附註 | T041, T046, T048, T051 |
| FR-023 trace.route / source 語意 | T012, T039, T040, T051 |
| FR-024 confidence 計算 | T040, T047, T050, T051 |
| FR-025 trace.steps 追溯 | T046, T048, T051 |
| FR-026 無命中 | T042, T051 |
| FR-030 TTY 互動 | T054, T059, T061 |
| FR-031 非 TTY 跳過 | T056, T059, T061 |
| FR-032 --writeback flag | T057, T059, T061, T064 |
| FR-033 index + log 更新 | T015, T060, T062 |
| FR-034 禁自動寫入 | T059, T063, T065 |
| FR-040 lint stub | T066, T067 |
| FR-050 /ks/ 結構 | T011, T035 |
| FR-051 禁 /ks/graph/ | T011, T038, T070 |
| FR-052 domain-agnostic | T006, T017, T045 |
| FR-060 local-first | T075 |
| FR-061 pytest 閘門 | T003, T004, T008, T073 |

## SC → Task 追溯

| SC | Tasks |
|---|---|
| SC-001 ingest 10 份成功 | T007, T021 |
| SC-002 idempotent + 快取 | T022, T028 |
| SC-003 summary/detail JSON | T039, T040, T051 |
| SC-004 非互動無阻塞 | T056, T078 |
| SC-005 p95 < 3s | T072 |
| SC-006 wiki 成長一致 | T015, T074 |
| SC-007 exit code 契約 | T020, T043 |
| SC-008 無 graph 於 runtime | T070, T071 |
| SC-009 pytest + 覆蓋率 | T003, T073 |

## 憲法 Gate → Task 追溯

| § | 條目 | Tasks |
|---|---|---|
| §I | Phase Discipline（無 graph） | T011（paths 黑名單）、T017（rules 拒 graph）、T019（blacklist negative test）、T045、T070（runtime 欄位檢查 + `KS_ROOT/graph/` 不存在）、T071（source grep）、T038（Checkpoint）、T079（終檢） |
| §II | Stable Output Contract（JSON） | T012（core/schema.py）、T019（schema 契約測試）、T036 / T051 / T067（runtime validate）、T053（jq 欄位檢查 no-graph） |
| §II 附屬 | CLI Exit Codes | T010（ExitCode enum）、T020（contract test）、T032 / T043 / T051（各指令對應）、[contracts/cli-exit-codes.md](./contracts/cli-exit-codes.md) |
| §III | CLI-First & Domain-Agnostic | T006（routing yaml）、T017（loader）、T018（typer CLI）、T075（離線） |
| §IV | Ingest-Time Organization | T033（extractor）、T034（pipeline 同步兩層）、T035（更新 manifest + artifacts）、T044（query no-reparse） |
| §V | Write-back Safety | T059（gate 矩陣無 confidence）、T061（decide 實作）、T063（integration 不存取 confidence）、T065（grep 驗證） |

---

## Notes

- `[P]` = 可獨立並行；同檔或有前置依賴者不標 `[P]`
- `[US*]` 僅用於 Phase 3–6；Setup / Foundational / Polish 不帶
- Phase 2 完成前 US 任務**不得**開工（Foundational 為唯一阻塞點）
- 每個 US 尾端 Checkpoint 為「可 demo 閘門」，未過不進下一 US
- Phase 2 / Phase 3 graph 相關能力一律不實作（憲法 §I）；tasks 中任何對 graph 的提及都是「排除性 assert」
- Commit 粒度：每完成一個 task 或一組 `[P]` 任務即 commit，commit message 起首 `T0XX:` 方便追溯

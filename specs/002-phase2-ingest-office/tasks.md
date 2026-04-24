---

description: "Phase 2 階段一 — Office 文件（docx / xlsx / pptx）ingest 擴充的任務清單"
---

# Tasks: Phase 2 階段一 — Office 文件（docx / xlsx / pptx）ingest 擴充

**Input**: Design documents from `/specs/002-phase2-ingest-office/`
**Prerequisites**: [plan.md](./plan.md)、[spec.md](./spec.md)、[research.md](./research.md)、[data-model.md](./data-model.md)、[contracts/](./contracts/)、[quickstart.md](./quickstart.md)

**Tests**: 本 feature 明示要求測試（spec FR-081、SC-008 覆蓋率 ≥ 80%）；沿用 Phase 1 TDD 慣例，契約與整合測試先寫、先紅再綠。

**Organization**: 依 spec.md 三個 User Story 分 phase，每個 phase 收尾以 Checkpoint 閘門可 demo。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可獨立並行（不同檔、無前置依賴）
- **[Story]**：所屬 User Story（US1 / US2 / US3）；Setup / Foundational / Polish 不帶
- 檔案路徑為絕對 repo-relative（以 repo root 為起點）

## Path Conventions

單一 Python package：`src/hks/`、`tests/`、`config/`、`specs/002-phase2-ingest-office/`。

---

## Phase 1: Setup（Shared Infrastructure）

**Purpose**：引入三個 parser library、更新 lock、預備 fixture 生成腳本骨架。

- [X] T001 更新 `pyproject.toml`：於 `[project.dependencies]` 新增 `python-docx>=1.1,<2`、`openpyxl>=3.1,<4`、`python-pptx>=1.0,<2`；於 `[dependency-groups.dev]` 新增 `msoffcrypto-tool>=5.4,<6`（僅用於產生 encrypted fixture）—（research §1–§3、§11）
- [X] T002 執行 `uv sync` 重生 `uv.lock` 並 commit；驗證 `uv.lock` 內新增三 parser 的 wheel URL 均為 PyPI（無 git/local path），以確保 airgapped 可安裝 —（research §10、FR-082）
- [X] T003 [P] 建立 `tests/fixtures/build_office.py` 骨架：定義 `build_all()` entrypoint、輸出目錄常數、空 function 占位（生成邏輯留給後續 tasks 補）—（research §11、quickstart §2）
- [X] T004 [P] 於 `Makefile` 新增 `make fixtures` target：呼叫 `uv run python tests/fixtures/build_office.py`，供 CI 與本機一鍵生成 —（DX）

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：擴充 data model、manifest、pipeline 基座；任何 US 開工前必須先完成。

**⚠️ CRITICAL**：三個 US 的所有 task 皆依賴本 phase。

- [X] T010 擴充 `src/hks/core/manifest.py`：`SourceFormat` Literal 加入 `"docx" | "xlsx" | "pptx"`；新增 `detect_source_format(path)` 以副檔名為主並對 PDF / OOXML 做輕量 content sniffing；`ManifestEntry` 在保留既有 `relpath/sha256/format/size_bytes/ingested_at/derived` schema 下新增 `parser_fingerprint: str = "*"` 欄位；`load()` 對舊 entry 無此欄位時自動以 `"*"` 補齊；`save()` 序列化新欄位 —（data-model §4、research §0、research §7、FR-001、FR-002、FR-003、FR-041、FR-044）
- [X] T011 [P] 新建 `src/hks/ingest/office_common.py`：定義 `PLACEHOLDER_PREFIXES`（8 種字面常數）、`SkippedSegmentType` Literal、`SkippedSegment` dataclass、`Segment` dataclass + `SegmentKind` Literal、`build_placeholder(kind, payload)` helper、`to_markdown_table(header, rows)` helper —（data-model §2–§3、research §4、FR-012、contracts/office-placeholder-prefix.md）
- [X] T012 [P] 擴充 `src/hks/ingest/models.py`：`ParsedDocument` 新增 `segments: list[Segment]`、`skipped_segments: list[SkippedSegment]`、`parser_fingerprint: str` 欄位（預設 empty / empty / `""`）；新增 `IngestFileReport` dataclass（`path, status, reason, skipped_segments, pptx_notes`）；`IngestSummary` 在保留既有 `created/updated/skipped/failures/pruned` 結構下新增 `files: list[IngestFileReport]` —（data-model §1, §5、FR-045）
- [X] T013 [P] 新建 `src/hks/ingest/guards.py`：`preflight_size_check(path, max_mb)` 以 `Path.stat().st_size` 檢查；`with_timeout(seconds)` context manager 以 `signal.setitimer(signal.ITIMER_REAL, seconds)` + `SIGALRM` handler 實作，退出時 reset itimer 至 0 —（research §5、§6、FR-063、FR-064）
- [X] T014 [P] 新建 `src/hks/ingest/fingerprint.py`：`compute_parser_fingerprint(format, flags)` 以 `importlib.metadata.version()` 取 library 版本，組成 `"{format}:v{version}:{flags_digest}"`；`flags_digest` 以穩定序列化 flags 算 hash（docx / xlsx 為空、pptx 的 `notes=exclude` 產出 `"notes_exclude"`）；`are_fingerprints_compatible(entry_fp, current_fp)` 回傳 `entry_fp in (current_fp, "*")` —（research §7、data-model §4）
- [X] T015 擴充 `src/hks/ingest/extractor.py`：chunk 切分改 segment-aware；當 `ParsedDocument.segments` 非空時，依 segment kind 優先在 `heading` / `sheet_header` / `slide_header` 邊界切 chunk；長度超上限（512 token）時以段落 / row / slide 為最小粒度切分、不跨 placeholder；chunk metadata 帶 `sheet_name` / `row_index` / `slide_index` / `section_type` —（research §9、FR-021、FR-031）
- [X] T016 擴充 `src/hks/ingest/pipeline.py`：`PARSERS` dict 改為可擴充入口（keyed by `SourceFormat`）；新增 `_ingest_one_file()` 流程：format detect → preflight size → `with_timeout` → parser dispatch → segments 組合 body → extractor → update wiki+vector；per-file rollback：失敗時回溯已寫 wiki page 與已加 vector ids；re-ingest 判定以 `sha256 + parser_fingerprint` 完成；每檔結果聚合為 `IngestFileReport` 填入 `IngestSummary.files`，但既有 counters 保留 —（research §0、§5、§7、§8、FR-040、FR-044、FR-060, FR-061、FR-063, FR-064）
- [X] T017 [P] 擴充 `src/hks/storage/wiki.py`：`LogEntry` 允許附屬欄位 `skipped_segments: list[SkippedSegment] | None`、`pptx_notes: Literal["included","excluded"] | None`；append 時仍沿用 Phase 1 header + bullet 明細格式，僅追加 `- skipped_segments:` / `- pptx_notes:` bullet；既有舊行解析不受影響 —（data-model §8、FR-043）
- [X] T018 [P] 擴充 `src/hks/cli.py`：`ingest` subcommand 新增 `--pptx-notes=include|exclude`（預設 `include`）option；值不合法 → 以 `ExitCode.USAGE=2` 結束；讀取 `HKS_OFFICE_TIMEOUT_SEC` / `HKS_OFFICE_MAX_FILE_MB` env（不合法亦 USAGE=2，訊息指出變數名與範圍）；將 flag 傳入 pipeline —（FR-033、contracts/office-cli-flags.md）
- [X] T019 [P] 固化 ingest summary detail 契約：延續 Phase 1 top-level `QueryResponse`，於 `src/hks/commands/ingest.py` 將 Office 專屬資料寫入 `trace.steps[kind="ingest_summary"].detail.files`；新增 detail validator（可置於 `src/hks/commands/ingest.py` 或 `src/hks/core/ingest_contract.py`）載入 [contracts/ingest-summary-detail.schema.json](./contracts/ingest-summary-detail.schema.json) 驗證該 `detail` object —（§II 擴充、contracts/ingest-summary-detail.schema.json、FR-045）
- [X] T020 契約測試 `tests/contract/test_ingest_summary_detail_schema.py`：(a) jsonschema self-validate、(b) 所有 examples 皆通過、(c) 反例（`files[].status="invalid"` / `skipped_segments[].type="unknown"` / `pptx_notes="maybe"`）均應拋 `ValidationError`；(d) 合法 empty batch 與合法 all-failed batch 各覆蓋一例 —（T019、FR-045、§II）
- [X] T021 單元測試 `tests/unit/test_manifest_fingerprint.py`：覆蓋舊 manifest（無 `parser_fingerprint`）→ load 自動補 `"*"`；`"*"` 對任何 current_fp 皆 compatible；一旦被 re-ingest 覆寫為具體字串後 wildcard 行為消失 —（T010、T014、FR-044）
- [X] T022 單元測試 `tests/unit/test_timeout_gate.py`、`tests/unit/test_filesize_gate.py`：前者 monkeypatch `signal.setitimer` 假造超時、後者以小檔案 + `HKS_OFFICE_MAX_FILE_MB=1` 模擬過大；皆驗證拋特定例外、pipeline 能承接為 `DATAERR` —（T013、FR-063、FR-064）
- [X] T023 整合測試 `tests/integration/test_ingest_summary_shape.py`：以既有 Phase 1 txt/md/pdf fixture 跑 ingest，驗證 stdout top-level 仍符合 Phase 1 `QueryResponse` schema，且 `trace.steps[kind="ingest_summary"].detail.files[]` 各項欄位存在、舊行為不退化（Phase 1 fixtures 對應 file report 的 `skipped_segments=[]`、`pptx_notes=null`）—（T012、T016、T019、§II、backward compat）
- [X] T024 [P] 單元/契約測試 `tests/unit/test_format_detection.py`：覆蓋 suffix + content sniffing；合法 PDF/OOXML 能正確判定，副檔名正確但內容不符時應落入 `corrupt` / `unsupported`，不得誤 dispatch 至錯 parser —（T010、FR-002）

**Checkpoint**：Foundation 完成——新 parser 可接入、format detect 運作、fingerprint/re-ingest 判定成立、時間 / 大小閘生效、契約固化、既有 Phase 1 路徑零退化。

---

## Phase 3: User Story 1 — Ingest Office 文件至兩層知識儲存（P1）🎯 MVP

**Goal**：`ks ingest` 能把 docx / xlsx / pptx 納入既有 pipeline，產出 wiki page + vector chunk，`manifest.json` 為每檔留下 entry；idempotency 生效；同一批次 ingest 混合格式不中斷。

**Independent Test**：docx / xlsx / pptx 各 ≥ 3 份 fixture，對空 `/ks/` 執行 `uv run ks ingest ./fixtures/`，驗證：(a) `raw_sources/` 9 份副本；(b) `wiki/pages/` 產出對應頁面（xlsx 多 sheet 以 H2 分段）；(c) `manifest.json` 每檔 `relpath/sha256/derived` 正確，Office entry 另含 `parser_fingerprint`；(d) 相同內容與相同 parser 設定重跑 skipped；(e) 修改一檔內容或切換 `--pptx-notes` 時僅受影響檔案 update。

### Tests for User Story 1（先寫，紅 → 綠）⚠️

- [X] T030 [P] [US1] 於 `tests/fixtures/build_office.py` 補上 docx 生成：`valid/docx/plain.docx`（多段落）、`valid/docx/with_table.docx`（markdown table 可還原）、`valid/docx/with_image.docx`（1 張嵌入圖片 + alt-text `"Figure 1: sample"`）—（FR-080、quickstart §2）
- [X] T031 [P] [US1] 於 `tests/fixtures/build_office.py` 補上 xlsx 生成：`valid/xlsx/single_sheet.xlsx`（header + 10 rows）、`valid/xlsx/multi_sheet.xlsx`（3 個 sheet、每個 sheet 不同 header）、`valid/xlsx/with_formula.xlsx`（含公式 cached value）—（FR-080、FR-022）
- [X] T032 [P] [US1] 於 `tests/fixtures/build_office.py` 補上 pptx 生成：`valid/pptx/plain.pptx`（5 slides 純文字）、`valid/pptx/with_notes.pptx`（每 slide 含 speaker notes）、`valid/pptx/with_table_image.pptx`（含 table + 2 張嵌入圖片）—（FR-080、FR-030）
- [X] T033 [P] [US1] 單元測試 `tests/unit/test_parser_docx.py`：驗 paragraph / heading（level）/ list_item / table_row / placeholder（image）segment 順序與 metadata；驗 markdown table 格式正確；alt-text 正確帶入 `[image: ...]` —（FR-010, FR-011, FR-012）
- [X] T034 [P] [US1] 單元測試 `tests/unit/test_parser_xlsx.py`：驗每 sheet 產出 `sheet_header` + 多筆 `table_row` segment；`row_index` 為 1-based；公式 cached value 正常回填；公式無 cached value 時 chunk metadata `formula_only=True` —（FR-020, FR-021, FR-022）
- [X] T035 [P] [US1] 單元測試 `tests/unit/test_parser_pptx.py`：驗 slide 順序決定性；每 slide `slide_header` + title + body + notes；`--pptx-notes=exclude` 時 `notes` segment 完全不產生；slide 內僅含圖片時產出 `placeholder`，slide 索引不出現空洞 —（FR-030, FR-031, FR-033, Edge case）
- [X] T036 [US1] 整合測試 `tests/integration/test_office_pipeline.py`：對 `tests/fixtures/valid/` 下 9 份 Office fixture 執行 ingest → 驗所有 acceptance scenarios 1–4（空 `/ks/` 首次 ingest、重跑 skip、單檔 update、混合 Phase 1 格式不分表）—（US1 Independent Test、FR-040、FR-044、FR-045）

### Implementation for User Story 1

- [X] T040 [P] [US1] 新建 `src/hks/ingest/parsers/docx.py`：以 `python-docx` 讀入 → 依文件 body 順序產出 `Segment` 序列（paragraph / heading / list_item / table_row）；嵌入圖片 → `[image: <alt-text>]` placeholder；OLE / SmartArt → 各自 placeholder；macros → `[macros: skipped]`；回傳 `ParsedDocument` 與 `skipped_segments` 計數 —（FR-010, FR-011, FR-012、research §1）
- [X] T041 [P] [US1] 新建 `src/hks/ingest/parsers/xlsx.py`：以 `openpyxl.load_workbook(read_only=True, data_only=True)` 讀入；逐 sheet 產出 `sheet_header` segment（`## <sheet name>`）+ 每 row 的 `table_row` segment（markdown 3 行片段）；公式 cached value fallback；`chart` / `pivot` / `macros` → placeholder —（FR-020, FR-021, FR-022, FR-023、research §2）
- [X] T042 [P] [US1] 新建 `src/hks/ingest/parsers/pptx.py`：以 `python-pptx` 讀入；逐 slide 決定性地串接 title → 本文（shape 內文字）→ table → notes（視 flag）；嵌入圖片 / 影片 / 音訊 / object → placeholder；slide 內僅含圖片仍保留 `slide_header` + placeholder；`--pptx-notes=exclude` 時不讀 notes_slide —（FR-030, FR-031, FR-032, FR-033、research §3）
- [X] T043 [US1] 在 `src/hks/ingest/pipeline.py` 的 `PARSERS` dict 註冊 `docx` / `xlsx` / `pptx`；parser 呼叫處統一套用 `guards.preflight_size_check` 與 `guards.with_timeout`；parser 回傳後呼叫 `fingerprint.compute_parser_fingerprint(format, flags)` 寫入 `ManifestEntry` —（T010, T013, T014, T016, T040–T042）
- [X] T044 [US1] 擴充 `src/hks/storage/wiki.py::WikiStore.write_page()`：xlsx 格式的 page 以「檔名 H1 + 各 sheet H2」結構寫入（sheet 文字內容為 segment body 串接）；docx / pptx 沿用 Phase 1 單一 body 寫入 —（FR-042、data-model §1）
- [X] T045 [US1] 將 `IngestFileReport.skipped_segments` / `pptx_notes` 串到 `WikiStore.append_log_entry()`，使 `log.md` 在既有 event header 下追加 `- skipped_segments: ...` / `- pptx_notes: ...` bullet（pptx 以外格式不附 `pptx_notes`）—（T017、FR-043、data-model §8）

**Checkpoint**：US1 閘門——`uv run ks ingest tests/fixtures/valid/` 成功，exit `0`，stdout JSON 通過 schema，`/ks/graph/` 不存在；重跑 skip；單檔 update 不波及其他；Phase 1 既有 fixture 行為零退化。

---

## Phase 4: User Story 2 — Query 路徑命中 Office 內容（P1）

**Goal**：US1 ingest 產物可被 Phase 1 既有 `ks query` 路徑檢索命中；JSON schema、source / trace.route enum、confidence 計算、exit code 全部零改動。

**Independent Test**：US1 完成後，對 docx / xlsx / pptx 各提出 summary 類與 detail 類各一個問題（共 ≥ 6 條），驗證所有 query 輸出通過 Phase 1 `query-response.schema.json`、`source` / `trace.route` 不出現新值、關係類仍走 vector fallback 並附 Phase 2 預告語、exit `0`。

### Tests for User Story 2

- [X] T050 [P] [US2] 契約測試擴充 `tests/contract/test_json_schema.py`：新增「Office 來源的 query 回應仍符合 Phase 1 schema」case；`source` 僅可為 `wiki`/`vector` 子集、`trace.route` 不得 `graph`/`llm` —（FR-050, FR-051, FR-052、§II）
- [X] T051 [P] [US2] 整合測試 `tests/integration/test_query_office_hits.py`：先跑 US1 ingest，再對 ≥ 6 條 query 斷言 `route` / `source` / `confidence` 期望值；包含 xlsx 多 sheet 檢索（query 中提到 sheet name）與 pptx slide 內容檢索 —（spec US2 Acceptance 1–3）
- [X] T052 [US2] 擴充 `tests/integration/test_query_does_not_reparse_sources.py`：將 fixture 改為 US1 產物；以 mock 確認 query 路徑不會開啟任何 `.docx/.xlsx/.pptx` 檔、不會呼叫 `PARSERS` —（FR-040、§IV）

### Implementation for User Story 2

- [X] T055 [US2] 契約測試 `tests/contract/test_query_phase1_contract_preserved.py`：確認 Office 支援不引入新 route/source 值、不引入 LLM/graph branch、關係類附註仍保留；允許 `trace.steps[].detail` 補充位置 metadata，但不得改寫 Phase 1 routing semantics，也不得用 `git diff` 當 gate —（FR-050、FR-051、FR-052）
- [X] T056 [US2] 在 query 返回之 `trace.steps[].detail` 中為命中的 chunk 附上 `sheet_name` / `slide_index` / `section_type` metadata（若 chunk 帶此 metadata）；schema enum 不動、僅 `detail` 欄位內容擴充（`additionalProperties: true` 已允許）—（T015、FR-023、data-model §2）

**Checkpoint**：US2 閘門——query JSON schema 驗證 100% 通過；Office 來源內容可命中且路徑正確；query 路徑未觸發任何 parser 或檔案 re-read。

---

## Phase 5: User Story 3 — 部分可讀檔案的安全降級（P2）

**Goal**：加密 / 損壞 / 空檔 / 超時 / 超大 / 含 macros / 嵌入圖片等情境下，`ks ingest` 不中斷整批、正確回報每檔狀態、文字部分入庫、不可讀部分以佔位符 + `skipped_segments` 記錄；`--pptx-notes` 切換正確觸發 re-ingest。

**Independent Test**：US1 完成後，針對 `tests/fixtures/broken/office/` 與 `tests/fixtures/valid/{docx,xlsx,pptx}/` 的含 macros / 圖片版本執行 ingest，驗證 exit code `65`（有 DATAERR）、合法檔仍被處理、失敗檔 `files[].status="failed"` 帶正確 reason、`skipped_segments` 正確計數；再以 `--pptx-notes=exclude` 重跑 pptx 批次，驗證全部 `updated`（fingerprint 變更）且 log.md 對應事件含 `- pptx_notes: excluded`。

### Tests for User Story 3

- [X] T060 [P] [US3] 補 `tests/fixtures/build_office.py` 生成 broken fixtures：`broken/office/encrypted.pptx`（以 `msoffcrypto-tool` 加密密碼 `secret`）、`broken/office/corrupt.xlsx`（合法 xlsx 截斷後 128 bytes）、`broken/office/empty.docx`（0 byte）、`broken/office/timeout_bomb.docx`（巢狀百萬段落觸發 60s 超時；需 `HKS_OFFICE_TIMEOUT_SEC` 可縮短以加速測試）、`broken/office/oversized.xlsx`（實體 > 200MB 或使用 monkeypatch `HKS_OFFICE_MAX_FILE_MB=1`）—（FR-080、FR-060–FR-064）
- [X] T061 [P] [US3] 契約測試 `tests/contract/test_placeholder_prefix.py`：依 [contracts/office-placeholder-prefix.md](./contracts/office-placeholder-prefix.md) 驗 8 種字面的 regex 匹配；parser 產出的 placeholder segment 一律命中；負面 case（大寫前綴 / 缺冒號 / 非 ASCII 類型）視為一般文字不計入 skipped_segments —（FR-012、contracts/office-placeholder-prefix.md）
- [X] T062 [P] [US3] 整合測試 `tests/integration/test_office_degradation.py`：跑完整 `broken/office/` + 含 macros 的 `valid/*`；斷言 acceptance scenarios 1–5（嵌入圖片文字入庫、加密 failed 不中斷、損壞 atomic rollback、批次混合 exit `65`、macros 忽略但文字入庫）—（spec US3 Acceptance 1–5）
- [X] T063 [P] [US3] 整合測試 `tests/integration/test_pptx_notes_flag.py`：先 `--pptx-notes=include` 跑 `valid/pptx/with_notes.pptx`；再 `--pptx-notes=exclude` 重跑同 fixture；斷言第二次 `updated`（fingerprint 變更）、vector DB 中該檔 chunk 數減少、log.md 對應事件記 `- pptx_notes: excluded` —（FR-033、contracts/office-cli-flags.md §1）
- [X] T064 [P] [US3] 整合測試 `tests/integration/test_idempotency_parser_fingerprint.py`：手動 monkeypatch `importlib.metadata.version("openpyxl")` 回傳不同值；第二次 ingest 應觸發 `updated` 而非 `skipped` —（research §7、FR-044）
- [X] T065 [P] [US3] 契約測試擴充 `tests/contract/test_exit_codes.py`：新增 4 個 Office 專屬 case（encrypted、corrupt、timeout、oversized）；每個 case assert exit code `65` 與 stderr 首行格式 `[ks:ingest] error: ...`，且 stdout 仍為合法 JSON —（contracts/office-cli-flags.md §3、FR-003）

### Implementation for User Story 3

- [X] T070 [US3] 在 `src/hks/ingest/pipeline.py::_ingest_one_file()` 實作 atomic rollback：`parsed = parse(...)` 失敗 / timeout / oversized 時，所有已新增的 wiki page / vector id 一律 revert；`manifest.json` 不寫該 entry；確保無 partial derived artifact 殘留 —（FR-061、research §8）
- [X] T071 [P] [US3] 在 `src/hks/ingest/parsers/` 與 format-detect path 內補「無法開啟 / 加密」判斷：捕捉 parser / zip container / OOXML package 可識別的 encrypted / corrupt signal（例如 `PackageNotFoundError`、`InvalidFileException`、`BadZipFile` 或等效訊號），統一轉成 `KSError(exit_code=DATAERR, reason="encrypted" | "corrupt")`；`msoffcrypto-tool` 僅供 fixture 生成，不進 runtime 依賴 —（FR-060, FR-061、contracts/office-cli-flags.md §3）
- [X] T072 [P] [US3] 在 `src/hks/ingest/pipeline.py` 處理空檔：以 `Path.stat().st_size == 0` preflight 判斷 → `IngestFileReport(status="skipped", reason="empty_file")`；不走 parser、不建 artifacts —（FR-062、spec Edge case）
- [X] T073 [US3] 完成 `guards.with_timeout` 與 pipeline 的整合：超時拋 `TimeoutError` 於 `_ingest_one_file()` 捕捉 → `IngestFileReport(status="failed", reason="timeout")`；檔案切換時 reset itimer；整批不中斷 —（T013、FR-063）
- [X] T074 [US3] 完成 `guards.preflight_size_check` 與 pipeline 的整合：超大檔 → `IngestFileReport(status="failed", reason="oversized", detail="file_mb=X, limit_mb=Y")`；不進 parse；整批不中斷 —（T013、FR-064）
- [X] T075 [US3] 在 `src/hks/storage/wiki.py::append_log_entry()` 補完降級事件的寫入：`reason=encrypted|corrupt|timeout|oversized|empty_file` 時 event type 記為 `failed`（或 `skipped` for empty_file），`skipped_segments` 空值時對應 bullet 可省略；沒有 partial wiki page 被 append —（FR-043、data-model §8）

**Checkpoint**：US3 閘門——`tests/fixtures/broken/office/` 全批次 ingest exit `65`、整批不中斷；placeholder 前綴契約測試全綠；pptx notes flag re-ingest 正確；parser version bump 觸發 re-ingest 正確。

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**：文件同步、憲法 §I 終檢、覆蓋率、離線驗證、效能回歸。

- [X] T080 [P] 同步 [docs/main.md](../../docs/main.md) §3.1 / §5 / §8：補上 Phase 2 階段一 ingest 範圍、Office 檔案寫入結構說明、placeholder 前綴示意；不改動 query routing 敘述 —（readme sync、Phase 2 路線圖）
- [X] T081 [P] 更新 [readme.md](../../readme.md) 路線圖與 `ks ingest --help` 的 flag 說明；補上「支援 docx/xlsx/pptx」與 `--pptx-notes` 說明 —（DX）
- [X] T082 [P] 在 CI（`.github/workflows/*.yml` 或等效）加入「airgapped install 驗證」：`uv sync --offline` 從 wheel cache 能裝起；`pytest tests/integration/test_office_pipeline.py` 可於無網路執行 —（FR-082、SC-009）
- [X] T083 憲法 §I 終檢（grep + filesystem）：
  - `rg -n '"graph"' src/ ks/ config/ tests/` → 僅出現於 Phase 2 預告註解（documented allowlist），runtime code 0 命中
  - `rg -n 'llm|openai|anthropic' src/` → 0 命中
  - `find .ks-smoke -type d -name graph` → 0 結果
  - 將上述指令固化為 `tests/contract/test_constitution_gate.py` —（憲法 §I、SC-007）
- [X] T084 效能回歸：以 50 份混合 fixture（Phase 1 10 份 + US1 9 份 + 補充 31 份）測 query p95 < 3s（commodity laptop）；以 `pytest-benchmark` 或簡易 timer 記錄；結果寫入 `specs/002-phase2-ingest-office/research.md` §Performance Log 區段 —（SC-006）
- [X] T085 覆蓋率確認：`uv run pytest --cov=hks --cov-fail-under=80`；若新 parser / 降級路徑覆蓋不足，補 unit test —（SC-008、FR-081）
- [X] T086 執行 [quickstart.md](./quickstart.md) §3–§8 全流程作為 final smoke；結果寫 PR 描述；不通過不得 merge —（quickstart review checklist）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：零前置依賴；T001 → T002 為序列（T002 需 T001 的 `pyproject.toml`）；T003 / T004 可與 T001–T002 並行。
- **Foundational (Phase 2)**：依賴 Setup 完成；T010–T019 與 T024 多可並行（見下方），T016 / T023 須於 T010–T015、T017、T019 之後；T020 須於 T019 之後。
- **User Stories (Phase 3–5)**：全部依賴 Foundational；US1 為 MVP，US2 / US3 可於 US1 完成後任一順序啟動，或分工並行。
- **Polish (Phase N)**：依賴所有 US 完成；T083（憲法終檢）必須為最後 PR 前的最後 commit 之一。

### User Story Dependencies

- **US1（P1）**：可於 Foundational 完成後立即啟動；無 US 依賴。
- **US2（P1）**：需 US1 的 ingest 產物才能跑 query → 邏輯上 US2 的 integration test 依賴 US1 ingest 成功；但 US2 的 implementation（T055 / T056）幾乎不新增 code（主要是保守斷言），可與 US1 末段並行。
- **US3（P2）**：需 US1 的 parser 與 fingerprint 才能測降級；與 US2 無耦合，可與 US2 並行。

### Within Each User Story

- Tests（契約 / 整合）先寫，紅後開始 implementation。
- Models / common module（Foundational 已完成）→ parser → pipeline 整合 → storage 擴充。
- Parser 之間無耦合，可 [P] 並行。

### Parallel Opportunities

**Setup**：T003、T004 可與 T001/T002 並行。

**Foundational**：T011 / T012 / T013 / T014 / T017 / T018 / T019 / T024 皆 [P]（不同檔案）。T010 先完成（其他 task 可能 import `SourceFormat` / detect helper）；T016 需 T010+T013+T014 完成；T015 需 T012 完成；T020 / T021 / T022 / T023 於各自相依 implementation 完成後 [P]。

**US1**：
- Fixtures：T030 / T031 / T032 [P]
- Parser unit tests：T033 / T034 / T035 [P]
- Parsers：T040 / T041 / T042 [P]
- T043 / T044 / T045 依賴前述完成，需序列

**US2**：T050 / T051 / T052 [P]；T055 / T056 多半驗證已完成狀態，可 [P]。

**US3**：T060 / T061 / T062 / T063 / T064 / T065 [P]；T071 / T072 [P]；T070 / T073 / T074 / T075 為 pipeline 編輯需序列。

**Polish**：T080–T082 [P]；T083–T086 需序列收尾。

---

## Parallel Example: User Story 1

```bash
# 先跑 fixture 生成（可並行）
Task: "[US1] docx fixtures 生成 in tests/fixtures/build_office.py (T030)"
Task: "[US1] xlsx fixtures 生成 in tests/fixtures/build_office.py (T031)"
Task: "[US1] pptx fixtures 生成 in tests/fixtures/build_office.py (T032)"

# Parser unit tests 並行（不同檔）
Task: "[US1] tests/unit/test_parser_docx.py (T033)"
Task: "[US1] tests/unit/test_parser_xlsx.py (T034)"
Task: "[US1] tests/unit/test_parser_pptx.py (T035)"

# 三個 parser 實作並行
Task: "[US1] src/hks/ingest/parsers/docx.py (T040)"
Task: "[US1] src/hks/ingest/parsers/xlsx.py (T041)"
Task: "[US1] src/hks/ingest/parsers/pptx.py (T042)"
```

---

## Implementation Strategy

### MVP First（僅 US1）

1. Phase 1 Setup（T001–T004）
2. Phase 2 Foundational（T010–T023）
3. Phase 3 US1（T030–T045）
4. **STOP & VALIDATE**：`uv run ks ingest tests/fixtures/valid/` 成功、top-level QueryResponse 與 ingest_summary detail schema 皆通過；暫停驗證後再決定 US2 / US3 順序。

### Incremental Delivery

1. Setup + Foundational → 基座 ready（可獨立 commit、PR 可 merge）
2. US1 → demo「能 ingest」（第一個 PR）
3. US2 → demo「能 query 到」（第二個 PR）
4. US3 → demo「壞檔不爆炸」（第三個 PR）
5. Polish → 收尾 PR（含文件與憲法 §I 終檢）

### Parallel Team Strategy

- Dev A：Setup + Foundational → 交接後 US2（小）
- Dev B：US1 三個 parser（主力）
- Dev C：US3 降級與 fingerprint（獨立）
- 所有人在 Polish 收尾

---

## FR → Task 追溯

| FR | Tasks |
|---|---|
| FR-001 格式支援 | T001, T010, T040–T043 |
| FR-002 suffix + sniff 判定 | T010, T024, T043 |
| FR-003 單一權威格式清單 | T010 |
| FR-010 docx 抽取 | T030, T033, T040 |
| FR-011 表格 markdown | T011, T033, T040, T041 |
| FR-012 佔位符 | T011, T033, T040, T041, T042, T061 |
| FR-020 xlsx 抽取 | T031, T034, T041 |
| FR-021 row chunk | T015, T031, T034, T041 |
| FR-022 公式 | T031, T034, T041 |
| FR-023 xlsx 忽略項 | T041, T061 |
| FR-030 pptx 抽取 | T032, T035, T042 |
| FR-031 slide 順序 | T032, T035, T042 |
| FR-032 pptx 忽略項 | T042, T061 |
| FR-033 `--pptx-notes` | T014, T018, T042, T063 |
| FR-040 pipeline 整合 | T016, T043, T052 |
| FR-041 manifest 延續 Phase 1 schema | T010, T021 |
| FR-042 wiki 頁面規則 | T044 |
| FR-043 log.md 格式 | T017, T045, T075 |
| FR-044 SHA256 + parser_fingerprint 判定 | T010, T014, T016, T021, T063, T064 |
| FR-045 ingest top-level QueryResponse 不變 | T012, T019, T020, T023, T065 |
| FR-050 query 契約 | T050, T055 |
| FR-051 Phase 2 附註保留 | T050 |
| FR-052 source/trace.route 不擴 | T050, T083 |
| FR-060 加密處理 | T060, T071 |
| FR-061 atomicity | T070, T071 |
| FR-062 空檔 | T072 |
| FR-063 timeout | T013, T022, T073 |
| FR-064 檔案大小 | T013, T022, T074 |
| FR-070 禁 graph | T010, T083 |
| FR-071 禁 LLM | T002, T083 |
| FR-072 write-back 不動 | T055, T083 |
| FR-073 domain-agnostic | T040–T042（無領域詞彙） |
| FR-080 fixtures | T030–T032, T060 |
| FR-081 pytest 閘門 | T085 |
| FR-082 local-first | T002, T082 |

## SC → Task 追溯

| SC | Tasks |
|---|---|
| SC-001 9 份 ingest | T036 |
| SC-002 idempotent 降 ≥50% | T036, T063, T064 |
| SC-003 query schema 100% | T050, T051, T055 |
| SC-004 Phase 1 無退化 | T023, T050, T052, T055 |
| SC-005 降級 100% | T062, T063 |
| SC-006 p95 < 3s | T084 |
| SC-007 無 graph runtime | T083 |
| SC-008 pytest + 覆蓋率 | T085 |
| SC-009 airgapped | T002, T082 |

## 憲法 Gate → Task 追溯

| § | Tasks |
|---|---|
| §I Phase Discipline | T010（SourceFormat 範圍）、T083（grep + filesystem）、T055（routing 不動） |
| §II Stable Output Contract | T019（ingest_summary detail schema）、T020（契約測試）、T023（top-level QueryResponse 不退化）、T050（query schema 不動）、T065（exit codes） |
| §III CLI-First & Domain-Agnostic | T002（無 LLM dep）、T040–T042（無領域詞彙）、T082（airgapped） |
| §IV Ingest-Time Organization | T015（segment-aware chunk）、T016（pipeline 同步兩層）、T052（query 不 reparse） |
| §V Write-back Safety | T055（writeback/ 不動）、T083（grep 驗證） |

---

## Notes

- `[P]` = 不同檔、無前置依賴
- `[USx]` 僅用於 Phase 3–5；Setup / Foundational / Polish 不帶
- Phase 2 Foundational 完成前不開 US；每個 US 尾端 Checkpoint 為「可 demo 閘門」
- 任何新增 graph / LLM / 自動 write-back 程式碼 = 破壞憲法 §I / §V → tasks 中提及 graph 皆為「排除性 assert」
- Commit 粒度：每完成一個 task 或一組 `[P]` 任務即 commit，commit message 起首 `T0XX:` 方便追溯
- 跨 task 衝突：T043 / T044 / T045（US1 尾段）與 T070 / T073 / T074 / T075（US3）都編輯 `pipeline.py` / `wiki.py`；若並行需在 T016 完成後以 rebase 解衝突，勿同時 push

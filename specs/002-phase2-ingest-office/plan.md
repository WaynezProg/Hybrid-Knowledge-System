# Implementation Plan: Phase 2 階段一 — Office 文件（docx / xlsx / pptx）ingest 擴充

**Branch**: `002-phase2-ingest-office` | **Date**: 2026-04-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-phase2-ingest-office/spec.md`

## Summary

將 Phase 1 的 ingestion pipeline 擴充至三種 Office 格式：以 `python-docx` / `openpyxl` / `python-pptx` 三個純 Python、MIT 授權、可離線的 parser 替代對應的 Office zip 結構；parser 共用抽象 `OfficeParser` 介面，回傳「有序 segment 序列 + skipped_segments 清單」，由 `ingest/pipeline.py` 進入既有 `parse → normalize → extract → update(wiki, vector)` 四階段，不另立平行流程。格式判定以副檔名為主，並對 PDF / OOXML 做輕量 content sniffing 驗證，避免錯副檔名誤 dispatch。xlsx 多 sheet 以單一 wiki 頁面壓平（每 sheet 為 H2 子標題）；表格全部以 markdown 表格呈現（wiki / vector 共用一份）；嵌入圖片、OLE object、macros、SmartArt 以固定前綴佔位符（`[image: ...]` / `[macros: skipped]` 等）保留文字流位置，同步於 `skipped_segments` 記錄，供 Phase 3 OCR / VLM 就地替換；pptx speaker notes 預設納入，`ks ingest --pptx-notes=include|exclude` 可切換。每檔加上 60s 超時（signal-based）與 200MB 大小閘（`Path.stat()` 前置檢查），兩者為 soft default、可由 `HKS_OFFICE_*` 環境變數調整。re-ingest 判定以內容 SHA256 為基線，另以 `parser_fingerprint`（格式別 + parser library 版本 + 影響解析結果的 flag）處理 parser 升級或 flag 切換，避免誤 skip。`/ks/graph/`、LLM routing、全自動 write-back 一律不碰；CLI stdout top-level QueryResponse 與 exit code 契約沿用 Phase 1 不變。

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`（mise 管理；沿用 Phase 1 `.python-version` / `.mise.toml`）
**Primary Dependencies**:
- 新增 parser（全部純 Python、MIT、可離線 wheel）：
  - `python-docx`（docx；抽取段落 / 標題 / 表格 / 清單；零 C 擴充）
  - `openpyxl`（xlsx；`data_only=True` 可直接取 cached 公式值 — 對應 FR-022）
  - `python-pptx`（pptx；slide / shape / notes 完整存取；處理 layout/master 時可跳過）
- 沿用 Phase 1：`typer` / `sentence-transformers` / `chromadb` / `ruamel.yaml` / `python-slugify` / `jsonschema` / `pypdf` / `markdown-it-py`
- 無新增 LLM / graph 依賴
- Test：`pytest` + `pytest-cov`（沿用）；新增 `tests/fixtures/valid/{docx,xlsx,pptx}/` 與 `tests/fixtures/broken/office/` 樹
- Lint / type：`ruff` / `mypy strict`（沿用）

**Storage**:
- `/ks/` runtime 結構不變（`raw_sources/`、`wiki/`、`vector/db/`、`manifest.json`）
- `raw_sources/` 新增 `.docx` / `.xlsx` / `.pptx` 原檔；檔案 immutable
- `/ks/graph/` **持續禁止建立**（憲法 §I）；parser 或 pipeline 中任何 graph 導向 code path 一律不加
- `config/routing_rules.yaml` 不需變更（僅 wiki / vector 兩路）

**Testing**: `pytest`（contract / integration / unit / fixture）；新增契約點包含 ingest stdout JSON 的 `skipped_segments` schema（作為 ingest summary 的擴充、非 query schema 變更）；覆蓋率 ≥ 80%（新 parser 與降級分支；門檻沿用 Phase 1 `[tool.coverage]`）

**Target Platform**: macOS / Linux CLI（沿用 Phase 1）。Windows 不支援（超時採 signal-based，POSIX only）；若未來需要 Windows，另開 spec 切換為 process-based timeout。

**Project Type**: CLI（單一 `hks` package，無 frontend / backend 拆分）

**Performance Goals**:
- 查詢 p95 延遲 < 3s（新增格式後仍須成立，見 spec SC-006）
- 單檔 ingest ≤ 60s（FR-063 soft default）
- 重複 ingest skip 率：未變更檔案 100% skip，重跑 wall-clock 降 ≥ 50%

**Constraints**:
- 所有 parser MUST offline（parser library 預打包於 `uv.lock` wheel cache；任何對外網路呼叫視為 bug）
- 單檔 200MB 上限（`HKS_OFFICE_MAX_FILE_MB` 可調，preflight 檢查）
- 單檔超時 60s（`HKS_OFFICE_TIMEOUT_SEC` 可調，signal-based）
- 佔位符前綴 MUST 跨 parser 一致，為 `[image:` / `[embedded object:` / `[macros:` / `[smartart:` / `[video:` / `[audio:` / `[chart:` / `[pivot:` 八種固定 ASCII 字面
- JSON 輸出 100% 符合憲法 §II schema（query 路徑）與 Phase 1 ingest summary 擴充 schema
- `source` / `trace.route` 仍限 `wiki | vector`；本 spec 不碰 schema enum

**Scale/Scope**:
- 驗收：docx / xlsx / pptx 各 ≥ 3 份 fixture、共 ≥ 9 份混合 + Phase 1 既有 10 份
- 單檔最大 sheet 數：openpyxl 預設支援即可（實測至 50 sheet 無壓力）
- 單 sheet 最大 row 數：以 chunk 化為 row 級別，不限制 row 總數（記憶體以 streaming read 控制：`openpyxl.load_workbook(read_only=True, data_only=True)`）
- Chunking：沿用 Phase 1 的 512 token / 64 overlap（MiniLM tokenizer）；segment 邊界優先於 chunk 邊界對齊（段落 / row / slide 不跨 chunk，長度超限時分段但保留 metadata）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

本 feature 對憲法 1.1.0 §I–§V 的遵守方式逐條對照。初檢於 Phase 0 前完成；Phase 1 設計產出後再檢（見文末 Post-Design Re-Check）。

### §I Phase Discipline — ✅ PASS

- 新 parser 全部位於 `src/hks/ingest/parsers/`，與 Phase 1 parser 平行；不新增 `src/hks/graph/`、不引入 graph database、不引入 LLM SDK。
- `core/paths.py` 的 `/ks/graph/` 黑名單規則不動；spec FR-070 再次以測試強制驗證（grep + 目錄存在性檢查）。
- Routing `config/routing_rules.yaml` 僅 `wiki`/`vector` 兩值，本 spec 不擴；enum validation 由 Phase 1 `routing/rules.py::RoutingRuleSet.validate()` 承擔。
- `dependencies` 僅增 `python-docx` / `openpyxl` / `python-pptx` 三個純 parse library，皆無 graph / LLM 相關 transitive dep（於 Phase 0 research 驗證 dep tree）。

### §II Stable Output Contract — ✅ PASS

- `ks query` 輸出 schema 零改動：`source` / `trace.route` enum 不擴、`confidence` 計算規則沿用、`trace.steps.kind` enum 不新增。
- Exit code 契約零改動；新增的降級案例（超時、超大、加密、損壞）全部歸入 Phase 1 `DATAERR=65` 或 `GENERAL=1`，無需新 code。
- `ks ingest` stdout top-level 仍為 Phase 1 已存在的 `QueryResponse`；本 spec 僅擴充 `trace.steps[kind="ingest_summary"].detail`，以 `contracts/ingest-summary-detail.schema.json` 固化其 shape。
- ingest summary detail schema 為 §II 的相容擴充；不影響既有 agent 解析 top-level QueryResponse。

### §III CLI-First & Domain-Agnostic — ✅ PASS

- 入口仍為 `ks` CLI；不引入任何 UI、HTTP server、MCP adapter。
- 本地 embedding 沿用 Phase 1 模型；parser 皆純 Python，無任何外部服務呼叫（Phase 0 會以 `pytest` `responses`/`respx` / socket guard 驗證 airgapped）。
- 領域詞彙：parser 僅處理文件結構（段落、cell、slide、表格），不寫入任何領域詞典；`routing_rules.yaml` 不碰。

### §IV Ingest-Time Organization — ✅ PASS

- 新 parser 統一回傳 `ParsedDocument`（見 data-model.md）；由既有 `ingest/pipeline.py` 驅動 `parse → normalize → extract → update(wiki, vector)` 四階段，不另立平行流程。
- Query 路徑零改動，不會重新 parse office 檔；測試 `test_query_does_not_reparse_sources` 涵蓋新格式。
- 三層同步仍由 `manifest.json` 承擔；atomicity 由 pipeline 的 per-file 交易邏輯保證（Phase 1 已有，新 parser 僅延伸）。

### §V Write-back Safety — ✅ PASS

- Write-back 邏輯完全不動；`writeback/gate.py` 僅消費 query 結果，與 parser 格式無關。
- Phase 2 第三張 spec 才會碰全自動 write-back；本 spec 禁止觸及。

**Gate 結果**：全數 PASS，無需 Complexity Tracking 豁免。

## Project Structure

### Documentation (this feature)

```text
specs/002-phase2-ingest-office/
├── plan.md                                  # 本文件（/speckit.plan 產出）
├── spec.md                                  # /speckit.specify 產出 + clarify 擴充
├── research.md                              # Phase 0 產出（parser 選型、timeout、atomicity、fingerprint）
├── data-model.md                            # Phase 1 產出（ParsedDocument 擴充、Segment / SkippedSegment、Manifest fingerprint）
├── quickstart.md                            # Phase 1 產出（本機 setup + fixture 生成腳本）
├── contracts/
│   ├── ingest-summary-detail.schema.json    # ingest_summary trace detail schema（新增，固化 files / skipped_segments 等）
│   ├── office-placeholder-prefix.md         # 8 種佔位符前綴的固定字面與使用時機
│   └── office-cli-flags.md                  # `--pptx-notes` 等新 flag 契約（exit code / 行為）
├── checklists/
│   └── requirements.md                      # /speckit.specify 建立、/speckit.clarify 更新
└── tasks.md                                 # /speckit.tasks 產出（本文件不建立）
```

### Source Code (repository root)

```text
src/hks/
├── cli.py                                    # 新增 `--pptx-notes` option；其餘不動
├── commands/
│   └── ingest.py                             # 保持 top-level QueryResponse；擴充 ingest_summary detail
├── errors.py                                 # 不動（ExitCode 與 KSError 沿用）
├── core/
│   ├── paths.py                              # 不動（graph 黑名單持續生效）
│   ├── schema.py                             # 不動（top-level QueryResponse schema 零改動）
│   ├── manifest.py                           # 擴充 SourceFormat/detect helper；ManifestEntry 新增 parser_fingerprint
│   ├── lock.py                               # 不動
│   └── text_models.py                        # 不動
├── ingest/
│   ├── pipeline.py                           # 擴充 PARSERS dict；新增 per-file timeout / size gate；atomic commit 強化
│   ├── models.py                             # 擴充 ParsedDocument → 新增 segments / skipped_segments
│   ├── extractor.py                          # 增加 segment-aware chunk 切分（段落 / row / slide 不跨 chunk）
│   ├── normalizer.py                         # 佔位符字串保留原樣；normalize 不剝除固定前綴
│   ├── office_common.py                      # 新增：PLACEHOLDER_PREFIX 常數、SkippedSegment dataclass、to_markdown_table()
│   └── parsers/
│       ├── txt.py / md.py / pdf.py           # 不動
│       ├── docx.py                           # 新增：段落 / 標題 / 表格 / 清單抽取 + 佔位符
│       ├── xlsx.py                           # 新增：sheet → row 展開 + markdown 表格 + H2 子標題
│       └── pptx.py                           # 新增：slide / notes / 表格 / 佔位符 + --pptx-notes 分流
├── routing/                                  # 不動（仍 rule-based、wiki/vector）
├── storage/
│   ├── wiki.py                               # 微調：log entry 允許附 skipped_segments / pptx_notes 欄位
│   └── vector.py                             # 不動
└── writeback/                                # 不動

config/
└── routing_rules.yaml                        # 不動

tests/
├── contract/
│   ├── test_json_schema.py                   # 不動（query schema 零改動）
│   ├── test_ingest_summary_detail_schema.py  # 新增：驗 ingest_summary detail 含 files / skipped_segments
│   ├── test_exit_codes.py                    # 擴充：加密 / 損壞 / 超時 / 超大各一個 case
│   └── test_placeholder_prefix.py            # 新增：8 種佔位符前綴的字面與位置
├── integration/
│   ├── test_office_pipeline.py               # 新增：docx+xlsx+pptx 混合 ingest → query 全流程
│   ├── test_pptx_notes_flag.py               # 新增：flag 切換觸發 re-ingest
│   ├── test_idempotency_parser_fingerprint.py# 新增：parser 升級或 flag 切換時正確 re-ingest
│   └── test_query_does_not_reparse_sources.py# 擴充：新格式納入驗證
├── unit/
│   ├── test_parser_docx.py                   # 新增
│   ├── test_parser_xlsx.py                   # 新增
│   ├── test_parser_pptx.py                   # 新增
│   ├── test_timeout_gate.py                  # 新增：signal-based timeout
│   └── test_filesize_gate.py                 # 新增：stat 前置檢查
└── fixtures/
    ├── valid/
    │   ├── docx/                             # ≥ 3 份：純文字 / 含表格 / 含嵌入圖片 + alt-text
    │   ├── xlsx/                             # ≥ 3 份：單 sheet / 多 sheet / 含公式 cached values
    │   └── pptx/                             # ≥ 3 份：純文字 / 含 notes / 含表格 + 嵌入圖片
    └── broken/
        └── office/                           # encrypted.pptx / corrupt.xlsx / oversized.docx / timeout_bomb.docx / empty.docx

docs/ / readme.md / AGENTS.md                 # 不動（Phase 2 階段性文件更新交由實作 commit）
```

**Structure Decision**: 沿用 Phase 1 單一 Python package `src/hks/` 布局；新功能以 parser 擴充 + 少量 core / ingest 檔的微調實作，不新增子套件層級（graph 子套件留到 Phase 2 第二張 spec）。`ingest/office_common.py` 為新增共用模組，聚合佔位符常數、SkippedSegment 型別、markdown 表格 helper，避免三個 parser 重複定義。

## Complexity Tracking

> 無憲法違反項需豁免。下表保留僅為文件一致性；若後續 Post-Design Re-Check 發現違反再填。

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| （無） | — | — |

## Post-Design Re-Check

設計產出（`research.md` / `data-model.md` / `contracts/`）完成後重新對照憲法：

- §I：`dependencies` 實測：`python-docx` / `openpyxl` / `python-pptx` 的 transitive 無 graph DB / 無 LLM SDK（Phase 0 research 附 dep tree 驗證）。✅
- §II：`contracts/ingest-summary-detail.schema.json` 以 `jsonschema` 固化；契約測試覆蓋全部新增欄位；top-level QueryResponse schema 零改動。✅
- §III：三個 parser 皆純 Python、純離線；無 HTTP client 匯入（ruff 規則搭配 `flake8-tidy-imports` 於 Phase 0 確認 import 黑名單）。✅
- §IV：ingest pipeline 在寫入階段完成 `parse → normalize(含佔位符保留) → extract(segment-aware chunk) → update(wiki + vector)`；query 路徑零改動、整合測試強制驗證無 re-parse。✅
- §V：write-back 邏輯完全不動；spec FR-072 已禁止任何自動寫入改動。✅

Re-check 結果：PASS（於 `research.md` / `data-model.md` / `contracts/` 完成後確認，無需 Complexity Tracking）。

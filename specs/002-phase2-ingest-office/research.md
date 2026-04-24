# Phase 0 — Research: Office Ingest Extension

**Feature**: 002-phase2-ingest-office
**Scope**: 解決 plan.md Technical Context 中的所有技術選擇與未決點，輸出可直接落地的決策表。

## §1 docx parser 選型

**Decision**: `python-docx`（`>=1.1,<2`；MIT；純 Python）

**Rationale**:
- 最成熟的 docx 解析器，社群 15+ 年、維護活躍。
- 原生 API 直接暴露段落、標題 style（`Heading 1`–`9`）、表格 row/cell、清單層級、run-level 格式。
- 支援讀取圖片 alt-text / caption（`docx.oxml` 路徑），對應 spec FR-012 的佔位符 `[image: <alt>]` 需求。
- 純 Python，無 C 擴充，可 vendor 至 `uv.lock` 離線 wheel。

**Alternatives considered**:
- `docx2txt`：只回傳平鋪 text，失去標題階層、表格結構、清單 — 不符 FR-010 / FR-011。
- `mammoth`：轉 HTML / markdown，但對表格與清單保留度不如 `python-docx` 可控；授權 BSD。備選但增加一層轉換、難以精準插入佔位符。
- `pandoc` 子程序：非 Python，額外系統依賴，違背 local-first wheel 化原則。

## §2 xlsx parser 選型

**Decision**: `openpyxl`（`3.1.x`；MIT；純 Python），以 `load_workbook(read_only=True, data_only=True)` 開啟

**Rationale**:
- `data_only=True` 直接回傳 cell 的 cached computed value（FR-022）；值不存在時自動 fallback 至公式字串，恰好對應「`formula_only=true` metadata」需求。
- `read_only=True` 啟用 streaming mode，記憶體占用與 sheet / row 數量解耦，可處理大型 xlsx。
- 原生支援 sheet 逐一迭代、merged cells 邊界偵測（納入 edge case 考量）。
- MIT，純 Python，可離線。

**Alternatives considered**:
- `pandas` + `openpyxl`：重量級（numpy、dateutil 等 transitive），違背 Phase 1 lean stack 基調；強行使用會引入測試不必要的複雜度。
- `xlrd`：2.0 後移除 xlsx 支援，不再適用。
- `xlsx2csv` 子程序：失去 sheet 結構與 metadata。

## §3 pptx parser 選型

**Decision**: `python-pptx`（`>=1.0,<2`；MIT；純 Python）

**Rationale**:
- 官方級穩定 pptx 解析器，slide / layout / master / notes 四層模型完整。
- `slide.notes_slide.notes_text_frame` 直接取 speaker notes（FR-030、FR-033）。
- 表格、形狀內文字、圖片 alt-text 皆有公開 API，對應佔位符需求。
- MIT，純 Python，可離線。

**Alternatives considered**:
- 無成熟替代。`pptx2txt` 僅有第三方實驗性包，不考慮。

## §4 佔位符前綴清單與字面

**Decision**: 以下 8 種固定 ASCII 字面，跨 parser 一致，於 `src/hks/ingest/office_common.py` 以常數集中管理：

| 來源類型 | 佔位字面 | 典型出處 |
|---|---|---|
| 嵌入圖片 | `[image: <alt-text 或空>]` | docx `<w:drawing>`、pptx `Picture` shape、xlsx `CellImage` |
| 嵌入 OLE object | `[embedded object: <type>]` | docx 嵌入 Excel、pptx 嵌入 PDF |
| SmartArt | `[smartart: <summary 或空>]` | docx / pptx 皆可能出現 |
| Macros | `[macros: skipped]` | docm / xlsm / pptm |
| 影片 | `[video: skipped]` | pptx 嵌入影片 |
| 音訊 | `[audio: skipped]` | pptx 嵌入音訊 |
| Chart | `[chart: skipped]` | xlsx、pptx |
| PivotTable | `[pivot: skipped]` | xlsx |

**Rationale**:
- 方括號 `[` 為 ASCII，`json` 序列化安全、CJK 文字中易視別。
- 前綴單字皆用小寫 + 冒號 + 空白，供 Phase 3 OCR / VLM 以 regex 就地替換（例：`\[image: [^\]]*\]` → `<OCR 後文字>`）。
- `<alt-text 或空>` 欄位允許為空字串（`[image: ]`），保留位置即可。

**Alternatives considered**:
- XML 風格 `<image alt="..."/>`：可能與 docx XML 意外 collide，破壞文字流的純文字假設。
- 純 emoji 或特殊字元：embedding 模型對此類 token 的語意向量不穩定，可能干擾檢索。

## §5 Timeout 機制

**Decision**: 以 `signal.setitimer(signal.ITIMER_REAL, 60.0)` + `SIGALRM` handler 實作 per-file 60 秒上限（可由 `HKS_OFFICE_TIMEOUT_SEC` 覆寫，最小 5s、最大 600s）。逾時以 `TimeoutError` 被 pipeline 捕捉轉為 `DATAERR`。

**Rationale**:
- HKS 鎖定 macOS / Linux，POSIX 信號可靠、零額外依賴。
- Ingest 為單進程單執行緒模型，`SIGALRM` 於主執行緒觸發符合預期。
- Signal handler 設計為「僅 raise TimeoutError，不做清理」；清理由 pipeline try/finally 走 atomic rollback。
- 檔案切換時必先 `signal.setitimer(ITIMER_REAL, 0)` 歸零，避免跨檔殘餘。

**Alternatives considered**:
- `concurrent.futures.ThreadPoolExecutor(..).result(timeout=)`：無法真正中斷 parser 執行緒，僅 CancelledError 但 thread 繼續跑、造成記憶體累積與下一檔超時錯位。
- `multiprocessing`：真能 kill，但啟動成本（fork + import 三個 parser + embedding model 的 spawn cost）與 ingest 單檔預期秒數不成比例。
- `faulthandler.dump_traceback_later`：僅供除錯，不中斷。

**Windows**：不支援；`SIGALRM` 不存在。若未來需跨平台，以獨立 spec 改採 `multiprocessing.Process` + `join(timeout)` 模式；本 spec 明示 target 為 POSIX only。

## §6 檔案大小閘

**Decision**: `Path.stat().st_size > 200 * 1024 * 1024` preflight 檢查（可由 `HKS_OFFICE_MAX_FILE_MB` 覆寫，最小 1、最大 2048）；超過上限直接標 `DATAERR`，不進入 parse。

**Rationale**:
- `stat` 成本 O(1)，遠低於開啟 zip container。
- 200MB 為 Office 實務保守上限：典型 docx < 10MB、xlsx < 50MB（含大量公式與 cached values）、pptx < 100MB（含 embedded media）。
- 超大 xlsx 雖有 `read_only=True` streaming，但 zip 內部解壓仍可能觸發記憶體激增；先擋後驗證。

**Alternatives considered**:
- 依格式分別定上限（docx 50MB、xlsx 200MB、pptx 300MB）：實作複雜、難以向使用者解釋單一數字。留待 plan 調整時再考慮（FR-064 已預留）。

## §0 格式判定策略（suffix + sniff）

**Decision**: 以副檔名作為 primary dispatch，並對容易偽裝的格式做輕量 content sniffing 驗證：

- PDF：副檔名為 `.pdf` 時，額外檢查檔頭 `%PDF-`
- OOXML（docx / xlsx / pptx）：副檔名命中時，額外檢查 zip container 與 `[Content_Types].xml` 的 main part/content-type
- txt / md：沿用 Phase 1 suffix-only；不新增昂貴 sniffing

**Rationale**:
- 符合 spec FR-002「副檔名為主，不可信任者搭配內容嗅探」。
- 不引入大型 MIME 偵測依賴；只做 parser dispatch 所需的最小驗證。
- 可把「副檔名對但內容壞掉」更早歸類到 `corrupt` / `unsupported`，避免 parser 錯誤訊息過度分散。

## §7 parser_fingerprint 與 re-ingest 判定

**Decision**: 在 `ManifestEntry` 新增 `parser_fingerprint: str` 欄位；re-ingest 判定改為「內容 SHA256 為主，另比對 parser_fingerprint」：

- `entry.sha256 == current_sha256` 且 `entry.parser_fingerprint in (current_fingerprint, "*")` → skip
- SHA256 改變，或 fingerprint 不相容 → update / create

`parser_fingerprint` 構造：`{format}:v{parser_library_version}:{flags_digest}`
- `format`：`docx` / `xlsx` / `pptx` / `txt` / `md` / `pdf`
- `parser_library_version`：`python-docx` / `openpyxl` / `python-pptx` 的實際安裝版本；以 `importlib.metadata.version()` 讀取
- `flags_digest`：影響解析結果的 flag 組合的短 hash（例如 `pptx` 含 `notes=include|exclude`；其他 format 目前為空字串）

**Rationale**:
- 單看 SHA256 會在 parser 升級 / flag 切換時誤 skip（例：`--pptx-notes=exclude` 後 notes 的 chunk 仍留在 vector DB）。
- 加入 library version 使 dependency 升級自動觸發 re-ingest；避免 subtle 差異累積。
- 加入 `flags_digest` 處理 FR-033 要求的「flag 變更須觸發 re-ingest」。
- 舊 Manifest（Phase 1 ingest 出的）無此欄位時視為 `*`（wildcard），允許跨版本無痛繼承；於 ingest 重跑時補齊。

**Alternatives considered**:
- 重跑全部 artifact：簡單但違背 idempotency 體感。
- 另立 `.parsers_version` 檔：分散 truth source、易失一致。

## §8 Atomicity / 交易語意

**Decision**: 沿用 Phase 1 per-file 交易模型，但針對 Office parser 的多段輸出強化 rollback。流程：
1. parse（含佔位符 + skipped_segments 收集）→ in-memory `ParsedDocument`
2. 取得 `file_lock(LOCK_PATH)`
3. 計算 `parser_fingerprint`；比對 Manifest 判斷 skip / create / update
4. 對 update 情境：先 delete 舊 `wiki_pages[]` 與 `vector_ids[]` 對應資源，**再**寫入新版本
5. 成功後 `atomic_write(manifest.json)`；任何 step 失敗 → rollback：復原被刪 artifacts（若可）或標 `DATAERR` 並清除 partial
6. 釋放 lock

**Rationale**:
- 與 Phase 1 `pipeline.py` 既有結構一致，新 parser 僅擴充步驟 1 的輸出欄位、其餘 rollback path 全復用。
- `manifest.json` 作為「事實來源」：artifact 只有在 manifest 引用時才算存在，rollback 透過 manifest 未 commit 自動達成「視為未寫入」。

**Alternatives considered**:
- 兩階段提交（先寫 staging 目錄再 rename）：Phase 1 未採，本 spec 亦不引入；增加 disk footprint 與跨 FS rename 複雜度。

## §9 Chunk 策略

**Decision**: 沿用 Phase 1 的 `512 token / 64 overlap`（MiniLM tokenizer），但 chunk 邊界 **優先於** segment 邊界對齊：

- docx：chunk 邊界優先落在段落 / heading 之間。heading 級別變化（例如 H1 → H2）MUST 為 chunk 邊界。
- xlsx：單 row chunk = `## <sheet name>\n\n` 前綴 + 該 row 的 markdown 表格片段（3 行）。row 內容長度超過 chunk 上限時，以 cell 為單位切分，每片段保留 sheet + row metadata。
- pptx：單 slide chunk = `## Slide <n>` 前綴 + title + body + notes（若 include）。slide 內容超限時分段保留 slide 索引。

**Rationale**:
- 與 Phase 1 `extractor.py` 的段落切分邏輯對齊；新增 segment-aware 策略而非重寫。
- query 命中時 chunk 帶 sheet / slide / section metadata，agent 可直接引用位置（例如「於 Sheet2 第 3 row」）。

**Alternatives considered**:
- per-sheet 或 per-slide 直接一個 chunk：長度失控，可能超過 MiniLM 512 token 上限被截斷。

## §10 Dependency 深度審查（§I 守門）

**Decision**: `python-docx` / `openpyxl` / `python-pptx` 三者的 transitive 依賴：

- `python-docx`：`lxml`（純 C 擴充，已存在於 Phase 1 dep tree，無新 transitive）、`typing-extensions`
- `openpyxl`：`et-xmlfile`（純 Python，openpyxl 專屬 xml writer）
- `python-pptx`：`lxml`（共用）、`Pillow`（圖片解碼；注意：不使用 PIL.show，僅為 alt-text 與尺寸讀取）、`XlsxWriter`（stub，未使用於讀取路徑）

**審查結果**：
- 無任何 graph DB / LLM SDK / HTTP client（違反 §I 可能性零）。
- `Pillow` 為圖片 metadata 讀取，不主動觸發網路；若不放心，於 `pyproject.toml [tool.uv]` 凍結版本並加 ruff 規則禁 `urllib` / `requests` import 至 `hks.ingest.parsers.*`。
- 所有 library 可從 PyPI 下載 `.whl`，預打包後 airgapped 可安裝。

## §11 測試策略

**Decision**:
- **Fixture 準備腳本**：`tests/fixtures/build_office.py`，以程式化方式由 `python-docx` / `openpyxl` / `python-pptx` 生成 fixture；確保跨平台、匿名化、可重現。加密檔與損壞檔以特殊手法產生（`msoffcrypto-tool` 加密，或直接截斷 zip bytes）。
- **Contract**：`test_ingest_summary_detail_schema.py` 驗 `trace.steps[kind="ingest_summary"].detail` 含 `files` / `skipped_segments` / `pptx_notes`；`test_placeholder_prefix.py` 以 fixture → pipeline → chunk 驗證 8 種佔位符字面出現位置正確。
- **Integration**：`test_office_pipeline.py` 混合 9 份 fixture 跑 ingest + query，比對 JSON；`test_pptx_notes_flag.py` 驗 flag 切換觸發 re-ingest；`test_idempotency_parser_fingerprint.py` 以 mock fingerprint 模擬 library 升級。
- **Unit**：各 parser 獨立測試 + timeout / size gate 單元測試。

**Rationale**：
- 程式化 fixture 比 commit 二進位檔更好審查（可 diff Python code）。
- 時間類測試以 `monkeypatch` 假造 signal，不實際等 60s。

## §12 變更影響面（為 tasks.md 做橋梁）

以下為 plan 需延續到 tasks.md 的改動清單（tasks 產出時將逐一拆分為 T0XX 項）：

1. `pyproject.toml`：加三 dep；`uv.lock` 重生。
2. `src/hks/core/manifest.py`：新欄位 `parser_fingerprint`；migration helper（舊 manifest 自動補欄位為 `*`）。
3. `src/hks/ingest/models.py`：`ParsedDocument` 加 `segments: list[Segment]`、`skipped_segments: list[SkippedSegment]`、`pptx_notes_flag: Optional[bool]`。
4. `src/hks/ingest/office_common.py`：新檔（placeholder 常數、dataclass、markdown 表格 helper）。
5. `src/hks/ingest/parsers/{docx,xlsx,pptx}.py`：新檔。
6. `src/hks/ingest/pipeline.py`：`PARSERS` 擴充；新增 timeout + size gate；fingerprint 整合。
7. `src/hks/ingest/extractor.py`：segment-aware chunk。
8. `src/hks/cli.py`：`--pptx-notes` option。
9. `src/hks/storage/wiki.py`：log entry 附屬欄位支援。
10. `contracts/ingest-summary-detail.schema.json`：固化 ingest_summary detail schema。
11. Tests + fixtures（詳 §11）。
12. `docs/main.md` §3.1 / §8 可能需同步（Phase 2 ingest 擴充；留 tasks 階段判斷）。

## §13 仍然「委任 plan 可調整」的 soft defaults

以下為 spec 層 soft default、plan 決定具體值，實作後若實測不合可於 plan.md 更新並附理由（不回改 spec）：

| 項目 | soft default | 可調範圍 | 觸發調整的信號 |
|---|---|---|---|
| per-file timeout | 60s | 5s–600s | 大型 pptx 正常 parse 接近 60s |
| 單檔大小上限 | 200MB | 1MB–2GB | 實測 > 200MB 仍可在時限內完成且為合法需求 |
| chunk token 上限 | 512（沿用 Phase 1） | 256–1024 | MiniLM 模型換新後調整 |
| chunk overlap | 64（沿用 Phase 1） | 0–128 | 檢索品質回歸測試決定 |

## §14 本階段不解決的問題（明示 Defer）

以下屬於 Phase 2 第二、三張 spec 範疇，**本 spec 禁止碰**：

- Entity / relation 抽取（graph 層）→ spec 003
- LLM-based routing → spec 004
- 高 confidence 自動 write-back → spec 004
- 圖片 OCR / VLM 文字回填佔位符 → Phase 3
- 跨檔 entity 連結（例 docx 中提到的 Project A 連到 xlsx 某 sheet）→ spec 003

## §15 Performance Log

- 2026-04-24：以 `tests/integration/test_query_performance.py` 實測 50 份混合 fixture（Phase 1 + Office）之 `summary Atlas` query，`p95 = 0.0058s`、`mean = 0.0056s`，通過 `p95 < 3s` 門檻。

## §16 Final Smoke

- 2026-04-24：依 quickstart 路徑做人工 smoke。
- `uv run ks ingest tests/fixtures/valid` 等效流程：exit `0`，建立 19 份 artifacts（Phase 1 10 + Office 9）。
- `uv run ks query "detail Q2 135"`：exit `0`，`trace.route = vector`，命中 `xlsx/multi_sheet.xlsx` 的 Budget sheet。
- `uv run ks query "detail fallback supplier"`：exit `0`，`trace.route = vector`，命中 `pptx/with_notes.pptx` notes 內容。
- `uv run ks ingest tests/fixtures/valid --pptx-notes=exclude` 等效流程：exit `0`，3 份 pptx 觸發 `updated`。
- 混合 `broken/office/` 降級 smoke：exit `65`，`corrupt / encrypted / oversized / timeout / empty_file` 路徑皆符合契約。

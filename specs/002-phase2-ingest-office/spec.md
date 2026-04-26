# Feature Specification: Phase 2 階段一 — Office 文件（docx / xlsx / pptx）ingest 擴充

**Feature Branch**: `002-phase2-ingest-office`
**Created**: 2026-04-24
**Status**: Complete
**Input**: 擴充 `ks ingest` 支援 docx / xlsx / pptx 三種 Office 格式，沿用 Phase 1 既有 ingestion 契約與兩層儲存（wiki + vector）。本 spec 不觸及 graph、不變更 query 路徑、不升級 routing 至 LLM，不開放 write-back 全自動化；graph / LLM routing / 自動 write-back 留待 Phase 2 第二、第三張 spec（[docs/main.md §9](../../docs/main.md)、[README.md](../../README.md) 路線圖）。對應憲法 [§I / §III / §IV](../../.specify/memory/constitution.md)。

## Clarifications

### Session 2026-04-24

- Q: xlsx 多 sheet 的 wiki 頁面粒度 → A: 一檔一頁，每 sheet 作為 H2 子標題分段（沿用 Phase 1 slug 規則不擴充）
- Q: pptx speaker notes 預設處理 → A: 預設納入，提供 `--pptx-notes=include|exclude` flag（預設 `include`）可覆寫
- Q: docx / xlsx 表格文字化格式 → A: markdown 表格（`| header | ... |`），wiki 與 vector 同格式
- Q: 嵌入圖片 / object / macros 在文字流中的處理 → A: 留固定前綴佔位符（`[image: <alt>]`、`[embedded object: <type>]`、`[macros: skipped]`），同時記 `skipped_segments` 供 log.md 觀測；Phase 3 OCR / VLM 以就地替換方式銜接
- Q: per-file 大小 / 超時上限 → A: spec 給 soft default — per-file 60 秒超時、檔案大小上限 200MB；plan 可基於實測調整但 MUST 於 plan 記錄調整理由（不得默改）

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Ingest Office 文件至兩層知識儲存（Priority: P1）

使用者或 agent 在 shell 下對含 docx / xlsx / pptx 來源的資料夾執行 `ks ingest <path>`，系統能與 Phase 1 的 txt / md / pdf 相同流程地：把原始檔複製至 `raw_sources/`（immutable）、在 ingest 階段完成 parse → normalize → extract → update，產出 wiki 頁面與 vector chunk。重複執行時以內容 SHA256 為基線，並搭配會影響抽取結果的 parser fingerprint 判定可否沿用既有 artifacts；skip / update / unsupported 事件維持以 Phase 1 相同結構寫入 `wiki/log.md`。

**Why this priority**：本階段的全部價值來自「能 ingest 更多種類的文件」；沒有這步就沒有 Phase 2 後續的 graph 抽取與 LLM routing。此故事一落地即可獨立交付「docx/xlsx/pptx 納入知識系統」這一塊。

**Independent Test**：準備 docx / xlsx / pptx 各 ≥ 3 份 fixtures（涵蓋多段落、含表格、含 slide notes、含多 sheet），對空的 `/ks/` 執行 `ks ingest ./fixtures/`，驗證：(a) `raw_sources/` 有 9 份副本；(b) `wiki/pages/` 下有對應頁面，內容可讀；(c) `manifest.json` 三份檔都有 `sha256` + `derived`，且 Office entry 含 `parser_fingerprint`；(d) 以相同內容與相同 parser 設定重跑時所有條目數量不變、`log.md` 追加 `skipped`；(e) 修改其一份內容或切換 `--pptx-notes` 重跑時，僅受影響檔案的 artifacts 被覆寫。

**Acceptance Scenarios**：

1. **Given** 空的 `/ks/` 目錄與含 docx / xlsx / pptx 各 3 份的資料夾，**When** 使用者執行 `ks ingest ./fixtures/`，**Then** 9 份原始檔複製至 `raw_sources/`、`wiki/pages/` 產出對應頁面、vector DB 新增對應 chunk、`manifest.json` 依 Phase 1 既有 schema 記下 `{relpath, sha256, format, size_bytes, ingested_at, derived}`，並為 Office entry 額外記 `parser_fingerprint`；指令以 exit code `0` 結束並於 stdout 輸出既有 `QueryResponse` top-level schema 的 JSON 摘要。
2. **Given** 已完成一次 ingest 的 `/ks/`，**When** 使用者對同一資料夾再次執行 `ks ingest`，**Then** 所有 hash 未變的檔案被標記為 skipped、不新增任何條目、`log.md` 僅追加 `skipped` 事件；再次執行的 wall-clock 時間相較首次顯著下降。
3. **Given** 已 ingest 過的 docx / xlsx / pptx，**When** 使用者修改其中一份（例如在 docx 新增一段文字）並重新 ingest，**Then** 該份對應之 wiki 頁面與 vector chunk 被整批覆寫為新版本、其餘 8 份不動、`log.md` 追加 `update` 紀錄。
4. **Given** 一個混合 txt / md / pdf / docx / xlsx / pptx 的資料夾，**When** 使用者執行 `ks ingest`，**Then** Phase 1 既有三格式與新增三格式皆以同一批次處理，事件同時列入 `log.md`、`manifest.json` 不因格式差異而分表。

---

### User Story 2 — Office 內容可被既有 query 路徑檢索命中（Priority: P1）

agent 或使用者在 Office 文件 ingest 完成後執行 `ks query "<question>"`，能以 Phase 1 既有的 rule-based routing、既有 JSON schema 取回答案；Office 來源的 wiki 頁面可被 wiki route 命中，Office 來源的 vector chunk 可被 vector route 命中。query 輸出的 `source` / `trace.route` 不因來源格式不同而出現新值，agent 端不需任何程式碼變更即可使用。

**Why this priority**：ingest 若無法反映到 query，對外價值為零；此故事確保 US1 的產物真正接入既有檢索路徑，是 Phase 2 第一張 spec 的另一半 MVP。

**Independent Test**：US1 完成後，對 docx / xlsx / pptx 內容各提出一個 summary 類問題（走 wiki）與一個 detail 類問題（走 vector），驗證：(a) JSON schema 與 Phase 1 完全一致；(b) `source` 欄位值僅為 `wiki` / `vector` 子集、不得出現新值；(c) `trace.route` 僅為 `wiki` / `vector`；(d) 關係類問題仍走 vector fallback、`answer` 結尾仍附註「深度關係推理將於 Phase 2 支援」（此附註移除屬於 Phase 2 第三張 spec 的範疇）；(e) exit code 符合 Phase 1 契約。

**Acceptance Scenarios**：

1. **Given** 已 ingest 一份 xlsx（含多 sheet），**When** 使用者執行 `ks query "<針對某 sheet 內容的 detail 類問題>"`，**Then** 系統走 vector route 並取回涵蓋該 sheet row / header 脈絡的 chunk；JSON 結構與 Phase 1 detail 類回應完全一致。
2. **Given** 已 ingest 一份 pptx，**When** 使用者執行 `ks query "<針對簡報重點的 summary 類問題>"`，**Then** 系統走 wiki route 並取回該 pptx 的 wiki 頁面摘要；`source==["wiki"]`、`confidence==1.0`。
3. **Given** 已 ingest 一份 docx（含表格），**When** 使用者執行 `ks query "<檢索表格內某欄位的 detail 類問題>"`，**Then** vector route 回傳之 chunk 包含原表格對應列的文字內容；agent 不需理解 docx 結構即可讀懂。
4. **Given** 任何一種 Office 格式的 ingest 結果，**When** 執行任何 query，**Then** stdout JSON `grep` 不出現 `"graph"` 字樣、`/ks/graph/` 目錄不存在；與 Phase 1 SC-008 檢核條件相同。

---

### User Story 3 — 部分可讀 Office 檔案的安全降級（Priority: P2）

Office 檔案可能含嵌入圖片、embedded objects、macros、加密或部分損壞內容。系統 MUST 以「安全降級 + 可觀測」方式處理：可讀的文字仍正常入庫、不可讀的部分於 `log.md` 與 stdout JSON 明列為 `skipped_segments`；整批 ingest 不因單檔或單段落失敗而中斷，exit code 按 Phase 1 契約返回。

**Why this priority**：實際企業 Office 檔案極少是「純文字」；降級處理直接影響使用者是否敢把既有資料夾丟進 `ks ingest`。但核心能力（US1 + US2）不依賴此故事，故列 P2。

**Independent Test**：準備五類 fixtures：(a) 含嵌入圖片的 docx；(b) 含 macros 的 xlsx；(c) 密碼加密的 pptx；(d) 位元組損壞的 xlsx；(e) 空檔（0 byte）docx。對同一批次執行 `ks ingest`，驗證：(a)(b) 文字部分入庫、嵌入圖片 / macros 於 `log.md` 額外 bullet 與 `trace.steps[].detail.files[]` 標記 `skipped_segments`；(c)(d) 單檔失敗、以 `DATAERR` 標註於輸出清單、不中斷其他檔；(e) 視為 skip、不產出 artifacts；整批 ingest 之 exit code 仍依 Phase 1 FR-003 契約（有 DATAERR 時 exit `65`、僅 skip 時 exit `0`）。

**Acceptance Scenarios**：

1. **Given** 一份 docx 含 3 張嵌入圖片，**When** ingest 該檔，**Then** 文字段落正常寫入 wiki + vector；`log.md` 在該事件下追加 `- skipped_segments: image:3`；stdout JSON 的 `trace.steps[kind="ingest_summary"].detail.files[]` 對應條目附 `skipped_segments` 欄位。
2. **Given** 一份加密的 pptx，**When** ingest 該檔，**Then** 不嘗試破解、以 `DATAERR` 標註於輸出失敗清單、`log.md` 追加 `failed (encrypted)` 事件；其他同批次檔案完成處理。
3. **Given** 一份位元組損壞的 xlsx（例如被截斷），**When** ingest 該檔，**Then** 以 `DATAERR` 標註於失敗清單；partial artifacts MUST NOT 留在 wiki / vector（視為 atomic — 要嘛全入庫要嘛完全不入庫）；`manifest.json` 不得為此檔留下孤兒 entry。
4. **Given** 一批次混有成功檔與 DATAERR 檔，**When** `ks ingest` 結束，**Then** 指令以 exit `65`（DATAERR）結束但 JSON stdout 仍為合法 `QueryResponse` top-level schema，且於 `trace.steps[kind="ingest_summary"].detail.files[]` 列出每個檔的最終狀態；此行為與 Phase 1 FR-003 的 partial-failure 契約相同。
5. **Given** 一份 xlsx 含 VBA macros，**When** ingest，**Then** macros 內容一律忽略且不執行、`log.md` 在該事件下記 `- skipped_segments: macros:1`；文字部分照常入庫。

---

### Edge Cases

- **超大 Office 檔案**：單份 docx / xlsx / pptx 超過 200MB（soft default，見 FR-064）以 `DATAERR` 拒絕入庫；單檔 parse + embedding 累計超過 60 秒（soft default，見 FR-063）以超時 `DATAERR` 終止該檔。兩個閾值可由 plan 依實測調整，但須記錄理由。
- **xlsx 公式 vs 值**：cell 若含公式，系統優先取「last computed value」；若無（未曾開啟過的 sheet），則取公式原字串並於該 chunk metadata 記 `formula_only`。
- **xlsx 超寬表**：欄位數量極多（例如 > 100）時，chunk 策略仍以 row 為單位；row 長度超過單次 embedding 長度上限時分段，但保留 sheet + row 索引 metadata，避免 query 命中後脈絡斷裂。
- **pptx 空 slide 或僅含圖片的 slide**：僅含圖片的 slide 以 `[image: <alt>]` 佔位符保留 slide 索引與內容位置（FR-032）；完全空的 slide（無 title / body / notes / image）於 `log.md` 記 `skipped_segments: empty_slide=N`，但仍保留 slide 序號不得讓索引出現空洞。
- **docx 目錄 / 頁首 / 頁尾**：納入文字流，但於 chunk metadata 標註 `section_type`，以便未來過濾；Phase 2 第一張 spec 不做過濾。
- **檔名含特殊字元 / 非 ASCII**：slug 生成規則與 Phase 1 FR-016 完全一致（衝突以 `-<n>` 後綴）。
- **多語系內容**：Office 檔內中英混排視為單一文字流；routing 仍依 Phase 1 `routing_rules.yaml` 的中英 keyword。
- **並發 ingest**：沿用 Phase 1 lock 檔規則；多進程存取以 exit `1` 拒絕。

## Requirements *(mandatory)*

### Functional Requirements

#### 格式支援

- **FR-001**：`ks ingest` MUST 在 Phase 1 支援的 txt / md / pdf 基礎上，額外接受 docx / xlsx / pptx 三種格式；其他副檔名仍 MUST 被標為 unsupported 並不計入失敗（維持 Phase 1 FR-011 契約）。
- **FR-002**：系統 MUST 依副檔名（不可信任者搭配內容嗅探）決定 parser；MUST NOT 依使用者顯式指定。
- **FR-003**：格式支援清單的權威位置 MUST 單一：plan 階段決定（例如 `core/formats.py` 或 routing 設定）；本 spec FR-001 與 Phase 1 spec 之 FR-011（格式支援）兩處若有擴充，必須同步更新該單一權威位置，不得散落在多個 hard-code 清單。

#### docx 抽取

- **FR-010**：docx parser MUST 抽取段落、標題（含層級）、清單（bullet / numbered）與表格內文字，並保留原文語意順序。
- **FR-011**：表格 MUST 轉為 markdown 表格格式（`| header | ... |` 與分隔列 `| --- | ... |`），保留 header row 與資料 row 的對應關係；wiki 頁面與 vector chunk MUST 使用相同格式（不得分別存兩種展開形式）。
- **FR-012**：嵌入圖片、embedded OLE objects、SmartArt、macros MUST 於文字流中以固定前綴佔位符保留位置（`[image: <alt-text 或空>]`、`[embedded object: <type>]`、`[smartart: <summary 或空>]`、`[macros: skipped]`），同時記入該檔 ingest 的 `skipped_segments` 欄位；不得直接丟棄造成上下文斷裂；不得中斷該檔 ingest。佔位前綴 MUST 為固定 ASCII 字串、跨 parser 一致，使 Phase 3（OCR / VLM）能以就地替換方式銜接。

#### xlsx 抽取

- **FR-020**：xlsx parser MUST 逐 sheet 抽取 cell 內容，並保留：(a) sheet 名稱；(b) 若 row 1 為 header，每 row 與對應 header 的映射；(c) row 在 sheet 內的索引（1-based，與 pptx `slide_index` 基底一致）。
- **FR-021**：chunk 策略 MUST 以 row 為主要單位，表達形式為 markdown 表格的「header 列 + 分隔列 + 單 row」三列片段（與 FR-011 一致）；同 sheet 前段需含 sheet 名稱前綴（例如 `## <sheet name>` 或等效標示），確保 query 命中時不失去脈絡。
- **FR-022**：cell 公式 MUST 優先取 last computed value；無快取值時取公式原字串並於 chunk metadata 記 `formula_only=true`。
- **FR-023**：VBA macros、PivotTable 定義、Chart 物件 MUST 以佔位符保留位置（規則同 FR-012：`[macros: skipped]` / `[pivot: skipped]` / `[chart: skipped]`）並記入 `skipped_segments`；macros 內容 MUST NOT 被執行。

#### pptx 抽取

- **FR-030**：pptx parser MUST 逐 slide 抽取：(a) slide title；(b) slide 內所有文字框內容（含形狀內文字）；(c) speaker notes（預設納入，可經 CLI flag 排除，見 FR-033）；(d) 表格內文字；並於 chunk metadata 保留 slide 索引（1-based）。
- **FR-033**：`ks ingest` MUST 提供 `--pptx-notes=include|exclude` flag，預設 `include`。`exclude` 模式下 speaker notes MUST NOT 進入 wiki 或 vector、且該檔 ingest 事件於 `log.md` 須以額外 bullet 記 `pptx_notes: excluded`（供重跑判定）；`--pptx-notes` 變更視為 parser 設定變更，MUST 觸發重新 ingest（比對 `parser_fingerprint` 或等效設定指紋）。
- **FR-031**：slide 順序 MUST 與簡報原順序一致；slide 內不同文字框的拼接順序於 plan 決定，但 MUST 為決定性（同檔重跑結果一致）。
- **FR-032**：嵌入圖片、影片、音訊、embedded objects、macros MUST 以佔位符保留位置（規則同 FR-012：`[image: <alt>]` / `[video: skipped]` / `[audio: skipped]` / `[embedded object: <type>]` / `[macros: skipped]`）並記入 `skipped_segments`；僅含圖片或空白的 slide 仍保留 slide 索引與佔位文字，不得讓 slide 序號出現空洞。

#### Pipeline 整合

- **FR-040**：所有新 parser 的輸出 MUST 進入 Phase 1 既有 ingestion pipeline（parse → normalize → extract → update wiki + vector），不得另立平行流程；憲法 §IV 要求 ingest 階段即完成整理，query 不得於運行時 re-parse 原檔。
- **FR-041**：`manifest.json` MUST 延續 Phase 1 現況 schema：`{relpath, sha256, format, size_bytes, ingested_at, derived}`；Office 格式不得另立平行結構。若需記錄會影響重跑判定的 parser 設定，僅可採向後相容的附加欄位（例如 `parser_fingerprint`）。
- **FR-042**：wiki 頁面生成規則 MUST 沿用 Phase 1 FR-015 / FR-016：一份來源檔對應一頁、slug 生成 + 碰撞 `-<n>` 後綴規則不變。xlsx 多 sheet 檔案 MUST 以「一檔一頁」壓平，每個 sheet 以 H2 子標題（`## <sheet name>`）分段；slug 規則不得因 sheet 數擴充為 `<file>__<sheet>` 之類的形式。
- **FR-043**：`wiki/log.md` 事件格式 MUST 與 Phase 1 完全一致（同結構、同時間戳、同事件類型集合）；新格式不得引入新事件類型。`skipped_segments` / `pptx_notes` 僅能作為既有事件下的額外 bullet 明細，不得改寫成另一種行格式。
- **FR-044**：re-ingest 判定 MUST 以整檔 SHA256 為內容基線，並對會改變抽取結果的 parser 版本 / flag 額外比對 `parser_fingerprint`；MUST NOT 使用 mtime、解析後內容或其他不穩定訊號作為判定依據。
- **FR-045**：`ks ingest` stdout MUST 保持 Phase 1 的 `QueryResponse` top-level schema；Office 專屬的每檔狀態、`skipped_segments`、`pptx_notes` 等資料 MUST 置於 `trace.steps[kind="ingest_summary"].detail` 內，不得另立新的 top-level response schema。

#### Query 契約保留

- **FR-050**：本 spec MUST NOT 修改 `ks query` 的輸出 schema、routing 路徑集合（僅 wiki / vector）、exit code 契約或 `trace` 語意；對應 Phase 1 spec 之 FR-002（JSON schema）、FR-003（exit codes）、FR-020（rule-based routing）、FR-021（僅 wiki/vector）、FR-023（trace.route 語意）。（注意：上列 FR 編號屬 Phase 1 spec；本 spec 同編號 FR 意義不同，勿相互混淆。）
- **FR-051**：關係類 query 仍走 vector fallback，`answer` 結尾 MUST 繼續附註「深度關係推理將於 Phase 2 支援」；附註的移除屬於 Phase 2 第三張 spec（LLM routing + graph 啟用）之範疇，本 spec 不可先動。
- **FR-052**：`source` 欄位 MUST NOT 因格式擴充而新增值；`trace.route` MUST NOT 出現 `"graph"`、`"llm"` 等 Phase 1 未定義之值。

#### 異常處理

- **FR-060**：加密 / 密碼保護的 Office 檔 MUST 以 `DATAERR`（exit `65`）標註於該檔條目，系統不嘗試破解、不要求密碼輸入；整批 ingest 不中斷。
- **FR-061**：位元組損壞或 parser 無法開啟的檔案 MUST 以 `DATAERR` 標註；parser MUST 保證 atomicity — 該檔要嘛全數 artifacts 入庫、要嘛完全不入庫（不得留 partial wiki page 或 partial vector chunk）。
- **FR-062**：空檔（0 byte 或僅 whitespace）MUST 視為 skip 並記 `log.md`，不產出 artifacts、不視為失敗（對齊 Phase 1 edge case）。
- **FR-063**：單檔處理超過 60 秒（soft default）時 MUST 以超時錯誤終止該檔、標註 `DATAERR`；整批 ingest 不中斷。runtime 可由 `HKS_OFFICE_TIMEOUT_SEC` 覆寫；plan 可於實測後調整 soft default 預設值，但 MUST 於 plan.md 記錄調整理由；兩者均未動時以 60 秒為準。
- **FR-064**：單檔大小超過 200MB（soft default）時 MUST 以 `DATAERR` 拒絕入庫、該檔不進入 parse 階段；整批 ingest 不中斷。runtime 可由 `HKS_OFFICE_MAX_FILE_MB` 覆寫；plan 可於實測後調整 soft default 預設值，規則同 FR-063。

#### 禁止事項

- **FR-070**：本 spec MUST NOT 建立 `/ks/graph/` 目錄、MUST NOT 寫入任何 graph 相關資料；`source` / `trace.route` MUST NOT 出現 `"graph"`（憲法 §I，沿用 Phase 1 FR-051 與 SC-008）。
- **FR-071**：本 spec MUST NOT 引入 LLM 呼叫至 ingest / query runtime；embedding 模型仍使用 Phase 1 既有本地模型。LLM routing 屬於第三張 spec 範疇。
- **FR-072**：本 spec MUST NOT 改為「高 confidence 自動回寫」或「背景靜默寫入」；write-back 行為完全沿用 Phase 1 FR-030 / FR-031 / FR-032 / FR-034（憲法 §V）。
- **FR-073**：parser 邏輯 MUST NOT hard-code 垂直領域詞彙；domain-agnostic 規定沿用 Phase 1 FR-052 / 憲法 §III。

#### 測試與 local-first

- **FR-080**：docx / xlsx / pptx 各 MUST 提供 ≥ 3 份 fixtures 於 `tests/fixtures/valid/` 下，涵蓋「純文字」、「含表格」、「含嵌入圖片或 macros」至少三種變體；另提供 `tests/fixtures/broken/` 下的加密、損壞、空檔樣本。
- **FR-081**：ingest、schema、idempotency 三類測試 MUST 附自動化測試；`uv run pytest` 為合併閘門（沿用 Phase 1 FR-061）。
- **FR-082**：所有 parser MUST 可於無網路環境執行；第三方函式庫 MUST 為純 Python 或可離線安裝（沿用 Phase 1 FR-060）。

### Key Entities

- **Office Raw Source**：被 ingest 的 docx / xlsx / pptx 原始檔；屬性繼承自 Phase 1 Raw Source（相對路徑、SHA256、格式、大小、ingest 時間），額外可於 manifest entry 記錄 `parser_fingerprint`（便於未來 parser 升級或 flag 切換時重跑判定）。
- **Sheet / Slide / Section Metadata**：xlsx 的 sheet、pptx 的 slide、docx 的 heading-section，作為 vector chunk 的 metadata 附屬（非獨立實體），用來在 query 命中時標示出處位置；schema 於 plan 定義，不改動 Phase 1 `Query Response` 對外欄位。
- **Skipped Segment Record**：雙軌紀錄。(a) 文字流內以固定前綴佔位符保留位置（規則見 FR-012 / FR-023 / FR-032），供 Phase 3 OCR / VLM 就地替換；(b) `wiki/log.md` ingest 事件的額外 bullet 明細與 `trace.steps[kind="ingest_summary"].detail.files[]` 內列出類型與數量（例如 `image:3, macros:1, empty_slide:2`）。佔位符與附屬明細皆為觀測與銜接用，不改動 `QueryResponse` top-level schema。
- **Parser**：per-format 的抽取單元（docx / xlsx / pptx 各一）；共同介面「讀入檔案路徑 → 回傳有序的 segment 清單（文字 + metadata）+ skipped_segments 清單」；介面細節於 plan 階段決定。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**：使用者可於單次指令成功 ingest docx / xlsx / pptx 各 ≥ 3 份（共 ≥ 9 份）混合格式文件，零手動干預、exit code `0`。
- **SC-002**：同批次重跑 ingest，衍生 artifacts 總數保持不變（idempotent）；第二次執行 wall-clock 相較首次下降 ≥ 50%（因 SHA256 判斷 skip）。
- **SC-003**：對 docx / xlsx / pptx 各提出至少一個 summary 類與一個 detail 類問題（共 ≥ 6 條 query），`ks query` 輸出 JSON 100% 可被標準 parser 解析，且 schema 與 Phase 1 比對無差異（欄位集合、型別、取值集合皆一致）。
- **SC-004**：混合 Phase 1（txt/md/pdf）與 Phase 2（docx/xlsx/pptx）來源的同一 `/ks/` 目錄上，wiki + vector 的既有 Phase 1 query 結果與 spec 002 實作前相比 100% 未退化（相同問題得相同 route / source / confidence / 類似 answer 命中區段）。
- **SC-005**：降級場景（嵌入圖片 / object / macros / 空 slide / 加密 / 損壞 / 空檔 / 超時（>60s）/ 超大（>200MB））於 100% 測試 fixtures 下符合預期：正常文字入庫、不可讀段落以佔位符保留位置並列於 `skipped_segments`、加密 / 損壞 / 超時 / 超大以 DATAERR 標註、整批不中斷。
- **SC-006**：本機查詢 p95 延遲 < 3s 之 Phase 1 SC-005 在新增三格式後仍成立（以 commodity laptop、已 ingest 50 份文件語料為基準）。
- **SC-007**：`source` 與 `trace.route` 於任何情境下 grep 不出現 `"graph"`、`"llm"`；`KS_ROOT/graph/` 不得存在；`src/hks/` 程式碼不得有 graph 實作的 code path（沿用 Phase 1 SC-008 檢核）。
- **SC-008**：`uv run pytest` 全數通過，新增 parser 與降級情境測試覆蓋率 ≥ 80%（具體門檻於 plan 決定）。
- **SC-009**：所有新 parser 可於 airgapped 環境完成 ingest（本地 wheel / vendored 套件安裝後）；任何 parser 觸發對外網路連線視為 bug。

## Assumptions

- **單使用者、單進程**：沿用 Phase 1 假設；並發安全性非本階段需求。
- **Parser 選型**：以 plan 階段於「純 Python、可離線、無授權風險」三條件下決定具體 library；一旦選定，版本與設定於 `pyproject.toml` pin 住，並納入 `parser_fingerprint` 以穩定重跑判定。
- **Chunk 策略**：docx 以段落 / 標題區塊為單位、xlsx 以 header + row 為單位、pptx 以 slide 為單位；具體的拆切 heuristic（例如 chunk 長度上限）於 plan 決定，但 MUST 為決定性（同檔重跑結果一致）。
- **Wiki 頁面粒度**：一份 Office 檔對應一份 wiki 頁面，與 Phase 1 策略一致；xlsx 的多 sheet 壓平為單一 wiki 頁面，每個 sheet 以 H2 子標題（`## <sheet name>`）分段；slug 規則沿用 Phase 1 FR-016 不擴充。若未來出現「單檔數十 sheet、單頁過長」的實務問題，交由後續 spec（或 Phase 2 第二張 graph spec 用跨 sheet 關係承擔）處理。
- **xlsx 公式**：取 last computed value 為主；若檔案從未於 Excel 開啟、僅有公式字串，仍入庫並標 `formula_only=true`，不主動計算公式。
- **pptx notes**：speaker notes 預設納入 ingest；使用者可以 `ks ingest --pptx-notes=exclude` 關閉。設定變更視為 `parser_fingerprint` 變更，會在內容 SHA256 不變時仍觸發對應檔案重新 ingest。此預設前提是 HKS 定位為 local-first、單使用者 / 小團隊系統，speaker notes 的檢索價值高於「自用環境的隱私風險」。
- **降級可觀測性**：`skipped_segments` 為 `wiki/log.md` 之附屬欄位，不改動 `Query Response` schema；agent 若需要解析，從 log.md 或 ingest stdout JSON 讀取。
- **Routing 規則**：`config/routing_rules.yaml` 在本 spec 不需新增新路由（僅 wiki / vector 兩路）；若 plan 發現需針對 Office 來源加規則（例如 xlsx 偏 detail 類），以新增 keyword 的方式完成，不改動 schema。
- **Phase 邊界**：graph 抽取、LLM routing、write-back 全自動、Phase 3 OCR / VLM 一律延後；本 spec 僅負責「讓 Office 格式進得來」。

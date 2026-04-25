# Feature Specification: Phase 3 階段一 — 影像 ingest（OCR）

**Feature Branch**: `004-phase3-image-ingest`
**Created**: 2026-04-25
**Status**: Complete
**Input**: 擴充 `ks ingest` 首次支援獨立影像檔（still raster images），以 OCR 為唯一 MVP 路徑，把影像內的文字納入既有 wiki + vector + graph 三層儲存。本 spec 不觸及 `ks lint` 真實實作（由 `005-phase3-lint-impl` 承擔）、不觸及 MCP adapter（`006`）與多 agent 協作（`007`）；不變更 query 路徑、不擴 `source` / `trace.route` enum。對應憲法 [§I / §III / §IV](../../.specify/memory/constitution.md)、沿用 [spec 002](../002-phase2-ingest-office/spec.md) 的 `parser_fingerprint` 機制與 [spec 003](../003-phase2-graph-routing/spec.md) 的 graph 契約。

## Clarifications

### Session 2026-04-25

- Q: OCR 引擎候選最後凍結哪一條 → A: `tesseract` CLI + `tesseract-lang`（預設 `eng+chi_tra`），純本機、可離線、Homebrew 可安裝
- Q: VLM 是否進 004 MVP → A: 不進；`004` 僅做 OCR ingest，VLM caption / description 另立後續 spec
- Q: `.heic` / `.webp` 是否納入 → A: 不納入；`004` 僅承諾 `.png` / `.jpg` / `.jpeg`
- Q: 影像 wiki 頁 body 放什麼 → A: 放 OCR 全文（依 OCR block / line 排序），不只放摘要
- Q: 0 byte image 的 skip reason 用哪個字面 → A: 對齊現有 runtime，維持 `empty_file`，不另造 `empty`

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Ingest 獨立影像檔至三層知識儲存（Priority: P1）

使用者或 agent 在 shell 下對含 `.png` / `.jpg` / `.jpeg` 檔案的資料夾執行 `ks ingest <path>`，系統能把影像原檔複製至 `raw_sources/`（immutable）、在 ingest 階段以 OCR 解讀文字、將文字帶入 Phase 2 既有 `parse → normalize → extract → update(wiki, vector, graph)` 四階段流程。重複執行時以 SHA256 + `parser_fingerprint` 判定 idempotency；OCR 模型升級時自動觸發 re-ingest。skip / update / failed 事件以與 Phase 2 相同結構寫入 `wiki/log.md`。

**Why this priority**：Phase 3 的核心價值是讓系統吃進「純文字以外的資料」；沒有獨立影像 ingest，Phase 3 所有後續使用場景都無法銜接。此故事一落地即交付「影像納入 HKS」這塊 MVP。

**Independent Test**：準備 6 份 fixture，涵蓋純英文、純中文、中英混排、低對比 / 旋轉、多欄版面、無文字純圖。對空的 `/ks/` 執行 `ks ingest ./fixtures/`，驗證：(1) `raw_sources/` 有 5 份副本（無文字純圖走 skip）；(2) `wiki/pages/` 下對應頁面內容可讀；(3) `manifest.json` 每檔含 `sha256` + `derived` + `parser_fingerprint`，fingerprint 字面包含 OCR 模型名與版本；(4) 相同內容與相同 OCR 設定重跑時所有條目數量不變、`log.md` 追加 `skipped`；(5) 以 mock 方式 bump OCR 模型版本重跑，僅受影響檔案被 `updated`。

**Acceptance Scenarios**：

1. **Given** 空的 `/ks/` 目錄與含 6 份影像 fixture 的資料夾，**When** 使用者執行 `ks ingest ./fixtures/`，**Then** 原檔複製至 `raw_sources/`、`wiki/pages/` 產出對應頁面、vector DB 新增 OCR 結果 chunk、`manifest.json` 為每檔記下 `{relpath, sha256, format, size_bytes, ingested_at, derived, parser_fingerprint}`；指令以 exit code `0` 結束並於 stdout 輸出 Phase 1 `QueryResponse` top-level schema 的 JSON 摘要；`trace.steps[kind="ingest_summary"].detail.files[]` 含每檔 OCR 結果概要（例如 `ocr_chunks`、`ocr_confidence_*` 區間）。
2. **Given** 已完成一次影像 ingest 的 `/ks/`，**When** 使用者對同一資料夾再次執行 `ks ingest`，**Then** 所有 hash + fingerprint 未變的檔案被標記 skipped、不新增任何條目；wall-clock 時間相較首次顯著下降。
3. **Given** 已 ingest 過的影像，**When** 系統偵測到 `parser_fingerprint` 變更（例如 OCR 模型升級），**Then** 該檔對應的 wiki 頁面與 vector chunk 被整批覆寫為新 OCR 結果、其他未受影響檔不動、`log.md` 追加 `updated` 紀錄。
4. **Given** 一個混合 txt / md / pdf / docx / xlsx / pptx / png / jpg / jpeg 的資料夾，**When** 使用者執行 `ks ingest`，**Then** 既有支援格式與影像三格式皆以同一批次處理、事件同時列入 `log.md`、`manifest.json` 不因格式差異而分表。

---

### User Story 2 — 影像 OCR 內容可被既有 query 路徑檢索命中（Priority: P1）

agent 或使用者在影像 ingest 完成後執行 `ks query "<question>"`，能以 Phase 1–2 既有的 routing、既有 JSON schema 取回答案；影像來源的 wiki 頁面可被 wiki route 命中、影像來源的 vector chunk 可被 vector route 命中；若 OCR 文字於 Phase 2 graph extractor 能成功抽 entity / relation，則 relation 類 query 仍可走 graph route。query 輸出的 `source` / `trace.route` 不因來源格式不同而出現新值，agent 端不需任何程式碼變更即可使用。

**Why this priority**：ingest 若無法反映到 query，對外價值為零。此故事確保 US1 的產物真正接入既有檢索路徑，是 Phase 3 影像 ingest 的另一半 MVP。

**Independent Test**：US1 完成後，對影像內容各提出一個 summary 類問題（走 wiki）、一個 detail 類問題（走 vector）、一個 relation 類問題（走 graph），驗證：(a) JSON schema 與 Phase 1 / 2 一致；(b) `source` 僅為 `wiki` / `vector` / `graph` 子集；(c) `trace.route` 值不擴；(d) 關係類問題若 OCR 文字含 `影響 / 依賴 / affects / depends on` 等 pattern，走 graph route；(e) exit code 符合 Phase 1–2 契約。

**Acceptance Scenarios**：

1. **Given** 已 ingest 一份含「Atlas 依賴 Mobile Gateway」的圖片，**When** 使用者執行 `ks query "Atlas 依賴什麼"`，**Then** 系統走 graph route 並取回對應 edge 描述；JSON 結構與 Phase 2 relation 類回應完全一致。
2. **Given** 已 ingest 一份摘要圖，**When** 使用者執行 `ks query "summary atlas dependency"`，**Then** 系統走 wiki route、取回該影像對應 wiki 頁面摘要、`source==["wiki"]`、`confidence==1.0`。
3. **Given** 已 ingest 一份純文字截圖，**When** 執行檢索圖片中原句的 detail 類 query，**Then** vector route 回傳 chunk 文字為 OCR 結果、chunk metadata 包含 `source_format=png|jpg|jpeg` 與 `ocr_confidence`。
4. **Given** 任何影像 ingest 結果，**When** 執行任何 query，**Then** stdout JSON `grep` 不出現新 `source` / `trace.route` 值；`/ks/graph/graph.json` 若已有 Phase 2 內容則不被破壞、仍可 parse。

---

### User Story 3 — 影像 ingest 的安全降級（Priority: P2）

影像檔可能是損壞位元組、超大尺寸、OCR 耗時異常、或純粹沒有可辨識文字。系統 MUST 以「安全降級 + 可觀測」方式處理：可讀的影像文字仍正常入庫、無法處理的影像以 `DATAERR` 標記於該檔條目；整批 ingest 不因單檔失敗而中斷；exit code 按 Phase 1 契約返回。OCR 低信心片段仍入庫但於 chunk metadata 標記 confidence，讓使用者端可決定是否採納。

**Why this priority**：影像在企業資料夾中變異極大；降級處理直接影響使用者是否敢把既有影像資料夾丟進 `ks ingest`。但核心能力（US1 + US2）不依賴此故事，故列 P2。

**Independent Test**：準備 4 類 degradation fixtures：(a) 位元組損壞的 png；(b) oversized jpg seed（測試時把 temp copy 擴張到超過目前 `HKS_IMAGE_MAX_FILE_MB` 設定，以穩定覆蓋 oversized 分支且不把超大 binary 直接放進 repo）；(c) 需觸發 30s 超時的 png（以測試 monkeypatch 穩定重現）；(d) 空檔（0 byte）；另與 US1 的無文字純圖 `no-text.png` 同批驗證 `ocr_empty` skip。對同一批次執行 `ks ingest`，驗證：(a)(b)(c) 單檔失敗、以 `DATAERR` 標註、不中斷其他檔；(d) 視為 skip、不產出 artifacts；`no-text.png` 視為 skip 並於 `log.md` 記 `skipped_segments: ocr_empty`，不入庫為空內容 wiki page；整批 exit code 依 Phase 1 FR-003 契約。

**Acceptance Scenarios**：

1. **Given** 一份位元組損壞的 png，**When** ingest 該檔，**Then** 以 `DATAERR` 標註於失敗清單；partial artifacts MUST NOT 留在 wiki / vector / graph；`manifest.json` 不得為此檔留下孤兒 entry。
2. **Given** 一份超過目前 `HKS_IMAGE_MAX_FILE_MB` 設定的 jpg，**When** ingest 該檔，**Then** 該檔以 `DATAERR` + `reason=oversized` 標註、不進入 decode、其他同批次檔完成處理。
3. **Given** 一份內容極大 / 極複雜的圖，**When** OCR 花超過 30 秒（soft default），**Then** 系統以超時錯誤終止該檔、標 `DATAERR` + `reason=timeout`；整批 ingest 不中斷。
4. **Given** 一份 0 byte 空檔，**When** ingest，**Then** 視為 skip + `reason=empty_file`、不產出 artifacts、不視為失敗。
5. **Given** 一份色塊純圖（OCR 無法辨識任何文字），**When** ingest，**Then** 該檔以 skip + `reason=ocr_empty` 記入 `IngestFileReport`；不產出 wiki 頁面、不新增 vector chunk；`log.md` 附屬欄位記 `skipped_segments: ocr_empty:1`。
6. **Given** 一份中等模糊的掃描圖，**When** OCR 回傳各 chunk 的 confidence，**Then** 每個 chunk metadata 帶 `ocr_confidence`（浮點 [0,1]）；低信心不自動剔除，交由 query 端檢視。

## Edge Cases

- **超大尺寸但合法影像**：解析度極高（例如 20000×20000）但檔案小於 20MB 的 png 仍可能在 decode 階段吃光記憶體；超限 → `DATAERR` + `reason=oversized_decoded`
- **EXIF 旋轉**：相機照片常內嵌 `Orientation` tag；decode 前 MUST 先 honor orientation
- **動畫 / 多頁 / 向量**：`gif`、多頁 `tiff`、`svg` 不在本 spec 範圍
- **混合格式批次**：影像與 txt / md / pdf / docx / xlsx / pptx 混跑不得互相阻塞
- **檔名含特殊字元 / 非 ASCII**：slug 生成規則與 Phase 1 FR-016 完全一致
- **並發 ingest**：沿用 Phase 1 lock 檔規則；多進程存取以 exit `1` 拒絕
- **Placeholder 與現有 Office 檔**：docx / xlsx / pptx 於 Phase 2 留下的 `[image: <alt>]` 佔位字面在本 spec 不被動到

## Requirements *(mandatory)*

### Functional Requirements

#### 格式支援

- **FR-001**：`ks ingest` MUST 在 Phase 1 / 2 支援的 txt / md / pdf / docx / xlsx / pptx 基礎上，額外接受 `.png` / `.jpg` / `.jpeg` 三種副檔名；其他副檔名 MUST 被標為 unsupported 並不計入失敗
- **FR-002**：系統 MUST 依副檔名為主並對影像三格式做輕量 content sniffing 驗證；副檔名命中但魔數不符 MUST 落入 `DATAERR` + `reason=corrupt`
- **FR-003**：格式支援清單的權威位置 MUST 延續 Phase 2 的單一權威原則，不得另立影像專屬 hard-code 清單
- **FR-004**：`.webp` 與 `.heic` MUST NOT 於本 spec 承諾支援；gif / tiff / svg 不在範圍

#### 影像 parse / decode

- **FR-010**：影像 parser MUST 解碼 png / jpg / jpeg 原始像素資料；不得把解碼延遲至 query 階段
- **FR-011**：parser MUST honor EXIF `Orientation`
- **FR-012**：parser 預處理策略（至少 EXIF transpose + grayscale + autocontrast）變更 MUST 反映於 `parser_fingerprint`
- **FR-013**：parser MUST NOT 於 ingest 階段對外網發送 decoder / preprocess 請求

#### OCR 路徑

- **FR-020**：系統 MUST 提供至少一條 OCR 路徑，接收 parsed 影像並回傳 `(text_blocks, confidence[], optional_bboxes)` 結構；具體引擎 MUST 為純本機、可離線、license 相容
- **FR-021**：每個 OCR line MUST 成為一個 `Segment(kind="ocr_text")`；所有 chunk metadata MUST 含 `ocr_confidence`
- **FR-022**：OCR 結果排序 MUST 為決定性；若引擎原生不保證，實作必須依 `top,left` 排序補齊
- **FR-023**：低信心區塊 MUST 不自動剔除；僅於 chunk metadata 標記

#### VLM 邊界（不進 MVP）

- **FR-030**：本 spec MUST NOT 引入 VLM runtime 路徑、`--vlm` CLI flag 或任何 caption model 依賴
- **FR-031**：若未來要加入 caption / description，MUST 另立後續 spec，重新定義 `parser_fingerprint`、segment kind 與 CLI flag 契約

#### Pipeline 整合

- **FR-040**：所有影像 parser 輸出 MUST 進入既有 ingestion pipeline（`parse → normalize → extract → update(wiki, vector, graph)`），不得另立平行流程
- **FR-041**：`manifest.json` MUST 延續 Phase 2 schema：`{relpath, sha256, format, size_bytes, ingested_at, derived, parser_fingerprint}`
- **FR-042**：wiki 頁面生成規則 MUST 沿用 Phase 1–2：一份來源檔對應一頁、slug 規則不變；影像檔 wiki 頁 MUST 明示 origin
- **FR-043**：`wiki/log.md` 事件格式 MUST 與 Phase 2 完全一致；`skipped_segments: ocr_empty` 僅為既有事件下新附屬 bullet
- **FR-044**：影像內容進入 `graph` MUST 沿用 Phase 2 既有 graph extractor；不新增影像專屬 entity / relation 類型
- **FR-045**：`ks ingest` stdout MUST 保持 Phase 1 `QueryResponse` top-level schema；影像專屬 per-file 結果欄位 MUST 置於 `trace.steps[kind="ingest_summary"].detail.files[]`

#### Query 契約保留

- **FR-050**：本 spec MUST NOT 修改 `ks query` 的輸出 schema、routing 路徑集合（僅 wiki / graph / vector）、exit code 契約或 `trace` 語意
- **FR-051**：影像來源的 chunk 經 vector 命中時，回傳之 chunk metadata MUST 包含 `ocr_confidence`
- **FR-052**：`source` 欄位 MUST NOT 因格式擴充而新增值；`trace.route` MUST NOT 出現 `"image"`、`"ocr"` 等新值

#### 異常處理

- **FR-060**：位元組損壞 / decoder 開啟失敗的影像 MUST 以 `DATAERR` + `reason=corrupt` 標註；parser MUST 保證 atomicity
- **FR-061**：空檔（0 byte）MUST 視為 skip + `reason=empty_file`，不產出 artifacts、不視為失敗
- **FR-062**：OCR 結果為空（整張圖無可辨識文字）MUST 視為 skip + `reason=ocr_empty`；不產出 wiki 頁面、不新增 vector chunk；`log.md` 附屬欄位記 `skipped_segments: ocr_empty:1`
- **FR-063**：單檔處理超過 30 秒（soft default）MUST 以 `DATAERR` + `reason=timeout` 終止該檔；整批 ingest 不中斷；runtime 可由 `HKS_IMAGE_TIMEOUT_SEC` 覆寫
- **FR-064**：單檔大小超過 20MB（soft default）MUST 以 `DATAERR` + `reason=oversized` 拒絕入庫；runtime 可由 `HKS_IMAGE_MAX_FILE_MB` 覆寫
- **FR-065**：解碼後像素總量超過上限 MUST 以 `DATAERR` + `reason=oversized_decoded` 標註

#### 禁止事項

- **FR-070**：本 spec MUST NOT 變更 Phase 2 既有 docx / xlsx / pptx parser 的 `[image: <alt>]` / `[smartart: ...]` 等固定前綴
- **FR-071**：本 spec MUST NOT 在 runtime 呼叫 hosted-only OCR / VLM API
- **FR-072**：本 spec MUST NOT 擴 query JSON schema 的 `source` / `trace.route` / `trace.steps.kind` enum
- **FR-073**：本 spec MUST NOT 改動 Phase 2 既有 graph schema 或 graph extractor 的 entity / relation 類型
- **FR-074**：本 spec MUST NOT 改動 Phase 2 既有 write-back gate / 自動寫入邏輯

#### Parser fingerprint 擴充

- **FR-080**：`parser_fingerprint` MUST 擴充以涵蓋影像 parser 設定：`{format}:v{decoder_version}:{preprocess_digest}:{ocr_model_name+version}:off`
- **FR-081**：fingerprint 生成 MUST 為決定性且穩定；模型路徑（絕對路徑）的變動不影響 fingerprint
- **FR-082**：舊 manifest（Phase 1 / 2 產出、無影像相關欄位）MUST 以 `"*"` wildcard 視為 compatible，首次對應影像 ingest 時才補齊具體 fingerprint

#### 測試與 local-first

- **FR-090**：影像三格式 MUST 提供 6 份 valid fixtures（含無文字純圖），另提供 4 份 broken fixtures（位元組損壞、超大、超時、空檔）
- **FR-091**：ingest / schema / idempotency / 降級四類測試 MUST 附自動化測試；`uv run pytest` 為合併閘門
- **FR-092**：OCR 與底層 decoder MUST 可於無網路環境執行；測試套 MUST 能於 airgapped 跑

### Key Entities

- **Image Raw Source**：被 ingest 的 `.png` / `.jpg` / `.jpeg` 原檔；屬性繼承自 Phase 1 Raw Source
- **OCR Segment**：OCR 輸出的文字區塊；屬性：`text`、`ocr_confidence`、可選 `bbox`、`source_engine`
- **Skipped Segment — `ocr_empty`**：擴充 Phase 2 SkippedSegmentType，新增 `ocr_empty`
- **Parser Fingerprint**：擴充 Phase 2 字串格式；新欄位含 decoder / preprocess / OCR 元件

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**：使用者可於單次指令 ingest 6 份影像 fixture；其中 5 份入庫、1 份 `ocr_empty` skip，整體 exit code `0`
- **SC-002**：相同影像與相同 parser 設定重跑 ingest，衍生 artifacts 總數保持不變；第二次執行 wall-clock 相較首次下降 ≥ 50%
- **SC-003**：以 mock 方式 bump OCR 模型版本重跑，對應影像 100% 觸發 `updated`
- **SC-004**：對影像內容各提 summary / detail / relation query，`ks query` 輸出 JSON 100% 可被標準 parser 解析，且 `source` / `trace.route` 值 100% 屬於既有集合
- **SC-005**：混合 Phase 1–3 既有格式與影像三格式於同一 `/ks/` 目錄上，既有 query 結果與 `004` 實作前相比 100% 未退化
- **SC-006**：降級場景（corrupt / oversized / timeout / empty_file / ocr_empty）於 100% 測試 fixtures 下符合預期
- **SC-007**：本機查詢 p95 延遲 < 3s 之 Phase 1 目標在新增影像格式後仍成立
- **SC-008**：`source` 與 `trace.route` 於任何情境下 grep 不出現 `"image"` / `"ocr"`；`graph.json` 仍為合法 JSON；程式碼不得有 query-time OCR 呼叫路徑
- **SC-009**：`uv run pytest`、`uv run ruff check .`、`uv run mypy src/hks` 全數通過
- **SC-010**：所有影像 parser 可於 airgapped 環境完成 ingest；任何 parser 觸發對外網路連線視為 bug

## Assumptions

- **MVP 格式集**：`.png` / `.jpg` / `.jpeg`
- **OCR only**：MVP 只保證 OCR 路徑；VLM 完全不進 004 runtime 與 CLI
- **OCR 引擎凍結**：`tesseract` + `tesseract-lang`，預設 `eng+chi_tra`
- **OCR 低信心僅標記、不過濾**：runtime 僅把 confidence 寫入 chunk metadata，query 端自行判讀
- **Placeholder 就地替換不做**：Phase 2 Office placeholder 完全不動
- **Preprocess 策略**：EXIF transpose + grayscale + autocontrast；策略變更一定反映於 `parser_fingerprint`
- **Graph 行為不擴**：影像 OCR 文字進入 graph 與 Phase 2 普通文字一致
- **檔案 / 超時 soft default**：單檔 20MB、OCR 30s；可由 `HKS_IMAGE_MAX_FILE_MB` / `HKS_IMAGE_TIMEOUT_SEC` 覆寫
- **Phase 邊界**：`ks lint`（005）、MCP adapter（006）、多 agent 協作（007）、動畫 / 多頁 / 向量圖、hosted-only API 一律延後；本 spec 僅負責「讓 raster image 進得來」

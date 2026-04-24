# Feature Specification: HKS Phase 1 MVP — CLI 骨架與核心知識流程

**Feature Branch**: `001-phase1-cli-mvp`
**Created**: 2026-04-23
**Status**: Complete
**Input**: 實作 `ks` CLI 的三個指令（ingest / query / lint-stub），以及支撐它們的 ingestion pipeline、兩層儲存（wiki / vector）、rule-based routing 與半自動 write-back，完整覆蓋 [readme.md](../../readme.md)、[docs/main.md](../../docs/main.md) §3–§8 與 [docs/PRD.md](../../docs/PRD.md) §4 / §9 / §10 的 Phase 1 清單。對應憲法 [§I–§V](../../.specify/memory/constitution.md)。

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Ingest 文件建立知識基底（Priority: P1）

工程師或個人使用者在 shell 下執行 `ks ingest <path>`，系統把 txt / md / pdf 來源納入知識系統：原始檔保留在 `raw_sources/`（immutable）、產出 wiki 頁面、並寫入 vector embedding。重複對同一來源執行時，系統能以內容 hash 判斷該跳過或更新，不會污染既有知識；skip / update / unsupported 事件需寫入 `wiki/log.md` 供後續追溯。

**Why this priority**：沒有 ingest 就沒有知識；所有後續查詢、write-back、統計都建立在 ingest 產出的三層資料上。這是 MVP 最低可交付單元。

**Independent Test**：準備 10 份混合格式（txt / md / pdf）的測試文件，對空的 `/ks/` 執行 `ks ingest ./fixtures/`，驗證：(a) `raw_sources/` 有 10 份副本；(b) `wiki/pages/` 下有對應頁面；(c) `wiki/index.md` 列出所有頁面；(d) vector DB 可以被後續查詢讀取；(e) 再次執行相同指令，所有項目數量不變、`log.md` 記錄「skipped (hash unchanged)」。

**Acceptance Scenarios**：

1. **Given** 空的 `/ks/` 目錄，**When** 使用者對一個含 10 份混合格式文件的資料夾執行 `ks ingest ./docs`，**Then** 系統在 `raw_sources/`、`wiki/pages/`、`vector/db/` 建立對應條目，並在 `manifest.json` 記錄每個來源的相對路徑與 SHA256；指令以 exit code `0` 結束並輸出 JSON 摘要（成功件數、跳過件數、失敗件數）。
2. **Given** 已經 ingest 過一次的 `/ks/`，**When** 使用者對相同資料夾再次執行 `ks ingest`，**Then** 所有 hash 未變的檔案被標記為 skipped，沒有新增或重複的 wiki / vector 條目，且 `log.md` 追加 `ingest | skipped` 紀錄。
3. **Given** 已經 ingest 過的檔案，**When** 使用者修改其中一個檔案內容並重新 ingest，**Then** 該檔衍生的 wiki / vector 被覆寫更新，其他檔案不動；`log.md` 追加一筆 update 紀錄。
4. **Given** 一個壞損或無法解析的 PDF，**When** 使用者 ingest 該檔，**Then** 系統跳過該檔並以 exit code `65`（DATAERR）結束，其他合法檔仍完成處理，JSON 輸出明列失敗清單。

---

### User Story 2 — Query 取得統一格式的答案（Priority: P1）

agent 或使用者在 shell 下執行 `ks query "<question>"`，系統依 rule-based routing 選擇 wiki 或 vector 路徑，回傳統一 JSON schema 的答案。agent 可直接 parse `answer` / `source` / `confidence` / `trace` 欄位，以 exit code 判別執行狀態，無需解析自然語言前綴。

**Why this priority**：query 是 HKS 的主價值交付點；只有 ingest 沒有 query 的系統沒有使用者意義。此故事與 P1 Ingest 共同構成「ingest → query」最小可用迴圈。

**Independent Test**：在 P1 Ingest 完成後，對不同類型問題執行 `ks query`：
- summary 類（「這份規範的重點是什麼」）→ 驗證 `trace.route=="wiki"`、`source==["wiki"]`、`confidence==1.0`
- detail 類（「條款 3.2 的原文是」）→ 驗證 `trace.route=="vector"`、`source==["vector"]`、`confidence` 為 [0,1] 之間的 cosine 值
- 關係類（「A 專案延遲會影響哪些系統」）→ 驗證走 vector fallback、`answer` 附註「深度關係推理將於 Phase 2 支援」
- 任何情況下的 JSON 皆可被標準 JSON parser 解析；`source` / `trace.route` 皆不出現 `"graph"`；exit code `0`（即使無命中也不返非零）。

**Acceptance Scenarios**：

1. **Given** 已 ingest 10 份文件，**When** 使用者執行 `ks query "摘要 專案X"`，**Then** 系統判定為 summary、從 wiki 取答、輸出 `{route:"wiki", source:["wiki"], confidence:1.0, ...}`、exit `0`。
2. **Given** 同上，**When** 使用者執行 `ks query "3.2 條款原文"`，**Then** 系統判定為 detail、從 vector 取 top-1 chunk、`confidence` 等於 cosine similarity、exit `0`。
3. **Given** 同上，**When** 使用者執行 `ks query "A 專案延遲影響哪些系統"`，**Then** 系統判定為關係類、走 vector fallback、`answer` 結尾附註「深度關係推理將於 Phase 2 支援」、exit `0`。
4. **Given** 已 ingest 文件，**When** 執行 `ks query` 但 wiki 命中為空，**Then** 系統自動 fallback 至 vector、`trace.route="vector"`、`trace.steps` 記錄 fallback 過程；若 vector 仍無結果，回 `answer="未能於現有知識中找到答案"`、`source=[]`、`confidence=0.0`、exit `0`。
5. **Given** `/ks/` 目錄尚未初始化（未曾 ingest），**When** 執行 `ks query`，**Then** 系統以 exit code `66`（NOINPUT）結束並輸出 JSON 錯誤說明。

---

### User Story 3 — 半自動 Write-back 累積知識（Priority: P2）

query 結束後，若答案具保留價值，使用者可確認將其回寫成 wiki 頁面，系統更新 `wiki/index.md` 與 append 至 `wiki/log.md`。TTY 環境互動詢問；非 TTY（agent 調用）環境自動跳過。使用者可透過 `--writeback=yes|no|ask` flag 覆寫預設行為。

**Why this priority**：write-back 是「知識隨使用成長」的關鍵機制，但即使不回寫，ingest + query 的核心迴圈仍可運作。故列為 P2，確保 P1 完成即可使用。

**Independent Test**：P1 完成後，在 TTY 模式執行 query 並回答 `y` 確認 → 驗證 `wiki/index.md` 多一行、`wiki/log.md` 多一筆；在 pipe 模式（`ks query ... | cat`）執行 → 驗證沒有 prompt、沒有回寫、`trace.steps` 註記「writeback=skip (non-tty)」；帶 `--writeback=yes` 在 pipe 模式執行 → 驗證直接回寫不詢問；帶 `--writeback=no` 在 TTY 執行 → 驗證不詢問、不回寫。

**Acceptance Scenarios**：

1. **Given** 已 ingest 文件、TTY 環境，**When** 使用者執行 `ks query ...` 並對提示答 `y`，**Then** 系統新增一份 wiki 頁面至 `pages/<slug>.md`、更新 `index.md` TOC、於 `log.md` 追加一筆，JSON `trace.steps` 包含 `writeback=committed`。
2. **Given** 同上，**When** 使用者答 `n`，**Then** 系統不回寫、`trace.steps` 包含 `writeback=declined`。
3. **Given** 非 TTY 環境（agent 或 pipe），**When** 執行 `ks query` 未指定 `--writeback`，**Then** 系統自動跳過回寫、`trace.steps` 包含 `writeback=skip-non-tty`、指令不阻塞。
4. **Given** 任何環境，**When** 執行 `ks query --writeback=yes`，**Then** 系統不問直接回寫；**When** 執行 `ks query --writeback=no`，**Then** 系統不問且不回寫。
5. **Given** write-back 目標 slug 已存在，**When** 回寫流程觸發，**Then** 系統以 `-<n>` 後綴產生不衝突的新 slug（例：`project-a.md` → `project-a-2.md`）並於 `log.md` 註記。

---

### User Story 4 — Lint Stub 維持 agent 相容性（Priority: P3）

`ks lint` 在 Phase 1 為 stub。為維持與未來 Phase 3 之 lint 實作的介面相容性，stub 吐出與 query 相同 schema 的 JSON，`answer` 說明「尚未實作」，exit code `0`。agent 在 Phase 1 呼叫 lint 不會收到非預期回應或非零 exit。

**Why this priority**：純為對外契約預留位；不影響 ingest / query 的 MVP 功能。

**Independent Test**：執行 `ks lint`，驗證：(a) stdout 是符合 §II schema 的 JSON；(b) `answer` 包含「尚未實作」字樣；(c) `source=[]`、`confidence=0.0`、`trace.route="wiki"`（佔位）、`trace.steps=[]`；(d) exit code `0`。

**Acceptance Scenarios**：

1. **Given** 任何 `/ks/` 狀態（包含空目錄），**When** 使用者執行 `ks lint`，**Then** stdout 輸出 `{answer: "lint 尚未實作，預計於 Phase 3 提供", source: [], confidence: 0.0, trace: {route: "wiki", steps: []}}`、exit `0`。

---

### Edge Cases

- **巨大檔案**：單份 PDF 超過合理大小（例如 > 200MB）時，系統應以 exit `65` 與明確錯誤 JSON 拒絕，避免 OOM；具體門檻於 plan 決定。
- **空檔案 / 只含 whitespace 的檔案**：視為 skip，記 `log.md`，不產出 wiki / vector 條目。
- **檔名含特殊字元 / 非 ASCII**：slug 生成須 normalize（保留可讀性，衝突加 `-<n>` 後綴）。
- **query 關鍵字同時命中多條 routing rule**：依 `config/routing_rules.yaml` 明確定義的優先順序選擇；不得 undefined。
- **query 未命中任何 rule**：fallback 至 default route（於 routing_rules.yaml 明定）；不得 crash。
- **`/ks/` 目錄被外部程序破壞（例如 manifest.json 遺失但 wiki / vector 仍在）**：`ks ingest` 應能偵測並重建 manifest；`ks query` 應以 exit `66` 停止並提示使用者重新 ingest。
- **多進程並發呼叫 `ks ingest`**：Phase 1 假設單進程；若偵測到 lock 檔存在，以 exit `1` 拒絕並提示。
- **Write-back 至 log.md 失敗（例如磁碟滿）**：回寫視為失敗、wiki/index.md 不更新、`trace.steps` 記錄、exit `1`。

## Requirements *(mandatory)*

### Functional Requirements

#### CLI 入口與指令集

- **FR-001**：系統 MUST 提供單一 CLI 入口 `ks`，支援 `ingest`、`query`、`lint` 三個子指令；`--help` 顯示指令使用說明。
- **FR-002**：CLI MUST 在 stdout 輸出符合 [憲法 §II](../../.specify/memory/constitution.md) 規範之 JSON schema，錯誤訊息 MUST 寫入 stderr。
- **FR-003**：CLI MUST 依下列 exit code 對外：`0` 成功、`1` 一般錯誤、`2` usage error、`65` ingest 資料錯、`66` 資源不存在；`ks query` 無命中 MUST NOT 返非零。

#### Ingest 行為

- **FR-010**：`ks ingest <path>` MUST 接受單檔或目錄；目錄 MUST 遞迴處理所有支援格式。
- **FR-011**：系統 MUST 支援 txt / md / pdf 三種格式；其他格式 MUST 被跳過並在輸出清單中標記 unsupported，不計入失敗。
- **FR-012**：系統 MUST 將來源檔複製至 `raw_sources/`（immutable，不修改內容）。
- **FR-013**：系統 MUST 維護 `/ks/manifest.json`，以相對路徑為 key、記錄 SHA256 與衍生 artifacts 清單。
- **FR-014**：重複 ingest 時，系統 MUST 以 SHA256 判斷 idempotency：hash 未變 → skip 並記 `log.md`；hash 變更 → 覆寫該檔所有衍生 artifacts（wiki chunk、vector rows）並記 `log.md` update；檔案遺失 → 預設保留 artifacts，`--prune` 可清除。
- **FR-015**：對每個被處理的來源檔，ingest MUST 在 ingest 階段即完成兩層整理（parse → normalize → extract → update wiki + vector），不得延遲至 query（憲法 §IV）。
- **FR-016**：wiki 頁面 slug MUST 以來源檔名 normalize 後產生；碰撞 MUST 以 `-<n>` 後綴避開。

#### Query 行為

- **FR-020**：`ks query "<q>"` MUST 透過 rule-based routing 選擇路徑；路由規則 MUST 以 `config/routing_rules.yaml`（中英雙語、含優先順序、含 default route）外部化，程式碼不得 hard-code 關鍵字。
- **FR-021**：路徑僅限 wiki / vector 兩路；Phase 1 實作 MUST NOT 產生 `"graph"` 字樣於 `source` 或 `trace.route`。
- **FR-022**：關係類問題命中時 MUST 走 vector fallback，`answer` 結尾 MUST 附註「深度關係推理將於 Phase 2 支援」。
- **FR-023**：`trace.route` MUST 為最終採用路徑；`source` MUST 為實際取用之知識層（可為複數，例如 `["wiki","vector"]` 表示 merge）；語意與組合表比照 [docs/main.md §5.4](../../docs/main.md)。
- **FR-024**：`confidence` 計算規則 MUST 為：wiki 命中 = 1.0；vector = top-1 cosine similarity；merge = max。
- **FR-025**：所有 routing 判定、fallback 切換、merge 決策 MUST 記入 `trace.steps` 可追溯紀錄。
- **FR-026**：無命中時，系統 MUST 回 `answer` 為友善說明、`source=[]`、`confidence=0.0`、exit `0`。

#### Write-back 行為

- **FR-030**：Write-back 預設為半自動；TTY 環境 MUST 互動詢問使用者是否回寫。
- **FR-031**：非 TTY 環境（agent / pipe）MUST 自動跳過回寫，不阻塞指令；`trace.steps` MUST 記 `writeback=skip-non-tty`。
- **FR-032**：CLI MUST 提供 `--writeback=yes|no|ask`（預設 `ask`）覆寫預設；`yes` 強制回寫、`no` 強制不回寫、`ask` 依 TTY 決定是否詢問。
- **FR-033**：回寫成功 MUST 同時更新 `wiki/index.md`（TOC 新增條目）與 `wiki/log.md`（append 紀錄），格式見 [docs/main.md §8.1 / §8.2](../../docs/main.md)。
- **FR-034**：Phase 1 MUST NOT 存在任何「高 confidence 自動回寫」或「背景靜默寫入」邏輯（憲法 §V）。

#### Lint Stub

- **FR-040**：`ks lint` MUST 輸出與 query 相同 schema 的 JSON，`answer="lint 尚未實作，預計於 Phase 3 提供"`、`source=[]`、`confidence=0.0`、`trace.route="wiki"`、`trace.steps=[]`、exit `0`。

#### 資料結構與禁止事項

- **FR-050**：`/ks/` 目錄結構 MUST 符合 [docs/main.md §8](../../docs/main.md)：`raw_sources/`、`wiki/{index.md, log.md, pages/}`、`vector/db/`、`manifest.json`。
- **FR-051**：Phase 1 MUST NOT 建立 `/ks/graph/` 目錄或寫入任何 graph 相關資料（憲法 §I）。
- **FR-052**：系統 MUST 為 domain-agnostic；ingest / routing / write-back 邏輯 MUST NOT hard-code 任何垂直領域（程式、法律、醫療等）專屬詞彙（憲法 §III）。

#### Local-first 與測試

- **FR-060**：所有 Phase 1 核心路徑（ingest / query / write-back / lint）MUST 可在無網路環境執行；雲端服務僅可為可選加速。
- **FR-061**：ingest、routing、JSON schema 三類變更 MUST 附對應自動化測試；`uv run pytest` 為合併閘門。

### Key Entities

- **Raw Source**：被 ingest 的原始文件，儲存於 `raw_sources/`，immutable。屬性：相對路徑、SHA256、格式（txt/md/pdf）、原始大小、ingest 時間。
- **Wiki Page**：一份 markdown 格式的知識頁面，儲存於 `wiki/pages/<slug>.md`。屬性：slug、標題、一句摘要、來源 Raw Source 參照、最後更新時間、來源類型（ingest 產出 / write-back 產出）。
- **Wiki Index Entry**：`wiki/index.md` 中一行 TOC，`- [Title](pages/<slug>.md) — summary`。
- **Log Entry**：`wiki/log.md` append-only 營運紀錄，結構見 [docs/main.md §8.2](../../docs/main.md)；至少含時間戳、事件類型（ingest / writeback）、狀態，並依事件附帶 target 或 query / route / source / pages touched / confidence。
- **Vector Chunk**：一段 normalized 後的文字段落 + embedding；屬性：來源 Raw Source 參照、chunk 序號、文字、embedding 向量、metadata。
- **Manifest Entry**：`manifest.json` 中一筆 `{path, sha256, derived: {wiki_pages:[...], vector_ids:[...]}}`，串接來源與兩層衍生 artifacts，為 idempotency 與 prune 的依據。
- **Routing Rule**：`config/routing_rules.yaml` 中一條規則；屬性：關鍵字清單（中 / 英）、目標 route（wiki / vector）、優先順序、是否觸發「Phase 2 附註」。
- **Query Response**：CLI 對外穩定 JSON schema `{answer, source, confidence, trace:{route, steps}}`，schema 為憲法 §II 規範之對外 API。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**：使用者可在單次指令內成功 ingest 10 份混合格式（含至少 2 份 PDF、3 份 md、3 份 txt）文件，零手動干預。
- **SC-002**：對相同輸入重複 ingest，衍生 artifacts 總數保持不變（idempotent），且執行時間相較首次下降 ≥ 50%（因跳過未變檔案）。
- **SC-003**：summary 類問題從 wiki 回答、detail 類問題從 vector 回答，JSON 結構 100% 可被標準 parser 解析。
- **SC-004**：CLI 在非互動環境（例如 `ks query ... | cat`、CI script、agent 呼叫）下無 prompt 阻塞；1000 次自動化呼叫成功率 100%。
- **SC-005**：本地查詢 p95 延遲 < 3s（於 commodity laptop、已 ingest 50 份文件的語料下）。
- **SC-006**：持續使用下 wiki 可成長至 ≥ 20 pages（ingest + write-back 合計），且 `wiki/index.md` 與 `pages/` 保持一致（無 orphan、無 dead link）。
- **SC-007**：exit code 在所有定義情境下符合契約（0/1/2/65/66 共 5 種），100% 可被外部 shell script 依賴。
- **SC-008**：Phase 1 runtime JSON 的 `source` 與 `trace.route` 欄位 grep 不出現 `"graph"` 字樣；`KS_ROOT/graph/` 目錄於任何情境下不得被建立；`src/hks/` 程式碼不得有為 graph 實作的 code path（註解 / docstring 內的 Phase 2 預告語可接受）。三條共同構成憲法 §I / §II 檢核。
- **SC-009**：`uv run pytest` 全數通過，ingest / routing / schema 三類測試覆蓋率 ≥ 80%（具體門檻於 plan 決定）。

## Assumptions

- **單使用者、單進程**：Phase 1 假設單一使用者、單一進程操作 `/ks/`；並發安全性非本階段需求（邊界以 lock 檔拒絕）。
- **Wiki 頁面粒度**：預設「一份來源檔對應一個 wiki 頁面」；Phase 2 引入 graph 後可能改為「一個主題一頁」，屆時走憲法修訂。
- **Slug 策略**：由來源檔名 ASCII normalize 產出；碰撞以 `-<n>` 後綴避開；非 ASCII 檔名採音譯或 slugify 套件決定（具體實作於 plan）。
- **Routing 關鍵字語言**：Phase 1 `routing_rules.yaml` 含中（zh-TW）/ 英兩語；其他語言於需求出現時再擴充。
- **Embedding / Vector DB / PDF parser 選型**：具體選型於 plan 階段決定，限制條件為「local-first、無須強制聯網」。
- **測試語料**：repo `tests/fixtures/` 下提供 `valid/` 的 10 份匿名化樣本，另有 `broken/`、`oversized/`、skip cases 供 edge case 測試；CI 以此為基準。
- **Non-TTY 偵測**：以標準 `isatty(stdout)` 為判斷依據；不處理偽 TTY 等邊角情境。
- **檔案變更判定**：以內容 SHA256 為唯一依據，不看檔案 mtime；符號連結以目標內容計。
- **Log.md 保留策略**：append-only、無輪替；容量管理屬 Phase 3 lint / 維運範疇。
- **Phase 邊界**：graph 相關能力（extraction、query、LLM routing、自動 write-back）一律延後至 Phase 2，本 feature 實作嚴禁觸及（憲法 §I）。

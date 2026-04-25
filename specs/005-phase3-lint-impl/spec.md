# Feature Specification: Phase 3 階段二 — `ks lint` 真實實作

**Feature Branch**: `005-phase3-lint-impl`
**Created**: 2026-04-25
**Status**: Complete
**Input**: 取代 Phase 1 的 `ks lint` stub（僅輸出「尚未實作，預計於 Phase 3 提供」）為真實的跨層一致性檢查。lint 跨 `wiki/`、`vector/`、`graph/`、`manifest.json` 四個資料層，列出 orphan / dead-link / drift 等結構化 findings；可選 `--strict` 把 error 級 finding 升級為 exit `1`，可選 `--fix=apply` 做極小集合的安全自動修復（rebuild index、prune orphan vector / graph 邊）。本 spec 不變更 query / ingest 路徑，不擴 `source` / `trace.route` enum。對應憲法 [§II / §IV / §V](../../.specify/memory/constitution.md)、沿用 [spec 002](../002-phase2-ingest-office/spec.md) 的 ingest summary detail 機制與 [spec 003](../003-phase2-graph-routing/spec.md) 的 graph 契約。

## Clarifications

### Session 2026-04-26

- Q: manifest / wiki / raw source 不一致的 severity 如何凍結 → A: manifest 缺失類為 error；orphan raw source 為 warning
- Q: `duplicate_slug` 在現行檔案系統下如何定義 → A: 以 `index.md` 與 page frontmatter slug 重複為準
- Q: `--fix=apply` 是否必須先跑 dry-run → A: 不需要；apply 內部重算同一批 fix plan
- Q: lint 與 ingest 併發時採阻塞還是拒絕 → A: 共用 non-blocking exclusive lock；取不到鎖 exit 1
- Q: lint trace 與 audit log 是否可新增獨立契約字面 → A: trace 新增單一 `lint_summary`；log 新增 event `lint` 與 status `lint_fix_applied`

## User Scenarios & Testing *(mandatory)*

### User Story 1 — 列出跨層不一致 findings（Priority: P1）

使用者或 agent 在 shell 下執行 `ks lint`，系統能 read-only 掃描 `/ks/` 下四層資料、列出全部 findings 於 stdout JSON 的 `trace.steps[kind="lint_summary"].detail.findings[]`，每筆 finding 含 `category` / `severity` / `target` / `message` 四個必填欄位；找到問題不視為指令失敗，預設 exit `0`。空 / 一致的 `/ks/` 結果為 `findings=[]`、severity counters 全 `0`。

**Why this priority**：lint 真實實作的核心價值是「能告訴我哪裡壞了」；沒有結構化 findings，agent 無法消費 lint 結果，CI 也無法把 lint 接進 pipeline。此故事一落地即取代 Phase 1 stub，是 005 的 MVP。

**Independent Test**：對乾淨 ingest 後的 `/ks/` 執行 `ks lint`，驗證：(a) JSON 通過 Phase 1 query schema；(b) `trace.steps[0].kind == "lint_summary"`、`detail.findings == []`、`detail.severity_counts.error == 0`；(c) exit `0`。再人為製造各 category 至少一筆不一致（手動刪 page、改 manifest、刪 vector chunk、graph 多餘節點），重跑驗證對應 finding 出現於 `findings[]`，且 `category` / `severity` / `target` 對得上具體實體。

**Acceptance Scenarios**：

1. **Given** 剛 ingest 完成的乾淨 `/ks/`，**When** 使用者執行 `ks lint`，**Then** stdout 為 Phase 1 `QueryResponse` schema、`detail.findings` 空陣列、`detail.severity_counts` 全 `0`、`answer` 為人類可讀摘要、exit code `0`、stderr 空。
2. **Given** `/ks/wiki/pages/` 多出一個 `index.md` 沒列的 page，**When** 使用者執行 `ks lint`，**Then** `findings[]` 至少含一筆 `category="orphan_page"`、`target` 為該 page slug、`severity="warning"`、`message` 一行可讀說明；其他無關層不誤報；exit `0`。
3. **Given** 在不影響其他層的前提下，把 `/ks/wiki/pages/` 內某 page 檔刪除（但 `index.md` 仍列），**When** 使用者執行 `ks lint`，**Then** `findings[]` 含 `category="dead_link"`、`target` 為該 slug；exit `0`。
4. **Given** `manifest.json` 引用了一個 `derived.wiki_pages[]` 對應頁面但實體不存在、且 `derived.vector_ids[]` 引用了 chroma 找不到的 chunk id，**When** 執行 `ks lint`，**Then** 兩筆 findings 各以 `category="manifest_wiki_mismatch"` / `category="manifest_vector_mismatch"` 標記、severity 一致為 `error`；severity counters 對應 +1。
5. **Given** `/ks/graph/graph.json` 含節點指向不存在的 document、`raw_sources/` 多出 manifest 沒對應的孤兒檔案，**When** 執行 `ks lint`，**Then** `findings[]` 同時含 `graph_drift`（`error`）與 `orphan_raw_source`（`warning`），順序與內部分類無關但 category 字面準確。
6. **Given** manifest entry 的 `parser_fingerprint` 與當前 runtime 計算結果不符，**When** 執行 `ks lint`，**Then** `findings[]` 含 `category="fingerprint_drift"`、`severity="info"`；不影響預設 exit code。

---

### User Story 2 — 把 lint 結果接進 CI（`--strict`）（Priority: P1）

使用者或 CI 環境希望「有 error 級 finding 即視為失敗」，可加 `--strict`：任何 `severity="error"` finding 觸發 exit `1`、其他 severity 維持 exit `0`；可進一步用 `--severity-threshold=error|warning|info` 把門檻放寬到 warning 或 info。`usage` 錯誤（flag 值非法）→ exit `2`。

**Why this priority**：MVP 同時要交付「人類用」（預設 exit `0`）與「機器用」（CI strict 模式）兩條路；缺其一就半套。

**Independent Test**：(a) 對乾淨 `/ks/` 執行 `ks lint --strict` → exit `0`；(b) 對含 error finding 的 `/ks/` 執行 `ks lint --strict` → exit `1`、stdout 仍為合法 JSON、findings 與不加 strict 完全相同；(c) `ks lint --severity-threshold=warning --strict` 對只有 warning 的 `/ks/` → exit `1`；(d) `ks lint --strict --severity-threshold=invalid` → exit `2`、`stderr` 首行為 `[ks:lint] usage:` 開頭。

**Acceptance Scenarios**：

1. **Given** 含至少一筆 `severity="error"` finding 的 `/ks/`，**When** 執行 `ks lint --strict`，**Then** exit `1`、stdout 仍為 Phase 1 schema、`detail.findings` 與不加 strict 完全相同。
2. **Given** 只有 `warning` 級 finding 的 `/ks/`，**When** 執行 `ks lint --strict`（門檻預設 `error`），**Then** exit `0`；改執行 `ks lint --strict --severity-threshold=warning`，**Then** exit `1`。
3. **Given** 任何 `/ks/`，**When** 執行 `ks lint --severity-threshold=garbage`，**Then** exit `2`、stderr 首行 `[ks:lint] usage: invalid value for --severity-threshold ...`、stdout 為合法錯誤 JSON。
4. **Given** 任何 `/ks/`，**When** 執行 `ks lint`（無 flag），**Then** exit code 一律為 `0`，與 findings 數量無關（`--strict` 是 opt-in）。

---

### User Story 3 — 安全自動修復（`--fix`）（Priority: P2）

使用者可加 `--fix` 列出本次掃描下會被執行的修復動作（dry-run 預設）；加 `--fix=apply` 才真正寫入。修復動作 MUST 限縮在「可逆 / 低風險」許可清單：rebuild `wiki/index.md`、prune orphan vector chunks、prune graph 中孤兒節點 / 邊。MUST NOT 自動刪 wiki page、MUST NOT 刪 raw_sources、MUST NOT 觸發 re-ingest。每次 `--fix=apply` MUST 在 `wiki/log.md` 留 audit log 一筆。

**Why this priority**：read-only 報告（US1+US2）不依賴此故事，但實際使用 lint 的人多半希望「順手把能修的修掉」；提供 `--fix=apply` 把人工複製貼上的工作消除。列為 P2 確保 P1 完成即可獨立交付。

**Independent Test**：(a) 對含 orphan_vector_chunk + graph_drift + 缺 index 的 `/ks/` 執行 `ks lint --fix`（dry-run）→ `detail.fixes_planned[]` 列出對應動作、資料層完全沒被動到、exit `0`；(b) 同 `/ks/` 改執行 `ks lint --fix=apply`，**Then** 該三類修復實際生效（重 grep 後 finding 消失）、`wiki/log.md` 多一筆 `lint_fix_applied` 紀錄、exit `0`；(c) 含 `manifest_wiki_mismatch` 的 `/ks/` 執行 `ks lint --fix=apply`，由於該類不在許可清單，**Then** 對應 finding 仍存在、`detail.fixes_skipped[]` 列為 `requires_manual` 並附 `message`、exit `0`。

**Acceptance Scenarios**：

1. **Given** `/ks/` 缺少 `wiki/index.md` 但 `pages/` 完整，**When** 執行 `ks lint --fix`（dry-run），**Then** `detail.fixes_planned[]` 含一筆 `action="rebuild_index"`、實際 `index.md` 內容不變、exit `0`。
2. **Given** 同情境，**When** 執行 `ks lint --fix=apply`，**Then** `wiki/index.md` 被重建、`detail.fixes_applied[]` 含對應 action、`wiki/log.md` 追加 `lint | lint_fix_applied` 事件且附 `action=rebuild_index` / `target=wiki/index.md`、exit `0`。
3. **Given** chroma collection 中存在沒有任何 manifest entry 引用的 chunk id，**When** 執行 `ks lint --fix=apply`，**Then** 對應 chunk 被 prune、再次 `ks lint` 該 finding 消失。
4. **Given** `graph.json` 中存在指向不存在 document 的孤兒節點 / 邊，**When** 執行 `ks lint --fix=apply`，**Then** 對應節點 / 邊被刪除、graph 仍為合法 JSON、其他節點不受影響。
5. **Given** `manifest_wiki_mismatch` finding（manifest 引用之 page 不存在），**When** 執行 `ks lint --fix=apply`，**Then** 該 finding 留存於 `findings[]`、`detail.fixes_skipped[]` 含 `category="manifest_wiki_mismatch"` + `reason="manifest_truth_unknown"`、資料層不被動到。
6. **Given** 任何 `/ks/`，**When** 同時下 `ks lint --fix=apply --strict`，**Then** 修復後仍存在的 error finding 觸發 exit `1`；無剩餘 error finding 時 exit `0`。

---

### Edge Cases

- **`/ks/` 不存在或核心資料層缺失**：`manifest.json` / `wiki/` / `vector/` 任一缺失 MUST 以 exit `66 NOINPUT` 結束，stderr 首行 `[ks:lint] error: ...`，stdout 仍為合法 JSON 錯誤 response。
- **`graph.json` 損毀（非合法 JSON）**：MUST 以 exit `1 GENERAL` 結束、stderr 標明損毀位置、stdout 仍為合法錯誤 response；不嘗試自動修復 graph 結構（超出許可清單）。
- **vector store 無法開啟**：以 exit `1 GENERAL` 結束、message 一致；不視為「找到 vector findings」。
- **多進程併發**：lint MUST 與 ingest 共用同一 non-blocking exclusive lock；取不到 lock MUST 以 exit `1 GENERAL` 拒絕，stderr 首行 `[ks:lint] error: ...`，避免讀到半更新資料層。
- **大型語料**：MVP 不做進度條 / 不做 streaming output；005 不提供 `--max-categories=` 或同等 filter。
- **fingerprint drift 但 hash 未變**：本身不是 error，僅 info（暗示「該 re-ingest 但暫時可用」）；`--fix=apply` 不觸發 re-ingest（FR-072）。
- **wiki page frontmatter `source` 指向 manifest 不存在的 raw_source**：標 `wiki_source_mismatch`、severity `error`；不擅自刪 page。
- **空 collection / 空 graph**：合法狀態，無 findings；不應誤報 `orphan_*`。

## Requirements *(mandatory)*

### Functional Requirements

#### CLI 入口

- **FR-001**：`ks lint` MUST 取代 Phase 1 stub；不再回傳「尚未實作」的固定字串；輸出 schema 維持 Phase 1 `QueryResponse`。
- **FR-002**：`ks lint` MUST 支援以下 flag：`--strict`（boolean）、`--severity-threshold=error|warning|info`（預設 `error`）、`--fix`（dry-run）/`--fix=apply`（real）。flag 值非法 → exit `2 USAGE`，stderr 首行 `[ks:lint] usage: ...`。
- **FR-003**：`ks lint` MUST 為 read-only by default；只在 `--fix=apply` 才允許寫入資料層。

#### 檢查項目（最少 MVP 涵蓋）

- **FR-010**：MUST 檢查 wiki 一致性：`orphan_page`、`dead_link`、`duplicate_slug`；`duplicate_slug` 指 `wiki/index.md` 中同一 slug 重複，或多個 page frontmatter 宣告相同 `slug`。
- **FR-011**：MUST 檢查 manifest ↔ wiki：`manifest_wiki_mismatch`（manifest 引用之 page 不存在，severity=`error`）、`wiki_source_mismatch`（page frontmatter 指向 manifest 沒有的 raw_source，severity=`error`）。
- **FR-012**：MUST 檢查 manifest ↔ raw_sources：`dangling_manifest_entry`（manifest 有 entry 但實體缺，severity=`error`）、`orphan_raw_source`（raw_sources/ 有檔但 manifest 沒對應，severity=`warning`）。
- **FR-013**：MUST 檢查 manifest ↔ vector：`manifest_vector_mismatch`（manifest 引用之 chunk id 不存在於 collection）、`orphan_vector_chunk`（collection 有 chunk 但無 manifest 引用）。
- **FR-014**：MUST 檢查 manifest ↔ graph：`graph_drift`（manifest `derived.graph_nodes/edges` 與 `graph.json` 實際內容不符；含節點 / 邊指向不存在 document 的子情境）。
- **FR-015**：MUST 檢查 `fingerprint_drift`：以 manifest entry 的 `parser_fingerprint` 與 runtime 計算值比對。
- **FR-016**：每筆 finding 的 `category` 字面 MUST 為 plan 凍結之 enum 之一；spec 內所列名稱（`orphan_page` / `dead_link` / `duplicate_slug` / `manifest_wiki_mismatch` / `wiki_source_mismatch` / `dangling_manifest_entry` / `orphan_raw_source` / `manifest_vector_mismatch` / `orphan_vector_chunk` / `graph_drift` / `fingerprint_drift`）MUST 為 enum 子集；plan 可新增其他 category 但須同步 schema。
- **FR-017**：severity mapping MUST 固定如下：`error` = `manifest_wiki_mismatch` / `wiki_source_mismatch` / `dangling_manifest_entry` / `manifest_vector_mismatch` / `graph_drift`；`warning` = `orphan_page` / `dead_link` / `duplicate_slug` / `orphan_raw_source` / `orphan_vector_chunk`；`info` = `fingerprint_drift`。

#### 輸出契約

- **FR-020**：`ks lint` stdout MUST 維持 Phase 1 `QueryResponse` top-level schema（`{answer, source, confidence, trace}`）；`source==[]`、`confidence==0.0`、`trace.route="wiki"`（佔位，與 Phase 1 stub 一致）。
- **FR-021**：detail object MUST 置於唯一一個 `trace.steps[kind="lint_summary"].detail`；MUST 含 `findings: list[Finding]`、`severity_counts: {error: int, warning: int, info: int}`、`category_counts: {<category>: int, ...}`。錯誤情境可改用既有 `trace.steps[kind="error"]`，不得同時輸出半成品 `lint_summary`。
- **FR-022**：每筆 `Finding` MUST 含 `{category, severity, target, message}` 四個必填欄位；`category` / `severity` 為 enum；`target` / `message` 為 string；可附選填欄位（例如 `details: dict`）但不得改動四個必填欄位語意。
- **FR-023**：`detail` MUST 同時含 `fixes_planned: list[FixAction]`、`fixes_applied: list[FixAction]`、`fixes_skipped: list[FixSkip]`：dry-run 模式下 `fixes_planned` 為非空、`fixes_applied` 為空；apply 模式下 `fixes_planned` 為空、`fixes_applied` / `fixes_skipped` 反映實際結果；不在 `--fix` 模式下三者皆為空陣列。
- **FR-024**：`answer` 字串 MUST 為人類可讀單行摘要，例如 `lint 完成：3 errors / 5 warnings / 1 info`；無 finding 時 `lint 完成：0 issues`；`--fix=apply` 時加一段 `applied N / skipped M` 後綴；MUST NOT 含 ANSI / 控制字元。

#### Exit code 行為

- **FR-030**：預設 exit `0`，無關 finding 數量（對齊 Phase 1 FR-003）。
- **FR-031**：`--strict` flag 啟用後，MUST 比對 `--severity-threshold`（預設 `error`）；若 findings 中存在等於或高於門檻者，exit `1`。severity 排序：`error > warning > info`。
- **FR-032**：`/ks/` 不存在或缺核心檔 MUST exit `66 NOINPUT`；資料層 IO 失敗 MUST exit `1 GENERAL`；flag 值非法 MUST exit `2 USAGE`。

#### `--fix` 自動修復

- **FR-040**：`--fix=apply` 之修復動作 MUST 限縮於以下許可清單：
  - `rebuild_index`：由 `wiki/pages/` 重建 `wiki/index.md`
  - `prune_orphan_vector_chunks`：刪除 chroma 中無 manifest 引用之 chunk id
  - `prune_orphan_graph_nodes`：刪除 graph 中孤兒節點與連帶 edge
  - `prune_orphan_graph_edges`：刪除 graph 中端點不存在之邊

  其他不在清單之 finding category 一律歸入 `fixes_skipped[]`，附 `reason` 說明（例如 `requires_manual`、`unsupported_in_005`）。
- **FR-041**：`--fix=apply` MUST 為 atomic per-action：單一 fix 失敗不影響其他 fix；失敗的 fix MUST 列入 `fixes_skipped[]`，附 `reason="apply_failed"` + 具體錯誤訊息。
- **FR-042**：`--fix=apply` MUST NOT：刪 `wiki/pages/*.md` 任一檔、刪 `raw_sources/*` 任一檔、修改 `manifest.json`、觸發 re-ingest、呼叫任何 LLM / 對外網路。
- **FR-043**：每次 `--fix=apply` MUST 在 `wiki/log.md` 追加一筆事件，event type 為 `lint`、status 為 `lint_fix_applied`，附 `action`、`target`、`outcome`（`success` / `skipped` / `apply_failed`）；多 action 時逐筆 append；`wiki/log.md` 既有事件格式不變、舊行解析不受影響。
- **FR-044**：`--fix=apply` 與 `--strict` 同時使用時，先做 fix、再判斷剩餘 findings 是否觸發 exit `1`。
- **FR-045**：dry-run 模式（`--fix` 無 value 或 `--fix=plan`）MUST 不寫任何資料層、`wiki/log.md` 不追加紀錄。

#### 必須維持的既有契約

- **FR-050**：本 spec MUST NOT 修改 `ks query` / `ks ingest` 的輸出 schema、routing 路徑集合、exit code 契約或 `trace` 語意。
- **FR-051**：`source` / `trace.route` enum MUST NOT 因 lint 擴增新值；lint 自身使用既有 `wiki` 佔位。
- **FR-052**：`trace.steps.kind` enum 在本 spec 僅新增 `lint_summary`（屬 §II MINOR 擴充，不影響既有 agent 解析 query / ingest）。
- **FR-053**：`wiki/log.md` event type 集合 MUST 僅新增 `lint`，event status 集合 MUST 僅新增 `lint_fix_applied`；其他既有 event / status 行為不變。

#### 異常處理

- **FR-060**：`/ks/` 路徑不存在 / 缺 `manifest.json` / 缺 `wiki/` 目錄 / 缺 `vector/db/` 目錄 → exit `66 NOINPUT`、stderr 首行 `[ks:lint] error: ...`、stdout 為合法錯誤 JSON。
- **FR-061**：`graph.json` 損毀（非合法 JSON）→ exit `1 GENERAL`、不觸發 `--fix` 動作（即使有 `--fix=apply`）；錯誤訊息明示損毀位置。
- **FR-062**：vector store 無法開啟 → exit `1 GENERAL`；不視為 vector 層 findings。
- **FR-063**：lint 全程 read-only（除 `--fix=apply` 外）；任何意外寫入路徑 MUST 視為 bug。

#### 禁止事項

- **FR-070**：本 spec MUST NOT 引入拼字 / 語意 / fact-check 相關功能；lint 僅做結構性一致性檢查。
- **FR-071**：本 spec MUST NOT 引入 LLM 呼叫；lint 全程 deterministic、不呼叫任何 hosted API。
- **FR-072**：本 spec MUST NOT 觸發 re-ingest；fingerprint drift 報告為 info、修復責任交給 `ks ingest`。
- **FR-073**：本 spec MUST NOT 改 ingest pipeline 行為；新增的 lint 模組不得共用 ingest 之寫入路徑。
- **FR-074**：本 spec MUST NOT 提供 MCP adapter 或多 agent 支援；遠端調用 lint 屬 006 / 007 範疇。

#### 測試與 local-first

- **FR-080**：MUST 提供 fixture 重現各 category 至少一筆（若 category 與既有 fixture 衝突則允許程式化注入）；fixtures 設計 MUST 不汙染 Phase 1–4 既有測試套。
- **FR-081**：lint 邏輯 MUST 可於 airgapped 執行；不引入新 third-party network dependency。
- **FR-082**：lint / `--strict` / `--fix` 三類測試 MUST 附自動化測試；`uv run pytest` 為合併閘門（沿用 Phase 1 FR-061）。

### Key Entities

- **Finding**：lint 掃描產出的最小單位；屬性 `category` (enum) / `severity` (enum) / `target` (string) / `message` (string) / 可選 `details` (dict)。`Finding` 為純資料結構，不含修復邏輯。
- **FixAction**：在 `--fix` 模式下產生的修復動作描述；屬性 `action` (enum，許可清單字面) / `target` (string) / `outcome` (enum：`planned` / `success` / `apply_failed`) / 可選 `details` (dict)。
- **FixSkip**：被刻意跳過的修復；屬性 `category`（對應的 finding category）、`reason`（enum 例如 `requires_manual` / `unsupported_in_005` / `apply_failed`）、可選 `message`。
- **LintSummaryDetail**：`trace.steps[kind="lint_summary"].detail` 的整體結構；含 `findings[]`、`severity_counts`、`category_counts`、`fixes_planned[]`、`fixes_applied[]`、`fixes_skipped[]`。
- **LintRunMode**：執行模式分類（純 lint / strict / fix-dry-run / fix-apply / strict+fix-apply 等組合）；不為 schema 欄位、僅 spec 概念。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**：對乾淨 ingest 後的 `/ks/` 執行 `ks lint`，`detail.findings == []`、`severity_counts.error == 0`、exit `0`、JSON 100% 通過 Phase 1 query schema。
- **SC-002**：對人為注入至少 1 筆/類的不一致狀態（涵蓋全部 11 個 spec 列出的 category），lint 100% 命中對應 category；`severity` 與 spec 預期一致。
- **SC-003**：`--strict` 模式下，含 error finding 必 exit `1`、不含 error finding 必 exit `0`；`--severity-threshold` 三種值在對應 fixture 上均能正確切換 exit code。
- **SC-004**：`--fix`（dry-run）執行後資料層內容 100% 未變動（以 sha256 比對 `/ks/` 全樹）；`--fix=apply` 後在許可清單內的 finding 100% 從重跑結果中消失，許可清單外的 finding 100% 維持。
- **SC-005**：`--fix=apply` 全程未觸發 re-ingest、未呼叫 LLM、未產生對外網路請求（airgapped 測試驗證）。
- **SC-006**：query / ingest 的既有 schema、exit code、routing 行為 100% 未退化（以既有 Phase 1–4 測試套為基準）。
- **SC-007**：`source` / `trace.route` 於任何情境下 grep 不出現新值；`trace.steps.kind` 僅可能多出 `lint_summary` 一個既有 spec 已預告的新值。
- **SC-008**：`uv run pytest` 全數通過、新增 lint 邏輯與許可清單測試覆蓋率 ≥ 80%（沿用 Phase 2 SC-008 門檻）。
- **SC-009**：lint 對中型語料（已 ingest 50 份混合文件 + 10 份影像）的 wall-clock < 5s（commodity laptop）；`--fix=apply` 對該語料的 wall-clock < 10s（含寫入）。

## Assumptions

- **`trace.steps.kind` enum 擴充**：本 spec 新增 `lint_summary` 為合法 step kind；屬 §II MINOR 擴充（既有 agent 解析 query 不會崩）；plan / contracts 階段固化於 schema。
- **lint findings detail schema 為單一權威**：本 spec 在 `contracts/lint-summary-detail.schema.json` 固化 detail schema，由 runtime validator 強制驗證；不擴 query schema。
- **fix 許可清單為硬性**：rebuild_index / prune_orphan_vector_chunks / prune_orphan_graph_nodes / prune_orphan_graph_edges 四項；後續 spec 才能擴。
- **manifest 視為 truth-of-record**：當 manifest 與其他層不一致時，lint 報告 mismatch；不會自動把 manifest 「對齊」到實際資料層（避免把錯誤的實際狀態寫進 manifest）。
- **fingerprint drift = info**：parser library / OCR 模型升級後尚未 re-ingest，不算 lint 失敗；建議使用者跑 `ks ingest` 觸發 re-ingest。
- **lock 共用**：lint 與 ingest 共用 `paths.lock`；採 non-blocking exclusive lock，取不到 lock 即拒絕（exit `1`）以避免讀到不一致快照。
- **效能上限**：MVP 不提供 streaming output / 進度條 / category filters；中型語料下 read-only lint 預期 < 5s 完成。
- **多 agent 協作 / MCP 暴露**：本 spec 不替 006 / 007 預留設計；lint detail schema 一旦穩定，後續 spec 自然能引用，但本 spec 不為其加保留欄位。
- **Phase 邊界**：影像 ingest（004 ✅）、MCP adapter（006）、多 agent（007）、auto re-ingest 一律延後；本 spec 僅負責「讓 lint 變成可用」。

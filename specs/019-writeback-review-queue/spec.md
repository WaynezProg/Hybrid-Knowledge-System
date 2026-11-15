# 019-writeback-review-queue — Write-back Review Queue 設計

- 日期：2026-05-22
- 狀態：已實作（2026-11-15，於當時的 main 上重新實作；見 §8 實作備註）
- 範圍：HKS write-back 從「query answer 直寫 wiki」改為「review queue → approve → evidence-backed wiki page」；併入 `confidence` 欄位群清理。

## 1. 動機

019 改造前，`ks query --writeback=auto|yes` 會把「query 當 title、answer 當 body」直接寫成 wiki page（`origin=writeback`、`source_relpath=<writeback>`）。對 agent memory 而言這有兩個問題：

1. 一次錯答會沉澱成可被下次 retrieval 取用的知識；`--writeback=yes` 更是無 confidence floor 的強制寫入。
2. 寫進去的是 `(query, answer)` 低保真配對，`source_relpath=<writeback>` 不可溯源，不是 evidence-backed memory object。

此外 query response 的 `confidence` 欄位群語意不一致：`calibrated_confidence` 實際只是 `clamp(raw_score, 0, 1)`，並非真校準，且與 `confidence` 是同一數字兩個名字。

本 spec 將 write-back 改為人工審核佇列，並把 `confidence` 欄位群收乾淨。

## 2. 已定案決策

| # | 決策 |
|---|---|
| Q1 | 所有 write-back 路徑改為 enqueue；`ks query` 永不直寫 wiki，approve 是唯一進 wiki 的路徑 |
| Q2 | approve 產出 evidence-backed wiki page（`source_relpath` 指向真實來源、body 含來源段），不新增第四知識層 |
| Q3 | 新 top-level CLI group `ks writeback`（`list` / `show` / `approve` / `reject`） |
| Q4 | `--writeback` 保留 `auto\|yes\|no\|ask` 四值；效果改為入隊意圖（`no`=不入隊、`auto`=僅通過 route-specific auto eligibility 時入隊、`yes`=有 hit 即送審、`ask`=TTY 問完後採 `yes` 語意、non-TTY=skip） |
| Q5 | 移除 `QueryResponse.calibrated_confidence`，留 `confidence` + `retrieval_score`；`writeback_eligible` 改義為 auto 入隊 eligibility（confidence threshold + evidence/provenance），reviewer 另看 `reasons` 判斷完整度 |
| 儲存 | 方案 A：file-per-item 目錄佇列，沿用 `llm/wiki-candidates/` 範式 |
| Adapter | v1 queue 管理（list/approve/reject）僅 CLI；`hks-api`/`hks-mcp` 的 `/query` 自動沿用（改為 enqueue），不開 writeback queue endpoint |
| 衝突 | approve 時 slug 撞既有頁：`writeback`/`llm_wiki` origin 直接覆寫、`ingest` origin 報衝突錯 |

## 3. 對外契約變更

1. `ks query --writeback=auto|yes` 不再寫 wiki page，改為 enqueue 或 skip 一筆 review item。trace 的 `writeback` step status：`auto-committed`/`forced-committed` → `enqueued`（或 `enqueued-deduped` / `already-promoted` / `skipped-ineligible`）。
2. 新 CLI：`ks writeback list|show <id>|approve <id>|reject <id>`。
3. `QueryResponse`：移除 `calibrated_confidence` 欄位；`writeback_eligible` 改義。
4. `EventStatus` 新增 `enqueued` / `approved` / `rejected`；舊的 writeback 專用 status（`forced-committed`、`auto-committed`、`auto-skipped-ineligible`、`auto-skipped-low-confidence`）保留型別但不再由 writeback 流程發出，避免破壞 `Literal` 契約。
5. `_record_forced_writeback_event`（coordination `forced_writeback` 事件）移除；queue 檔案 + wiki `log.md` 即 audit。
6. 同步更新 `specs/005-phase3-lint-impl/contracts/` JSON schema、adapter OpenAPI schema、README 輸出格式。

## 4. 元件與資料流

### 4.1 儲存佈局

```text
KS_ROOT/writeback/
  queue/<id>.json      # pending 項目
  archive/<id>.json    # approved / rejected 項目（audit，不刪）
```

queue item schema：

```json
{
  "id": "<content-hash>",
  "question": "...",
  "answer": "...",
  "route": "graph",
  "source": ["graph"],
  "evidence": [
    {"source_relpath": "dependency-map.md", "route": "graph", "quote": "..."}
  ],
  "retrieval_score": 0.81,
  "writeback_eligible": true,
  "reasons": ["graph route: all evidence requirements met"],
  "created_at": "2026-05-22T09:00:00Z",
  "status": "pending"
}
```

archive item 在 queue item 基礎上加：`status`（`approved`/`rejected`）、`decided_at`，approved 時加 `slug`。

- **`id`** = `(question, answer, route, normalized_evidence)` 的 content hash，檔名 deterministic，dedup 自動：同內容與同 evidence 重複 enqueue 即同一檔；若同問答但 evidence 改善，產生新 item，避免舊 pending item 吃掉更好的 provenance。
- **併發**：per-item `blocking_file_lock`（`hks/wiki_synthesis/store.py` 既有 helper），multi-agent enqueue 與 reviewer approve 互不阻塞。
- **`reasons`** 由 `assess()` 帶出，讓 reviewer 看到 evidence 完整度判斷依據。

### 4.2 新模組 `hks/writeback/queue.py`

| 函式 | 行為 |
|---|---|
| `enqueue(item)` | 回 `created` / `deduped`（同 id 已在 queue）/ `already-promoted`（同 id 已在 archive 且 `approved`）。`rejected` 不阻擋重新入隊。 |
| `list_pending()` | 掃 `queue/`，依 `created_at` 排序回傳。 |
| `load(id)` | 讀單筆 pending item。 |
| `archive(id, status, slug=None)` | 將 `queue/<id>.json` 移到 `archive/<id>.json`，寫入 `status`、`decided_at`、`slug`。 |

### 4.3 enqueue 流程

- `hks/writeback/gate.py` 簡化：`decide()` 的 action 改為 `enqueue` / `skip` / `skip-non-tty`；`no`→skip、`yes`/`auto`→enqueue intent、`ask`→TTY 問→enqueue|skip、non-TTY→skip-non-tty。`decide()` 不再吃 `confidence`/`auto_threshold`。
- `hks/commands/query.py`：`_maybe_writeback` → `_maybe_enqueue`。enqueue 時用 `QueryResponse` + question 組 item、呼 `queue.enqueue`、加 trace step `{"kind":"writeback","detail":{"status":<status>,"id":...}}`。`auto` 必須再檢查 `writeback_eligible=true`，不合格只加 trace `skipped-ineligible`，不寫 queue；`yes`/TTY-confirmed `ask` 可將 `writeback_eligible=false` 的 hit 送審，但 approve 仍受 evidence hard gate 限制。trace `status` 取 `queue.enqueue` 結果：`created`→`enqueued`、`deduped`→`enqueued-deduped`、`already-promoted`→`already-promoted`。wiki `log.md` 僅在 `created` 時 append 一筆 `enqueued`；dedup / already-promoted / skipped-ineligible 不寫 log（無新事件）。
- `hks/writeback/writer.py` 的 `commit()` 刪除；改放 `promote()`（見 4.4）。

### 4.4 review / promote 流程

新 `hks/commands/writeback.py`（Typer group，於 `hks/cli.py` 註冊）：

| 子指令 | 行為 |
|---|---|
| `list` | 掃 `queue/`，依 `created_at` 排序輸出（id、route、retrieval_score、writeback_eligible、question 截斷）。 |
| `show <id>` | 完整 item（含 evidence、reasons）。 |
| `approve <id>` | load → 檢查 evidence 至少一筆含有效 `source_relpath`（不得為 `<writeback>`）+ `quote` → `promote()` → 寫 evidence-backed wiki page → `archive(id, "approved", slug)`。輸出沿用 `ks wiki synthesize apply` 形態：`answer` 為完成訊息 + slug，附 `trace`。 |
| `reject <id>` | `archive(id, "rejected")`，不寫 wiki。 |

`promote(item)` 產出的 evidence-backed wiki page：

- `title` = question；`body` = answer + `## 來源依據` 段，逐筆列 `- {source_relpath} — "{quote}"`。
- `source_relpath` = 首筆有效 evidence 的真實來源；evidence 為空、缺 `source_relpath`/`quote`、或 `source_relpath="<writeback>"` 時 `approve` 失敗，不允許 fallback `<writeback>`。
- `origin` = `writeback`；frontmatter 加 `writeback_query`（原問句，機器可溯源）。
- 沿用既有 `_build_writeback_context` 的關聯頁連結邏輯（依共享 source_relpath 連到既有 wiki 頁），移到此處。
- append wiki `log.md` 一筆 `approved`。

### 4.5 confidence 欄位變更

- `QueryResponse`：移除 `calibrated_confidence`；保留 `confidence`（= `clamp(raw,0,1)`）、`retrieval_score`（raw）、`writeback_eligible`。`to_dict`/`to_json` 同步。
- `ConfidenceAssessment`：內部欄位 `calibrated_confidence` → `confidence`；`auto_threshold` 可保留為內部判斷與 `reasons` 訊息，不進 `QueryResponse`。
- `hks/retrieval/confidence.py`：保留 route-specific `_AUTO_THRESHOLDS` 作為 `auto` 入隊 gate，但改用 `confidence` 名稱；`writeback_eligible` 必須同時滿足 threshold 與 evidence/provenance 結構檢查，並排除 `source_relpath="<writeback>"`。

## 5. 錯誤處理與邊界

| 情境 | 處理 |
|---|---|
| no-hit（`source=[]`） | 不入隊（沿用 skip-no-source） |
| 同內容重複 enqueue | dedup，trace `enqueued-deduped` |
| id 已在 archive 且 `approved` | 跳過，trace `already-promoted` |
| id 已在 archive 且 `rejected` | 允許重新入隊（reject 是單次，非永久封鎖） |
| `approve`/`reject` 不存在的 id | `KSError` NOINPUT，明確訊息 |
| 兩 reviewer 競爭同 id | file lock；後者見 `queue/<id>.json` 已移除 → 報「已決議」 |
| approve 時 slug 撞 `ingest` 頁 | `KSError` 衝突碼，reviewer 須改走 reject |
| approve 時 slug 撞 `writeback`/`llm_wiki` 頁 | 直接覆寫（同問題重審） |
| `writeback/queue/` 不存在 | `list` 回空，exit 0 |
| hit 但 evidence 為空或只有 `<writeback>` source | `yes`/TTY-confirmed `ask` 可入隊給 reviewer 看，`writeback_eligible=false`；`approve` 失敗並要求 reject 或重跑 query，不產生 `<writeback>` page |

## 6. 測試策略

- **contract tests**：`QueryResponse` 不再有 `calibrated_confidence`；`ks writeback` 四子指令 JSON shape；trace `writeback` step `enqueued` status；approve 不存在 id 的 error payload。
- **unit**：`writeback/queue.py`（enqueue/dedup/already-promoted/list/load/archive + locking）；`promote()` 頁面組裝（來源段、source_relpath、frontmatter、關聯連結）；`gate.decide()` 新 action；`assess()` threshold + evidence/provenance eligibility。
- **integration**：`ks query --writeback=yes` → queue 1 筆且 wiki 未動；`ks writeback approve` → wiki 頁出現含來源段、item 進 archive；`ks query --writeback=no` → 無動作；同 query 跑兩次 → dedup 成 1 筆。
- **既有測試更新**：015 confidence-writeback 測試、http adapter writeback 測試、任何斷言直寫或 `calibrated_confidence` 的測試。
- **golden eval 調整**：eval 的 `writeback_false_positive` 檢查改成「不該 auto 入隊卻入隊」。實作上以 `writeback_eligible` 作主要訊號，並補一個 isolated `writeback=auto` smoke 確認 ineligible case 不產生 queue item。此語意修正收進 019；擴充案例數屬後續 Sub-project B。

## 7. 不在範圍內

- adapter（`hks-api`/`hks-mcp`）的 writeback queue 管理 endpoint —— v1 僅 CLI。
- approve 前編輯 answer —— v1 只有 approve/reject，要改答案請 reject 後重跑 query。
- 真 confidence 校準 —— 目前 golden cases 僅 13 筆，資料量不足以 fit 校準曲線；`confidence` 維持 clamp。
- golden cases 案例數擴充 —— 屬 Sub-project B，019 merge 後進行。

## 8. 實作備註（2026-11-15）

設計定案後 main 又前進了 90 多個 commit，以下幾點以 main 較新的行為為準，與上文不同：

| 項目 | 上文 | 實作 | 依據 |
|---|---|---|---|
| auto 被跳過的 trace status | `skipped-ineligible` | `auto-skipped-ineligible` | 021 的契約測試；§3.4 所列舊 status 中只有這一個仍會發出 |
| auto 被跳過 / `ask` 被拒絕是否寫 `wiki/log.md` | 不寫 | 寫（`auto-skipped-ineligible` / `declined`）；`--writeback=no` 完全不寫 | 021 決策 3、4 |
| per-item lock helper（§4.1） | `hks/wiki_synthesis/store.py` 的 `blocking_file_lock` | `hks.core.lock.blocking_file_lock` | 供 queue 使用的共用 helper |
| approve 寫 wiki 的鎖 | 未規定 | per-item lock → `paths.lock`（`file_lock`，被占用時回 `LOCKED`，item 留在 queue） | PR #26：wiki 寫入與 ingest / lint fix / synthesis apply 共用同一把鎖 |
| queue 管理指令的範圍 | 預設 KS root | 另接受 `-w/--workspace`、`--registry-path`、`--ks-root` | PR #32 workspace-scoped 指令 |
| approve 的 evidence hard gate | 有效 `source_relpath` + `quote` | 另要求來源仍在 manifest 且 `raw_sources/` 檔案存在 | 5 月分支 review 修正（18148be） |
| 不存在的 id 與已決議的 id | 同為 NOINPUT | 同為 NOINPUT（exit 66），已決議的訊息為「已決議（approved\|rejected）」 | §5「報已決議」 |
| `retrieval_score` schema | — | 005 schema 取消 `[0,1]` 上下限（raw score）；`confidence` 仍限 `[0,1]` | tasks T002 |

沒有答案的查詢（包含被 026 vector evidence gate 判為 `weak_evidence` 的答案）`source=[]`，任何 `--writeback` 模式都不入隊。

Review 後補上的行為（上文未涵蓋）：

| 項目 | 行為 |
|---|---|
| 答案來自 writeback 頁 | wiki route 的答案若是從 `origin=writeback` 的頁面讀出（evidence 的 quote 就是該頁摘要），不入隊。該頁的 `writeback_query` 與問句相同時 trace 為 `already-promoted`，否則為 `skipped-derived-answer`；兩者的 `detail` 都帶該頁的 `slug` / `path` / `source_relpath`，不寫 log。以 id 判斷的 `already-promoted`（§4.2）不變。`--writeback=no` 不做這項檢查；`auto` 在 wiki route 本來就是 `auto-skipped-ineligible`。 |
| approve 的 evidence | 引用 writeback 頁摘要的 wiki evidence 不算有效 evidence。Item 只有這種 evidence 時 approve 回 `WRITEBACK_EVIDENCE_REQUIRED`；同時有真實來源段落時只採用後者。 |
| 頁面內文 | answer 行首的 heading 標記（`#`…`######`、setext 的 `===` / `---` 底線）在寫入 body 與 `summary` 前移除，文字不變；頁面只有 `# <question>` 一個 H1。引文一律單行。 |
| archive 紀錄 | 被 reject 的 item 重新入隊並再次決議時，新的 archive 紀錄取代 `archive/<id>.json`，先前的決議依序放在紀錄的 `history`（`status`、`decided_at`、`slug`、`created_at`）；沒有先前決議時不輸出 `history`。檔名仍只有 `<id>.json`。 |
| source 被移除 | ingest 刪除某個 source 的 artifacts（`--prune`，或重新 ingest 後內容為空）時，一併刪除 `origin=writeback` 且 `source` 為該 relpath 的 wiki pages，並列在 `ingest_summary.detail.pruned_writeback_pages`（004 ingest detail schema 新增的 optional 欄位）。`ingest` / `llm_wiki` 頁不受影響；queue 與 archive 紀錄保留。 |
| lint | 既有的 `wiki_source_mismatch`（頁面指向不在 manifest 的 source）原本只檢查 `origin=ingest`，現在也檢查 `origin=writeback`；019 之前寫入、`source` 為 `<writeback>` 的舊頁不檢查。 |

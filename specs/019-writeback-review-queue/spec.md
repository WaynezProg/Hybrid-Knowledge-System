# 019-writeback-review-queue — Write-back Review Queue 設計

- 日期：2026-05-22
- 狀態：設計通過，待轉 implementation plan
- 範圍：HKS write-back 從「query answer 直寫 wiki」改為「review queue → approve → evidence-backed wiki page」；併入 `confidence` 欄位群清理。

## 1. 動機

現況 `ks query --writeback=auto|yes` 會把「query 當 title、answer 當 body」直接寫成 wiki page（`origin=writeback`、`source_relpath=<writeback>`）。對 agent memory 而言這有兩個問題：

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
| Q4 | `--writeback` 保留 `auto\|yes\|no\|ask` 四值；效果改為入隊（`no`=不入隊、`yes`/`auto`=入隊、`ask`=TTY 問完入隊、non-TTY=skip） |
| Q5 | 移除 `QueryResponse.calibrated_confidence`，留 `confidence` + `retrieval_score`；`writeback_eligible` 改義為 reviewer 的 evidence 完整度提示 |
| 儲存 | 方案 A：file-per-item 目錄佇列，沿用 `llm/wiki-candidates/` 範式 |
| Adapter | v1 queue 管理（list/approve/reject）僅 CLI；`hks-api`/`hks-mcp` 的 `/query` 自動沿用（改為 enqueue），不開 writeback queue endpoint |
| 衝突 | approve 時 slug 撞既有頁：`writeback`/`llm_wiki` origin 直接覆寫、`ingest` origin 報衝突錯 |

## 3. 對外契約變更

1. `ks query --writeback=auto|yes` 不再寫 wiki page，改為 enqueue 一筆 review item。trace 的 `writeback` step status：`auto-committed`/`forced-committed` → `enqueued`（或 `enqueued-deduped` / `already-promoted`）。
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

- **`id`** = `(question, answer, route)` 的 content hash，檔名 deterministic，dedup 自動：同內容重複 enqueue 即同一檔。
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

- `hks/writeback/gate.py` 簡化：`decide()` 的 action 改為 `enqueue` / `skip` / `skip-non-tty`；`no`→skip、`yes`/`auto`→enqueue、`ask`→TTY 問→enqueue|skip、non-TTY→skip-non-tty。`decide()` 不再吃 `assessment`/`confidence`/`auto_threshold`。
- `hks/commands/query.py`：`_maybe_writeback` → `_maybe_enqueue`。enqueue 時用 `QueryResponse` + question 組 item、呼 `queue.enqueue`、加 trace step `{"kind":"writeback","detail":{"status":<status>,"id":...}}`。trace `status` 取 `queue.enqueue` 結果：`created`→`enqueued`、`deduped`→`enqueued-deduped`、`already-promoted`→`already-promoted`。wiki `log.md` 僅在 `created` 時 append 一筆 `enqueued`；dedup / already-promoted 不寫 log（無新事件）。
- `hks/writeback/writer.py` 的 `commit()` 刪除；改放 `promote()`（見 4.4）。

### 4.4 review / promote 流程

新 `hks/commands/writeback.py`（Typer group，於 `hks/cli.py` 註冊）：

| 子指令 | 行為 |
|---|---|
| `list` | 掃 `queue/`，依 `created_at` 排序輸出（id、route、retrieval_score、writeback_eligible、question 截斷）。 |
| `show <id>` | 完整 item（含 evidence、reasons）。 |
| `approve <id>` | load → `promote()` → 寫 evidence-backed wiki page → `archive(id, "approved", slug)`。輸出沿用 `ks wiki synthesize apply` 形態：`answer` 為完成訊息 + slug，附 `trace`。 |
| `reject <id>` | `archive(id, "rejected")`，不寫 wiki。 |

`promote(item)` 產出的 evidence-backed wiki page：

- `title` = question；`body` = answer + `## 來源依據` 段，逐筆列 `- {source_relpath} — "{quote}"`。
- `source_relpath` = 首筆 evidence 的真實來源；evidence 為空才 fallback `<writeback>`。
- `origin` = `writeback`；frontmatter 加 `writeback_query`（原問句，機器可溯源）。
- 沿用既有 `_build_writeback_context` 的關聯頁連結邏輯（依共享 source_relpath 連到既有 wiki 頁），移到此處。
- append wiki `log.md` 一筆 `approved`。

### 4.5 confidence 欄位變更

- `QueryResponse`：移除 `calibrated_confidence`；保留 `confidence`（= `clamp(raw,0,1)`）、`retrieval_score`（raw）、`writeback_eligible`。`to_dict`/`to_json` 同步。
- `ConfidenceAssessment`：內部欄位 `calibrated_confidence` → `confidence`；移除 `auto_threshold`。
- `hks/retrieval/confidence.py`：移除 `_AUTO_THRESHOLDS` dict；`assess()` 的 `writeback_eligible` 只由 evidence 結構檢查決定，移除 `calibrated < threshold` → ineligible 判斷。

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
| hit 但 evidence 為空 | 仍可 approve，`source_relpath` fallback `<writeback>`、`writeback_eligible=false` |

## 6. 測試策略

- **contract tests**：`QueryResponse` 不再有 `calibrated_confidence`；`ks writeback` 四子指令 JSON shape；trace `writeback` step `enqueued` status；approve 不存在 id 的 error payload。
- **unit**：`writeback/queue.py`（enqueue/dedup/already-promoted/list/load/archive + locking）；`promote()` 頁面組裝（來源段、source_relpath、frontmatter、關聯連結）；`gate.decide()` 新 action；`assess()` evidence-only eligibility。
- **integration**：`ks query --writeback=yes` → queue 1 筆且 wiki 未動；`ks writeback approve` → wiki 頁出現含來源段、item 進 archive；`ks query --writeback=no` → 無動作；同 query 跑兩次 → dedup 成 1 筆。
- **既有測試更新**：015 confidence-writeback 測試、http adapter writeback 測試、任何斷言直寫或 `calibrated_confidence` 的測試。
- **golden eval 調整**：eval 的 `writeback_false_positive` 檢查原本是「不該寫卻寫了」，新模型 query 永不寫，須改為「不該入隊卻入隊」。此語意修正收進 Spec A（不改 eval 會壞）；擴充案例數屬後續 Sub-project B。

## 7. 不在範圍內

- adapter（`hks-api`/`hks-mcp`）的 writeback queue 管理 endpoint —— v1 僅 CLI。
- approve 前編輯 answer —— v1 只有 approve/reject，要改答案請 reject 後重跑 query。
- 真 confidence 校準 —— 目前 golden cases 僅 13 筆，資料量不足以 fit 校準曲線；`confidence` 維持 clamp。
- golden cases 案例數擴充 —— 屬 Sub-project B，Spec A merge 後進行。

# 021-writeback-no-skips-log — `--writeback=no` 的查詢不寫 `wiki/log.md`

- 日期：2026-11-14
- 狀態：已實作
- 範圍：`ks query --writeback=no`（亦即預設）不再在 `wiki/log.md` 追加紀錄；write-back 的結果只出現在 response 的 trace。

## 1. 動機

`--writeback=no` 的語意是「這次查詢不要寫東西」，但原本每一次有答案的查詢都會在 `wiki/log.md` 追加一筆 `writeback | declined`。在一份真實的 `KS_ROOT` 上以 `--writeback=no` 查詢 6 題後，`wiki/log.md` 多了對應的紀錄。這造成兩個問題：

- 以唯讀目的查詢（檢查、評測、agent 反覆試問）會改動知識庫內容，`log.md` 被查詢紀錄灌滿。
- 呼叫端無法從 flag 判斷一次查詢會不會寫檔。

## 2. 決策

| # | 決策 |
|---|---|
| 1 | `--writeback=no`（含未帶 flag 的預設值）不呼叫 `append_log`，`wiki/log.md` 不變 |
| 2 | Trace 不變：最後一個 step 仍是 `writeback`，`detail.status` 仍為 `declined`；沒有答案時仍為 `skip-no-source` |
| 3 | `--writeback=ask` 被使用者拒絕（`declined`）仍寫 log：那是一次實際做出的決定 |
| 4 | `--writeback=auto` 被跳過（`auto-skipped-ineligible`、`auto-skipped-low-confidence`）仍寫 log：用來回頭檢查 auto gate 為什麼沒寫 |
| 5 | `--writeback=yes` 與 commit 路徑不變 |

判斷依據是呼叫端傳入的 flag，不是 decision 的 status：`no` 與「`ask` 被拒絕」的 status 同為 `declined`，但只有前者不寫 log。

## 3. 契約變更

- Response schema、route 名稱、trace step 的 kind 與 `detail` 欄位都沒有變。
- 行為變更：`--writeback=no` 的查詢不再於 `wiki/log.md` 產生 `writeback | declined` 紀錄。依賴該紀錄統計「查過哪些問題」的用法會失效；需要查詢紀錄時改讀 response 的 trace，或使用 `--writeback=auto`。
- MCP 與 HTTP 的 query 入口走同一個函式，行為一併改變。

## 4. 驗證

`tests/contract/test_writeback_no_log_contract.py`：

- `--writeback=no` 與未帶 flag：查詢前後 `wiki/log.md` 逐 byte 相同，trace 的 writeback step 為 `{"status": "declined"}`。
- 沒有答案的查詢：`wiki/log.md` 不變，writeback step 為 `{"status": "skip-no-source"}`。
- `--writeback=auto` 在 wiki route 被跳過：`wiki/log.md` 新增 `writeback | auto-skipped-ineligible`。
- `--writeback=ask` 被拒絕：`wiki/log.md` 新增 `writeback | declined`。

移除實作後，前兩項（`--writeback=no` 與預設）的測試會失敗。

## 5. 不在範圍內

- `--writeback=no` 的查詢仍不是完全唯讀：Chroma 在開啟 vector db 時會改動 `vector/db/` 下的檔案（實測查詢前後 `chroma.sqlite3` 與 `data_level0.bin` 的內容不同，embedding 筆數相同）。要讓查詢對 `KS_ROOT` 完全不寫入，需要另外以唯讀方式開啟 vector store，本次不處理。
- 既有 `wiki/log.md` 中已存在的 `declined` 紀錄不清除。

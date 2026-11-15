# 031-session-memory-date-topic — 有日期的 session-memory 問句依主題篩選，設定可由 user 層載入

- 日期：2026-11-15
- 狀態：已實作
- 範圍：`ks query` 對 session-memory 日期問句的篩選、wiki 候選在「只共用意圖詞」時的處理、設定檔的搜尋位置、Graphify latest pointer 的路徑寫法。

## 1. 動機

- 有日期又有主題的問句（「2026-11-14 session2memory 做了哪些修改？」）原本回傳當天全部條目，主題沒有作用；當天沒有該主題時也照樣回傳整天內容。
- 一般文件庫裡帶日期的問句（「2026-11-14 Atlas ERR-4012」）被當成 session-memory 查詢。
- 「summary Atlas」會挑到完全沒提 Atlas 的「architecture summary」頁。
- 安裝後的 `ks` 從 repo 以外的目錄執行時讀不到 repo 的 `config/`。
- Graphify 的 latest pointer 記的是絕對路徑，搬移 `KS_ROOT` 後 lint 回報 run manifest 遺失。

## 2. 決策

| # | 決策 |
|---|---|
| 1 | 日期問句扣掉日期、workspace 與問法用語後剩下的文字是主題（`SessionMemoryIntent.topic`，`wiki_lookup` 的 `intent` detail 會帶 `topic`） |
| 2 | 主題含名稱（以拉丁字母或數字寫的詞、編號：`session2memory`、`OpenCode`、`ERR-4012`）時是硬性條件：條目只留下含該名稱的行；沒有任何條目提到它時回 no-hit，`fallback` step 的 `reason` 為 `session_memory_no_match`。名稱旁邊的用語（「Paperclip 新增了哪些東西」）不必出現在條目中 |
| 3 | 主題不含名稱時：有條目含這些詞（「索引」）就依它篩選；沒有任何條目含這些詞（「工作」「有哪些決定」「主要成果是」）時視為問法用語，不篩選，照舊回傳該日期的內容。剩下單一個字（「有」）不算主題 |
| 4 | 知識庫中沒有任何 session-memory 來源時，帶日期的問句不走 session-memory 路徑 |
| 5 | wiki 候選：問句去掉意圖詞後的主題詞完全不在頁面中時，relevance 為 0，不再因為頁面含 `summary` 而加分；此時改從含主題詞的頁面中重新挑選 |
| 6 | 設定檔：`HKS_CONFIG_FILE` / `HKS_CONFIG_ENV` 明確指定時用指定的；否則 repo 的 `config/` 有設定檔就用它，沒有才用 `${XDG_CONFIG_HOME:-~/.config}/hks/`。兩處不逐欄混合。user 層設定是指向 repo `config/` 的 symlink 時，`${HKS_REPO_ROOT}` 依該 repo 展開 |
| 7 | Graphify latest pointer 的 `run_manifest_path` 改記相對於 `KS_ROOT` 的路徑；lint 同時接受舊的絕對路徑 |

決策 3 是 review 時補上的。初版把剩下的文字一律當成硬性條件，「2026-11-14 的工作摘要」「2026-11-14 有哪些決定」「11/12-11/14 之間完成了哪些工作」這類問句因此從回傳當天內容變成 no-hit。

## 3. 契約變更

- `wiki_lookup`（session_memory mode）的 `intent` detail 新增選填的 `topic`。
- `fallback` step 新增 `reason: session_memory_no_match`。
- Graphify `latest.json` 的 `run_manifest_path` 由絕對路徑改為相對路徑。

## 4. 驗證

- `tests/integration/test_session_memory_topic.py`：主題篩選、名稱不存在時 no-hit、日期區間、只有日期時回傳整天、一般文件庫不受影響；以及決策 3 的問句（單日與日期區間）與名稱旁帶其他用語的情況。
- `tests/unit/core/test_runtime_config.py`、`tests/integration/test_user_config_adapters.py`：設定檔搜尋位置。
- `tests/integration/test_graphify_lint.py`：搬移 `KS_ROOT` 後 lint 通過。
- `tests/contract/test_wiki_relevance_contract.py`：決策 5。

## 5. 不在範圍內

- 不含名稱的主題在當天沒有對應條目時（「2026-11-14 購物車做了哪些修改」而當天沒有購物車的條目），回傳整天內容而不是 no-hit：無法區分它是主題還是問法用語。
- 主題是以問法用語清單相減得出的，清單沒列到的用語會留在主題裡；決策 3 讓這種情況不影響結果。
- 「2026-11-14 Paperclip 進度」這類帶狀態詞的問句會把單一英文詞當成 workspace，沒有名為該詞的 workspace 時回 no-hit；這是既有的 workspace 判斷，這次沒有改。

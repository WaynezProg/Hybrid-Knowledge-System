# 024-wiki-relevance-score — wiki 候選的分數隨頁面與問句的吻合程度變動

- 日期：2026-11-14
- 狀態：已實作
- 範圍：`ks query` 的 wiki route 候選如何給分，以及吻合太少的頁面不成為候選。

## 1. 動機

Wiki 候選的 score 是寫死的：router 選 wiki 為主要 route 時 1.0，否則 0.65，與頁面內容無關。各 route 的第一名在 RRF 中同分，再以 score 分高下，所以 wiki 候選一出現幾乎必勝。

頁面搜尋（`WikiStore.search`）以子字串比對問句的詞。在一份真實 `KS_ROOT` 上：

| 問句 | 原本的答案 | 實際情況 |
|---|---|---|
| `agent security and capability testing framework 做了什麼？` | `Memory Candidate: No candidates.`，confidence 1.0 | 問句的 `and` 是 `Candidate` 的子字串；vector route 已找到正確文件（0.74）卻被蓋過 |
| `OpenClaw 10.1 蛇魔更新的重點` | 另一天的頁面，confidence 1.0 | vector route 找到正確文件（0.89）卻被蓋過 |

## 2. 決策

| # | 決策 |
|---|---|
| 1 | 對搜尋到的頁面計算 relevance：問句的詞（ASCII 詞與 CJK bigram，整詞比對）以 idf 加權後被頁面（title、slug、summary、body）涵蓋的比例，idf 以全部 wiki 頁面計算 |
| 2 | 只表示想要哪種答案的詞（`summary`、`overview`、`摘要`、`總結`、`重點`、`說明`）不必出現在頁面中：relevance 取「含這些詞」與「去掉這些詞」兩種算法中較高者 |
| 3 | relevance < 0.15 的頁面不成為候選。`wiki_lookup` step 記 `hit: false`、`reason: low-relevance`、`slug`、`relevance` |
| 4 | 其餘頁面的 score = base ×（0.7 + 0.3 × relevance），base 仍是 1.0（主要 route）或 0.65 |
| 5 | Overview 候選（0.7）、session memory 候選、write-back 資格都不變 |

底分取 0.7：wiki 頁面是整理過的摘要，router 選了 wiki 且頁面確實相關時仍應優先；較低的底分會讓 `simple` embedding 的雜訊分數（0.5–0.6）蓋過正確的 wiki 答案。

## 3. 契約變更

- Response schema、route 名稱、trace step 的 kind 沒有變。
- `wiki_lookup` step 的 `detail` 新增 `relevance`（命中與 `low-relevance` 時都有）；新增一種未命中的 `reason`：`low-relevance`，並附 `slug`。
- 行為變更：wiki route 作答時 `confidence` 不再固定為 1.0 或 0.65，而是落在 0.7–1.0（主要 route）或 0.455–0.65。問句的詞全部在頁面中時仍是 1.0／0.65。依賴固定數值的下游需要調整。

## 4. 驗證

測試：

- `tests/contract/test_wiki_relevance_contract.py`：relevance 的計算、score 與 relevance 的關係、`low-relevance` 的 trace、經 `ks query` 的一個子字串誤中案例。最後一項以原本的程式執行時失敗。
- `tests/integration/test_query_flows.py::test_query_summary_uses_wiki`：原本斷言 `confidence == 1.0`，改為斷言它等於 `0.7 + 0.3 × relevance`。
- 其餘既有測試（含 `tests/eval/test_golden_retrieval_quality.py`）不需修改即通過。

`evals/hybrid_modes.py`（`simple` embedding，240 份文件 × 3 seed）每一格與變更前相同。這份評測的問題多由 vector／lexical route 作答，對這項變更不敏感。

真實資料（session-memory `KS_ROOT` 複本，197 份 daily md，`simple` embedding，`--writeback=no`）：

| 問句 | 變更前 | 變更後 |
|---|---|---|
| `agent security and capability testing framework 做了什麼？` | `wiki`，1.0，`No candidates.` | `vector`，0.50，正確文件（wiki relevance 0.0） |
| `OpenClaw 10.1 蛇魔更新的重點` | `wiki`，1.0，另一天的頁面 | `vector`，0.65，正確文件（wiki relevance 0.126） |
| `VID-236` | `wiki`，1.0，正確頁面 | 相同（relevance 1.0） |
| `2026-10-12 做了什麼？` | `wiki`，1.0（session memory 路徑） | 相同 |
| `session2memory reconcile 步驟做了哪些事？` | `wiki`，1.0，一頁只提到 session2memory 的 daily | no-hit（wiki relevance 0.081；知識庫中沒有 reconcile 的內容） |

## 5. 已知限制

- 頁面搜尋本身仍是子字串比對，這次只在搜尋之後擋掉誤中的頁面；搜尋若因此選錯頁，正確的頁面不會被補上。
- 換句話說的問句與頁面用詞不同時 relevance 偏低，score 會落在底分附近；低於 0.15 時該頁不成為候選。
- 0.15 與 0.7 是依一份真實知識庫與既有測試訂的，沒有在其他語料上調過。
- 沒有在 OpenAI embedding 的 `KS_ROOT` 上驗證。
- 空內容的頁面（`No candidates.`）來自上游 export，這次沒有在 ingest 時排除。

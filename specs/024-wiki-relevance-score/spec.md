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
| 2 | 只表示想要哪種答案的詞不必出現在頁面中：relevance 取「含這些詞」與「去掉這些詞」兩種算法中較高者。這些詞是 `summary`、`overview`、`摘要`、`總結`、`重點`、`說明`，加上 routing rules 中導向 wiki route 的關鍵詞（`summarize`、`概述` 等）。ASCII 的詞只在是完整的詞時去掉，`SummaryStore` 裡的 `summary` 不算 |
| 3 | 問句去掉這些詞後沒有可比對的詞（單一個字，或只有 `overview`）時不計算 relevance：沒有依據說頁面不相關，候選與分數維持原樣，`wiki_lookup` step 不帶 `relevance` |
| 4 | relevance 為 0（問句沒有任何一個詞在頁面中）的頁面不成為候選。`wiki_lookup` step 記 `hit: false`、`reason: low-relevance`、`slug`、`relevance` |
| 5 | 其餘頁面的 score = base ×（0.7 + 0.3 × relevance），base 仍是 1.0（主要 route）或 0.65 |
| 6 | Overview 候選（0.7）、session memory 候選、write-back 資格都不變 |
| 7 | 一次查詢只讀一次 wiki 頁面（`WikiStore.search` 可接收已讀入的頁面），每頁只斷詞一次 |

底分取 0.7：wiki 頁面是整理過的摘要，router 選了 wiki 且頁面確實相關時仍應優先；較低的底分會讓 `simple` embedding 的雜訊分數（0.5–0.6）蓋過正確的 wiki 答案。

只擋 relevance 為 0 的頁面，是因為 relevance 在小型知識庫或問句用詞與頁面不同時會很低：只有一頁「Atlas: Owner: Alice.」時問「Who owns Atlas?」，relevance 只有 0.094，但那一頁就是答案。吻合少的頁面交給分數去比，不直接排除。

## 3. 契約變更

- Response schema、route 名稱、trace step 的 kind 沒有變。
- `wiki_lookup` step 的 `detail` 新增 `relevance`（命中與 `low-relevance` 時都有）；新增一種未命中的 `reason`：`low-relevance`，並附 `slug`。
- 行為變更：wiki route 作答時 `confidence` 不再固定為 1.0 或 0.65，而是落在 0.7–1.0（主要 route）或 0.455–0.65。問句的詞全部在頁面中、或問句沒有可比對的詞時仍是 1.0／0.65。依賴固定數值的下游需要調整。
- `WikiStore.search` 新增選用參數 `pages`。

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
| `OpenClaw 10.1 蛇魔更新的重點` | `wiki`，1.0，另一天的頁面 | `vector`，0.65，正確文件（wiki 候選 relevance 0.126、score 0.74，低於 vector 的 0.89） |
| `VID-236` | `wiki`，1.0，正確頁面 | 相同（relevance 1.0） |
| `2026-10-12 做了什麼？` | `wiki`，1.0（session memory 路徑） | 相同 |
| `session2memory reconcile 步驟做了哪些事？` | `wiki`，1.0，一頁只提到 session2memory 的 daily | 同一頁，confidence 降為 0.72（relevance 0.081；知識庫中沒有 reconcile 的內容） |

### 4.1 Review 後的修正

Codex review 指出初版（relevance < 0.15 即排除、以子字串去掉意圖詞）的四個問題，都已修正並各有測試：

| 問題 | 反例 | 修正 |
|---|---|---|
| 門檻會丟掉正確的頁面 | 唯一頁面「Atlas: Owner: Alice.」，問「Who owns Atlas?」；只問「overview」；問「火 摘要」 | 決策 3、4 |
| 去掉意圖詞時改到名稱 | 問「summary SummaryStore」，不相關的 Store 頁 relevance 變成 1.0 | 決策 2 |
| 意圖詞清單與 router 不一致 | 「summarize Atlas」「Atlas 概述」的分數低於「summary Atlas」 | 決策 2 |
| 每次查詢重複讀取並斷詞全部頁面 | 3000 頁時 wiki retrieval 由 0.10 秒升到 1.59 秒 | 決策 7 |

修正後沒有重新量測 3000 頁的耗時；每次查詢仍會對全部頁面斷詞一次，沒有做跨查詢的快取。

### 4.2 OpenAI embedding 的知識庫

`.hks-runs/openai/ks` 的複本（`openai:text-embedding-3-small`，24 個 wiki 頁；vector collection 只有 144 個 daily chunk，wiki 頁的來源文件不在其中），14 個問題，`--writeback=no`，變更前 → 後：

| 問題 | 變更前 | 變更後 |
|---|---|---|
| 頁面主題吻合的 6 題（`Project Atlas 目前的狀態是什麼？`、`project borealis 摘要`、`Risk Register 列了哪些風險？`、`Clause 3.2 規定什麼？`、`Spec Alpha 的目標是什麼？`、`meeting notes 的重點`） | `wiki`，1.0 或 0.65，正確頁面 | 同一頁；confidence 0.49–1.0 |
| `誰是 Mobile Gateway 的 owner？` | `wiki` 1.0，`atlas-dependency`（內含 Owner Iris） | `graph` 0.99，列出關係但答案開頭沒有 owner（wiki 0.87，relevance 0.574） |
| `plain text export format 怎麼設定？`（知識庫中沒有） | `wiki` 0.65，`plain` 頁 | 同一頁，0.48（relevance 0.112） |
| `What is the vacation policy for contractors?`（知識庫中沒有） | `wiki` 0.65，`Field Visit` 頁 | 同一頁，0.47（relevance 0.089） |
| `Atlas-10 的風險是什麼？` | `wiki` 1.0，`atlas-dependency`（不含 Atlas-10） | 同一頁，0.71（relevance 0.044） |
| 其餘 4 題（`graph`、`vector` 作答或 no-hit） | — | 相同 |

觀察：

- 正確頁面沒有被擋掉，作答的 route 只有一題改變。
- 那一題是退步：wiki 的分數不再固定為 1.0 之後，低於 graph 固定的 0.99，原本較直接的 wiki 答案輸給 graph。
- 知識庫中沒有答案的兩題仍以誤中的頁面作答，只是 confidence 降低；vector 最高相似度 0.37 與 0.20，沒有更好的候選。
- 這份知識庫上正確頁面的 relevance 最低為 0.19，誤中頁面最高為 0.11。只有 5 個資料點，沒有據此提高門檻。

## 5. 已知限制

- 頁面搜尋本身仍是子字串比對，這次只在搜尋之後擋掉誤中的頁面；搜尋若因此選錯頁，正確的頁面不會被補上。
- 換句話說的問句與頁面用詞不同時 relevance 偏低，score 會落在底分附近，可能輸給分數較高的 vector 候選。
- 只吻合少數詞的誤中頁面（relevance 大於 0）仍是候選，靠分數與其他 route 比較；其他 route 沒有更好的候選時仍會以它作答。
- 0.7 是依一份真實知識庫與既有測試訂的，沒有在其他語料上調過。
- wiki 分數低於 graph 固定的 0.99 時，原本由 wiki 作答的問題會改由 graph 作答（§4.2 有一例退步）。
- 空內容的頁面（`No candidates.`）來自上游 export，這次沒有在 ingest 時排除。

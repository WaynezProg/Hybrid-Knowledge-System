# 026-vector-evidence-gate — vector 答案要有它與問句相關的證據

- 日期：2026-11-14
- 狀態：已實作
- 範圍：`ks query` 在 `route` 模式（預設）下，vector 答案通過 final score gate 之後多一項檢查。

## 1. 動機

Embedding 檢索永遠會回傳最接近的 chunk，知識庫裡完全沒有相關內容時也一樣。Final score gate（vector 0.25，router 選 vector 為主要 route 時 0.2）是相似度的單一門檻，分不開「語意相近但用詞不同的正確答案」與「只是最近的一個無關 chunk」。020 §4.6 已記錄這個限制。

以 `openai:text-embedding-3-small` 跑擴充題組（240 份文件 × 3 seed，`route` 模式），逐題記錄作答的 vector 候選：

| | 題數 | vector similarity | query coverage |
|---|---|---|---|
| 無答案題被誤答 | 5 | 0.20–0.25 | 0–0.009 |
| paraphrase 題答錯、coverage 為 0 者 | 6 | 0.25–0.40 | 0 |
| paraphrase 題答對（內容與問句沒有共用詞） | 4 | 0.39–0.51 | 0–0.001 |
| 其餘由 vector 答對、coverage 低於 0.35 者 | 10 | 0.296–0.37 | 0.17–0.25 |

Query coverage 是問句詞彙以 idf 加權後被該 chunk 涵蓋的比例（020 的 lexical route 已在用）。單看相似度，無答案題的誤答（最高 0.25）與正確答案（最低 0.296）只差不到 0.05，而 paraphrase 的錯誤答案與正確答案更是重疊；加上 coverage 之後，「相似度低、而且內容幾乎不含問句的任何罕見詞」這個組合只出現在答錯的題目上。

## 2. 決策

| # | 決策 |
|---|---|
| 1 | Vector 候選勝出並通過 final score gate 之後，若它的 vector similarity 低於 0.30 **而且** query coverage 低於 0.05，回 no-hit |
| 2 | 兩個條件要同時成立。相似度夠高的答案不看 coverage（paraphrase 的正確答案與問句沒有共用詞）；coverage 夠高的答案不看相似度（內容逐字含有問句的罕見詞） |
| 3 | 先過 final score gate 再做這項檢查，原本就被 gate 擋下的答案 `reason` 不變 |
| 4 | Coverage 由 lexical retriever 在讀出全部 chunk 時順便算出，記在 vector 候選的 metadata（`query_coverage`）。沒有量到 coverage 的情況（`HKS_HYBRID_SEARCH=fused`／`off`，或 chunk 數超過 `HKS_HYBRID_MAX_CHUNKS`）不做這項檢查，行為與之前相同 |
| 5 | 只檢查 vector route 的答案；wiki、graph、lexical、page_tree 各有自己的判定 |

0.30 與 0.05 取在 §1 兩群之間：誤答的相似度最高 0.25、coverage 最高 0.009；被保留的正確答案中，coverage 低於 0.05 的相似度最低 0.39，相似度低於 0.30 的 coverage 最低 0.236。

## 3. 契約變更（additive）

- `fallback` step 的 `reason` 新增 `weak_evidence`，並附 `route`、`vector_similarity`、`query_coverage`、`thresholds`（`{"vector_similarity": 0.3, "query_coverage": 0.05}`）。
- vector candidate metadata 新增 `query_coverage`（不出現在 response 的 `evidence[]`）。
- 行為變更：部分原本由 vector route 以低分作答的問題改回 no-hit（`source=[]`、`confidence=0.0`，exit code 仍為 0）。

## 4. 驗證

擴充題組，`route` 模式，變更前 → 後。沒有列出的格子（identifier、keyword、code-in-sentence、code-spelling、short-code、name-with-digit、no-answer-code 的 answer@1 與 recall@5，以及 `off`、`fused` 兩個模式的全部格子）與變更前相同。

| 指標 | `simple` | `openai:text-embedding-3-small` |
|---|---|---|
| no-answer 正確回 no-hit | 7/12 → 9/12 | 7/12 → 12/12 |
| paraphrase answer@1 | 0/15 → 0/15 | 4/15 → 4/15 |
| 有答案的題目答對數（102 題） | — | 88 → 88 |
| 有答案的題目中給出錯誤答案的題數 | — | 14 → 11 |

OpenAI 逐題比對：126 題中 8 題改變，全部是原本答錯的題目改回 no-hit（5 題無答案題、3 題 paraphrase）；沒有任何一題從答對變成 no-hit。

真實資料（session-memory `KS_ROOT`，198 份 daily，`openai:text-embedding-3-small`，`--writeback=no`）：

| 問句 | 變更前 | 變更後 |
|---|---|---|
| `VID-236 的畫面是用來決定什麼？` 等 6 個有答案的問題 | 作答 | 相同（作答的 route、文件、confidence 都沒變） |
| `火星殖民地的預算是多少？` | 未量測；similarity 0.256 高於原門檻 | no-hit，`weak_evidence`（0.256／0.0） |
| `How do I reset my router password?` | 未量測；similarity 0.266 高於原門檻 | no-hit，`weak_evidence`（0.266／0.0） |
| `量子電腦採購計畫` | `vector`，0.471，內容為「電腦資料整理」 | 相同（見 §5） |

預設 embedding model（`paraphrase-multilingual-MiniLM-L12-v2`）沒有重跑評測。依 020 §4.6，它的誤答相似度約 0.33–0.35，高於 0.30，這項檢查對它預期沒有作用。

## 5. 已知限制

- 相似度高的誤答擋不住：`量子電腦採購計畫` 對上只寫「電腦資料整理」的短 chunk，similarity 0.47，高於任何合理的門檻。短 chunk 與短問句共用一個詞就會有這種相似度。這類情況仍需要 LLM reranker 或 answerability 判斷。
- 0.30 是相似度的絕對值，各 embedding model 的分布不同。這裡依 `openai:text-embedding-3-small` 訂定；換 model 時應以 §1 的方式重新量測。
- 門檻依一份合成評測與一份真實知識庫訂定，樣本少（誤答 5 題、相鄰的正確答案 4 題）。
- `fused` 與 `off` 模式沒有這項檢查。

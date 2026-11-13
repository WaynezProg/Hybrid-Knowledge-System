# 020-hybrid-lexical-retrieval — vector route 的 hybrid 檢索

- 日期：2026-11-13
- 狀態：已實作
- 範圍：`ks query` 在 dense 檢索之外加入 BM25 keyword 檢索；預設以獨立的 `lexical` route 提供（`route` 模式），另保留併入 vector route 的 `fused` 模式。

## 1. 動機

原本 vector candidates 只取 embedding 相似度前 5 筆，lexical overlap 只對這些已撈到的 chunk 加分。Embedding 排不到前面的精確詞（名稱、ID、錯誤碼、檔名）即使 chunk 內逐字出現，也進不了候選。

## 2. 決策

| # | 決策 |
|---|---|
| 1 | 預設模式為 `route`：embedding 沒帶出的 keyword 命中以新的 `lexical` route 回傳；vector route 的排序、分數、final score gate、write-back threshold 都不變 |
| 2 | BM25 在 query 時對 vector store 的所有 chunk 即時計算，不新增落地索引，既有 `KS_ROOT` 不需 re-ingest，ingest / lint / manifest 不受影響 |
| 3 | Tokenization 沿用 `lexical_terms` 的單位：ASCII 詞（長度 ≥ 2）與 CJK bigram |
| 4 | `fused` 模式：dense 排名（至多 50 筆）與 BM25 排名（前 20 筆）以 RRF（k=60）融合，取前 5 筆為 vector candidates |
| 5 | Candidate score 公式不變（similarity + lexical overlap bonus）。BM25-only 的 chunk 以其已存 embedding 計算與問句的 cosine similarity |
| 6 | `HKS_HYBRID_SEARCH` 有三個值：`route`（預設）、`fused`（亦接受 `1`）、`off`（亦接受 `0`）；chunk 數超過 `HKS_HYBRID_MAX_CHUNKS`（預設 20000）自動退回 dense |
| 7 | `route`：keyword 命中自成 `lexical` route（第五路 candidate），score 為「問句詞彙以 idf 加權後被 chunk 涵蓋的比例 × 0.85」，final score gate 0.3，不具 auto write-back 資格。校準內容與是否改為預設見 §4.4、§4.5 |

## 3. 契約變更（additive）

- `Route` enum 新增 `lexical`、trace kind 新增 `lexical_lookup`（`route` 模式，即預設）。Response 的 `source` / `trace.route` / `evidence[].route` 因此可能出現 `lexical`。
- `merge` trace detail 新增 `identifier_filtered`；全部候選被 identifier 過濾掉時，`fallback` step 的 `reason` 為 `identifier_not_found`，並附 `identifiers`、`candidates_dropped`。
- `lexical_lookup` trace detail：`hit`、`candidate_count`、`shared_with_vector`、`skipped_missing_identifier`（僅有略過時）。
- `vector_lookup` trace detail 新增：`retrieval_mode`（`hybrid` / `dense`）、`lexical_candidate_count`、`lexical_only_count`、`lexical_skipped`（僅略過時）。
- vector candidate metadata 新增 `dense_rank`、`lexical_rank`、`bm25_score`（不出現在 response 的 `evidence[]`）。
- 結構化設定新增 `retrieval.hybrid_search`、`retrieval.hybrid_max_chunks`。

## 4. `fused` 與 `route` 的比較

`evals/hybrid_modes.py`：合成語料 240 份文件 × 3 組 seed，20 個有答案的問題與 4 個無答案的問題，rerank 走 RRF。每格為三組 seed 合計。

### 4.1 預設 embedding model（`paraphrase-multilingual-MiniLM-L12-v2`）

| 指標 | `off` | `fused` | `route`（校準前） | `route`（校準後） |
|---|---|---|---|---|
| identifier answer@1 | 17/30 | 24/30 | 23/30 | 23/30 |
| identifier recall@5 | 22/30 | 30/30 | 30/30 | 30/30 |
| keyword answer@1 | 6/15 | 10/15 | 12/15 | 12/15 |
| keyword recall@5 | 5/15 | 13/15 | 15/15 | 15/15 |
| paraphrase answer@1 | 4/15 | 3/15 | 4/15 | 4/15 |
| paraphrase recall@5 | 4/15 | 3/15 | 4/15 | 4/15 |
| no-answer 正確回 no-hit | 2/12 | 2/12 | 4/12 | 2/12 |
| 有答案的問題合計 answer@1 | 27/60 | 37/60 | 39/60 | 39/60 |

### 4.2 `simple`（hash bag-of-words）embedding

| 指標 | `off` | `fused` | `route`（校準前） | `route`（校準後） |
|---|---|---|---|---|
| identifier answer@1 | 19/30 | 24/30 | 22/30 | 24/30 |
| identifier recall@5 | 22/30 | 30/30 | 30/30 | 30/30 |
| keyword answer@1 | 10/15 | 12/15 | 12/15 | 12/15 |
| keyword recall@5 | 9/15 | 11/15 | 12/15 | 12/15 |
| paraphrase answer@1 | 0/15 | 0/15 | 0/15 | 0/15 |
| no-answer 正確回 no-hit | 4/12 | 4/12 | 6/12 | 4/12 |

### 4.3 Golden gate

`tests/eval/test_golden_retrieval_quality.py`（固定用 `simple` embedding）：

- `off`、`fused`：3/3 通過。
- `route` 校準前：1/3。`lexical` route 取代了原本預期的 `vector` route（`vector-clause-32`、`long-doc-alpha-seven-retention`），且 `vector-clause-32` 成為 write-back false positive。
- `route` 校準後：3/3 通過。

### 4.4 `route` 的校準

1. **重複的 chunk 讓給 vector**：vector route 已提名的 chunk，lexical route 不再重複提名；該候選保留 `vector` route 與原本的分數，只在 metadata 記下 `lexical_rank` / `bm25_score`。lexical route 只以 embedding 沒帶出的 chunk 作答。這修掉了 golden gate 的 route 取代問題。
2. **lexical route 不具 auto write-back 資格**（`auto_threshold` 999，與 wiki route 相同）：僅靠關鍵字命中的答案不自動寫回。這修掉了 write-back false positive。
3. **編號必須吻合**：問句中的 identifier（定義見 §4.6，原為「任何帶數字的詞」）必須全部出現在 chunk 中才成為 lexical 候選，否則在 trace 記 `skipped_missing_identifier`。避免「INC-00001」以只共用前綴的「INC-90217」內容作答。
4. **final score gate 0.4 → 0.3**：「ERR-4012 怎麼修」這類夾帶問句的編號查詢，問句詞不在語料中而拉低 coverage（約 0.38），原門檻會擋掉正確答案。

校準前 `route` 在 no-answer 的 4/12、6/12 並不是判斷較準：當時 lexical 候選先勝出、再因分數低於 gate 而整題回 no-hit。校準後這些情況由 vector 候選作答，數字回到與 `fused` 相同。

### 4.5 結論

- 兩種 hybrid 都明顯優於只用 dense（預設 model 下 37/60、39/60 對 27/60），主要來自 identifier 與 keyword 類問題。
- 校準後的 `route` 通過全部 golden gate，答對數不低於 `fused`（預設 model 39 對 37，`simple` 36 對 36）。39 對 37 在這個樣本量下不足以稱為顯著。
- `route` 不會動到 vector route 的排序，所以沒有 `fused` 在 paraphrase 類少答對 1 題的代價（BM25 排名把一個 dense 命中擠出前 5）。
- 依上述結果，預設改為 `route`。這是對外行為變更：response 的 `source` / `trace.route` 會出現新的值 `lexical`，且這類答案不會自動 write-back。要維持舊行為可設 `HKS_HYBRID_SEARCH=fused`。

這份比較的限制：語料與問題是合成的，每類只有 5–10 題 × 3 seed。§4.4 的第 3、4 項是依這份評測集的失敗案例調整的，有對它過度擬合的風險，需要以真實語料驗證。無答案問題的處理見 §4.6。

### 4.6 Identifier 過濾（no-hit 判定）

§4.1–§4.5 的數字是在這項變更之前量的。

逐題檢查無答案問題的誤答後，主因是 vector route 以主題相近、但講的是別的東西的 chunk 作答（問 `ERR-9999`，以 `ERR-4012` 的內容回答）。相似度分不開：誤答約 0.33–0.35，正確答案最低 0.358。

做法：rerank 之前，問句中的 identifier 必須全部出現在候選的完整 chunk 或 wiki page 中，否則該候選不採用；全部被濾掉時回 no-hit（`fallback` step，`reason: identifier_not_found`）。Identifier 指英數混合的詞（`rc2`），或三位以上且非年份的數字（`4012`、`00001`）；短數字與年份不算。三種模式都生效，lexical route 也改用同一套判定。

預設 embedding model，同一份評測，變更前 → 後：

| 指標 | `off` | `fused` | `route` |
|---|---|---|---|
| no-answer 正確回 no-hit | 2/12 → 8/12 | 2/12 → 8/12 | 2/12 → 8/12 |
| identifier answer@1 | 17/30 → 22/30 | 24/30 → 30/30 | 23/30 → 30/30 |
| keyword answer@1 | 6/15 → 6/15 | 10/15 → 10/15 | 12/15 → 12/15 |
| paraphrase answer@1 | 4/15 → 4/15 | 3/15 → 3/15 | 4/15 → 4/15 |
| 有答案的問題合計 answer@1 | 27/60 → 32/60 | 37/60 → 43/60 | 39/60 → 46/60 |

`simple` embedding：no-hit 4/12 → 9/12（三種模式相同）；identifier answer@1 為 19 → 22、24 → 27、24 → 30。

identifier 類同時變好，是因為原本以較高分數搶走答案的錯誤 wiki page 被濾掉了。keyword 與 paraphrase 類的問句不含 identifier，數字不變。Golden gate 在 `route` 與 `fused` 模式仍為 3/3。

沒有解決的情況：問一個語料裡完全沒有的主題、問句又不含 identifier 時（例如評測中的「What is the vacation policy for contractors?」，逐題檢查的那個 seed 仍誤答），仍會被 vector route 以相似度約 0.35 的內容作答。同一個 model 下正確的 paraphrase 答案相似度也只有 0.36–0.39，提高門檻會誤殺它們，所以沒有動相似度門檻。這類情況需要 LLM reranker 或 answerability 判斷。

## 5. 限制

- 每次 query 會讀出整個 collection 的文字；大型知識庫的延遲隨 chunk 數線性成長，故有 `HKS_HYBRID_MAX_CHUNKS` 上限。超過上限需要落地索引（例如 SQLite FTS5），不在本 spec 範圍。
- 未以真實語料量測 retrieval quality 的前後差異。`tests/eval` 中不需 API key 的 11 個測試通過；需 LLM 的 15 個 eval 在開發環境被跳過，未驗證。

## 6. 測試

- `tests/unit/retrievers/test_vector.py`：BM25 排序、keyword-only 命中進候選、雙重命中排前、關閉與上限。
- `tests/unit/retrievers/test_lexical.py`：模式切換、lexical route 的 score 與 evidence、上限、write-back 資格、與 vector 重複的 chunk、編號必須吻合。
- `tests/integration/test_query_hybrid.py`：`VectorStore.all_chunks` / `similarities` 對真實 Chroma collection 的行為；`route` 模式經 CLI 的 end-to-end 與 schema 驗證。

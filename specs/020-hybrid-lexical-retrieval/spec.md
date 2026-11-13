# 020-hybrid-lexical-retrieval — vector route 的 hybrid 檢索

- 日期：2026-11-13
- 狀態：已實作
- 範圍：`ks query` 的 vector route 由 dense-only 改為 dense + BM25 keyword 融合。

## 1. 動機

原本 vector candidates 只取 embedding 相似度前 5 筆，lexical overlap 只對這些已撈到的 chunk 加分。Embedding 排不到前面的精確詞（名稱、ID、錯誤碼、檔名）即使 chunk 內逐字出現，也進不了候選。

## 2. 決策

| # | 決策 |
|---|---|
| 1 | 預設模式（`fused`）不產生新 route。Keyword 命中仍以 `vector` route 回傳，final score gate、write-back threshold 都不變 |
| 2 | BM25 在 query 時對 vector store 的所有 chunk 即時計算，不新增落地索引，既有 `KS_ROOT` 不需 re-ingest，ingest / lint / manifest 不受影響 |
| 3 | Tokenization 沿用 `lexical_terms` 的單位：ASCII 詞（長度 ≥ 2）與 CJK bigram |
| 4 | dense 排名（至多 50 筆）與 BM25 排名（前 20 筆）以 RRF（k=60）融合，取前 5 筆為 candidates |
| 5 | Candidate score 公式不變（similarity + lexical overlap bonus）。BM25-only 的 chunk 以其已存 embedding 計算與問句的 cosine similarity |
| 6 | `HKS_HYBRID_SEARCH` 有三個值：`fused`（預設，亦接受 `1`）、`route`、`off`（亦接受 `0`）；chunk 數超過 `HKS_HYBRID_MAX_CHUNKS`（預設 20000）自動退回 dense |
| 7 | `route` 是 opt-in 的替代做法：keyword 命中自成 `lexical` route（第五路 candidate），score 為「問句詞彙以 idf 加權後被 chunk 涵蓋的比例 × 0.85」，final score gate 0.4，auto write-back 規則同 vector（0.65）。預設不啟用，理由見 §4 |

## 3. 契約變更（additive）

- `Route` enum 新增 `lexical`、trace kind 新增 `lexical_lookup`（僅 `route` 模式會出現）。
- `vector_lookup` trace detail 新增：`retrieval_mode`（`hybrid` / `dense`）、`lexical_candidate_count`、`lexical_only_count`、`lexical_skipped`（僅略過時）。
- vector candidate metadata 新增 `dense_rank`、`lexical_rank`、`bm25_score`（不出現在 response 的 `evidence[]`）。
- 結構化設定新增 `retrieval.hybrid_search`、`retrieval.hybrid_max_chunks`。

## 4. `fused` 與 `route` 的比較

`evals/hybrid_modes.py`：合成語料 240 份文件 × 3 組 seed，20 個有答案的問題與 4 個無答案的問題，rerank 走 RRF。每格為三組 seed 合計。

### 4.1 預設 embedding model（`paraphrase-multilingual-MiniLM-L12-v2`）

| 指標 | `off` | `fused` | `route` |
|---|---|---|---|
| identifier answer@1 | 17/30 | 24/30 | 23/30 |
| identifier recall@5 | 22/30 | 30/30 | 30/30 |
| keyword answer@1 | 6/15 | 10/15 | 12/15 |
| keyword recall@5 | 5/15 | 13/15 | 15/15 |
| paraphrase answer@1 | 4/15 | 3/15 | 4/15 |
| paraphrase recall@5 | 4/15 | 3/15 | 4/15 |
| no-answer 正確回 no-hit | 2/12 | 2/12 | 4/12 |
| 有答案的問題合計 answer@1 | 27/60 | 37/60 | 39/60 |

### 4.2 `simple`（hash bag-of-words）embedding

| 指標 | `off` | `fused` | `route` |
|---|---|---|---|
| identifier answer@1 | 19/30 | 24/30 | 22/30 |
| identifier recall@5 | 22/30 | 30/30 | 30/30 |
| keyword answer@1 | 10/15 | 12/15 | 12/15 |
| keyword recall@5 | 9/15 | 11/15 | 12/15 |
| paraphrase answer@1 | 0/15 | 0/15 | 0/15 |
| no-answer 正確回 no-hit | 4/12 | 4/12 | 6/12 |

### 4.3 Golden gate

`tests/eval/test_golden_retrieval_quality.py`（固定用 `simple` embedding）：`off` 與 `fused` 3/3 通過；`route` 2 個 gate 失敗：`lexical` route 取代了原本預期的 `vector` route（`vector-clause-32`、`long-doc-alpha-seven-retention`），且 `vector-clause-32` 因 lexical score 達 auto write-back 門檻而成為 write-back false positive。

### 4.4 結論

- 兩種 hybrid 都明顯優於只用 dense（預設 model 下 37/60、39/60 對 27/60），主要來自 identifier 與 keyword 類問題。
- `fused` 與 `route` 的答對數差距（37 對 39）在這個樣本量下不足以分出高下：`route` 在 keyword 與 no-hit 略好，`fused` 在 identifier 略好。
- `fused` 在 paraphrase 類比只用 dense 少答對 1 題（3 對 4）：BM25 排名把一個 dense 命中擠出前 5。這是 `fused` 的已知代價。
- 預設維持 `fused`，理由不是答對率，而是 `route` 引入另一套尺度的 score，會改變跨 route 的勝出結果並造成 auto write-back 誤判（§4.3）。`route` 的 score 與 write-back 門檻校準後，可以重新評估是否改為預設。

這份比較的限制：語料與問題是合成的，每類只有 5–10 題 × 3 seed；無答案問題在三種模式下多數都答錯（最好 4/12），顯示 no-hit 判定本身偏弱，與 hybrid 無關。

## 5. 限制

- 每次 query 會讀出整個 collection 的文字；大型知識庫的延遲隨 chunk 數線性成長，故有 `HKS_HYBRID_MAX_CHUNKS` 上限。超過上限需要落地索引（例如 SQLite FTS5），不在本 spec 範圍。
- 未以真實語料量測 retrieval quality 的前後差異。`tests/eval` 中不需 API key 的 11 個測試通過；需 LLM 的 15 個 eval 在開發環境被跳過，未驗證。

## 6. 測試

- `tests/unit/retrievers/test_vector.py`：BM25 排序、keyword-only 命中進候選、雙重命中排前、關閉與上限。
- `tests/unit/retrievers/test_lexical.py`：模式切換、lexical route 的 score 與 evidence、上限、confidence。
- `tests/integration/test_query_hybrid.py`：`VectorStore.all_chunks` / `similarities` 對真實 Chroma collection 的行為；`route` 模式經 CLI 的 end-to-end 與 schema 驗證。

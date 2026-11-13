# 020-hybrid-lexical-retrieval — vector route 的 hybrid 檢索

- 日期：2026-11-13
- 狀態：已實作
- 範圍：`ks query` 的 vector route 由 dense-only 改為 dense + BM25 keyword 融合。

## 1. 動機

原本 vector candidates 只取 embedding 相似度前 5 筆，lexical overlap 只對這些已撈到的 chunk 加分。Embedding 排不到前面的精確詞（名稱、ID、錯誤碼、檔名）即使 chunk 內逐字出現，也進不了候選。

## 2. 決策

| # | 決策 |
|---|---|
| 1 | 不新增 route。Keyword 命中仍以 `vector` route 回傳，`Route` enum、response schema、final score gate、write-back threshold 都不變 |
| 2 | BM25 在 query 時對 vector store 的所有 chunk 即時計算，不新增落地索引，既有 `KS_ROOT` 不需 re-ingest，ingest / lint / manifest 不受影響 |
| 3 | Tokenization 沿用 `lexical_terms` 的單位：ASCII 詞（長度 ≥ 2）與 CJK bigram |
| 4 | dense 排名（至多 50 筆）與 BM25 排名（前 20 筆）以 RRF（k=60）融合，取前 5 筆為 candidates |
| 5 | Candidate score 公式不變（similarity + lexical overlap bonus）。BM25-only 的 chunk 以其已存 embedding 計算與問句的 cosine similarity |
| 6 | `HKS_HYBRID_SEARCH=0` 關閉；chunk 數超過 `HKS_HYBRID_MAX_CHUNKS`（預設 20000）自動退回 dense |

## 3. 契約變更（additive）

- `vector_lookup` trace detail 新增：`retrieval_mode`（`hybrid` / `dense`）、`lexical_candidate_count`、`lexical_only_count`、`lexical_skipped`（僅略過時）。
- vector candidate metadata 新增 `dense_rank`、`lexical_rank`、`bm25_score`（不出現在 response 的 `evidence[]`）。
- 結構化設定新增 `retrieval.hybrid_search`、`retrieval.hybrid_max_chunks`。

## 4. 限制

- 每次 query 會讀出整個 collection 的文字；大型知識庫的延遲隨 chunk 數線性成長，故有 `HKS_HYBRID_MAX_CHUNKS` 上限。超過上限需要落地索引（例如 SQLite FTS5），不在本 spec 範圍。
- 未以真實語料量測 retrieval quality 的前後差異。`tests/eval` 中不需 API key 的 11 個測試通過；需 LLM 的 15 個 eval 在開發環境被跳過，未驗證。

## 5. 測試

- `tests/unit/retrievers/test_vector.py`：BM25 排序、keyword-only 命中進候選、雙重命中排前、關閉與上限。
- `tests/integration/test_query_hybrid.py`：`VectorStore.all_chunks` / `similarities` 對真實 Chroma collection 的行為。

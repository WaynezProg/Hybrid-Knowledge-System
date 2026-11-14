# 022-identifier-rules — 問句中 identifier 的認定規則

- 日期：2026-11-14
- 狀態：已實作
- 範圍：修改 020 §4.6 的 identifier 定義，以及 keyword 檢索查編號的方式。三種 `HKS_HYBRID_SEARCH` 模式都生效。

## 1. 動機

020 的 identifier 規則是「英數混合的詞，或三位以上且非年份的數字」，並以 `[a-z0-9]{2,}` 切詞。連字號會把詞切開，所以 `VID-236` 實際只認 `236`。在兩份真實 `KS_ROOT` 上查詢後，看到四個問題：

| # | 問句 | 原本的結果 | 原因 |
|---|---|---|---|
| 1 | `session2memory reconcile 步驟做了哪些事？` | 5 個候選被濾掉 | 產品名含數字，被當成 identifier |
| 2 | `Atlas-10 對應哪一個 risk？` | 以另一頁（Atlas 的主要風險）作答 | `10` 是短數字，不算 identifier，`Atlas-10` 沒有任何保護 |
| 3 | `VID236 …`（文件寫 `VID-236`） | no-hit，`identifier_not_found` | `vid236` 與 `vid`、`236` 是不同的詞 |
| 4 | `VID-99999 …` | no-hit，但 `identifiers` 是 `["99999"]` | 前綴不在 identifier 裡，文件只要出現 `99999` 就算吻合 |

## 2. 決策

| # | 決策 |
|---|---|
| 1 | **複合編號**：兩個以上字母，後接數字，中間是 `-`、`_` 或沒有分隔（`ERR-4012`、`Atlas-10`、`CVE-2031-7781`、`vid236`、`svc01`）。整個算一個 identifier，數字長短不限 |
| 2 | 複合編號統一寫成 `字母-數字`（小寫，數字段之間也用 `-`）：`VID236`、`VID_236`、`VID-236` 都是 `vid-236` |
| 3 | 候選內容中的複合編號另外接受空白分隔（`Budget 135`），也接受往下延伸的編號（問 `RFC-0193`，內容寫 `RFC-0193-2`）。問句中的空白分隔不算複合編號：「top 10 risks」問的是主題 |
| 4 | **其他英數混合的詞**：結尾是數字，或含三個以上數字，才算 identifier（`v17r2`、`8c5487a`）。數字夾在字母中間的名稱不算（`session2memory`、`k8s`、`i18n`） |
| 5 | **純數字**：維持三位以上且非年份 |
| 6 | **Keyword 檢索的排名**：BM25 對問句中的複合編號同時用兩種寫法的詞查（`vid236` 與 `vid`、`236`）。Lexical route 取前幾名之前，先排除不含問句 identifier 的 chunk，避免只含零散片段的內容（「VID status 236」）擠掉真正寫出編號的 chunk |
| 7 | **Coverage**：問句中的複合編號算一個單位，不論問句或內容怎麼寫；內容寫出該編號才算涵蓋，稀有度以寫出該編號的 chunk 數計算。它的權重等於拆開時的詞數（`vid-236` 為 2），與 020 的權重一致。零散的片段不算涵蓋 |
| 8 | 內容中字母與數字之間的空白可以是多個空白、tab、不換行空白或全形空白，但不跨行 |

## 3. 契約變更

- Response schema、route 名稱、trace step 的 kind 與欄位都沒有變。
- `fallback` step（`reason: identifier_not_found`）的 `identifiers` 內容改變：複合編號以 `字母-數字` 的寫法回報。例：問 `ERR-9999`，原本是 `["9999"]`，現在是 `["err-9999"]`。
- 行為變更：
  - 變嚴：問 `VID-236` 時，內容只出現 `236`（沒有 `VID`）不再算吻合。問 `Atlas-10`、`phase-2`、`gpt-4` 這類短數字編號時，內容必須出現該編號。
  - 變寬：含數字的名稱不再是必要條件；編號換寫法（有無 `-`／`_`）視為相同。

## 4. 驗證

測試：

- `tests/unit/retrieval/test_identifiers.py`：認定規則、各種寫法的吻合與不吻合、BM25 與 coverage 的雙寫法。
- `tests/contract/test_identifier_rules_contract.py`：經 `ks query` 的四種情況。以 020 的規則執行時，6 個測試中 4 個失敗。
- `tests/integration/test_query_hybrid.py`：`identifiers` 的期望值由 `["9999"]` 改為 `["err-9999"]`。

`evals/hybrid_modes.py`（240 份文件 × 3 seed）變更前 → 後：

| 指標（`simple` embedding） | `off` | `fused` | `route` |
|---|---|---|---|
| identifier answer@1 | 22/30 → 22/30 | 27/30 → 27/30 | 30/30 → 30/30 |
| identifier recall@5 | 22/30 → 22/30 | 30/30 → 30/30 | 30/30 → 30/30 |
| keyword answer@1 | 10/15 → 10/15 | 12/15 → 12/15 | 12/15 → 12/15 |
| keyword recall@5 | 9/15 → 9/15 | 11/15 → 11/15 | 12/15 → 12/15 |
| paraphrase answer@1 | 0/15 → 0/15 | 0/15 → 0/15 | 0/15 → 0/15 |
| no-answer 正確回 no-hit | 9/12 → 9/12 | 9/12 → 9/12 | 9/12 → 9/12 |

| 指標（預設 embedding model） | `off` | `fused` | `route` |
|---|---|---|---|
| identifier answer@1 | 22/30 → 22/30 | 30/30 → 30/30 | 30/30 → 30/30 |
| identifier recall@5 | 22/30 → 22/30 | 30/30 → 30/30 | 30/30 → 30/30 |
| keyword answer@1 | 6/15 → 6/15 | 10/15 → 10/15 | 12/15 → 12/15 |
| keyword recall@5 | 5/15 → 5/15 | 13/15 → 13/15 | 15/15 → 15/15 |
| paraphrase answer@1 | 4/15 → 4/15 | 3/15 → 3/15 | 4/15 → 4/15 |
| no-answer 正確回 no-hit | 8/12 → 8/12 | 8/12 → 8/12 | 8/12 → 8/12 |

這份評測沒有換寫法、短數字編號、含數字名稱這三類題目，所以它只能說明沒有退步，不能說明這次變更有效。

真實資料：在一份 session-memory `KS_ROOT`（197 份 daily md，`simple` embedding）的複本上，`--writeback=no`：

| 問句 | 變更前 | 變更後 |
|---|---|---|
| `VID236` | no-hit，`identifier_not_found` | `lexical`，0.85，與 `VID-236` 同一份文件 |
| `PRD008 是什麼？` | 未測 | `lexical`，0.425，與 `PRD-008 是什麼？` 相同 |
| `VID-99999 的進度如何？` | no-hit，`identifiers: ["99999"]` | no-hit，`identifiers: ["vid-99999"]` |
| `session2memory reconcile 步驟做了哪些事？` | `identifier_filtered: 5` | `identifier_filtered: 0` |
| `VID236 的畫面是用來決定什麼？` | no-hit，`identifier_not_found` | no-hit，`final_score_below_threshold`（0.148 < 0.3），與 `VID-236 …` 相同 |

### 4.1 Review 後的修正

Codex review 指出初版的四個問題，都已修正並各有測試：

| 問題 | 反例 | 修正 |
|---|---|---|
| 連寫編號的 coverage 被不存在的片段拉低 | `query_coverage("svc01", "svc01", ["svc01"])` 為 0.094 | 決策 7 |
| 零散片段擠掉完整編號 | 問 `VID236`，一份長文件寫 `VID236`、五份寫「VID status 236」，前五名都不含編號 | 決策 6 |
| 多個空白或 tab 不算吻合 | 問 `VID-236`，內容 `VID  236` | 決策 8 |
| 未知編號的 coverage 為 1.0 | `query_coverage("ERR9999", "ERR-4012 handles 9999 requests", …)` | 決策 7 |

修正後原評測（`simple`）每一格仍與變更前相同；預設 embedding model 與 OpenAI 的數字是修正前量的，修正後沒有重跑。

## 5. 已知限制

- 最後一列：編號夾帶問句時被 lexical gate 0.3 擋掉的問題（020 §4.4 第 4 項）不在這次範圍，換寫法後的結果只是變得與原寫法一致。
- `Atlas-10` 的修正沒有在真實資料上重跑：那份 `KS_ROOT` 用 OpenAI embedding。它只由 contract test 驗證。
- wiki route 的頁面搜尋與 passage 擷取沒有做寫法正規化：`VID-236` 由 wiki route 作答，`VID236` 由 lexical route 作答，找到的是同一份文件，但 route 與 confidence 不同。
- 短數字的複合編號可能過嚴：問 `phase-2`，內容寫「第二階段」會 no-hit。常見的技術名稱（`gpt4`、`mp4`、`h264`）仍算 identifier。
- 不處理前導零（`INC-1` 與 `INC-00001` 不同）、中文前綴（`風險-10`）、單一字母前綴（`v-2`）。
- 規則仍是依少量案例訂的，同樣有過度擬合的風險。

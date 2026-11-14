# 023-lexical-identifier-floor — 編號夾帶問句時 lexical route 的分數

- 日期：2026-11-14
- 狀態：已實作
- 範圍：`route` 模式下 lexical 候選的 score 計算；`evals/hybrid_modes.py` 新增可選的擴充題組。建立在 022 的 identifier 規則之上。

## 1. 動機

Lexical 候選的 score 是「問句詞彙以 idf 加權後被 chunk 涵蓋的比例 × 0.85」，final score gate 是 0.3（020 §4.4 第 4 項）。在一份真實 `KS_ROOT` 上：

- 問 `VID-236`：答對。
- 問 `VID-236 的畫面是用來決定什麼？`：BM25 找到同一個 chunk，但 score 0.148，被 gate 擋成 no-hit。

原因是問句的其他詞（中文 bigram）在語料中完全不存在，每一個都以「最稀有」計入分母。0.3 的門檻是照「ERR-4012 怎麼修」這種短問句調的，問句一長就過不了。

## 2. 決策

| # | 決策 |
|---|---|
| 1 | 問句有 identifier 時，lexical 候選的 score 改為 `0.85 ×（0.5 + 0.5 × coverage）`。Lexical 候選本來就必須含有問句的全部 identifier（020 §4.4 第 3 項），所以拿到底分的都是點名到的那個東西 |
| 2 | 問句沒有 identifier 時，score 維持 `0.85 × coverage`，gate 維持 0.3 |
| 3 | Gate、vector route 的分數與門檻、write-back 資格都不變。Lexical route 仍不具 auto write-back 資格 |
| 4 | 候選 metadata 記 `identifier_match: true`（不出現在 response 的 `evidence[]`） |

不提高或降低 gate，是因為沒有 identifier 的問句靠 coverage 擋掉無關內容（「量子電腦採購計畫」），那一段不該動。

## 3. 契約變更

- Response schema、route 名稱、trace step 都沒有變。
- 行為變更：問句有 identifier 且由 lexical route 作答時，`confidence` 落在 0.425–0.85（原本是 0–0.85，低於 0.3 的會變成 no-hit）。只問編號本身時仍是 0.85。

## 4. 驗證

測試：

- `tests/unit/retrievers/test_lexical.py::test_a_code_inside_a_sentence_still_clears_the_gate`
- `tests/contract/test_identifier_rules_contract.py::test_a_code_wrapped_in_a_sentence_is_answered_by_the_keyword_route`

兩者在沒有這項變更時失敗。

### 4.1 擴充題組

`HKS_EVAL_EXTRA=1 uv run python evals/hybrid_modes.py` 在原有題目之外加入 14 題有答案、4 題無答案的題目，取自真實 `KS_ROOT` 上答錯的問法：

| 類別 | 例 |
|---|---|
| `code-in-sentence` | `VID-236 的畫面是用來決定什麼`、`tell me everything you know regarding INC-30558 please` |
| `code-spelling` | 文件寫 `VID-412`，問 `VID412`；文件寫 `svc07`，問 `svc-07` |
| `short-code` | `Atlas-10 對應哪一個 risk`，語料另有「Atlas 專案目前有 10 個主要風險」 |
| `name-with-digit` | `session2memory 的 reconcile 步驟做了哪些事`，答案不重複這個名稱 |
| `no-answer-code` | `VID999 的進度`、`Atlas-99 對應哪一個 risk` |

擴充題的句子放在沒有原題答案的文件裡，並使用獨立的亂數產生器，所以原題的答案位置不變；但語料多了句子，原題的數字只能在相同設定下互相比較。不設 `HKS_EVAL_EXTRA` 時腳本的行為與數字和原本完全相同。

### 4.2 結果

`simple` embedding，240 份文件 × 3 seed，`route` 模式，answer@1（無答案題為正確回 no-hit）：

| 類別 | 020（main） | + 022 | + 023 |
|---|---|---|---|
| code-in-sentence | 2/12 | 4/12 | 12/12 |
| code-spelling | 3/12 | 9/12 | 12/12 |
| short-code | 6/9 | 9/9 | 9/9 |
| name-with-digit | 0/9 | — | 4/9 |
| no-answer-code | 6/12 | — | 12/12 |
| identifier（原題） | 29/30 | 29/30 | 29/30 |
| keyword（原題） | 9/15 | 9/15 | 9/15 |
| no-answer（原題） | 7/12 | — | 7/12 |

「—」是沒有單獨量測的格子。`off` 與 `fused` 模式不受 023 影響（它們沒有 lexical route）：`fused` 下 code-in-sentence 為 7/12 → 10/12，code-spelling 維持 3/12，因為 `fused` 的 vector 候選分數沒有這個底分。

不設 `HKS_EVAL_EXTRA` 的原評測，`simple` embedding 每一格與 022 相同。

`openai:text-embedding-3-small`（以 `HKS_EVAL_CONFIG_FILE` 指向含 OpenAI 設定的 config），同一份擴充題組，answer@1，020（main）→ 022 + 023：

| 類別 | `fused` | `route` |
|---|---|---|
| code-in-sentence | 9/12 → 12/12 | 8/12 → 12/12 |
| code-spelling | 3/12 → 12/12 | 3/12 → 12/12 |
| short-code | 9/9 → 9/9 | 9/9 → 9/9 |
| name-with-digit | 0/9 → 9/9 | 0/9 → 9/9 |
| no-answer-code | 6/12 → 12/12 | 6/12 → 12/12 |
| identifier（原題） | 30/30 → 30/30 | 30/30 → 30/30 |
| keyword（原題） | 12/15 → 12/15 | 12/15 → 12/15 |
| paraphrase（原題） | 4/15 → 4/15 | 4/15 → 4/15 |
| no-answer（原題） | 9/12 → 9/12 | 7/12 → 7/12 |

這一欄量的是 022 與 023 合起來的效果，沒有把兩者分開。Review 修正（022 §4.1 與本 spec 的評測腳本修正）之後以同樣設定重跑，`fused` 與 `route` 的每一格都與上表相同。

真實資料（session-memory `KS_ROOT` 複本，`simple` embedding，`--writeback=no`）：

| 問句 | 022 | 023 |
|---|---|---|
| `VID-236 的畫面是用來決定什麼？` | no-hit，`final_score_below_threshold`（0.148） | `lexical`，0.499，正確文件 |
| `VID236 的畫面是用來決定什麼？` | 同上 | `lexical`，0.499，正確文件 |
| `PRD-008 是什麼？` | `lexical`，0.425 | `lexical`，0.6375，同一份文件 |
| `VID-99999 的進度如何？` | no-hit，`identifier_not_found` | 相同 |

## 5. 已知限制

- 只提到編號、但答不了問句的 chunk 也會被回傳，confidence 至少 0.425。Response 帶有 evidence，由呼叫端判斷；lexical route 不會自動 write-back。
- `name-with-digit` 還有 5/9 沒答對：答案不含問句的名稱，只能靠其餘詞彙的 coverage 或 vector route。
- 擴充題組下原題的 no-answer 在 `route` 是 7/12、`fused` 是 9/12，變更前後相同；`route` 在這兩題比 `fused` 差的原因沒有追查。
- 0.5 這個比例是依上面的題組與一份真實知識庫訂的，沒有在其他語料上調過。

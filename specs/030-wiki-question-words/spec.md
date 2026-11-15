# 030-wiki-question-words — 只與問句共用疑問詞的 wiki 頁面不成為候選

- 日期：2026-11-15
- 狀態：已實作
- 範圍：`ks query` 的 wiki route 候選（`collect_wiki_candidates`）在什麼情況下不採用搜尋到的頁面。延伸 024 的決策 4。

## 1. 動機

024 只排除 relevance 為 0 的頁面（問句沒有任何一個詞在頁面中）。只要共用一個詞，頁面就成為候選，而且至少拿到 route 分數的 70%（次要 route 時 0.455），高於 no-hit 門檻 0.25。

共用的那個詞可以是疑問詞。019 之後，從 review queue 核准的 write-back 頁以問句為標題，所以這類頁面比 ingest 的頁面更常帶有疑問詞。實際案例（兩個來源、一個 write-back 頁，prune 掉 `atlas.md` 之後）：

| 問句 | 搜尋到的頁面 | 共用的詞 | relevance | 結果 |
|---|---|---|---|---|
| `When is the Atlas migration scheduled` | `What risk does the Bolt cache have` | `the` | 0.0199 | `wiki`，confidence 0.4589，回答 Bolt 的內容 |

知識庫裡已經沒有 Atlas 的內容，正確結果是 no-hit。

## 2. 決策

| # | 決策 |
|---|---|
| 1 | 問句的詞扣掉疑問詞後稱為主題詞。頁面沒有任何一個主題詞時不成為候選，`wiki_lookup` step 與 024 相同：`hit: false`、`reason: low-relevance`、`slug`、`relevance`（此時 relevance 可以大於 0） |
| 2 | 疑問詞是一份固定清單：英文的功能詞與疑問詞（`the`、`is`、`what`、`when`、`does`、`have` 等）；中文的疑問片語（`做了什麼`、`是什麼`、`為什麼`、`如何`、`哪些`、`是否`、`嗎` 等，含簡體），在斷詞前從問句移除，所以跨過片語邊界的 bigram 不會留下 |
| 3 | 全大寫的英文詞（`IT`、`US`）視為名稱，不算疑問詞 |
| 4 | 表示想要哪種答案的詞（`summary`、`摘要` 等，024 決策 2）仍是主題詞：標題為「architecture summary」的頁面仍可回答「summary …」 |
| 5 | 問句扣掉疑問詞後沒有詞（`what is it`、`做了什麼`）時不做這項檢查，沿用 024 的行為 |
| 6 | 通過檢查的頁面，relevance 與 score 的算法不變（024 決策 5） |

不採用 relevance 門檻：024 的 review 已指出門檻會丟掉正確的頁面（唯一頁面「Atlas: Owner: Alice.」，問「Who owns Atlas?」，relevance 只有 0.094）。這裡看的是共用了哪一種詞，不是共用了多少：那個案例共用的是 `atlas`，照樣通過。

## 3. 契約變更

- Response schema、route 名稱、trace step 的 kind 沒有變。
- `wiki_lookup` 的 `reason: low-relevance` 現在可能帶大於 0 的 `relevance`。
- 行為變更：原本由只共用疑問詞的頁面回答的問句，改由其他 route 回答，或回 no-hit。

## 4. 驗證

- `tests/contract/test_wiki_question_words_contract.py`：主題詞的取法、只共用疑問詞的頁面不成為候選（英文與中文）、共用主題詞的頁面照舊、只有疑問詞的問句照舊、經 `ks query` 重現上表的案例（英文與中文問句各一）。
- 既有測試（含 `tests/contract/test_wiki_relevance_contract.py`、`tests/eval/test_golden_retrieval_quality.py`）不需修改即通過。

## 5. 不在範圍內

- `WikiStore.search` 怎麼挑頁面沒有改。它仍以子字串比對挑出一頁，這裡只決定挑出的那一頁要不要用；被排除時不會改挑另一頁。
- 中文問句經 `ks query` 時，`WikiStore.search` 以整段連續中文字當一個詞比對，上表的中文版本在搜尋階段就找不到頁面，沒有走到這項檢查。中文的檢查由單元測試覆蓋。
- 共用一個普通實詞（例如兩頁都提到 `migration`）的頁面仍是候選，由分數去比（024）。
- 疑問詞清單是列舉的，沒列到的功能詞仍算主題詞。

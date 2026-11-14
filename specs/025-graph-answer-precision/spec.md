# 025-graph-answer-precision — graph route 只以問句點名的實體作答

- 日期：2026-11-14
- 狀態：已實作
- 範圍：`ks query` 的 graph route 何時成為候選、列出哪些關係、confidence 如何計算。

## 1. 動機

Graph route 對每條 edge 給分：關係類型符合問句意圖 +4，問句點名 edge 兩端的 node 再加分。只要問句有關係字眼（「影響」「依賴」`impact`、`own`…），所有該類型的 edge 都有 4 分，confidence 就有 0.79，三條 edge 再加到 0.89 以上。問句要的關係類型在 graph 中一條都沒有時，還會改用其他類型的 edge 作答。

在一份以 `openai:text-embedding-3-small` 重建、內容一致的 `KS_ROOT`（24 份文件，51 條 edge）上：

| 問句 | 原本的答案 | 實際情況 |
|---|---|---|
| `What does the weather impact?` | `Project A delay 會影響 notification service、checkout service；Borealis 會影響 Billing Service`，0.95 | 知識庫沒有 weather；三條 edge 都只因為是 `impacts` 而入選 |
| `誰是 Mobile Gateway 的 owner？` | `atlas-dependency 參考 Mobile Gateway；Atlas 依賴 Mobile Gateway；…`，0.99 | graph 沒有 `owns` 的 edge，改以 `references`／`depends_on` 作答；vector 已找到寫著 Owner Iris 的文件（0.61）卻被蓋過 |
| `Borealis 影響哪個服務、ETA 多久？` | `Borealis 會影響 Billing Service；若風險擴大，會 會影響 五月底的里程碑；Project A delay 會影響 notification service`，0.99 | 後兩條與 Borealis 無關 |
| `Atlas 的風險會影響什麼？` | 三條與 Atlas 無關的 `impacts` edge，0.89 | Atlas 只出現在 `depends_on`／`references` 的 edge |

## 2. 決策

| # | 決策 |
|---|---|
| 1 | 只有問句要的關係類型的 edge 可以作答；graph 中沒有該類型的 edge 時不改用其他類型，graph route 不成為候選 |
| 2 | edge 的兩端至少有一端被問句提到（node 分數大於 0）才可以作答；都沒有時 graph route 不成為候選 |
| 3 | 入選的 edge 中，node 分數低於最高者一半的不列出。問句點名 `checkout service` 時，只共用 `service` 一詞的 `notification service` 不會跟著出現 |
| 4 | confidence 公式不變（0.55 + 0.06 × min(最高 edge 分數, 6) + 0.05 ×（列出的 edge 數 − 1），上限 0.99）；但問句只提到 label 的部分詞、沒有完整寫出任何 label 或 alias 時，上限為 0.8 |

決策 4 的 0.8：完整寫出 label 的問句最低 0.91，只共用一個詞的不該與它同級。初版訂為 0.6，但 golden gate 的 `cross-language-project-a-impact`（「Which services are affected if Project A slips」，label 是 `Project A delay`，只共用 `project`）是預期可 auto write-back 的正確答案，0.6 低於 graph 的 write-back 門檻 0.75 而讓它失去資格，所以改為 0.8。

## 3. 契約變更

沒有新增或移除欄位、route、trace step。行為變更：

- `graph_lookup` step 的 `hit: false` 會比以前常出現（決策 1、2）。
- graph 答案列出的關係可能變少（決策 3），`edge_ids`、`relpaths`、`node_ids` 隨之變少。
- graph 候選的 confidence 可能被壓到 0.8（決策 4）；仍高於 graph 的 auto write-back 門檻 0.75，資格不因此改變。

## 4. 驗證

同一份 `KS_ROOT`，變更前 → 後（graph route 本身的結果）：

| 問句 | 變更前 | 變更後 |
|---|---|---|
| `What does the weather impact?` | 0.95，三條無關的 edge | 不成為候選 |
| `誰是 Mobile Gateway 的 owner？` | 0.99，`references`／`depends_on` | 不成為候選 |
| `Atlas 的風險會影響什麼？` | 0.89，三條無關的 edge | 不成為候選 |
| `Borealis 影響哪個服務、ETA 多久？` | 0.99，三條 edge | 0.91，`Borealis 會影響 Billing Service` |
| `A 專案延遲會影響哪些服務？` | 0.99，另含 Borealis 的 edge | 0.96，`A 專案延遲 會影響 checkout service、notification service` |
| `checkout service 依賴什麼？` | 0.99，另含 notification service 與 Atlas 的 edge | 0.91，`checkout service 依賴 A 專案提供的 pricing API，` |
| `Atlas 依賴什麼？` | — | 0.91，`Atlas 依賴 Mobile Gateway` |
| `哪些 service 受影響？` | — | 0.8，列出三條 `impacts` edge（問句只有 `service` 一詞吻合） |

「—」是沒有量測變更前的格子。整個 `ks query` 的前後比對見 PR 說明。

## 5. 已知限制

- 「問句提到」仍是詞彙重疊：CJK 以不重疊的兩字切分，偶然共用一個兩字詞也算提到（confidence 上限 0.8，仍可 auto write-back）。
- 答案只有關係句，不含關係以外的資訊：`Borealis 影響哪個服務、ETA 多久？` 只回答前半。
- 0.8 與「一半」是依這份知識庫與 golden gate 訂的，沒有在其他語料上調過。
- graph 的 edge 來自 pattern-based extraction，label 可能是斷句的殘片（`若風險擴大，會`、`A 專案提供的 pricing API，`）；這次沒有處理。

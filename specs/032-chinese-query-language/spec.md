# 032：中文主題、同義詞與 workspace 別名

日期主題無命中時不再擴回整天內容；混合問句同時保留 Latin 名稱與中文條件。一般工作摘要的問法仍可回整天。

詞彙替換是有界集合（等待／等候、快捷鍵／熱鍵、相容／兼容、風險／隱憂、狀態／狀況等），不宣稱處理任意同義改述。專案譯名由各 KS_ROOT 的 `query_aliases.json` 指定：

```json
{"session2memory": ["s2m", "會話記憶"], "HKS": ["混合知識系統"]}
```

- canonical name -> alias string list。查詢與內容比較使用同一映射；ASCII 採完整詞界，`s2m` 不匹配 `s2m2`。
- 每次 query 載入，ContextVar 隔離 workspace；不修改 process environment、source、embedding 或原始 writeback question。
- 最多 64 KiB；錯誤格式、衝突別名、ticket/version identifier 的 alias 回 CONFIG_ERROR（exit 65）。編號不能透過別名放寬。
- trace 沿用 routing_model kind，新增 query_normalization 與 subject_constraint detail。主題不符的拒答 reason 為 subject_not_found，不計入 identifier_filtered。
- configured entity 與所問風險／狀態面向必須在答案片段有支持。wiki/vector/lexical 截取 top candidates 前先篩；所有 routes 在最後排序前再次檢查。wiki 改取可回答問題的原文 passage，避免摘要截斷狀態。
- 片段同時有明確 entity 與面向時，可用 primary-vector floor，且以這份字面支持取代弱 embedding gate；不提高 confidence 或 writeback eligibility。只有其中一項不能通過此條件。

Regression tests 覆蓋中英文日期、區間與工作摘要、不同專案尾碼、中文 unknown topic、混合條件、alias 雙向召回、服務主體與面向、錯誤設定及並行隔離。原 27 個實際案例另以現有 OpenAI runtime 的隔離副本重播，核對最終 answer 與 evidence，不改正式資料。

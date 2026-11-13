# 架構圖、流程圖與時序圖

本頁以 Mermaid 畫出 HKS 目前 runtime 的實際結構，依 `src/hks/` 的程式繪製。契約的文字敘述以 [main.md](main.md) 為準；兩者不一致時以 runtime code 與測試為事實，並請修正本頁。

`LLM wiki Graphify.png` 等圖是早期的概念願景（含 Neo4j、RBAC、雲端連接器等未實作項目），不代表現況。

## 1. 系統架構

三個入口共用同一組 command 與儲存層；沒有常駐服務，每次呼叫結束即退出（`hks-mcp` / `hks-api` 是本機 adapter）。

```mermaid
flowchart LR
    subgraph entry["入口"]
        cli["ks CLI<br/>hks.cli"]
        mcp["hks-mcp<br/>adapters/mcp_server"]
        api["hks-api<br/>adapters/http_server"]
    end

    subgraph core["Core（src/hks）"]
        cmd["commands/<br/>ingest · query · lint · coord · update<br/>llm · wiki · graphify · watch · source · workspace"]
        ing["ingest/<br/>parsers · normalizer · extractor"]
        ret["retrievers/ + retrieval/ + rerank/"]
        route["routing/"]
        wb["writeback/"]
        lint["lint/"]
    end

    subgraph store["KS_ROOT（權威層）"]
        raw[("raw_sources/")]
        wiki[("wiki/<br/>index.md · log.md · pages/")]
        graphS[("graph/graph.json")]
        vec[("vector/db<br/>Chroma")]
        tree[("page_trees/")]
        man[("manifest.json")]
        coord[("coordination/<br/>state.json · events.jsonl")]
    end

    subgraph derived["KS_ROOT（衍生層，不影響權威層）"]
        llm[("llm/extractions<br/>llm/wiki-candidates")]
        gfy[("graphify/runs")]
        watch[("watch/")]
    end

    cli --> cmd
    mcp --> cmd
    api --> cmd
    cmd --> ing
    cmd --> route
    cmd --> ret
    cmd --> wb
    cmd --> lint
    ing --> raw
    ing --> wiki
    ing --> graphS
    ing --> vec
    ing --> tree
    ing --> man
    ret --> wiki
    ret --> graphS
    ret --> vec
    ret --> tree
    wb --> wiki
    lint --> man
    cmd --> coord
    cmd --> llm
    cmd --> gfy
    cmd --> watch
```

## 2. Ingest 流程

`ks ingest <path>`（`ingest/pipeline.py`）。寫入是逐檔的：任一步失敗會把該檔已寫入的各層還原，其他檔不受影響。

```mermaid
flowchart TD
    start(["ks ingest path"]) --> lock["取得 KS_ROOT lock"]
    lock --> each{"還有檔案？"}
    each -- "否" --> prune["prune：移除來源已不存在的 manifest entry<br/>與其 wiki / graph / vector / page_tree"]
    prune --> done(["輸出 ingest_summary"])
    each -- "是" --> fmt["判定格式<br/>txt · md · pdf · docx · xlsx · pptx · png · jpg"]
    fmt --> guard{"通過大小與格式 guard？"}
    guard -- "否" --> skip["記錄 skipped / failed"]
    skip --> each
    guard -- "是" --> same{"sha256 與 parser fingerprint<br/>皆未變，且各層 artifact 齊全？"}
    same -- "是" --> unchanged["記錄 unchanged"]
    unchanged --> each
    same -- "否" --> parse["parse<br/>影像走 OCR，Office 有 timeout"]
    parse --> norm["normalize + chunk"]
    norm --> ext["extract<br/>標題 · 摘要 · 內文"]
    ext --> ptree["建立 page tree"]
    ptree --> write["依序寫入"]

    subgraph atomic["逐檔寫入（失敗則全部還原）"]
        w1["page_trees/"] --> w2["raw_sources/（複製原檔）"]
        w2 --> w3["wiki page"]
        w3 --> w4["graph：entity 與 relation"]
        w4 --> w5["vector：chunk 與 metadata"]
        w5 --> w6["manifest entry"]
    end

    write --> w1
    w6 --> stale["刪除此檔舊版的 vector chunk 與 page tree"]
    stale --> each
```

## 3. Query 流程

`ks query "<q>"`（`commands/query.py`）。不是 sequential fallback：各 route 都收集 candidates 後統一排序。

```mermaid
flowchart TD
    q(["ks query"]) --> init{"manifest 存在且有內容？"}
    init -- "否" --> noinput(["NOINPUT：請先 ks ingest"])
    init -- "是" --> r["routing：決定 requested route<br/>並分析 session memory intent"]

    r --> collect["收集 candidates"]
    subgraph routes["各 route 的 retriever"]
        c0["session memory<br/>（wiki 中的 session 記憶頁）"]
        c1["wiki"]
        c2["graph"]
        c3["vector<br/>dense，取前 5"]
        c4["lexical<br/>BM25，見第 5 節"]
        c5["page_tree<br/>有 summary 的節點"]
    end
    collect --> c0
    collect --> c1
    collect --> c2
    collect --> c3
    collect --> c4
    collect --> c5
    c0 --> any{"有任何 candidate？"}
    c1 --> any
    c2 --> any
    c3 --> any
    c4 --> any
    c5 --> any

    any -- "否" --> nohit(["no-hit"])
    any -- "是" --> special{"session memory intent<br/>是 workspace 狀態或日期區間？"}
    special -- "是，且合成成功" --> synth(["回傳合成結果<br/>不具 auto write-back 資格"])
    special -- "否" --> rerank["rerank<br/>有 opt-in 與 key：LLM<br/>否則：跨 route RRF"]
    rerank --> gate{"第一名通過該 route 的<br/>final score gate？"}
    gate -- "否" --> nohit
    gate -- "是" --> ev["由勝出 candidate 產生 evidence"]
    ev --> conf["confidence assess<br/>route 別門檻與 evidence 要求"]
    conf --> wbq{"--writeback"}
    wbq -- "no" --> out(["回傳 response"])
    wbq -- "auto 且 eligible，或 yes" --> commit["寫回 wiki，記錄 log"]
    commit --> out
    wbq -- "auto 但不 eligible" --> logskip["wiki log 記錄 skip 原因"]
    logskip --> out
```

## 4. Query 時序圖

```mermaid
sequenceDiagram
    autonumber
    actor A as Agent / 使用者
    participant E as ks / hks-mcp / hks-api
    participant Q as commands/query
    participant R as routing
    participant T as retrievers
    participant S as wiki · graph · vector · page_trees
    participant K as rerank
    participant C as retrieval/confidence
    participant W as writeback

    A->>E: query(question, writeback)
    E->>Q: run(question)
    Q->>S: 載入 manifest（必要時重建）
    Q->>R: route_query + session memory intent
    R-->>Q: requested route、trace steps
    loop 每個 route
        Q->>T: collect_*_candidates
        T->>S: 讀取
        S-->>T: 命中內容
        T-->>Q: candidates + lookup trace step
    end
    Q->>K: rerank_candidates
    alt LLM opt-in 且有 key
        K-->>Q: LLM 排序
    else
        K-->>Q: RRF 排序
    end
    Q->>Q: final score gate（不過則 no-hit）
    Q->>C: assess(route, score, evidence)
    C-->>Q: calibrated confidence、writeback_eligible
    opt writeback 決定為 commit
        Q->>W: commit
        W->>S: 寫 wiki page 與 log
    end
    Q-->>E: QueryResponse
    E-->>A: JSON（answer · source · confidence · evidence · trace）
```

## 5. Keyword 檢索（`HKS_HYBRID_SEARCH`）

BM25 在 query 時對 vector store 的所有 chunk 即時計算，沒有落地索引。預設是 `route` 模式；細節與比較數字見 [specs/020](../specs/020-hybrid-lexical-retrieval/spec.md)。

```mermaid
flowchart TD
    q(["question"]) --> mode{"HKS_HYBRID_SEARCH"}

    mode -- "off" --> dense0["vector：dense 前 5"]
    dense0 --> outv(["vector candidates"])

    mode -- "fused" --> big1{"chunk 數超過<br/>HKS_HYBRID_MAX_CHUNKS？"}
    big1 -- "是" --> dense0
    big1 -- "否" --> fuse["dense 排名（至多 50）與 BM25 排名（前 20）<br/>以 RRF 融合，取前 5"]
    fuse --> outv

    mode -- "route（預設）" --> dense1["vector：dense 前 5"]
    dense1 --> outv
    dense1 --> big2{"chunk 數超過上限？"}
    big2 -- "是" --> none(["沒有 lexical candidate"])
    big2 -- "否" --> bm["BM25 前 5"]
    bm --> idq{"問句中帶數字的詞<br/>全部出現在 chunk？"}
    idq -- "否" --> drop["略過<br/>skipped_missing_identifier"]
    idq -- "是" --> dup{"vector 已提名同一 chunk？"}
    dup -- "是" --> note["仍歸 vector<br/>只在 metadata 記 lexical_rank"]
    dup -- "否" --> lex["成為 lexical candidate<br/>score = 0.85 × 問句詞彙的 idf 加權涵蓋率"]
    lex --> outl(["lexical candidates<br/>gate 0.3，不具 auto write-back 資格"])
```

## 6. 與 session2memory 的銜接

session2memory 把各 agent 的 session 整理成 Markdown；HKS 只讀它輸出的檔案，不直接讀任何 agent 的 session store。

```mermaid
flowchart LR
    subgraph s2m["session2memory"]
        exp["auto export<br/>projects/*.md · sessions/YYYY-MM/*.md"]
        daily["每日匯入<br/>daily/*.md（session_daily）"]
    end
    subgraph hks["HKS"]
        upd["ks update / ks ingest"]
        wikiS[("wiki")]
        vecS[("vector")]
        sm["retrievers/session_memory<br/>workspace 狀態 · 日期區間合成"]
    end
    agent["Agent（MCP / HTTP，agent profile）"]

    exp -- "--index-cmd" --> upd
    daily --> upd
    upd --> wikiS
    upd --> vecS
    wikiS --> sm
    vecS --> sm
    agent -- "query" --> sm
```

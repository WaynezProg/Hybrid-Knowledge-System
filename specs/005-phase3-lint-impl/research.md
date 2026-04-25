# Research: Phase 3 階段二 — `ks lint` 真實實作

## 1. Lint execution model

- **Decision**: 使用 snapshot + pure checks。`LintRunner` 先在 lock 內讀取 `RuntimeSnapshot`，再由各 checker 回傳 `Finding[]`；checks 不直接寫資料層。
- **Rationale**: lint 的主要價值是可預測與可測。把資料讀取、檢查、修復分開，可讓 read-only 模式、strict 模式、fix 模式共用同一 findings。
- **Alternatives considered**:
  - 在 `WikiStore` / `VectorStore` / `GraphStore` 內直接散落 check：容易把一致性規則分散，測試也難以覆蓋完整 category。
  - 每個 category 直接讀檔：重複 IO，且無法保證 fix 前後使用同一份 snapshot。

## 2. Lock policy

- **Decision**: lint 與 ingest 共用 `paths.lock`，採現有 non-blocking exclusive lock；取不到 lock 時 exit `1 GENERAL`。
- **Rationale**: 現有 ingest lock 已是 non-blocking。lint 若等待，CI 會卡住；若無 lock，會讀到 ingest 中途狀態。
- **Alternatives considered**:
  - Blocking lock：人類互動看似友善，但 CI timeout 行為不可控。
  - Read lock：目前 lock helper 無 shared lock，且 ingest 寫入多層資料，不值得為 005 擴 lock 模型。

## 3. Severity mapping

- **Decision**:
  - `error`: `manifest_wiki_mismatch` / `wiki_source_mismatch` / `dangling_manifest_entry` / `manifest_vector_mismatch` / `graph_drift`
  - `warning`: `orphan_page` / `dead_link` / `duplicate_slug` / `orphan_raw_source` / `orphan_vector_chunk`
  - `info`: `fingerprint_drift`
- **Rationale**: manifest 與 derived artifact 互相缺失代表 truth-of-record 斷裂，應讓 `--strict` fail。孤兒實體多半可人工判斷或安全 prune，不預設阻擋。fingerprint drift 只是提示 re-ingest。
- **Alternatives considered**:
  - 全部 mismatch 都 error：會讓 orphan raw source 這類低風險狀態阻擋 CI。
  - dead link 設為 error：對 wiki index 可 rebuild 的情境過重，先維持 warning。

## 4. Fix policy

- **Decision**: `--fix` 等同 dry-run；`--fix=apply` 不要求先跑 dry-run，但必須在 apply 前重新計算同一批 fix plan。apply 僅允許 `rebuild_index`、`prune_orphan_vector_chunks`、`prune_orphan_graph_nodes`、`prune_orphan_graph_edges`。
- **Rationale**: 使用者要求 apply 時應一次完成；強制兩階段會降低 CLI ergonomics。重新計算 plan 可避免 dry-run 與 apply 之間資料漂移。
- **Alternatives considered**:
  - 強制 dry-run token / confirmation：更安全但不適合 agent/CI。
  - 自動補 manifest：manifest 是 truth-of-record，不應由 lint 猜測來源反寫。

## 5. Vector inspection

- **Decision**: 在 `VectorStore` 增加 `list_ids()` 與 `delete()` 共用，透過 Chroma collection `get()` 取得 collection 中所有 chunk ids。
- **Rationale**: spec 需要同時檢查 manifest 引用不存在的 chunk、collection 中無 manifest 引用的 chunk；必須有完整 id set。
- **Alternatives considered**:
  - 用 `count()` + search 近似推斷：不完整，無法列出 orphan ids。
  - 直接在 lint module 存取 collection 私有細節：耦合 Chroma 實作。

## 6. Graph repair

- **Decision**: graph repair 只 prune 明確孤兒：source/target 不存在的 edge、source_relpath 不在 manifest 的 node/edge，以及 prune node 後連帶 dangling edge。
- **Rationale**: 這些狀態不需要語意推論即可判斷。重建 graph 或補 node 屬 ingest/extract 責任。
- **Alternatives considered**:
  - 由 lint 重新抽 entity/relation：違反不 re-ingest。
  - 自動修 manifest graph artifact refs：會把錯誤現況寫回 truth-of-record。

## 7. Contract placement

- **Decision**: 005 新增 `contracts/query-response.schema.json` 與 `contracts/lint-summary-detail.schema.json`；implementation 時把 runtime contract path 切到 005 schema。
- **Rationale**: 003 schema 不含 `lint_summary`。直接改 003 會破壞歷史 artifact；005 應成為新 canonical。
- **Alternatives considered**:
  - 只新增 lint detail schema，不新增 query schema：runtime `QueryResponse.validate()` 仍會拒絕 `lint_summary`。

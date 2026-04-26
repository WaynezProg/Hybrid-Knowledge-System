# Feature Specification: Source catalog and workspace selection

**Feature Branch**: `012-source-catalog`  
**Created**: 2026-04-26  
**Status**: Complete  
**Input**: User description: "Plan HKS 012 for a feature that lets users see what data has been ingested, choose which data or HKS runtime to query, and manage multiple HKS folders/projects without mixing their knowledge bases."

## Clarifications

### Session 2026-04-26

- Q: 這個需求是在同一個 HKS 內選資料，還是多個 HKS runtime 間切換？ -> A: 兩者都需要，但先以 read-only source catalog 作 MVP，再補 workspace registry 管多個 `KS_ROOT`。
- Q: CLI 是否能真的改變使用者 shell 的 `KS_ROOT`？ -> A: 不能依賴 child process 修改 parent shell；`workspace use` 必須回傳 shell-safe export command 或 JSON root，實際 query 以明確 `workspace_id` / `ks_root` 執行。
- Q: Catalog 是否可以修改 wiki / graph / vector / manifest？ -> A: 不可以。source catalog 只讀 manifest 與現有 artifacts；workspace registry 只寫自己的 registry config。
- Q: `workspace register` 對「id 已存在但 root 不同」的衝突行為？ -> A: 預設拒絕，以 exit `66` + conflict envelope 回；`--force` 才覆寫，response 必含 `previous_root`。
- Q: workspace id 的具體 validation 規則為何？ -> A: `^[A-Za-z][A-Za-z0-9_-]{0,63}$`（ASCII 開頭字母、字母數字／`-`／`_`、最長 64 字）。
- Q: registry 預設路徑與 override 順序？ -> A: `$HKS_WORKSPACE_REGISTRY` > `$XDG_CONFIG_HOME/hks/workspaces.json` > `~/.config/hks/workspaces.json`；測試一律用顯式 temp path。
- Q: `workspace use` 是否 persist last-used pointer？ -> A: stateless，不寫任何 last-used 狀態；後續 catalog/workspace/query call 都需要顯式 `workspace_id` 或 `ks_root`。
- Q: `trace.steps.kind="catalog_summary"` 的 detail schema 欄位？ -> A: required `kind`、`command`、`total_count`、`filtered_count`、`filter`（object 或 `null`）；workspace 範圍指令額外含 `workspace_id`。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 查看單一 HKS 已 ingest 資料 (Priority: P1)

使用者或 agent 可以對目前 `KS_ROOT` 查詢已 ingest 的 sources，看到 relpath、format、size、ingested_at、sha256 短碼、parser fingerprint、derived wiki / graph / vector counts，以及是否可查詢。

**Why this priority**: 這是「做過哪些資料」的最小可用能力。沒有 source catalog，使用者只能手動打開 `manifest.json`。

**Independent Test**: 建立 temporary `KS_ROOT`，ingest fixture folder，執行 `ks source list` 後應列出 manifest entries，且不改 `wiki/`、`graph/graph.json`、`vector/db/`、`manifest.json`、`watch/`。

**Acceptance Scenarios**:

1. **Given** `KS_ROOT` 已 ingest 多個 supported sources，**When** caller 執行 source list，**Then** response 依 relpath 穩定排序並回傳每筆 source 的 metadata 與 derived artifact counts。
2. **Given** `KS_ROOT` 尚未初始化或缺少 `manifest.json`，**When** caller 執行 source list，**Then** command 以 `66` 回報 no input，並提供「先執行 ks ingest」提示。
3. **Given** caller 提供 format 或 relpath filter，**When** source list 執行，**Then** response 只回傳符合條件的 sources，counts 反映 filtered result。

---

### User Story 2 - 查看單筆資料細節與關聯 artifacts (Priority: P1)

使用者或 agent 可以針對 manifest relpath 查看單筆 source 的完整 metadata、raw source path、wiki pages、graph node/edge ids、vector ids、最近 ingest 時間與 parser fingerprint，用來決定是否要 query、refresh 或做 LLM synthesis。

**Why this priority**: 只列清單不足以判斷資料是否完整或適合查詢；source detail 是 agent 選擇資料與 debug ingestion 的必要入口。

**Independent Test**: 對已 ingest fixture 執行 `ks source show project-atlas.txt`，確認回傳 artifact references 與 manifest derived fields 一致，不讀取 arbitrary runtime internals。

**Acceptance Scenarios**:

1. **Given** relpath 存在於 manifest，**When** caller 執行 source show，**Then** response 包含該 source 的 manifest metadata、derived artifacts、raw source path 與 query hint。
2. **Given** relpath 不存在於 manifest，**When** caller 執行 source show，**Then** command 以 `66` 回報 source not found。
3. **Given** source 的 derived artifact reference 已遺失，**When** caller 執行 source show，**Then** response 標示 integrity status 為 warning，但不自動修復。

---

### User Story 3 - 管理多個 HKS workspace (Priority: P2)

使用者可以把不同專案的 `KS_ROOT` 註冊成 named workspace，列出可用 workspace、檢查每個 workspace 是否 initialized、看到 source counts，並取得可直接用於 query 的 root。

**Why this priority**: 使用者的實際問題是多個資料夾 / 專案間選擇。workspace registry 提供穩定選擇層，不把不同專案強行混到同一個 `KS_ROOT`。

**Independent Test**: 建立兩個 temporary `KS_ROOT`，分別 ingest 不同 fixture，註冊為兩個 workspace，執行 workspace list 後應看到兩者 root、status、source count，且 registry 寫入不影響任一 HKS runtime layer。

**Acceptance Scenarios**:

1. **Given** caller 註冊 workspace `proj-a` 指向 initialized `KS_ROOT`，**When** workspace list 執行，**Then** response 顯示 `proj-a`、root、status=`ready`、source_count。
2. **Given** workspace root 不存在或缺少 manifest，**When** workspace list 執行，**Then** response 顯示 status=`missing` 或 `uninitialized`，不讓後續 query 假裝成功。
3. **Given** caller 執行 workspace use，**When** command 成功，**Then** response 回傳 resolved `ks_root` 與 shell-safe `export KS_ROOT=...` 字串；不假裝已改變 parent shell。

---

### User Story 4 - 選 workspace 後查詢 (Priority: P2)

使用者或 agent 可以用 workspace id 執行 query，系統解析 registry 後把查詢導向該 workspace 的 `KS_ROOT`，回傳既有 `ks query` response shape。

**Why this priority**: Catalog 只有列資料，不足以完成「我想查某個專案內容」的目標；workspace-aware query 讓選擇與查詢接起來。

**Independent Test**: 兩個 workspace 各 ingest 不同 fixture，對同一問題執行 `ks workspace query proj-a "..."` 與 `ks workspace query proj-b "..."`，確認結果只來自指定 workspace。

**Acceptance Scenarios**:

1. **Given** workspace id 存在且 ready，**When** caller 執行 workspace query，**Then** command 用該 workspace root 執行既有 query 並保持 query response contract。
2. **Given** workspace id 不存在，**When** caller 執行 workspace query，**Then** command 以 `66` 回報 unknown workspace。
3. **Given** caller 同時提供 workspace id 與 explicit `ks_root`，**When** 兩者衝突，**Then** command 拒絕執行並以 `2` 回報 usage error，避免查錯資料庫。

---

### User Story 5 - 透過 MCP / HTTP 使用 catalog 與 workspace (Priority: P3)

Agent 可以透過 MCP tools 或 loopback HTTP endpoints 列 sources、查看 source detail、列 workspace、註冊 workspace、用 workspace query，語意與 CLI 一致。

**Why this priority**: HKS 已將 MCP / HTTP 視為正式介面；012 若只做 CLI，agent 仍無法安全選資料庫。

**Independent Test**: 對同一 temporary registry 與兩個 `KS_ROOT`，分別呼叫 CLI、MCP、HTTP list/query，確認 counts、workspace status、error envelope 與 query semantics 一致。

**Acceptance Scenarios**:

1. **Given** MCP caller 呼叫 source list with `ks_root`，**When** runtime ready，**Then** response 與 CLI source list 的 catalog summary detail 等價。
2. **Given** HTTP caller 註冊 workspace root，**When** root path 無效，**Then** endpoint 回傳 adapter error envelope 並不寫入 invalid ready workspace。

### Edge Cases

- `manifest.json` corrupt：source list/show 回傳 data error，不嘗試 rebuild manifest。
- `manifest.json` 存在但 `raw_sources/` 缺 source：source detail 標示 warning，建議 `ks lint` 或 watch refresh，不自動修。
- workspace id 包含空白、路徑分隔符或 shell metacharacters：拒絕。
- workspace root 指向 HKS repo checkout 而不是 runtime root：標示 uninitialized，提示需要指向含 `manifest.json` 的 `KS_ROOT`。
- registry file corrupt：workspace commands 回傳 data error；不得覆寫 corrupt registry。
- registry 中兩個 workspace 指向同一 resolved root：允許但回傳 duplicate_root warning。
- workspace id 已存在但呼叫者要綁不同 root：預設拒絕（exit `66`，conflict envelope）；`--force` 才覆寫並在 response 包含 `previous_root`。
- source relpath filter 無命中：成功回傳空 list，exit code `0`。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide `ks source list` for the active `KS_ROOT` or explicit root and return manifest-derived source catalog metadata.
- **FR-002**: System MUST provide `ks source show <relpath>` for one manifest source and return source metadata plus derived artifact references.
- **FR-003**: Source catalog commands MUST be read-only against authoritative HKS runtime layers: `wiki/`, `graph/`, `vector/`, `raw_sources/`, `manifest.json`, `watch/`, `graphify/`, `llm/`, and `coordination/`.
- **FR-004**: Source catalog responses MUST include enough metadata to choose data for query: relpath, format, size_bytes, ingested_at, sha256 prefix, parser_fingerprint, derived artifact counts, integrity status (one of `ok | warning | error | unknown`), and query hint.
- **FR-005**: Source catalog MUST support deterministic filtering by relpath substring/prefix and source format.
- **FR-006**: Source catalog MUST validate relpath input against manifest entries and MUST NOT expose a generic file read API for runtime internals.
- **FR-007**: System MUST provide a local workspace registry that maps stable workspace ids to resolved `KS_ROOT` paths and optional display metadata.
- **FR-008**: Workspace registry writes MUST be explicit caller actions and MUST NOT mutate any registered HKS runtime layers.
- **FR-009**: Workspace ids MUST match `^[A-Za-z][A-Za-z0-9_-]{0,63}$` (ASCII letter start, alphanumeric / `-` / `_`, max 64 chars); this rule guarantees no path separators, whitespace, shell metacharacters, or control characters.
- **FR-010**: System MUST provide workspace list/show/register/remove/use operations with deterministic JSON responses and status classification for each registered root. `workspace register` MUST reject (exit code `66`, conflict envelope) when the id already exists with a different resolved root; `--force` overrides this and the success response MUST include `previous_root`.
- **FR-011**: `workspace use` MUST NOT claim to change the caller's parent shell environment; it MUST return resolved root and a shell-safe export command or JSON field. `workspace use` is stateless and MUST NOT persist any last-used pointer; subsequent catalog / workspace / query calls MUST require explicit `workspace_id` or `ks_root`.
- **FR-012**: System MUST provide workspace-aware query that resolves workspace id to `KS_ROOT` and delegates to existing query behavior without changing query response shape.
- **FR-013**: Workspace-aware query MUST reject ambiguous calls that provide conflicting workspace id and explicit root.
- **FR-014**: Catalog/workspace list-style commands MUST use existing top-level HKS success shape with `trace.steps.kind="catalog_summary"` and MUST NOT introduce new top-level `source` or `route` enum values. The `catalog_summary` detail object MUST contain `kind`, `command` (e.g. `source.list`, `workspace.list`, `source.show`), `total_count`, `filtered_count`, and `filter` (object or `null`); workspace-scoped commands MUST also include `workspace_id`.
- **FR-015**: MCP and HTTP adapters MUST expose catalog/workspace operations with the same validation, error mapping, and loopback safety behavior as existing adapter tools.
- **FR-016**: `ks lint` MUST detect corrupt workspace registry, invalid workspace ids, duplicate ready roots, and workspace records whose derived `WorkspaceStatus` is `missing`, `uninitialized`, or `corrupt` after 012 implementation.
- **FR-017**: README, README.en.md, docs/main.md, docs/PRD.md, CLAUDE.md (Active Technologies / Recent Changes), contracts, quickstart, and archive docs MUST be updated when runtime surface is implemented.

### Key Entities *(include if feature involves data)*

- **Source Catalog Entry**: Read-only view of a manifest entry plus derived artifact counts and integrity status.
- **Source Detail**: One source catalog entry with full derived artifact references and raw source path.
- **Workspace Registry**: Local config file containing named workspace records and schema version.
- **Workspace Record**: Workspace id, label, resolved `ks_root`, created_at, updated_at, optional tags, and status derived at read time.
- **Workspace Status**: Derived health state such as `ready`, `missing`, `uninitialized`, `corrupt`, or `duplicate_root`.
- **Catalog Summary**: `trace.steps[kind="catalog_summary"].detail` payload for catalog/workspace commands that are not normal knowledge queries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After ingesting `tests/fixtures/valid`, `ks source list` returns every manifest entry in deterministic relpath order and performs zero writes to authoritative HKS layers.
- **SC-002**: `ks source show <relpath>` returns artifact references matching `manifest.json` exactly for at least wiki pages and vector ids.
- **SC-003**: Two registered workspaces backed by different `KS_ROOT` values report distinct source counts and can be queried independently.
- **SC-004**: `workspace use` output is shell-safe and can be evaluated manually to run a normal `ks query` against the selected root.
- **SC-005**: CLI, MCP, and HTTP source list responses agree on total_count, filtered_count, first relpath, and trace step kind for the same `KS_ROOT`.
- **SC-006**: Full test suite adds deterministic contract/integration coverage for catalog schema, registry schema, CLI commands, adapter parity, and lint checks.
- **SC-007**: On a synthetic 1,000-entry manifest, `ks source list` returns within 1.0s wall-clock; on a registry with 100 records, `ks workspace list` returns within 1.0s wall-clock (measured on local fixtures, warm cache).

## Assumptions

- 012 targets local personal workspaces; it does not add UI, cloud sync, RBAC, team sharing, or remote registry.
- Existing `manifest.json` remains the source of truth for ingested sources; 012 does not add external source root provenance retroactively.
- Existing `ks query` semantics remain unchanged; workspace-aware query is a wrapper that selects root first.
- Registry path resolution order: `$HKS_WORKSPACE_REGISTRY` env override → `$XDG_CONFIG_HOME/hks/workspaces.json` → `~/.config/hks/workspaces.json`. Tests MUST use explicit temporary registry paths.
- Source catalog is not a semantic search result filter in MVP; it helps humans/agents choose a runtime/source, while actual query still runs against the selected HKS runtime.
- Future UI/TUI can consume the same CLI/MCP/HTTP catalog contracts but is out of scope for 012.

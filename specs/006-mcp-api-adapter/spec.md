# Feature Specification: Phase 3 階段三 — MCP / API adapter

**Feature Branch**: `006-mcp-api-adapter`
**Created**: 2026-04-26
**Status**: Complete
**Input**: 提供 local-first API / MCP adapter，讓外部 agent 能以穩定介面呼叫現有 `ks ingest`、`ks query`、`ks lint`；不引入雲端服務、不做 UI、不改既有 CLI JSON contract。

## Clarifications

### Session 2026-04-26

- Q: MCP tool 成功回應是否包 adapter envelope？ → A: 不包；成功回應直接是現有 HKS `QueryResponse`，只有錯誤使用 adapter error envelope。
- Q: Streamable HTTP transport 是否屬 MCP MVP？ → A: 是；MCP MVP 必須支援 stdio 與 loopback Streamable HTTP，HTTP REST facade 仍是 P2 optional。
- Q: path safety 的邊界是什麼？ → A: `hks_ingest.path` 可指向任意本機 file/dir；adapter 不提供讀取 `/ks/` runtime internals 的通用 file API，`ks_root` 只作 runtime root override。

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Agent 透過 MCP 呼叫查詢（Priority: P1）

外部 agent 可以透過本機 MCP server 呼叫 HKS query tool，取得與 `ks query` 相同語意的 JSON response，包含 `answer`、`source`、`confidence`、`trace`。

**Why this priority**：HKS 的產品定位是被 agent 調用；若只剩 CLI，agent integration 仍要自行 shell wrapping，錯誤處理與 schema 驗證會分散。

**Independent Test**：啟動本機 MCP server，對已初始化 `KS_ROOT` 呼叫 query tool，驗證回傳 payload 通過現行 `query-response.schema.json`，且與同問題的 `ks query --writeback=no` route/source 行為一致。

**Acceptance Scenarios**：

1. **Given** 已 ingest 的 `/ks/`，**When** agent 透過 MCP query tool 查 summary 問題，**Then** 回傳 schema-valid JSON，route/source 與 CLI query 一致。
2. **Given** `KS_ROOT` 未初始化，**When** agent 呼叫 query tool，**Then** 回傳結構化錯誤，錯誤碼語意與 CLI `66 NOINPUT` 對齊。

---

### User Story 2 — Agent 透過 MCP 執行 ingest / lint（Priority: P1）

外部 agent 可以透過本機 MCP tool 執行 ingest 與 lint，並取得與 CLI 同一 top-level response contract 的結果。

**Why this priority**：只開 query 會讓 agent 無法維護知識庫；ingest / lint 是 agent workflow 的最小閉環。

**Independent Test**：用 MCP client 對暫存資料夾執行 ingest，再執行 lint，驗證 runtime artifacts 建立、lint 回 `lint_summary`，且 stdout-equivalent payload 通過現行 schema。

**Acceptance Scenarios**：

1. **Given** 一組本機 fixture files，**When** agent 呼叫 MCP ingest tool，**Then** `/ks/` 建立 raw/wiki/graph/vector/manifest artifacts，response 與 CLI ingest contract 一致。
2. **Given** 已初始化且一致的 `/ks/`，**When** agent 呼叫 MCP lint tool，**Then** 回傳 `lint_summary` 且 findings 為空。

---

### User Story 3 — 本機 HTTP API 作為 optional adapter（Priority: P2）

使用者可選擇啟動 local-only HTTP adapter，讓非 MCP client 以 HTTP 呼叫同一組 ingest/query/lint 能力。

**Why this priority**：HTTP API 對泛用 tooling 有價值，但不是 agent-first MVP 的必要條件。

**Independent Test**：啟動只綁定 loopback 的 API server，呼叫 `/query`、`/ingest`、`/lint`，驗證 response 與 CLI/MCP contract 一致。

**Acceptance Scenarios**：

1. **Given** API server 綁定 `127.0.0.1`，**When** 呼叫 `/query`，**Then** 回傳 schema-valid JSON。
2. **Given** 使用者嘗試綁定非 loopback host，**When** 啟動 API server，**Then** 預設拒絕，除非使用者明確覆寫設定。

### Edge Cases

- `KS_ROOT` 未初始化：adapter MUST 回傳與 CLI 對齊的 `NOINPUT` 語意，不產生半初始化資料層。
- ingest / lint 併發：adapter MUST 沿用現有 `.lock` 行為，不繞過 CLI/core lock。
- write-back：query adapter 預設 MUST 使用 `writeback=no`，避免 agent 背景查詢默默寫入 wiki。
- 路徑安全：ingest path MUST 經本機路徑檢查；不得允許讀取 `/ks/` contract 外的 runtime internals 作為 tool output。
- 網路邊界：MCP / API adapter MUST local-first；不得引入 hosted dependency 或 telemetry。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**：系統 MUST 提供本機 MCP server entry point，暴露 `hks_query`、`hks_ingest`、`hks_lint` 三個 tools。
- **FR-002**：MCP tool 成功 response MUST 直接維持現有 CLI top-level JSON contract，不包 adapter-specific envelope，且不新增 `source` / `trace.route` enum。
- **FR-003**：MCP query tool MUST 支援 `question` 與 `writeback` 參數；預設 `writeback=no`。
- **FR-004**：MCP ingest tool MUST 支援本機 file/dir path；支援格式不得超出目前 runtime 已承諾格式。
- **FR-005**：MCP lint tool MUST 支援 `strict`、`severity_threshold`、`fix` 參數，語意對齊 `ks lint`。
- **FR-006**：adapter MUST 重用現有 command/core 層，不得 duplicate query / ingest / lint 邏輯。
- **FR-007**：adapter MUST 將 CLI exit code 語意映射為結構化 tool error；成功 response 仍回 schema-valid payload。
- **FR-008**：HTTP API 若納入 006，MUST 預設只綁定 loopback，且 endpoint 語意與 MCP tools 對齊。
- **FR-009**：本 spec MUST NOT 實作 UI、雲端部署、多使用者 / RBAC、多 agent orchestration。
- **FR-010**：adapter MUST 可在 airgapped 環境執行；不得新增對外網路需求。
- **FR-011**：MCP server MUST 支援 stdio 與 Streamable HTTP transport；Streamable HTTP 預設只綁定 loopback。
- **FR-012**：adapter MUST 驗證本機 path 參數；`hks_ingest.path` 可指向任意本機 file/dir，但 adapter 不得提供讀取 `/ks/` runtime internals 的通用 file API。

### Key Entities

- **AdapterRequest**：外部呼叫 adapter 的結構化輸入；包含 tool name、arguments、`KS_ROOT` context。
- **AdapterError**：adapter 錯誤結果；保留 CLI error code/hint 語意，並可攜帶 schema-valid error `QueryResponse`。
- **ToolDefinition**：MCP tool metadata；描述 tool name、input schema、output contract。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**：MCP query / ingest / lint 三個 tools 的成功 response 100% 通過現行 JSON schema。
- **SC-002**：同一 fixture 與同一 query 下，MCP query 與 CLI query 的 `trace.route`、`source`、exit/error 語意一致。
- **SC-003**：`KS_ROOT` 未初始化、lock contention、usage error 三類錯誤皆有自動化測試覆蓋。
- **SC-004**：adapter 測試在 `HKS_EMBEDDING_MODEL=simple` 與 no-network monkeypatch 下通過。
- **SC-005**：既有 `uv run pytest --tb=short -q`、`uv run ruff check .`、`uv run mypy src/hks` 全數通過。
- **SC-006**：adapter wrapper overhead 對 query/lint p95 < 250ms（不含底層 command 執行時間），並以自動化 regression 測試覆蓋。

## Assumptions

- 006 的 MVP 是 MCP server；HTTP API 是 P2 optional，不阻塞 MCP MVP。
- Adapter 是 local process，不處理 auth / RBAC；安全邊界由 local-only、path checks、lock 與 explicit user launch 承擔。
- `ks query` 在 adapter 中預設 `writeback=no`，由 caller 明確要求才可改為 `auto|yes|ask`。
- 006 不更動 storage schema、不新增 graph/vector/wiki runtime layout。

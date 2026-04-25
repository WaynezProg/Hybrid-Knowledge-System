# Tasks: Phase 3 階段三 — MCP / API adapter

**Input**: Design documents from `/specs/006-mcp-api-adapter/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 本 feature 明確要求 MCP/adapter contract、integration、offline/error path 測試；測試任務列於各 user story implementation 前。

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 新增 adapter dependency、entry points、contract loaders。

- [x] T001 Add `mcp` dependency and `hks-mcp` entry point in pyproject.toml
- [x] T002 [P] Add adapter package skeleton in src/hks/adapters/__init__.py
- [x] T003 [P] Add contract loading helpers for specs/006-mcp-api-adapter/contracts/ in src/hks/adapters/contracts.py
- [x] T004 [P] Add JSON schema contract tests for specs/006-mcp-api-adapter/contracts/mcp-tools.schema.json and adapter-error.schema.json in tests/contract/test_mcp_contract.py
- [x] T005 [P] Add HTTP OpenAPI parse/shape smoke test for specs/006-mcp-api-adapter/contracts/http-api.openapi.yaml in tests/contract/test_http_api_contract.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 建立共用 adapter request/response/error wrapper；所有 tools 共用，不含 MCP transport。

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T006 Implement AdapterError and tool input models in src/hks/adapters/models.py
- [x] T007 Implement `ks_root` scoped environment/context helper in src/hks/adapters/core.py
- [x] T008 Implement command invocation wrappers for query/ingest/lint in src/hks/adapters/core.py
- [x] T009 Map KSError and usage validation errors to adapter error envelope in src/hks/adapters/core.py
- [x] T010 [P] Add unit tests proving successful wrapper output is direct QueryResponse payload in tests/unit/adapters/test_core.py
- [x] T011 [P] Add unit tests for adapter error envelope and exit code mapping in tests/unit/adapters/test_errors.py
- [x] T012 [P] Add unit tests for adapter usage validation and path safety in tests/unit/adapters/test_validation.py
- [x] T013 [P] Add no-network adapter core regression in tests/integration/test_mcp_offline.py

**Checkpoint**: adapter core 可在不啟動 MCP server 的情況下呼叫現有 command/core 並回傳穩定 payload/error。

---

## Phase 3: User Story 1 — Agent 透過 MCP 呼叫查詢 (Priority: P1) MVP

**Goal**: MCP server exposes `hks_query` with schema-valid output and safe `writeback=no` default.

**Independent Test**: 啟動 in-process MCP server/client，呼叫 `hks_query`，驗證 response 通過 canonical HKS response schema，且 route/source 與 CLI query 一致。

### Tests for User Story 1

- [x] T014 [P] [US1] Add contract test for `hks_query` input defaults and schema in tests/contract/test_mcp_query_contract.py
- [x] T015 [P] [US1] Add MCP query integration test using initialized fixture runtime in tests/integration/test_mcp_query.py
- [x] T016 [P] [US1] Add MCP query NOINPUT/error-envelope integration test in tests/integration/test_mcp_query.py
- [x] T017 [P] [US1] Add MCP query usage-error integration test for invalid writeback in tests/integration/test_mcp_query.py
- [x] T018 [P] [US1] Add regression proving `hks_query` default does not write back pages in tests/integration/test_mcp_query.py

### Implementation for User Story 1

- [x] T019 [US1] Implement FastMCP server factory and `hks_query` tool in src/hks/adapters/mcp_server.py
- [x] T020 [US1] Implement stdio and streamable-http transport CLI parsing for `hks-mcp` in src/hks/adapters/mcp_server.py
- [x] T021 [US1] Enforce loopback-only host default for streamable-http in src/hks/adapters/mcp_server.py
- [x] T022 [US1] Add query adapter examples to specs/006-mcp-api-adapter/quickstart.md

**Checkpoint**: User Story 1 is independently usable by an MCP client for read-only query.

---

## Phase 4: User Story 2 — Agent 透過 MCP 執行 ingest / lint (Priority: P1)

**Goal**: MCP server exposes `hks_ingest` and `hks_lint` with CLI-aligned semantics.

**Independent Test**: 用 MCP client 呼叫 ingest fixture directory，再呼叫 lint，驗證 artifacts 建立、lint 回 `lint_summary`，所有 payload 通過 schema。

### Tests for User Story 2

- [x] T023 [P] [US2] Add contract tests for `hks_ingest` and `hks_lint` input schemas in tests/contract/test_mcp_ingest_lint_contract.py
- [x] T024 [P] [US2] Add MCP ingest integration test that creates raw/wiki/graph/vector/manifest artifacts in tests/integration/test_mcp_ingest_lint.py
- [x] T025 [P] [US2] Add MCP lint clean-runtime and strict-error integration tests in tests/integration/test_mcp_ingest_lint.py
- [x] T026 [P] [US2] Add MCP ingest/lint lock contention regression in tests/integration/test_mcp_ingest_lint.py
- [x] T027 [P] [US2] Add MCP ingest/lint usage-error integration tests for invalid `pptx_notes`, `severity_threshold`, and `fix` in tests/integration/test_mcp_ingest_lint.py

### Implementation for User Story 2

- [x] T028 [US2] Implement `hks_ingest` tool in src/hks/adapters/mcp_server.py
- [x] T029 [US2] Implement `hks_lint` tool in src/hks/adapters/mcp_server.py
- [x] T030 [US2] Validate `pptx_notes`, `severity_threshold`, and `fix` values before invoking command wrappers in src/hks/adapters/core.py
- [x] T031 [US2] Preserve 005 lint fix allowlist behavior through adapter tests and wrappers in src/hks/adapters/core.py
- [x] T032 [US2] Add ingest/lint adapter examples to specs/006-mcp-api-adapter/quickstart.md

**Checkpoint**: User Stories 1 and 2 provide complete MCP MVP.

---

## Phase 5: User Story 3 — 本機 HTTP API 作為 optional adapter (Priority: P2)

**Goal**: Optional loopback HTTP facade exposes `/query`, `/ingest`, `/lint` over the same adapter core.

**Independent Test**: 啟動 loopback HTTP server，呼叫 endpoints，驗證 response/error shape 與 MCP/CLI contract 一致。

### Tests for User Story 3

- [x] T033 [P] [US3] Add HTTP query/ingest/lint contract tests against specs/006-mcp-api-adapter/contracts/http-api.openapi.yaml in tests/contract/test_http_api_contract.py
- [x] T034 [P] [US3] Add loopback HTTP integration tests for `/query`, `/ingest`, `/lint` in tests/integration/test_http_adapter.py
- [x] T035 [P] [US3] Add non-loopback host rejection test in tests/integration/test_http_adapter.py

### Implementation for User Story 3

- [x] T036 [US3] Implement optional Starlette app factory in src/hks/adapters/http_server.py
- [x] T037 [US3] Add and implement `hks-api` entry point with loopback-only default in pyproject.toml and src/hks/adapters/http_server.py
- [x] T038 [US3] Map adapter error envelope to HTTP 400/500 responses without changing payload semantics in src/hks/adapters/http_server.py
- [x] T039 [US3] Add HTTP adapter examples to specs/006-mcp-api-adapter/quickstart.md

**Checkpoint**: HTTP adapter is usable but remains secondary to MCP MVP.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, regression, and final verification before merge.

- [x] T040 [P] Update readme.md and README.en.md with MCP adapter usage and safety defaults
- [x] T041 [P] Update docs/main.md and docs/PRD.md to mark 006 status and adapter boundaries
- [x] T042 [P] Add or update mypy missing-import override for `mcp` only if required in pyproject.toml
- [x] T043 Run `.specify/scripts/bash/check-prerequisites.sh --json --include-tasks --require-tasks`
- [x] T044 Run `/speckit.analyze` equivalent consistency check across spec.md, plan.md, tasks.md and repair high/critical drift
- [x] T045 Run `uv run pytest --tb=short -q`, `uv run ruff check .`, and `uv run mypy src/hks`
- [x] T046 Smoke-test quickstart with `HKS_EMBEDDING_MODEL=simple` and temporary `KS_ROOT`
- [x] T047 Add adapter wrapper overhead regression for query/lint p95 < 250ms in tests/integration/test_mcp_performance.py

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1) → Foundational (Phase 2) → US1 / US2 → US3 → Polish.
- US1 and US2 both depend on adapter core from Phase 2.
- US3 depends on adapter core and can reuse US1/US2 wrappers; it does not block MCP MVP.

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational; no dependency on US2.
- **US2 (P1)**: Can start after Foundational; no dependency on US1 except shared MCP server factory.
- **US3 (P2)**: Starts after adapter core; preferably after US1/US2 to avoid REST-first drift.

## Parallel Opportunities

- T002–T005 can run in parallel after T001.
- T010–T013 can run in parallel after T006–T009.
- T014–T018 can run in parallel before T019.
- T023–T027 can run in parallel before T028.
- T033–T035 can run in parallel before T036.
- T040–T042 can run in parallel during Polish.

## Implementation Strategy

### MVP First

Complete Phase 1 + Phase 2 + US1 + US2. This delivers the agent-facing MCP MVP: query, ingest, lint over local MCP with stable HKS contracts.

### Incremental Delivery

1. Build adapter core and contract tests.
2. Add `hks_query` MCP tool and prove safe read-only default.
3. Add `hks_ingest` / `hks_lint` tools for closed-loop knowledge maintenance.
4. Add optional HTTP REST facade only after MCP MVP is green.
5. Update docs and run full verification.

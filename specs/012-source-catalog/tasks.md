# Tasks: Source catalog and workspace selection

**Input**: Design documents from `/specs/012-source-catalog/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/  
**Tests**: Tests are required because 012 adds CLI/MCP/HTTP contracts, registry persistence, lint behavior, and no-mutation safety.  
**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish schemas, trace kind, and package skeletons before behavior work.

- [x] T001 Add catalog package skeleton in `src/hks/catalog/__init__.py`
- [x] T002 Add workspace package skeleton in `src/hks/workspace/__init__.py`
- [x] T003 [P] Add 012 schema loading helpers in `src/hks/adapters/contracts.py`
- [x] T004 [P] Add canonical query-response schema support for `trace.steps.kind == "catalog_summary"` in `specs/005-phase3-lint-impl/contracts/query-response.schema.json`
- [x] T005 [P] Add contract tests for catalog summary, source catalog, and workspace registry schemas in `tests/contract/test_catalog_contract.py`
- [x] T006 [P] Add MCP catalog tool and HTTP OpenAPI validation tests in `tests/contract/test_catalog_adapter_contract.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core source catalog models, workspace registry models, validation, and atomic registry persistence.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T007 Implement `SourceCatalogEntry`, `SourceDetail`, and `CatalogSummaryDetail` in `src/hks/catalog/models.py`
- [x] T008 Implement `WorkspaceRegistry`, `WorkspaceRecord`, and `WorkspaceStatus` in `src/hks/workspace/models.py`
- [x] T009 Implement conservative source relpath and filter validation in `src/hks/catalog/validation.py`
- [x] T010 Implement workspace id/root/metadata validation in `src/hks/workspace/validation.py`
- [x] T011 Implement registry path resolution, atomic read/write, and corrupt-registry handling in `src/hks/workspace/registry.py`
- [x] T012 [P] Add unit tests for catalog models and serialization in `tests/unit/catalog/test_catalog_models.py`
- [x] T013 [P] Add unit tests for workspace models and serialization in `tests/unit/workspace/test_workspace_models.py`
- [x] T014 [P] Add unit tests for workspace registry atomic writes and corrupt-file handling in `tests/unit/workspace/test_workspace_registry.py`
- [x] T015 [P] Add unit tests for workspace id/root validation in `tests/unit/workspace/test_workspace_validation.py`

**Checkpoint**: Catalog and workspace records can be modeled, validated, persisted, and schema-checked without touching CLI/adapters.

---

## Phase 3: User Story 1 - 查看單一 HKS 已 ingest 資料 (Priority: P1) MVP

**Goal**: `ks source list` returns deterministic manifest-derived source catalog entries without mutating HKS runtime layers.

**Independent Test**: Ingest fixture data, run source list, verify counts/order/metadata and byte-for-byte no mutation of authoritative runtime files.

### Tests for User Story 1

- [x] T016 [P] [US1] Add source list integration test with fixture ingest in `tests/integration/test_source_catalog_cli.py`
- [x] T017 [P] [US1] Add source list no-mutation regression in `tests/integration/test_source_catalog_cli.py`
- [x] T018 [P] [US1] Add source list format and relpath filter tests in `tests/integration/test_source_catalog_cli.py`
- [x] T019 [P] [US1] Add missing manifest noinput test in `tests/integration/test_source_catalog_cli.py`
- [x] T020 [P] [US1] Add catalog service unit tests for sorting/counts/issues in `tests/unit/catalog/test_catalog_service.py`

### Implementation for User Story 1

- [x] T021 [US1] Implement manifest-to-catalog list logic in `src/hks/catalog/service.py`
- [x] T022 [US1] Implement catalog summary response builder in `src/hks/catalog/service.py`
- [x] T023 [US1] Add command wrapper for source list in `src/hks/commands/source.py`
- [x] T024 [US1] Add CLI `ks source list` options in `src/hks/cli.py`

**Checkpoint**: Source list is read-only, deterministic, and usable as the 012 MVP.

---

## Phase 4: User Story 2 - 查看單筆資料細節與關聯 artifacts (Priority: P1)

**Goal**: `ks source show <relpath>` returns one source's metadata and derived artifact references.

**Independent Test**: Show an ingested relpath and compare response detail against `manifest.json` derived fields.

### Tests for User Story 2

- [x] T025 [P] [US2] Add source show happy-path integration test in `tests/integration/test_source_catalog_cli.py`
- [x] T026 [P] [US2] Add unknown relpath noinput test and FR-006 negative test (path-traversal / arbitrary-file-read attempts via `ks source show` MUST be rejected without leaking runtime internals) in `tests/integration/test_source_catalog_cli.py`
- [x] T027 [P] [US2] Add missing derived artifact warning test in `tests/integration/test_source_catalog_cli.py`

### Implementation for User Story 2

- [x] T028 [US2] Implement source detail lookup and integrity status in `src/hks/catalog/service.py`
- [x] T029 [US2] Add command wrapper for source show in `src/hks/commands/source.py`
- [x] T030 [US2] Add CLI `ks source show <relpath>` in `src/hks/cli.py`

**Checkpoint**: Users and agents can inspect one source without opening runtime files directly.

---

## Phase 5: User Story 3 - 管理多個 HKS workspace (Priority: P2)

**Goal**: `ks workspace register/list/show/remove/use` manages named `KS_ROOT` values through an explicit local registry.

**Independent Test**: Register two temp `KS_ROOT` values and verify workspace list/status/use output without mutating registered runtimes.

### Tests for User Story 3

- [x] T031 [P] [US3] Add workspace register/list/show integration tests, including (a) `--force` overwrite returning `previous_root` and (b) conflict envelope (exit `66`) when id exists with a different root, in `tests/integration/test_workspace_cli.py`
- [x] T032 [P] [US3] Add workspace remove integration test in `tests/integration/test_workspace_cli.py`
- [x] T033 [P] [US3] Add workspace use export command test in `tests/integration/test_workspace_cli.py`
- [x] T034 [P] [US3] Add missing/uninitialized/corrupt workspace status tests in `tests/integration/test_workspace_cli.py`
- [x] T035 [P] [US3] Add duplicate root warning test in `tests/integration/test_workspace_cli.py`
- [x] T036 [P] [US3] Add registry no-runtime-mutation regression and stateless `workspace use` regression (no last-used / current pointer file is written; subsequent catalog/workspace/query calls require explicit `workspace_id` or `ks_root`) in `tests/integration/test_workspace_cli.py`

### Implementation for User Story 3

- [x] T037 [US3] Implement workspace register (with `--force` conflict handling and `previous_root` in success detail), list/show/remove/use (stateless — no last-used persistence) service methods in `src/hks/workspace/service.py`
- [x] T038 [US3] Implement workspace status derivation from manifest in `src/hks/workspace/service.py`
- [x] T039 [US3] Add command wrappers in `src/hks/commands/workspace.py`
- [x] T040 [US3] Add CLI `ks workspace register|list|show|remove|use` (with `--force` flag on `register`) in `src/hks/cli.py`

**Checkpoint**: Users can maintain a stable local list of HKS runtimes and pick one explicitly.

---

## Phase 6: User Story 4 - 選 workspace 後查詢 (Priority: P2)

**Goal**: `ks workspace query <workspace-id> "<question>"` resolves registry entry and delegates to existing query.

**Independent Test**: Query two workspaces with different data and verify each result is scoped to the chosen root.

### Tests for User Story 4

- [x] T041 [P] [US4] Add workspace query scoping integration test in `tests/integration/test_workspace_query.py`
- [x] T042 [P] [US4] Add unknown workspace noinput test in `tests/integration/test_workspace_query.py`
- [x] T043 [P] [US4] Add conflicting workspace/root usage-error test in `tests/integration/test_workspace_query.py`
- [x] T044 [P] [US4] Add writeback=no propagation test in `tests/integration/test_workspace_query.py`

### Implementation for User Story 4

- [x] T045 [US4] Implement scoped workspace query delegation in `src/hks/workspace/service.py`
- [x] T046 [US4] Add command wrapper for workspace query in `src/hks/commands/workspace.py`
- [x] T047 [US4] Add CLI `ks workspace query` in `src/hks/cli.py`

**Checkpoint**: Selection and query are connected without changing existing `ks query`.

---

## Phase 7: User Story 5 - 透過 MCP / HTTP 使用 catalog 與 workspace (Priority: P3)

**Goal**: MCP and HTTP expose catalog/workspace capabilities with CLI-equivalent semantics and adapter error mapping.

**Independent Test**: Call CLI/MCP/HTTP against the same fixture roots and registry and verify matching counts/status/query behavior.

### Tests for User Story 5

- [x] T048 [P] [US5] Add MCP source/workspace integration tests in `tests/integration/test_catalog_mcp.py`
- [x] T049 [P] [US5] Add HTTP catalog/workspace endpoint tests in `tests/integration/test_catalog_http.py`
- [x] T050 [P] [US5] Add CLI/MCP/HTTP semantic consistency tests in `tests/integration/test_catalog_adapter_consistency.py`
- [x] T051 [P] [US5] Add adapter validation/error mapping tests in `tests/contract/test_catalog_adapter_contract.py`

### Implementation for User Story 5

- [x] T052 [US5] Add shared adapter wrappers for source list/show and workspace operations in `src/hks/adapters/core.py`
- [x] T053 [US5] Add MCP tools in `src/hks/adapters/mcp_server.py`
- [x] T054 [US5] Add HTTP endpoints in `src/hks/adapters/http_server.py`
- [x] T055 [US5] Reuse adapter error envelope mapping for catalog/workspace errors in `src/hks/adapters/core.py`

**Checkpoint**: Agent-facing adapter surfaces match CLI semantics.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Lint, docs, regression gates, quickstart smoke, and archive readiness.

- [x] T056 [P] Add workspace registry lint checks in `src/hks/lint/checks.py`
- [x] T057 [P] Register catalog/workspace lint checks in `src/hks/lint/runner.py`
- [x] T058 [P] Update lint summary schema for workspace registry finding categories in `specs/005-phase3-lint-impl/contracts/lint-summary-detail.schema.json`
- [x] T059 [P] Add catalog lint integration tests in `tests/integration/test_catalog_lint.py`
- [x] T059a [P] Add catalog/workspace performance bench tests covering SC-007 (1k-entry synthetic manifest source list ≤ 1.0s, 100-record workspace list ≤ 1.0s on warm local fixtures) in `tests/integration/test_catalog_performance.py`
- [x] T060 [P] Update `README.md` and `README.en.md` with source catalog and workspace selection usage
- [x] T061 [P] Update `docs/main.md`, `docs/PRD.md`, and `CLAUDE.md` (Active Technologies + Recent Changes for 012) with 012 runtime surface, registry boundary, and source semantics
- [x] T062 [P] Update `specs/012-source-catalog/quickstart.md` after implementation details settle
- [x] T063 [P] Add 012 post-implementation notes to `specs/012-source-catalog/speckit-flow.md`
- [x] T064 Run focused 012 tests: `uv run pytest tests/contract/test_catalog_contract.py tests/contract/test_catalog_adapter_contract.py tests/integration/test_source_catalog_cli.py tests/integration/test_workspace_cli.py tests/integration/test_workspace_query.py tests/integration/test_catalog_lint.py tests/integration/test_catalog_mcp.py tests/integration/test_catalog_http.py tests/integration/test_catalog_adapter_consistency.py tests/unit/catalog tests/unit/workspace --tb=short -q`
- [x] T065 Run `uv run pytest --tb=short -q`
- [x] T066 Run `uv run ruff check .`
- [x] T067 Run `uv run mypy src/hks`
- [x] T068 Smoke-test `specs/012-source-catalog/quickstart.md` with `HKS_EMBEDDING_MODEL=simple`, temporary `KS_ROOT`, and temporary `HKS_WORKSPACE_REGISTRY`
- [x] T069 Run `/speckit.analyze` equivalent consistency check across spec.md, plan.md, tasks.md, contracts, and docs; repair high/critical drift before implementation completion
- [x] T070 Add `specs/012-source-catalog/ARCHIVE.md` after runtime/docs/contracts/tests are complete
- [x] T071 Update `specs/ARCHIVE.md` only after 012 is verified and archived

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories.
- **US1 Source List (Phase 3)**: Depends on Foundational; MVP.
- **US2 Source Show (Phase 4)**: Depends on US1 catalog service.
- **US3 Workspace Registry (Phase 5)**: Depends on Foundational; can proceed after US1 interfaces are stable.
- **US4 Workspace Query (Phase 6)**: Depends on US3 registry resolution and existing query service.
- **US5 Adapters (Phase 7)**: Depends on CLI/service semantics from US1-US4.
- **Polish (Phase 8)**: Depends on selected stories being complete.

### User Story Dependencies

- **US1 (P1)**: Can ship as MVP after Foundational.
- **US2 (P1)**: Requires catalog detail lookup built on US1 models.
- **US3 (P2)**: Can ship after Foundational but needs source count/status helpers from catalog.
- **US4 (P2)**: Requires workspace registry resolution.
- **US5 (P3)**: Requires stable service semantics.

### Parallel Opportunities

- T003-T006 can run in parallel.
- T012-T015 can run in parallel after model interfaces are defined.
- US1 tests T016-T020 can run in parallel before implementation.
- US3 tests T031-T036 can run in parallel.
- US5 adapter tests T048-T051 can run in parallel.
- Documentation T060-T063 can run in parallel after public surface stabilizes.

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete US1 source list.
3. Validate read-only behavior, deterministic ordering, no-mutation behavior, and contract schema.
4. Complete US2 source show.
5. Then add workspace registry and workspace query.

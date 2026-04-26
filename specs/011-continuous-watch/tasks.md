# Tasks: Continuous update / watch workflow

**Input**: Design documents from `/specs/011-continuous-watch/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Tests**: Tests are required because 011 changes CLI/MCP/HTTP contracts, refresh state, lint behavior, and mutation safety.
**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish contracts and domain skeleton before runtime work.

- [x] T001 Add watch package skeleton in `src/hks/watch/__init__.py`
- [x] T002 [P] Add watch schema loading helpers in `src/hks/adapters/contracts.py`
- [x] T003 [P] Add canonical query-response schema support for `trace.steps.kind == "watch_summary"` in `specs/005-phase3-lint-impl/contracts/query-response.schema.json`
- [x] T004 [P] Add contract tests for watch summary, watch plan, watch run, and watch latest schemas in `tests/contract/test_watch_contract.py`
- [x] T005 [P] Add MCP watch tool schema tests in `tests/contract/test_watch_adapter_contract.py`
- [x] T006 [P] Add OpenAPI validation for `http-watch-api.openapi.yaml` in `tests/contract/test_watch_adapter_contract.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core watch data model, persistence, locking, and deterministic planning shared by all stories.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T007 Implement `WatchRequest`, `WatchSource`, `RefreshPlan`, `RefreshAction`, `WatchRun`, and `WatchSummaryDetail` in `src/hks/watch/models.py`
- [x] T008 Implement watch state paths and atomic persistence in `src/hks/watch/store.py`
- [x] T009 Implement dedicated watch lock helpers in `src/hks/watch/store.py`
- [x] T010 Implement watch artifact schema validation in `src/hks/watch/validation.py`
- [x] T011 Implement deterministic plan id and fingerprint helpers in `src/hks/watch/planner.py`
- [x] T012 [P] Add unit tests for watch models and serialization in `tests/unit/watch/test_watch_models.py`
- [x] T013 [P] Add unit tests for watch store atomic writes, latest pointer, and lock conflicts in `tests/unit/watch/test_watch_store.py`
- [x] T014 [P] Add unit tests for plan fingerprint stability in `tests/unit/watch/test_watch_planner.py`

**Checkpoint**: Watch artifacts can be modeled, validated, stored, fingerprinted, and locked without calling HKS pipelines.

---

## Phase 3: User Story 1 - 掃描變更並產生 refresh plan (Priority: P1) MVP

**Goal**: `ks watch scan` returns a deterministic refresh plan without mutating authoritative HKS layers.

**Independent Test**: Modify a source in fixture `KS_ROOT`, run scan, verify stale counts/actions and no mutation to wiki/graph/vector/manifest/graphify.

### Tests for User Story 1

- [x] T015 [P] [US1] Add scan stale/unchanged/new/missing integration tests with explicit source roots in `tests/integration/test_watch_cli.py`
- [x] T016 [P] [US1] Add scan no-mutation regression in `tests/integration/test_watch_cli.py`
- [x] T017 [P] [US1] Add corrupt/unsupported source scan tests in `tests/integration/test_watch_cli.py`
- [x] T018 [P] [US1] Add lineage stale detection tests for 008/009/010 artifacts in `tests/unit/watch/test_watch_lineage.py`
- [x] T019 [P] [US1] Add scanner unit tests for sha256 and parser fingerprint comparison in `tests/unit/watch/test_watch_scanner.py`

### Implementation for User Story 1

- [x] T020 [US1] Implement filesystem and manifest scanner with explicit source root handling in `src/hks/watch/scanner.py`
- [x] T021 [US1] Implement 008 extraction, 009 wiki candidate/page, and 010 graphify lineage inspection in `src/hks/watch/lineage.py`
- [x] T022 [US1] Implement refresh plan action generation in `src/hks/watch/planner.py`
- [x] T023 [US1] Implement scan orchestration and response builder in `src/hks/watch/service.py`
- [x] T024 [US1] Add CLI `ks watch scan` namespace and `--source-root` option in `src/hks/cli.py`
- [x] T025 [US1] Add command wrapper for scan in `src/hks/commands/watch.py`

**Checkpoint**: Scan is read-only, deterministic, and useful as MVP.

---

## Phase 4: User Story 2 - 明確觸發 bounded refresh run (Priority: P1)

**Goal**: `ks watch run --mode execute --profile ingest-only` executes caller-approved refresh actions through existing services and records auditable run state.

**Independent Test**: Create stale source, execute ingest-only run, verify manifest/wiki/vector update through ingest behavior and watch run state records completed action.

### Tests for User Story 2

- [x] T026 [P] [US2] Add dry-run no-mutation regression in `tests/integration/test_watch_run.py`
- [x] T027 [P] [US2] Add ingest-only execute integration test in `tests/integration/test_watch_run.py`
- [x] T028 [P] [US2] Add graphify refresh profile integration test in `tests/integration/test_watch_run.py`
- [x] T029 [P] [US2] Add failed action retry-state regression in `tests/integration/test_watch_run.py`
- [x] T030 [P] [US2] Add concurrent watch run lock conflict test in `tests/integration/test_watch_run.py`
- [x] T031 [P] [US2] Add executor unit tests for profile/action permission rules in `tests/unit/watch/test_watch_executor.py`

### Implementation for User Story 2

- [x] T032 [US2] Implement bounded action executor using existing ingest service in `src/hks/watch/executor.py`
- [x] T033 [US2] Implement optional 008/009/010 action dispatch with existing service calls in `src/hks/watch/executor.py`
- [x] T034 [US2] Enforce dry-run and profile mutation boundaries in `src/hks/watch/executor.py`
- [x] T035 [US2] Implement run orchestration, action state updates, and retry-safe summaries in `src/hks/watch/service.py`
- [x] T036 [US2] Add CLI `ks watch run` options including `--source-root` in `src/hks/cli.py`
- [x] T037 [US2] Add command wrapper for run in `src/hks/commands/watch.py`

**Checkpoint**: Bounded run can refresh stale sources while preserving explicit mutation boundaries.

---

## Phase 5: User Story 3 - 查看 watch 狀態與歷史 (Priority: P2)

**Goal**: `ks watch status` reports latest plan/run state, counts, failures, and retry hints.

**Independent Test**: Run scan and execute/dry-run flows, then status returns latest ids, counts, blocked failures, and artifact references.

### Tests for User Story 3

- [x] T038 [P] [US3] Add status after scan and run integration tests in `tests/integration/test_watch_cli.py`
- [x] T039 [P] [US3] Add status failed-run reporting test in `tests/integration/test_watch_run.py`
- [x] T040 [P] [US3] Add corrupt watch state handling test in `tests/integration/test_watch_lint.py`

### Implementation for User Story 3

- [x] T041 [US3] Implement status summary loading in `src/hks/watch/service.py`
- [x] T042 [US3] Add CLI `ks watch status` in `src/hks/cli.py`
- [x] T043 [US3] Add command wrapper for status in `src/hks/commands/watch.py`
- [x] T044 [US3] Add watch lint checks for corrupt artifacts, partial runs, and latest mismatch in `src/hks/lint/checks.py`
- [x] T045 [US3] Register watch lint checks in `src/hks/lint/runner.py`
- [x] T046 [US3] Update lint summary schema for watch finding categories in `specs/005-phase3-lint-impl/contracts/lint-summary-detail.schema.json`

**Checkpoint**: Watch state is observable and lint-detectable.

---

## Phase 6: User Story 4 - 透過 MCP / HTTP 觸發同一 watch 能力 (Priority: P2)

**Goal**: MCP and loopback HTTP expose the same watch scan/run/status capability and contracts as CLI.

**Independent Test**: Call CLI/MCP/HTTP against the same fixture and verify matching summary semantics and adapter error mapping.

### Tests for User Story 4

- [x] T047 [P] [US4] Add MCP scan/run/status integration tests in `tests/integration/test_watch_mcp.py`
- [x] T048 [P] [US4] Add HTTP `/watch/scan`, `/watch/run`, and `/watch/status` integration tests in `tests/integration/test_watch_http.py`
- [x] T049 [P] [US4] Add CLI/MCP/HTTP semantic consistency tests in `tests/integration/test_watch_adapter_consistency.py`
- [x] T050 [P] [US4] Add adapter usage and validation error tests in `tests/contract/test_watch_adapter_contract.py`

### Implementation for User Story 4

- [x] T051 [US4] Add shared adapter wrappers `hks_watch_scan`, `hks_watch_run`, and `hks_watch_status` in `src/hks/adapters/core.py`
- [x] T052 [US4] Add MCP tools `hks_watch_scan`, `hks_watch_run`, and `hks_watch_status` in `src/hks/adapters/mcp_server.py`
- [x] T053 [US4] Add HTTP endpoints `/watch/scan`, `/watch/run`, and `/watch/status` in `src/hks/adapters/http_server.py`
- [x] T054 [US4] Reuse adapter error envelope mapping for watch errors in `src/hks/adapters/core.py`

**Checkpoint**: Agent-facing adapter surfaces match CLI semantics.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, regression gates, quickstart smoke, and archive readiness.

- [x] T055 [P] Update `README.md` and `README.en.md` with watch scan/run/status usage and safety boundaries
- [x] T056 [P] Update `docs/main.md` and `docs/PRD.md` with 011 runtime layout, status, and source semantics
- [x] T057 [P] Update `specs/011-continuous-watch/quickstart.md` after implementation details settle
- [x] T058 [P] Add 011 post-implementation notes to `specs/011-continuous-watch/speckit-flow.md`
- [x] T059 Run `uv run pytest tests/contract/test_watch_contract.py tests/contract/test_watch_adapter_contract.py tests/integration/test_watch_cli.py tests/integration/test_watch_run.py tests/integration/test_watch_lint.py tests/integration/test_watch_mcp.py tests/integration/test_watch_http.py tests/integration/test_watch_adapter_consistency.py tests/unit/watch`
- [x] T060 Run `uv run pytest --tb=short -q`
- [x] T061 Run `uv run ruff check .`
- [x] T062 Run `uv run mypy src/hks`
- [x] T063 Smoke-test `specs/011-continuous-watch/quickstart.md` with `HKS_EMBEDDING_MODEL=simple` and temporary `KS_ROOT`
- [x] T064 Add `specs/011-continuous-watch/ARCHIVE.md` after runtime/docs/contracts/tests are complete
- [x] T065 Update `specs/ARCHIVE.md` only after 011 is verified and archived

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories.
- **US1 Scan (Phase 3)**: Depends on Foundational; MVP.
- **US2 Run (Phase 4)**: Depends on US1 planning/scanning.
- **US3 Status/Lint (Phase 5)**: Depends on watch store and benefits from US1/US2 artifacts.
- **US4 Adapters (Phase 6)**: Depends on CLI/service semantics from US1-US3.
- **Polish (Phase 7)**: Depends on selected stories being complete.

### User Story Dependencies

- **US1 (P1)**: Can ship as MVP after Foundational.
- **US2 (P1)**: Requires US1 plan generation.
- **US3 (P2)**: Requires persisted state from Foundational and US1/US2.
- **US4 (P2)**: Requires stable service/command semantics.

### Parallel Opportunities

- T002-T006 can run in parallel.
- T012-T014 can run in parallel after T007-T011 interfaces are defined.
- US1 tests T015-T019 can run in parallel before implementation.
- US2 tests T026-T031 can run in parallel before implementation.
- US4 adapter tests T047-T050 can run in parallel.
- Documentation T055-T058 can run in parallel after public surface stabilizes.

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete US1 scan only.
3. Validate read-only scan, deterministic fingerprint, no-mutation behavior, and contract schema.
4. Then proceed to US2 bounded execution.

### Incremental Delivery

1. US1 gives safe visibility into stale sources.
2. US2 adds caller-approved execution.
3. US3 adds status/lint observability.
4. US4 exposes the same capability to agents through MCP/HTTP.

### Validation Gates

Do not archive 011 until `uv run pytest --tb=short -q`, `uv run ruff check .`, `uv run mypy src/hks`, targeted watch tests, and quickstart smoke are green.

# Tasks: Phase 3 階段三 — Multi-agent support

**Input**: Design documents from `/specs/007-multi-agent-support/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 007 requires contract, unit, integration, MCP, and concurrency regression tests because correctness depends on machine-readable contracts and atomic lease behavior.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add coordination schemas, package skeleton, and schema loaders.

- [x] T001 Add coordination package skeleton in src/hks/coordination/__init__.py
- [x] T002 [P] Add schema loading helpers for specs/007-multi-agent-support/contracts/ in src/hks/adapters/contracts.py
- [x] T003 [P] Add contract tests for coordination-summary-detail.schema.json and coordination-ledger.schema.json in tests/contract/test_coordination_contract.py
- [x] T004 [P] Add contract tests for mcp-coordination-tools.schema.json in tests/contract/test_coordination_mcp_contract.py
- [x] T005 Update canonical query-response schema to allow `trace.steps.kind == "coordination_summary"` in specs/005-phase3-lint-impl/contracts/query-response.schema.json

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement ledger models, validation, storage, and response shaping shared by all stories.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T006 Implement AgentSession, CoordinationLease, HandoffNote, ResourceReference, CoordinationEvent models in src/hks/coordination/models.py
- [x] T007 Implement agent_id/resource_key validation in src/hks/coordination/models.py
- [x] T008 Implement coordination runtime paths in src/hks/coordination/store.py
- [x] T009 Implement locked JSON state + JSONL event persistence in src/hks/coordination/store.py
- [x] T010 Map ledger missing/corrupt/validation errors to KSError exit semantics in src/hks/coordination/store.py
- [x] T011 Implement QueryResponse builder with `coordination_summary` detail in src/hks/commands/coord.py
- [x] T012 [P] Add unit tests for model validation in tests/unit/coordination/test_models.py
- [x] T013 [P] Add unit tests for store read/write, event append, and corrupt ledger handling in tests/unit/coordination/test_store.py
- [x] T014 [P] Add contract test proving coordination response validates against canonical QueryResponse in tests/contract/test_coordination_contract.py

**Checkpoint**: coordination state can be read/written safely and returned as schema-valid HKS response without CLI/MCP transport.

---

## Phase 3: User Story 1 — Agent 宣告工作身份與心跳 (Priority: P1) MVP

**Goal**: `ks coord session` supports start, heartbeat, close, and status.

**Independent Test**: Two agents can start sessions in the same `KS_ROOT`; heartbeat updates last_seen_at; stale sessions are derived by TTL.

### Tests for User Story 1

- [x] T015 [P] [US1] Add CLI integration tests for session start/heartbeat/status in tests/integration/test_coordination_cli.py
- [x] T016 [P] [US1] Add stale session TTL regression in tests/unit/coordination/test_service.py
- [x] T017 [P] [US1] Add invalid agent_id usage-error tests in tests/integration/test_coordination_cli.py

### Implementation for User Story 1

- [x] T018 [US1] Implement session start/heartbeat/close/status service methods in src/hks/coordination/service.py
- [x] T019 [US1] Add `ks coord session start|heartbeat|close` commands in src/hks/cli.py and src/hks/commands/coord.py
- [x] T020 [US1] Add `ks coord status` command in src/hks/cli.py and src/hks/commands/coord.py
- [x] T021 [US1] Ensure all session writes append CoordinationEvent in src/hks/coordination/service.py

**Checkpoint**: User Story 1 is independently usable by CLI for agent presence.

---

## Phase 4: User Story 2 — Agent 對工作資源取得 lease (Priority: P1)

**Goal**: Agents can claim, renew, release, and expire resource leases atomically.

**Independent Test**: Concurrent claims for the same resource produce exactly one active owner; release/expiry allows a later claim.

### Tests for User Story 2

- [x] T022 [P] [US2] Add lease claim/renew/release CLI integration tests in tests/integration/test_coordination_cli.py
- [x] T023 [P] [US2] Add concurrent claim regression with 100 attempts in tests/integration/test_coordination_concurrency.py
- [x] T024 [P] [US2] Add lease conflict structured-response test in tests/integration/test_coordination_cli.py
- [x] T025 [P] [US2] Add expired lease takeover unit test in tests/unit/coordination/test_service.py

### Implementation for User Story 2

- [x] T026 [US2] Implement lease claim/renew/release/expire service methods in src/hks/coordination/service.py
- [x] T027 [US2] Add `ks coord lease claim|renew|release` commands in src/hks/cli.py and src/hks/commands/coord.py
- [x] T028 [US2] Implement active-owner conflict response in src/hks/commands/coord.py
- [x] T029 [US2] Ensure lease claim decision and state write happen under coordination lock in src/hks/coordination/store.py

**Checkpoint**: User Stories 1 and 2 provide the CLI MVP for multi-agent coordination.

---

## Phase 5: User Story 3 — Agent 留下 handoff note (Priority: P2)

**Goal**: Agents can add and list structured handoff notes.

**Independent Test**: Agent A creates a handoff with references; Agent B lists it by resource_key and receives schema-valid detail.

### Tests for User Story 3

- [x] T030 [P] [US3] Add handoff add/list CLI integration tests in tests/integration/test_coordination_cli.py
- [x] T031 [P] [US3] Add missing reference lint test in tests/integration/test_coordination_lint.py
- [x] T032 [P] [US3] Add handoff schema validation tests in tests/unit/coordination/test_models.py

### Implementation for User Story 3

- [x] T033 [US3] Implement handoff add/list service methods in src/hks/coordination/service.py
- [x] T034 [US3] Add `ks coord handoff add|list` commands in src/hks/cli.py and src/hks/commands/coord.py
- [x] T035 [US3] Implement coordination lint for missing references and stale leases in src/hks/coordination/lint.py
- [x] T036 [US3] Add `ks coord lint` command in src/hks/cli.py and src/hks/commands/coord.py

**Checkpoint**: CLI supports presence, ownership, handoff, and ledger lint.

---

## Phase 6: User Story 4 — MCP / HTTP adapter 暴露 coordination 能力 (Priority: P2)

**Goal**: MCP tools expose the same coordination operations as CLI; optional HTTP facade can follow after MCP.

**Independent Test**: MCP claim/status and CLI status see the same ledger state for one `KS_ROOT`.

### Tests for User Story 4

- [x] T037 [P] [US4] Add MCP coordination tool contract tests in tests/contract/test_coordination_mcp_contract.py
- [x] T038 [P] [US4] Add MCP session/lease/handoff integration tests in tests/integration/test_coordination_mcp.py
- [x] T039 [P] [US4] Add MCP/CLI consistency test for same `KS_ROOT` in tests/integration/test_coordination_mcp.py
- [x] T040 [P] [US4] Add optional HTTP coordination endpoint tests only if HTTP facade is implemented in tests/integration/test_coordination_http.py

### Implementation for User Story 4

- [x] T041 [US4] Add hks_coord_session MCP tool in src/hks/adapters/mcp_server.py
- [x] T042 [US4] Add hks_coord_lease MCP tool in src/hks/adapters/mcp_server.py
- [x] T043 [US4] Add hks_coord_handoff MCP tool in src/hks/adapters/mcp_server.py
- [x] T044 [US4] Add hks_coord_status MCP tool in src/hks/adapters/mcp_server.py
- [x] T045 [US4] Reuse adapter error envelope mapping for coordination errors in src/hks/adapters/core.py
- [x] T046 [US4] Optionally add loopback-only HTTP coordination endpoints in src/hks/adapters/http_server.py

**Checkpoint**: MCP clients can use all 007 MVP coordination primitives.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, consistency, and final verification before implementation branch completion.

- [x] T047 [P] Update readme.md and README.en.md with `ks coord` and MCP coordination usage
- [x] T048 [P] Update docs/main.md and docs/PRD.md to mark 007 status and remaining Phase 3 boundaries
- [x] T049 [P] Update specs/ARCHIVE.md only after implementation is complete and verified
- [x] T050 Run `.specify/scripts/bash/check-prerequisites.sh --json --include-tasks --require-tasks`
- [x] T051 Run `/speckit.analyze` equivalent consistency check across spec.md, plan.md, tasks.md and repair high/critical drift
- [x] T052 Run `uv run pytest --tb=short -q`, `uv run ruff check .`, and `uv run mypy src/hks`
- [x] T053 Smoke-test quickstart with `HKS_EMBEDDING_MODEL=simple` and temporary `KS_ROOT`
- [x] T054 Re-run 005 lint regression suite after adding `coordination_summary`: `tests/contract/test_lint_contract.py`, `tests/integration/test_lint_findings.py`, `tests/integration/test_lint_fix.py`, `tests/integration/test_lint_strict.py`
- [x] T055 Re-run 006 adapter regression suite after adding coordination tools: `tests/contract/test_mcp_contract.py`, `tests/integration/test_mcp_query.py`, `tests/integration/test_mcp_ingest_lint.py`, `tests/integration/test_http_adapter.py`, `tests/integration/test_mcp_performance.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup → Foundational → US1 / US2 → US3 → US4 → Polish.
- US1 and US2 both depend on Foundational.
- US3 depends on Foundational; it benefits from US1 session identity but must remain testable with caller-provided `agent_id`.
- US4 depends on command/service wrappers from US1-US3.

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational; no dependency on leases or handoffs.
- **US2 (P1)**: Can start after Foundational; no dependency on sessions if caller provides `agent_id`, but session_id integration should be supported.
- **US3 (P2)**: Can start after Foundational; references may point to sessions/leases/handoffs but are weak references.
- **US4 (P2)**: Starts after CLI/service behavior is stable to avoid adapter-first drift.

### Parallel Opportunities

- T002-T004 can run in parallel after T001.
- T012-T014 can run in parallel after T006-T011.
- T015-T017 can run in parallel before T018.
- T022-T025 can run in parallel before T026.
- T030-T032 can run in parallel before T033.
- T037-T040 can run in parallel before T041.

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational.
2. Complete US1 session presence.
3. Complete US2 atomic resource lease.
4. Validate CLI MVP before adding handoff or MCP expansion.

### Full 007 Before Merge

1. Add US3 handoff and coordination lint.
2. Add US4 MCP tools.
3. Update docs and run full verification.
4. Do not archive 007 until implementation and smoke tests pass.

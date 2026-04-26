# Tasks: Graphify pipeline

**Input**: Design documents from `/specs/010-graphify-pipeline/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 010 requires contract, unit, CLI, MCP, HTTP, lint, artifact atomicity, HTML/report, and no-mutation regression tests because it adds a derived graph artifact surface and agent-facing contracts.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add 010 schemas, package skeleton, and contract loading points.

- [x] T001 Add graphify package skeleton in `src/hks/graphify/__init__.py`
- [x] T002 [P] Add schema loading helpers for `specs/010-graphify-pipeline/contracts/` in `src/hks/adapters/contracts.py`
- [x] T003 [P] Add contract tests for graphify summary/run/graph schemas in `tests/contract/test_graphify_contract.py`
- [x] T004 [P] Add MCP tool schema tests for `mcp-graphify-tools.schema.json` in `tests/contract/test_graphify_adapter_contract.py`
- [x] T005 [P] Add OpenAPI validation for `http-graphify-api.openapi.yaml` in `tests/contract/test_graphify_adapter_contract.py`
- [x] T006 Update canonical query-response schema to allow `trace.steps.kind == "graphify_summary"` in `specs/005-phase3-lint-impl/contracts/query-response.schema.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement models, config, builder, clustering, validation, artifact storage, and output rendering shared by all stories.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T007 Implement `GraphifyRequest`, `GraphifyRun`, `GraphifyNode`, `GraphifyEdge`, `GraphifyCommunity`, and `GraphifyAuditFinding` in `src/hks/graphify/models.py`
- [x] T008 Implement provider/env configuration by reusing 008 local-first gates in `src/hks/graphify/config.py`
- [x] T009 Implement runtime input collector for wiki pages, `graph/graph.json`, manifest, and optional 008/009 artifacts in `src/hks/graphify/builder.py`
- [x] T010 Implement deterministic node/edge derivation and input fingerprinting in `src/hks/graphify/builder.py`
- [x] T011 Implement deterministic community clustering in `src/hks/graphify/clustering.py`
- [x] T012 Implement audit finding generation and side-effect text filtering with `side_effect_text_ignored` in `src/hks/graphify/audit.py`
- [x] T013 Implement schema validation wrappers in `src/hks/graphify/validation.py`
- [x] T014 Implement graphify run idempotency, file lock, temp-run writes, atomic finalize, and latest pointer update in `src/hks/graphify/store.py`
- [x] T015 Implement static HTML and Markdown report rendering in `src/hks/graphify/export.py`
- [x] T016 Implement response builder with `graphify_summary` detail in `src/hks/commands/graphify.py`
- [x] T017 [P] Add unit tests for graphify models and idempotency key in `tests/unit/graphify/test_graphify_models.py`
- [x] T018 [P] Add unit tests for provider config safety gates in `tests/unit/graphify/test_graphify_config.py`
- [x] T019 [P] Add unit tests for builder provenance and input fingerprinting in `tests/unit/graphify/test_graphify_builder.py`
- [x] T020 [P] Add unit tests for clustering determinism in `tests/unit/graphify/test_graphify_clustering.py`
- [x] T021 [P] Add unit tests for store atomicity and latest pointer generation in `tests/unit/graphify/test_graphify_store.py`
- [x] T022 [P] Add unit tests for HTML/report rendering without remote dependencies in `tests/unit/graphify/test_graphify_export.py`

**Checkpoint**: Graphify can collect current HKS runtime data, build deterministic graph/community/audit objects, and shape a response without CLI/MCP/HTTP transport.

---

## Phase 3: User Story 1 - 建立 Graphify derived graph artifact (Priority: P1)

**Goal**: `ks graphify build --mode preview` returns a derived graph summary from existing HKS layers without mutating authoritative state.

**Independent Test**: Ingest fixture data, run 008 store and 009 apply, run 010 preview, validate response schemas, and assert wiki/graph/vector/manifest/llm artifacts remain unchanged.

### Tests for User Story 1

- [x] T023 [P] [US1] Add CLI preview integration test in `tests/integration/test_graphify_cli.py`
- [x] T024 [P] [US1] Add no-mutation regression for preview mode in `tests/integration/test_graphify_cli.py`
- [x] T025 [P] [US1] Add missing runtime and no analyzable input error tests in `tests/integration/test_graphify_cli.py`
- [x] T026 [P] [US1] Add invalid graph schema error test in `tests/integration/test_graphify_cli.py`

### Implementation for User Story 1

- [x] T027 [US1] Implement preview orchestration in `src/hks/graphify/service.py`
- [x] T028 [US1] Add `ks graphify build` namespace and options in `src/hks/cli.py`
- [x] T029 [US1] Wire CLI command wrapper in `src/hks/commands/graphify.py`
- [x] T030 [US1] Map missing/invalid runtime and provider errors to HKS `KSError` / exit code semantics in `src/hks/graphify/service.py`
- [x] T031 [US1] Ensure preview response validates against canonical QueryResponse, 010 detail schema, `trace.route="graph"`, `confidence=1.0` for valid runs, and `source` as the actual non-empty subset of stable layers read such as `["wiki","graph"]` or `["wiki"]`; if no stable layer is read, return exit `66` no analyzable input

**Checkpoint**: User Story 1 is independently usable by CLI and provides the 010 MVP preview path.

---

## Phase 4: User Story 2 - 儲存 community clustering 與 JSON export (Priority: P1)

**Goal**: `store` mode persists idempotent graphify run artifacts under `$KS_ROOT/graphify/runs/` without writing authoritative layers.

**Independent Test**: Run store mode twice for the same input and verify one run artifact is reused by idempotency key; latest pointer is valid; authoritative layers remain unchanged.

### Tests for User Story 2

- [x] T032 [P] [US2] Add stored graphify run payload validation test in `tests/contract/test_graphify_contract.py`
- [x] T033 [P] [US2] Add store-mode integration test in `tests/integration/test_graphify_store.py`
- [x] T034 [P] [US2] Add idempotent reuse and force-new-run regression in `tests/integration/test_graphify_store.py`
- [x] T035 [P] [US2] Add concurrent store regression for the same idempotency key in `tests/integration/test_graphify_store.py`
- [x] T036 [P] [US2] Add corrupt/invalid graphify artifact lint-detection test in `tests/integration/test_graphify_lint.py`

### Implementation for User Story 2

- [x] T037 [US2] Implement `mode=store` run write/reuse behavior in `src/hks/graphify/store.py`
- [x] T038 [US2] Integrate store mode into `src/hks/graphify/service.py`
- [x] T039 [US2] Return run artifact references in `graphify_summary` detail from `src/hks/commands/graphify.py`
- [x] T040 [US2] Add graphify run artifact, partial-run, and latest pointer lint checks in `src/hks/lint/checks.py` and `src/hks/lint/runner.py`
- [x] T041 [US2] Update lint detail schema for additive graphify finding categories in `specs/005-phase3-lint-impl/contracts/lint-summary-detail.schema.json`

**Checkpoint**: User Stories 1 and 2 produce reusable, auditable Graphify JSON artifacts without touching authoritative HKS state.

---

## Phase 5: User Story 3 - 產生 HTML visualization 與 audit report (Priority: P2)

**Goal**: Store mode can emit static local `graph.html` and `GRAPH_REPORT.md` from the same graphify run.

**Independent Test**: Run store mode with default outputs, validate files exist, contain no remote script dependency, and report separates extracted/inferred/ambiguous evidence.

### Tests for User Story 3

- [x] T042 [P] [US3] Add HTML artifact generation test in `tests/integration/test_graphify_store.py`
- [x] T043 [P] [US3] Add `--no-html` regression in `tests/integration/test_graphify_store.py`
- [x] T044 [P] [US3] Add Markdown report evidence-class audit test in `tests/integration/test_graphify_store.py`
- [x] T045 [P] [US3] Add no absolute home path leak regression for HTML/report outputs in `tests/integration/test_graphify_store.py`

### Implementation for User Story 3

- [x] T046 [US3] Implement self-contained static HTML rendering in `src/hks/graphify/export.py`
- [x] T047 [US3] Implement Markdown `GRAPH_REPORT.md` rendering in `src/hks/graphify/export.py`
- [x] T048 [US3] Add CLI flags `--html/--no-html` and `--report/--no-report` in `src/hks/cli.py`
- [x] T049 [US3] Include output option fields and artifact paths in graphify run manifest and summary detail

**Checkpoint**: User Stories 1-3 provide complete local Graphify artifacts.

---

## Phase 6: User Story 4 - Agent 透過 CLI / MCP / HTTP 使用同一能力 (Priority: P2)

**Goal**: MCP and loopback HTTP expose the same Graphify build capability and contract as CLI.

**Independent Test**: Run fake-provider preview through CLI, MCP, and HTTP for the same fixture and verify equivalent detail fields.

### Tests for User Story 4

- [x] T050 [P] [US4] Add MCP tool input contract tests in `tests/contract/test_graphify_adapter_contract.py`
- [x] T051 [P] [US4] Add MCP integration tests for preview/store in `tests/integration/test_graphify_mcp.py`
- [x] T052 [P] [US4] Add HTTP loopback endpoint tests for preview, errors, and non-loopback rejection in `tests/integration/test_graphify_http.py`
- [x] T053 [P] [US4] Add CLI/MCP/HTTP semantic consistency test in `tests/integration/test_graphify_adapter_consistency.py`
- [x] T054 [P] [US4] Add hosted-provider-without-opt-in adapter error test in `tests/integration/test_graphify_mcp.py`

### Implementation for User Story 4

- [x] T055 [US4] Add `hks_graphify_build` MCP tool in `src/hks/adapters/mcp_server.py`
- [x] T056 [US4] Add loopback-only `/graphify/build` HTTP endpoint in `src/hks/adapters/http_server.py`
- [x] T057 [US4] Reuse adapter error envelope mapping for graphify errors in `src/hks/adapters/core.py`
- [x] T058 [US4] Ensure adapter success payloads remain direct HKS top-level responses without adapter-specific success envelope

**Checkpoint**: Agent-facing surfaces can consume 010 without shell-only coupling.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, consistency, and final verification before implementation branch completion.

- [x] T059 [P] Update `README.md` and `README.en.md` with `ks graphify build`, preview/store behavior, artifacts, and agent usage
- [x] T060 [P] Update `docs/main.md` and `docs/PRD.md` with 010 runtime layout, source semantics, and remaining 011 boundary
- [x] T061 [P] Add source/route semantics row for `ks graphify build` in `docs/main.md`
- [x] T062 [P] Update `specs/ARCHIVE.md` only after implementation is complete and verified
- [x] T063 Run `.specify/scripts/bash/check-prerequisites.sh --json --include-tasks --require-tasks`
- [x] T064 Run `/speckit.analyze` equivalent consistency check across `spec.md`, `plan.md`, `tasks.md`, contracts, and docs; repair high/critical drift before implementation completion
- [x] T065 Run `uv run pytest --tb=short -q`, `uv run ruff check .`, and `uv run mypy src/hks`
- [x] T066 Smoke-test `specs/010-graphify-pipeline/quickstart.md` with `HKS_EMBEDDING_MODEL=simple`, fake provider, and temporary `KS_ROOT`
- [x] T067 Re-run 008/009 regression suites after consuming their artifacts
- [x] T068 Re-run 005 lint and 006 adapter regression suites after adding graphify trace/contracts
- [x] T069 [P] Add domain-agnostic classification prompt audit unit test if optional LLM classification prompts are implemented

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup -> Foundational -> US1 / US2 -> US3 -> US4 -> Polish.
- US1 and US2 both depend on Foundational.
- US3 depends on stored run behavior from US2.
- US4 depends on CLI/service behavior from US1-US3.

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational; no dependency on stored artifacts.
- **US2 (P1)**: Can start after Foundational and reuse US1 builder output.
- **US3 (P2)**: Starts after run storage is stable.
- **US4 (P2)**: Starts after CLI/service behavior is stable to avoid adapter-first drift.

### Parallel Opportunities

- T002-T005 can run in parallel after T001.
- T017-T022 can run in parallel after T007-T016.
- T023-T026 can run in parallel before T027.
- T032-T036 can run in parallel before T037.
- T042-T045 can run in parallel before T046.
- T050-T054 can run in parallel before T055.
- T059-T061 and T069 can run in parallel after story implementation is stable.

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational.
2. Complete US1 preview/read-only CLI behavior.
3. Validate schema contract and no-mutation regression before adding store/export.

### Full 010 Before Merge

1. Add US2 stored graphify run reuse and lint detection.
2. Add US3 static HTML/report exports.
3. Add US4 MCP / HTTP parity.
4. Update docs and run full verification.
5. Do not archive 010 until implementation, quickstart smoke test, and regression gates pass.

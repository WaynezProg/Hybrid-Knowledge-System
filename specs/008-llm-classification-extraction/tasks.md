# Tasks: LLM-assisted classification and extraction

**Input**: Design documents from `/specs/008-llm-classification-extraction/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 008 requires contract, unit, CLI, MCP, HTTP, and regression tests because it adds a new agent-facing contract and must prove preview mode does not mutate existing knowledge layers.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add 008 schemas, package skeleton, and contract loading points.

- [x] T001 Add LLM package skeleton in `src/hks/llm/__init__.py`
- [x] T002 [P] Add schema loading helpers for `specs/008-llm-classification-extraction/contracts/` in `src/hks/adapters/contracts.py`
- [x] T003 [P] Add contract tests for `llm-extraction-summary-detail.schema.json` and `llm-extraction-artifact.schema.json` in `tests/contract/test_llm_contract.py`
- [x] T004 [P] Add contract tests for `mcp-llm-tools.schema.json` in `tests/contract/test_llm_adapter_contract.py`
- [x] T005 [P] Add OpenAPI contract validation for `http-llm-api.openapi.yaml` in `tests/contract/test_llm_adapter_contract.py`
- [x] T006 Update canonical query-response schema to allow `trace.steps.kind == "llm_extraction_summary"` in `specs/005-phase3-lint-impl/contracts/query-response.schema.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement provider config, models, validation, prompt contract, and read-only orchestration shared by all stories.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T007 Implement `LlmProviderConfig`, `LlmExtractionRequest`, `LlmExtractionResult`, `EntityCandidate`, `RelationCandidate`, and `ExtractionArtifact` models in `src/hks/llm/models.py`
- [x] T008 Implement provider/env configuration and local-first hosted-provider gates in `src/hks/llm/config.py`
- [x] T009 Implement provider protocol and deterministic fake provider in `src/hks/llm/providers.py`
- [x] T010 Implement versioned extraction prompt contract in `src/hks/llm/prompts.py`
- [x] T011 Implement output validation and graph schema normalization checks in `src/hks/llm/validation.py`
- [x] T012 Implement source/manifest resolution for already-ingested sources in `src/hks/llm/service.py`
- [x] T013 Implement QueryResponse builder with `llm_extraction_summary` detail in `src/hks/commands/llm.py`
- [x] T014 [P] Add unit tests for model validation in `tests/unit/llm/test_models.py`
- [x] T015 [P] Add unit tests for provider config safety gates in `tests/unit/llm/test_config.py`
- [x] T016 [P] Add unit tests for fake provider determinism and malformed-output simulation in `tests/unit/llm/test_providers.py`
- [x] T017 [P] Add unit tests for schema validation and unsupported entity/relation rejection in `tests/unit/llm/test_validation.py`

**Checkpoint**: LLM extraction can be represented, validated, and returned as schema-valid HKS response without CLI/MCP/HTTP transport.

---

## Phase 3: User Story 1 - 取得 schema-valid LLM 抽取候選 (Priority: P1)

**Goal**: `ks llm classify` preview returns classification/extraction candidates for an already ingested source without mutating existing knowledge layers.

**Independent Test**: Ingest a fixture source, run preview with fake provider, validate response schemas, and assert wiki / graph / vector / manifest content remains unchanged.

### Tests for User Story 1

- [x] T018 [P] [US1] Add CLI preview integration test in `tests/integration/test_llm_cli.py`
- [x] T019 [P] [US1] Add no-mutation regression for preview mode in `tests/integration/test_llm_no_mutation.py`
- [x] T020 [P] [US1] Add malformed provider output error test in `tests/integration/test_llm_cli.py`
- [x] T021 [P] [US1] Add missing source / missing manifest error tests in `tests/integration/test_llm_cli.py`
- [x] T022 [P] [US1] Add unsafe model side-effect output rejection test in `tests/integration/test_llm_cli.py`

### Implementation for User Story 1

- [x] T023 [US1] Implement preview orchestration in `src/hks/llm/service.py`
- [x] T024 [US1] Add `ks llm classify` namespace and options in `src/hks/cli.py`
- [x] T025 [US1] Wire CLI command wrapper in `src/hks/commands/llm.py`
- [x] T026 [US1] Map provider errors, validation errors, and missing source errors to HKS `KSError` / exit code semantics in `src/hks/llm/service.py`
- [x] T027 [US1] Ensure response validates against canonical QueryResponse and 008 detail schema in `src/hks/commands/llm.py`
- [x] T028 [US1] Reject side-effect instructions or attempted write directives in model output in `src/hks/llm/validation.py` — schema 之外的 free-text 指令（例如「ALSO write to wiki/...」）MUST 被忽略，僅保留 schema-valid 部分；不得僅因 free-text 出現而 fail，但須在 `findings[]` 留下 `code="side_effect_text_ignored"` 紀錄供 audit

**Checkpoint**: User Story 1 is independently usable by CLI and provides the 008 MVP.

---

## Phase 4: User Story 2 - 儲存可追溯 extraction artifact (Priority: P1)

**Goal**: Explicit store mode persists idempotent extraction artifacts under `KS_ROOT/llm/extractions/` without applying them to wiki / graph / vector.

**Independent Test**: Run store mode twice for the same fixture and verify one artifact is reused by idempotency key; force/new-run behavior produces a distinct artifact only when requested.

### Tests for User Story 2

- [x] T029 [P] [US2] Add artifact schema validation test in `tests/contract/test_llm_contract.py`
- [x] T030 [P] [US2] Add store-mode integration test in `tests/integration/test_llm_store.py` — 並斷言 store 執行後 `wiki/`、`graph/graph.json`、`vector/db/` 與 `manifest.json` 與執行前 byte-equal（覆蓋 SC-002 對 store mode 的非變動保證）
- [x] T031 [P] [US2] Add idempotent reuse and schema-version mismatch regression in `tests/integration/test_llm_store.py`
- [x] T032 [P] [US2] Add concurrent store regression for the same idempotency key in `tests/integration/test_llm_store.py`
- [x] T033 [P] [US2] Add partial/corrupt artifact lint-detection test in `tests/integration/test_llm_store.py`

### Implementation for User Story 2

- [x] T034 [US2] Implement extraction artifact path and idempotency key generation in `src/hks/llm/store.py`
- [x] T035 [US2] Implement atomic artifact write and read/reuse behavior in `src/hks/llm/store.py` — 使用既有 coordination lock（007 引入）或 `fcntl` file lock，確保並發 store 對同一 `idempotency_key` 收斂為單一 artifact；late writer 重用既有 artifact 並回 `idempotent_reuse=true`，不重新呼叫 provider
- [x] T036 [US2] Integrate `mode=store` into `src/hks/llm/service.py`
- [x] T037 [US2] Return artifact reference in `llm_extraction_summary` detail from `src/hks/commands/llm.py`
- [x] T038 [US2] Add LLM artifact consistency checks to `src/hks/lint/checks.py` or a dedicated lint hook without changing existing lint semantics

**Checkpoint**: User Stories 1 and 2 provide reusable, auditable extraction candidates for 009/010/011.

---

## Phase 5: User Story 3 - Agent 透過 CLI / MCP / HTTP 使用同一能力 (Priority: P2)

**Goal**: MCP and loopback HTTP expose the same LLM classification/extraction capability and contract as CLI.

**Independent Test**: Run fake-provider extraction through CLI, MCP, and HTTP for the same fixture and verify equivalent extraction detail fields.

### Tests for User Story 3

- [x] T039 [P] [US3] Add MCP tool input contract tests in `tests/contract/test_llm_adapter_contract.py`
- [x] T040 [P] [US3] Add MCP integration tests for preview and store in `tests/integration/test_llm_mcp.py`
- [x] T041 [P] [US3] Add HTTP loopback endpoint tests for preview, errors, 與 non-loopback host 拒絕 in `tests/integration/test_llm_http.py` — non-loopback 拒絕測試應沿用 006 的 `_validate_host` 路徑，覆蓋 US3 Acceptance #2
- [x] T042 [P] [US3] Add CLI/MCP/HTTP semantic consistency test in `tests/integration/test_llm_adapter_consistency.py`
- [x] T043 [P] [US3] Add hosted-provider-without-opt-in adapter error test in `tests/integration/test_llm_mcp.py`

### Implementation for User Story 3

- [x] T044 [US3] Add `hks_llm_classify` MCP tool in `src/hks/adapters/mcp_server.py`
- [x] T045 [US3] Add loopback-only `/llm/classify` HTTP endpoint in `src/hks/adapters/http_server.py`
- [x] T046 [US3] Reuse adapter error envelope mapping for LLM provider/config/validation errors in `src/hks/adapters/core.py`
- [x] T047 [US3] Ensure adapter success payloads remain direct HKS top-level responses without adapter-specific success envelope

**Checkpoint**: Agent-facing surfaces can consume 008 without shell-only coupling.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, consistency, and final verification before implementation branch completion.

- [x] T048 [P] Update `README.md` and `README.en.md` with `ks llm classify`, provider safety, preview/store behavior, and agent usage
- [x] T049 [P] Update `docs/main.md` and `docs/PRD.md` with 008 runtime layout, remaining 009/010/011 boundaries, and local-first provider rules
- [x] T050 [P] Update `specs/ARCHIVE.md` only after implementation is complete and verified
- [x] T051 Run `.specify/scripts/bash/check-prerequisites.sh --json --include-tasks --require-tasks`
- [x] T052 Run `/speckit.analyze` equivalent consistency check across `spec.md`, `plan.md`, `tasks.md`, contracts, and docs; repair high/critical drift before implementation completion
- [x] T053 Run `uv run pytest --tb=short -q`, `uv run ruff check .`, and `uv run mypy src/hks` against `src/hks/` and `tests/`
- [x] T054 Smoke-test `specs/008-llm-classification-extraction/quickstart.md` with `HKS_EMBEDDING_MODEL=simple`, fake provider, and temporary `KS_ROOT`
- [x] T055 Re-run 005 lint contract regression in `tests/contract/test_lint_contract.py`, `tests/integration/test_lint_findings.py`, `tests/integration/test_lint_fix.py`, and `tests/integration/test_lint_strict.py`
- [x] T056 Re-run 006 adapter regression in `tests/contract/test_mcp_contract.py`, `tests/integration/test_mcp_query.py`, `tests/integration/test_mcp_ingest_lint.py`, `tests/integration/test_http_adapter.py`, and `tests/integration/test_mcp_performance.py`
- [x] T057 [P] Add domain-agnostic prompt audit unit test in `tests/unit/llm/test_prompts_domain_agnostic.py` — 掃 `src/hks/llm/prompts.py` 文本，斷言不含特定領域硬編詞（legal、medical、code、specific company / product names），並在多領域 fixture 上跑 fake provider 確認流程不依賴領域字典（覆蓋 FR-018）

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup -> Foundational -> US1 / US2 -> US3 -> Polish.
- US1 and US2 both depend on Foundational.
- US2 depends on US1 response shaping but remains independently testable through store-mode assertions.
- US3 depends on CLI/service behavior from US1 and storage behavior from US2.

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational; no dependency on artifact store.
- **US2 (P1)**: Can start after Foundational and reuse US1 service path.
- **US3 (P2)**: Starts after CLI/service behavior is stable to avoid adapter-first drift.

### Parallel Opportunities

- T002-T005 can run in parallel after T001.
- T014-T017 can run in parallel after T007-T013.
- T018-T022 can run in parallel before T023.
- T029-T033 can run in parallel before T034.
- T039-T043 can run in parallel before T044.
- T048-T049 and T057 can run in parallel after story implementation is stable.

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational.
2. Complete US1 preview/read-only CLI behavior.
3. Validate schema contract and no-mutation regression before adding store mode.

### Full 008 Before Merge

1. Add US2 stored artifact reuse and lint detection.
2. Add US3 MCP / HTTP parity.
3. Update docs and run full verification.
4. Do not archive 008 until implementation, quickstart smoke test, and regression gates pass.

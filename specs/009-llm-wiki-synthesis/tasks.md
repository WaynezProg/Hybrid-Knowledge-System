# Tasks: LLM-assisted wiki synthesis

**Input**: Design documents from `/specs/009-llm-wiki-synthesis/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 009 requires contract, unit, CLI, MCP, HTTP, apply-safety, and no-mutation regression tests because it adds a new agent-facing contract and writes to the wiki only in explicit apply mode.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add 009 schemas, package skeleton, and contract loading points.

- [x] T001 Add wiki synthesis package skeleton in `src/hks/wiki_synthesis/__init__.py`
- [x] T002 [P] Add schema loading helpers for `specs/009-llm-wiki-synthesis/contracts/` in `src/hks/adapters/contracts.py`
- [x] T003 [P] Add contract tests for `wiki-synthesis-summary-detail.schema.json`, `wiki-synthesis-candidate.schema.json`, and `wiki-synthesis-artifact.schema.json` in `tests/contract/test_wiki_synthesis_contract.py`
- [x] T004 [P] Add contract tests for `mcp-wiki-tools.schema.json` in `tests/contract/test_wiki_synthesis_adapter_contract.py`
- [x] T005 [P] Add OpenAPI contract validation for `http-wiki-api.openapi.yaml` in `tests/contract/test_wiki_synthesis_adapter_contract.py`
- [x] T006 Update canonical query-response schema to allow `trace.steps.kind == "wiki_synthesis_summary"` in `specs/005-phase3-lint-impl/contracts/query-response.schema.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement artifact resolution, provider config, models, validation, candidate storage, and wiki origin plumbing shared by all stories.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T007 Implement `WikiSynthesisRequest`, `WikiSynthesisCandidate`, `WikiSynthesisArtifact`, `WikiApplyResult`, `WikiLineage`, and `candidate_artifact_id` apply validation in `src/hks/wiki_synthesis/models.py`
- [x] T008 Implement provider/env configuration by reusing 008 local-first gates in `src/hks/wiki_synthesis/config.py`
- [x] T009 Implement synthesizer protocol and deterministic fake synthesizer in `src/hks/wiki_synthesis/providers.py`
- [x] T010 Implement versioned synthesis prompt contract in `src/hks/wiki_synthesis/prompts.py`
- [x] T011 Implement 008 extraction artifact resolver and stale-source validation in `src/hks/wiki_synthesis/resolver.py`
- [x] T012 Implement candidate schema validation, slug validation, summary confidence derivation, and `side_effect_text_ignored` finding handling in `src/hks/wiki_synthesis/validation.py`
- [x] T013 Implement candidate artifact idempotency, atomic writes, and reuse in `src/hks/wiki_synthesis/store.py`
- [x] T014 Extend `src/hks/storage/wiki.py` to parse/write `origin=llm_wiki` frontmatter fields and skip valid `llm_wiki` pages from raw-source manifest reconciliation while preserving existing `ingest` and `writeback` page compatibility
- [x] T015 Implement response builder with `wiki_synthesis_summary` detail in `src/hks/commands/wiki.py`
- [x] T016 [P] Add unit tests for request/model validation in `tests/unit/wiki_synthesis/test_wiki_synthesis_models.py`
- [x] T017 [P] Add unit tests for provider config safety gates using `HKS_LLM_NETWORK_OPT_IN` and `HKS_LLM_PROVIDER_<ID>_API_KEY` in `tests/unit/wiki_synthesis/test_wiki_synthesis_config.py`
- [x] T018 [P] Add unit tests for fake synthesizer determinism in `tests/unit/wiki_synthesis/test_wiki_synthesis_providers.py`
- [x] T019 [P] Add unit tests for extraction artifact resolver and stale artifact detection in `tests/unit/wiki_synthesis/test_wiki_synthesis_resolver.py`
- [x] T020 [P] Add unit tests for candidate validation and side-effect finding handling in `tests/unit/wiki_synthesis/test_wiki_synthesis_validation.py`
- [x] T021 [P] Add unit tests for candidate store idempotency in `tests/unit/wiki_synthesis/test_wiki_synthesis_store.py`

**Checkpoint**: Wiki synthesis can resolve an 008 artifact, build a schema-valid candidate, and shape a response without CLI/MCP/HTTP transport or wiki writes.

---

## Phase 3: User Story 1 - 預覽 wiki page candidate (Priority: P1)

**Goal**: `ks wiki synthesize --mode preview` returns a wiki page candidate from an existing 008 artifact without mutating runtime knowledge layers.

**Independent Test**: Ingest a fixture, run 008 store, run 009 preview, validate response schemas, and assert wiki / graph / vector / manifest content remains unchanged.

### Tests for User Story 1

- [x] T022 [P] [US1] Add CLI preview integration test in `tests/integration/test_wiki_synthesis_cli.py`
- [x] T023 [P] [US1] Add no-mutation regression for preview mode in `tests/integration/test_wiki_synthesis_no_mutation.py`
- [x] T024 [P] [US1] Add missing extraction artifact error test in `tests/integration/test_wiki_synthesis_cli.py`
- [x] T025 [P] [US1] Add stale extraction artifact error test in `tests/integration/test_wiki_synthesis_cli.py`

### Implementation for User Story 1

- [x] T026 [US1] Implement preview orchestration in `src/hks/wiki_synthesis/service.py`
- [x] T027 [US1] Add `ks wiki synthesize` namespace and options in `src/hks/cli.py`
- [x] T028 [US1] Wire CLI command wrapper in `src/hks/commands/wiki.py`
- [x] T029 [US1] Map missing/stale/invalid artifact and provider errors to HKS `KSError` / exit code semantics in `src/hks/wiki_synthesis/service.py`
- [x] T030 [US1] Ensure preview response validates against canonical QueryResponse, 009 detail schema, `trace.route="wiki"`, and `source=[]` semantics in `src/hks/commands/wiki.py`

**Checkpoint**: User Story 1 is independently usable by CLI and provides the 009 MVP preview path.

---

## Phase 4: User Story 2 - 儲存可審核 wiki synthesis candidate (Priority: P1)

**Goal**: `store` mode persists idempotent wiki synthesis candidate artifacts under `KS_ROOT/llm/wiki-candidates/` without writing authoritative wiki pages.

**Independent Test**: Run store mode twice for the same extraction artifact and verify one candidate artifact is reused by idempotency key; wiki / graph / vector / manifest remain unchanged.

### Tests for User Story 2

- [x] T031 [P] [US2] Add stored candidate artifact payload validation test in `tests/contract/test_wiki_synthesis_contract.py`
- [x] T032 [P] [US2] Add store-mode integration test in `tests/integration/test_wiki_synthesis_store.py`
- [x] T033 [P] [US2] Add idempotent reuse and force-new-run regression in `tests/integration/test_wiki_synthesis_store.py`
- [x] T034 [P] [US2] Add concurrent store regression for the same idempotency key in `tests/integration/test_wiki_synthesis_store.py`
- [x] T035 [P] [US2] Add corrupt/invalid candidate artifact lint-detection test in `tests/integration/test_wiki_synthesis_store.py`

### Implementation for User Story 2

- [x] T036 [US2] Implement `mode=store` candidate write/reuse behavior in `src/hks/wiki_synthesis/store.py`
- [x] T037 [US2] Integrate store mode into `src/hks/wiki_synthesis/service.py`
- [x] T038 [US2] Return candidate artifact reference in `wiki_synthesis_summary` detail from `src/hks/commands/wiki.py`
- [x] T039 [US2] Add wiki synthesis candidate artifact, `origin=llm_wiki` frontmatter, partial-apply, and wiki-to-manifest reconciliation lint checks in `src/hks/lint/checks.py` and `src/hks/lint/runner.py` without changing existing lint finding shapes, strict exit semantics, or fix allowlist behavior
- [x] T040 [US2] Update lint detail schema for additive wiki synthesis artifact finding categories in `specs/005-phase3-lint-impl/contracts/lint-summary-detail.schema.json`

**Checkpoint**: User Stories 1 and 2 produce reusable, auditable wiki candidates without touching authoritative wiki.

---

## Phase 5: User Story 3 - 明確 apply wiki candidate (Priority: P2)

**Goal**: `apply` mode writes an approved candidate to `wiki/pages/`, rebuilds index, appends log, and records provenance while leaving graph/vector/manifest unchanged.

**Independent Test**: Apply one stored candidate and verify page frontmatter, index, log, response detail, conflict behavior, and no mutation outside wiki.

### Tests for User Story 3

- [x] T041 [P] [US3] Add apply integration test requiring stored `candidate_artifact_id` in `tests/integration/test_wiki_synthesis_apply.py`
- [x] T042 [P] [US3] Add apply no-mutation regression for graph/vector/manifest in `tests/integration/test_wiki_synthesis_apply.py`
- [x] T043 [P] [US3] Add slug conflict fail-closed tests for non-`llm_wiki` pages and unequal `(extraction_artifact_id, source_fingerprint, parser_fingerprint)` lineage in `tests/integration/test_wiki_synthesis_apply.py`
- [x] T044 [P] [US3] Add `origin=llm_wiki` parse/write regression in `tests/unit/wiki_synthesis/test_wiki_synthesis_apply.py`
- [x] T045 [P] [US3] Add missing stored candidate, stale candidate, and no-regenerate apply rejection tests in `tests/integration/test_wiki_synthesis_apply.py`

### Implementation for User Story 3

- [x] T046 [US3] Implement apply conflict detection using exact lineage equality and non-`llm_wiki` fail-closed behavior in `src/hks/wiki_synthesis/service.py`
- [x] T047 [US3] Implement explicit wiki page create/update from stored candidate artifacts only in `src/hks/wiki_synthesis/service.py`
- [x] T048 [US3] Rebuild `wiki/index.md`, append `wiki/log.md`, and enforce rollback or lint-detectable partial state for apply in `src/hks/wiki_synthesis/service.py`
- [x] T049 [US3] Return `WikiApplyResult` in `wiki_synthesis_summary` detail and allow `source=["wiki"]` only after a successful wiki write in `src/hks/commands/wiki.py`
- [x] T050 [US3] Ensure apply writes reuse the 008 fcntl-based lock pattern and return `idempotent_apply=true` when a same-lineage candidate was already applied in `src/hks/wiki_synthesis/service.py`

**Checkpoint**: User Stories 1-3 provide the complete CLI wiki synthesis workflow.

---

## Phase 6: User Story 4 - Agent 透過 CLI / MCP / HTTP 使用同一能力 (Priority: P2)

**Goal**: MCP and loopback HTTP expose the same wiki synthesis capability and contract as CLI.

**Independent Test**: Run fake-provider preview through CLI, MCP, and HTTP for the same fixture and verify equivalent detail fields.

### Tests for User Story 4

- [x] T051 [P] [US4] Add MCP tool input contract tests in `tests/contract/test_wiki_synthesis_adapter_contract.py`
- [x] T052 [P] [US4] Add MCP integration tests for preview/store/apply in `tests/integration/test_wiki_synthesis_mcp.py`
- [x] T053 [P] [US4] Add HTTP loopback endpoint tests for preview, errors, and non-loopback rejection in `tests/integration/test_wiki_synthesis_http.py`
- [x] T054 [P] [US4] Add CLI/MCP/HTTP semantic consistency test in `tests/integration/test_wiki_synthesis_adapter_consistency.py`
- [x] T055 [P] [US4] Add hosted-provider-without-opt-in adapter error test in `tests/integration/test_wiki_synthesis_mcp.py`

### Implementation for User Story 4

- [x] T056 [US4] Add `hks_wiki_synthesize` MCP tool in `src/hks/adapters/mcp_server.py`
- [x] T057 [US4] Add loopback-only `/wiki/synthesize` HTTP endpoint in `src/hks/adapters/http_server.py`
- [x] T058 [US4] Reuse adapter error envelope mapping for wiki synthesis errors in `src/hks/adapters/core.py`
- [x] T059 [US4] Ensure adapter success payloads remain direct HKS top-level responses without adapter-specific success envelope

**Checkpoint**: Agent-facing surfaces can consume 009 without shell-only coupling.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, consistency, and final verification before implementation branch completion.

- [x] T060 [P] Update `README.md` and `README.en.md` with `ks wiki synthesize`, preview/store/apply behavior, and agent usage
- [x] T061 [P] Update `docs/main.md` and `docs/PRD.md` with 009 runtime layout, remaining 010/011 boundaries, and write safety rules
- [x] T062 [P] Update `specs/ARCHIVE.md` only after implementation is complete and verified
- [x] T063 Run `.specify/scripts/bash/check-prerequisites.sh --json --include-tasks --require-tasks`
- [x] T064 Run `/speckit.analyze` equivalent consistency check across `spec.md`, `plan.md`, `tasks.md`, contracts, and docs; repair high/critical drift before implementation completion
- [x] T065 Run `uv run pytest --tb=short -q`, `uv run ruff check .`, and `uv run mypy src/hks` against `src/hks/` and `tests/`
- [x] T066 Smoke-test `specs/009-llm-wiki-synthesis/quickstart.md` with `HKS_EMBEDDING_MODEL=simple`, fake provider, and temporary `KS_ROOT`
- [x] T067 Re-run 008 LLM extraction regression suite after consuming extraction artifacts
- [x] T068 Re-run 005 lint and 006 adapter regression suites after adding wiki synthesis trace/contracts
- [x] T069 [P] Add domain-agnostic prompt audit unit test in `tests/unit/wiki_synthesis/test_wiki_synthesis_prompts_domain_agnostic.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup -> Foundational -> US1 / US2 -> US3 -> US4 -> Polish.
- US1 and US2 both depend on Foundational.
- US3 depends on candidate generation and storage behavior from US1/US2.
- US4 depends on CLI/service behavior from US1-US3.

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational; no dependency on candidate storage.
- **US2 (P1)**: Can start after Foundational and reuse US1 candidate generation.
- **US3 (P2)**: Starts after candidate generation is stable; apply must fail closed on conflicts/stale candidates.
- **US4 (P2)**: Starts after CLI/service behavior is stable to avoid adapter-first drift.

### Parallel Opportunities

- T002-T005 can run in parallel after T001.
- T016-T021 can run in parallel after T007-T015.
- T022-T025 can run in parallel before T026.
- T031-T035 can run in parallel before T036.
- T041-T045 can run in parallel before T046.
- T051-T055 can run in parallel before T056.
- T058-T059 must run after T056-T057 because adapter envelope reuse and success-payload parity require both MCP and HTTP surfaces to exist.
- T060-T061 and T069 can run in parallel after story implementation is stable.

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational.
2. Complete US1 preview/read-only CLI behavior.
3. Validate schema contract and no-mutation regression before adding store/apply.

### Full 009 Before Merge

1. Add US2 stored candidate reuse and lint detection.
2. Add US3 explicit wiki apply with provenance and conflict checks.
3. Add US4 MCP / HTTP parity.
4. Update docs and run full verification.
5. Do not archive 009 until implementation, quickstart smoke test, and regression gates pass.

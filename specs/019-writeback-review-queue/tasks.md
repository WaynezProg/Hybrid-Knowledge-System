# Tasks: 019 Write-back Review Queue

**Input**: `specs/019-writeback-review-queue/spec.md`, `specs/019-writeback-review-queue/plan.md`  
**Prerequisites**: Current `main` at or after commit `6107966`, with low-risk README/dependency cleanup handled as a separate commit if committing.  
**Tests**: Required. 019 changes public CLI behavior, query response schema, adapter response schema, eval semantics, and wiki mutation safety.  
**Organization**: Tasks are grouped by dependency order. Each phase must pass its focused tests before moving on.

## Phase 1: Contract Baseline

**Purpose**: Lock the public shape before runtime changes.

- [x] T001 Update `tests/contract/test_query_phase1_contract_preserved.py` to reject `calibrated_confidence` and accept raw `retrieval_score`
- [x] T002 Update `specs/005-phase3-lint-impl/contracts/query-response.schema.json` to remove `calibrated_confidence`, keep `writeback_eligible`, and allow raw `retrieval_score`
- [x] T003 Update `src/hks/core/schema.py` so `QueryResponse.to_dict()` never emits `calibrated_confidence`
- [x] T004 Run `uv run pytest tests/contract/test_query_phase1_contract_preserved.py tests/contract/test_json_schema.py -q`

**Checkpoint**: Contract tests fail before T002/T003 and pass after them.

## Phase 2: Queue Storage

**Purpose**: Add deterministic review queue persistence without touching query behavior.

- [x] T005 Create `tests/unit/writeback/test_queue.py` with tests for deterministic id, evidence-sensitive id changes, enqueue created/deduped, approved archive already-promoted, rejected archive requeue, sorted list, load missing id, and archive missing id
- [x] T006 Create `src/hks/writeback/queue.py` with `WritebackQueueItem`, `EnqueueResult`, `build_item()`, `enqueue()`, `list_pending()`, `load()`, and `archive()`
- [x] T007 Use `sha256(json.dumps(..., sort_keys=True, separators=(",", ":")))[:24]` over question, answer, route, and normalized evidence for item ids
- [x] T008 Store pending items in `$KS_ROOT/writeback/queue/<id>.json` and decided items in `$KS_ROOT/writeback/archive/<id>.json`
- [x] T009 Wrap enqueue/archive in `blocking_file_lock($KS_ROOT/writeback/.locks/<id>.lock)` and use `atomic_write()` for JSON writes
- [x] T010 Run `uv run pytest tests/unit/writeback/test_queue.py -q`

**Checkpoint**: Queue can be tested independently of CLI and wiki writer.

## Phase 3: Confidence and Gate Semantics

**Purpose**: Preserve auto safety while removing misleading calibrated naming.

- [x] T011 Update `tests/unit/retrieval/test_confidence.py` to assert `ConfidenceAssessment.confidence`
- [x] T012 Add confidence unit coverage for invalid `<writeback>` provenance
- [x] T013 Modify `src/hks/retrieval/confidence.py`: rename `calibrated_confidence` to `confidence`, keep internal `_AUTO_THRESHOLDS`, keep `auto_threshold` internal, and mark `<writeback>` evidence ineligible
- [x] T014 Update `tests/unit/writeback/test_gate.py` and `tests/unit/writeback/test_gate_assessment.py` for intent actions `enqueue`, `skip`, and `skip-non-tty`
- [x] T015 Modify `src/hks/writeback/gate.py` so `decide()` no longer evaluates confidence and never returns direct commit actions
- [x] T016 Run `uv run pytest tests/unit/retrieval/test_confidence.py tests/unit/writeback/test_gate.py tests/unit/writeback/test_gate_assessment.py -q`

**Checkpoint**: `writeback_eligible` still represents auto eligibility; gate only expresses caller intent.

## Phase 4: Query Enqueue

**Purpose**: Stop query from writing wiki pages directly.

- [x] T017 Update `tests/integration/test_writeback.py::test_writeback_yes_overrides_non_tty` to expect queue item creation, trace status `enqueued`, no wiki page count increase, and no `forced_writeback` coordination event when `events.jsonl` exists
- [x] T018 Update auto ineligible integration test to expect trace status `skipped-ineligible` and zero queue files
- [x] T019 Update default/no/ask integration tests to assert no queue files and no wiki page count increase unless user confirms `ask`
- [x] T020 Add dedup integration test: same `ks query --writeback=yes` twice produces one queue file and second trace status `enqueued-deduped`
- [x] T021 Modify `src/hks/commands/query.py`: replace `_maybe_writeback()` with `_maybe_enqueue()`
- [x] T022 Remove `_record_forced_writeback_event()` and all calls to `commit()` from query flow
- [x] T023 In `_maybe_enqueue()`, build queue item from question, response, and assessment reasons; map queue statuses to trace statuses
- [x] T024 Append wiki `log.md` status `enqueued` only when queue result is `created`
- [x] T025 Add `enqueued`, `approved`, and `rejected` to `EventStatus` in `src/hks/storage/wiki.py`
- [x] T026 Run `uv run pytest tests/integration/test_writeback.py tests/unit/commands/test_writeback_context.py -q`

**Checkpoint**: `ks query` can create queue files but cannot create wiki pages through writeback.

## Phase 5: Promote Writer

**Purpose**: Make approval the only wiki mutation path for writeback.

- [x] T027 Replace `tests/unit/writeback/test_writer.py` direct `commit()` tests with `promote()` tests
- [x] T028 Add `promote()` happy-path test for `## 來源依據`, real source frontmatter, `origin=writeback`, `writeback_query`, approved log, and related links
- [x] T029 Add `promote()` hard-gate tests for empty evidence, missing `source_relpath`, missing `quote`, and `source_relpath="<writeback>"`
- [x] T030 Add slug conflict tests: `origin=ingest` raises `CONFLICT`; `origin=writeback` and `origin=llm_wiki` overwrite same slug
- [x] T031 Modify `src/hks/writeback/writer.py`: remove `commit()`, keep `WritebackContext`, add `valid_evidence_items()` and `promote()`
- [x] T032 In `promote()`, use first valid evidence item for page `source_relpath`; do not fallback to `<writeback>`
- [x] T033 In `promote()`, include answer body, `## 來源依據`, and existing related page links
- [x] T034 Run `uv run pytest tests/unit/writeback/test_writer.py -q`

**Checkpoint**: Invalid queue items may exist for review, but cannot be approved into wiki.

## Phase 6: `ks writeback` CLI

**Purpose**: Add reviewer-facing queue management.

- [x] T035 Create `tests/unit/commands/test_writeback_cli.py` for list/show/approve/reject JSON shape and missing-id errors
- [x] T036 Create `src/hks/commands/writeback.py` with `list_pending`, `show`, `approve`, and `reject` handlers returning `QueryResponse`
- [x] T037 Register `writeback_app` in `src/hks/cli.py`
- [x] T038 Add CLI subcommands `ks writeback list`, `ks writeback show <id>`, `ks writeback approve <id>`, and `ks writeback reject <id>`
- [x] T039 Update `tests/contract/test_exit_codes.py` for missing writeback id error payload and exit code `66`
- [x] T040 Run `uv run pytest tests/unit/commands/test_writeback_cli.py tests/contract/test_exit_codes.py -q`

**Checkpoint**: Queue can be reviewed and decided entirely through CLI.

## Phase 7: End-to-End Writeback Flow

**Purpose**: Prove query → queue → approve/reject behavior with real ingest fixture.

- [x] T041 Add integration test: `ks query --writeback=yes` creates queue item and `ks writeback approve <id>` writes evidence-backed page then moves item to archive
- [x] T042 Add integration test: `ks writeback reject <id>` moves item to archive and does not write wiki
- [x] T043 Add integration test: approving item with invalid evidence fails and leaves pending item available for reject
- [x] T044 Add integration test: approved item blocks identical re-enqueue with trace status `already-promoted`
- [x] T045 Run `uv run pytest tests/integration/test_writeback.py -q`

**Checkpoint**: 019's core user workflow works without adapter involvement.

## Phase 8: Adapter and Eval Alignment

**Purpose**: Keep API/MCP and quality gates aligned with the new writeback model.

- [x] T046 Remove `calibrated_confidence` from `specs/006-mcp-api-adapter/contracts/http-api.openapi.yaml`
- [x] T047 Update contract tests under `tests/contract/test_http_api_contract.py` and `tests/contract/test_mcp_query_contract.py`
- [x] T048 Add HTTP adapter integration smoke: query with `writeback=yes` creates queue item and no wiki page
- [x] T049 Add MCP query integration smoke: query with `writeback=yes` creates queue item and no wiki page
- [x] T050 Modify `src/hks/evaluation/retrieval_quality.py`: rename `_auto_committed()` to `_auto_enqueued()` and detect `enqueued`, `enqueued-deduped`, `already-promoted`
- [x] T051 Update `tests/unit/evaluation/test_retrieval_quality.py` for auto enqueue false-positive semantics
- [x] T052 Update `tests/eval/test_golden_retrieval_quality.py` with isolated `writeback=auto` smoke for one ineligible case
- [x] T053 Run `uv run pytest tests/contract/test_http_api_contract.py tests/contract/test_mcp_query_contract.py tests/integration/test_http_adapter.py tests/integration/test_mcp_query.py tests/unit/evaluation/test_retrieval_quality.py tests/eval/test_golden_retrieval_quality.py -q`

**Checkpoint**: Query adapters inherit queue behavior; eval no longer talks about direct auto commit.

## Phase 9: Docs and Final Gates

**Purpose**: Align user-facing docs and run full verification.

- [x] T054 Update `README.md` writeback section with queue workflow and confidence fields
- [x] T055 Update `README.en.md` with the same behavior
- [x] T056 Update `docs/main.md` write-back contract and runtime layout
- [x] T057 Update `specs/019-writeback-review-queue/spec.md` post-implementation status after verification
- [x] T058 Run focused writeback tests: `uv run pytest tests/unit/writeback tests/unit/retrieval/test_confidence.py tests/unit/commands/test_writeback_context.py tests/unit/commands/test_writeback_cli.py tests/integration/test_writeback.py -q`
- [x] T059 Run adapter/contract/eval tests: `uv run pytest tests/contract/test_query_phase1_contract_preserved.py tests/contract/test_json_schema.py tests/contract/test_http_api_contract.py tests/contract/test_mcp_query_contract.py tests/integration/test_http_adapter.py tests/integration/test_mcp_query.py tests/unit/evaluation/test_retrieval_quality.py tests/eval/test_golden_retrieval_quality.py -q`
- [x] T060 Run `uv run ruff check .`
- [x] T061 Run `uv run mypy src/hks`
- [x] T062 Run `uv run pytest --tb=short -q`

**Checkpoint**: 019 is implementation-complete only after all gates pass.

## Dependencies

- Phase 1 blocks all runtime work because `QueryResponse` schema drives CLI/adapters/tests.
- Phase 2 blocks Phase 4 and Phase 6 because query and CLI both need queue storage.
- Phase 3 blocks Phase 4 because query enqueue depends on `writeback_eligible` semantics.
- Phase 5 blocks approve command in Phase 6.
- Phase 8 depends on Phase 4 because adapters inherit query behavior.
- Phase 9 depends on all prior phases.

## Parallel Opportunities

- T001-T003 can be split between contract/schema and core dataclass work, but must land together.
- T005 queue tests and T011 confidence tests can be written in parallel.
- T027 writer tests and T035 command tests can be written in parallel after queue interfaces settle.
- Docs T054-T056 can be drafted after CLI output shape stabilizes.

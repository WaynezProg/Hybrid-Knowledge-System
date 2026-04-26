# Tasks: Phase 3 階段二 — `ks lint` 真實實作

**Input**: Design documents from `/specs/005-phase3-lint-impl/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

## Phase 1: Setup

- [X] T001 Update `src/hks/core/schema.py` TraceKind and contract path to allow `lint_summary` from `specs/005-phase3-lint-impl/contracts/query-response.schema.json`
- [X] T002 Add `src/hks/core/lint_contract.py` runtime validator for `specs/005-phase3-lint-impl/contracts/lint-summary-detail.schema.json`
- [X] T003 Replace lint stub contract expectations in `tests/contract/test_lint_stub.py` with real lint-summary assertions
- [X] T004 Add JSON schema regression coverage for `lint_summary` in `tests/contract/test_json_schema.py`

## Phase 2: Foundational

- [X] T005 Add lint dataclasses/enums and fixed severity mapping in `src/hks/lint/models.py`
- [X] T006 Add `src/hks/lint/checks.py` pure check functions for wiki, manifest, vector, graph, and fingerprint findings
- [X] T007 Add `src/hks/lint/runner.py` to build runtime snapshot under `src/hks/core/lock.py` file lock and return `LintSummaryDetail`
- [X] T008 Add `src/hks/lint/fixer.py` to plan/apply allowlisted fix actions only
- [X] T009 Add `src/hks/lint/__init__.py` public exports for runner, models, and fix modes
- [X] T010 Extend `src/hks/storage/vector.py` with `list_ids()` for Chroma chunk enumeration
- [X] T011 Extend `src/hks/graph/store.py` with safe prune helpers for orphan nodes and dangling edges
- [X] T012 Extend `src/hks/storage/wiki.py` LogEntry event/status typing and audit fields to support `event=lint`, `status=lint_fix_applied`, `action`, and `outcome`

## Phase 3: User Story 1 - 列出跨層不一致 findings（P1）

**Independent Test**: `ks lint` on clean runtime emits one `lint_summary` step with empty findings; injected corruptions produce each category with correct severity and target.

- [X] T013 [US1] Implement clean runtime validation and `NOINPUT` missing-layer errors in `src/hks/lint/runner.py`
- [X] T014 [US1] Implement wiki checks `orphan_page`, `dead_link`, and `duplicate_slug` in `src/hks/lint/checks.py`
- [X] T015 [US1] Implement manifest/wiki/raw checks `manifest_wiki_mismatch`, `wiki_source_mismatch`, `dangling_manifest_entry`, and `orphan_raw_source` in `src/hks/lint/checks.py`
- [X] T016 [US1] Implement manifest/vector checks `manifest_vector_mismatch` and `orphan_vector_chunk` in `src/hks/lint/checks.py`
- [X] T017 [US1] Implement graph checks `graph_drift` and corrupt `graph.json` handling in `src/hks/lint/checks.py`
- [X] T018 [US1] Implement `fingerprint_drift` detection using existing parser fingerprint helpers in `src/hks/lint/checks.py`
- [X] T019 [US1] Replace `src/hks/commands/lint.py` stub with real response builder using `LintSummaryDetail`
- [X] T020 [P] [US1] Add unit tests for all check functions in `tests/unit/lint/test_checks.py`
- [X] T021 [P] [US1] Add integration fixtures/injection helpers for each category in `tests/integration/test_lint_findings.py`
- [X] T022 [US1] Add contract validation for `lint-summary-detail.schema.json` in `tests/contract/test_lint_contract.py`

## Phase 4: User Story 2 - CI strict mode（P1）

**Independent Test**: `ks lint --strict` exits `1` only when findings meet threshold; stdout remains schema-valid and identical to non-strict findings.

- [X] T023 [US2] Add Typer options `--strict` and `--severity-threshold=error|warning|info` in `src/hks/cli.py`
- [X] T024 [US2] Implement severity threshold evaluation in `src/hks/lint/runner.py`
- [X] T025 [US2] Implement invalid threshold usage error path with `[ks:lint] usage:` and stdout error JSON in `src/hks/cli.py`
- [X] T026 [P] [US2] Add strict-mode integration tests in `tests/integration/test_lint_strict.py`
- [X] T027 [P] [US2] Extend `tests/contract/test_exit_codes.py` for lint OK, strict fail, usage error, noinput, lock contention, graph corruption, and vector open failure

## Phase 5: User Story 3 - 安全自動修復（P2）

**Independent Test**: `ks lint --fix` produces planned actions with no file changes; `ks lint --fix=apply` applies only allowlisted actions and writes audit log.

- [X] T028 [US3] Add Typer `--fix` option supporting no value, `plan`, and `apply` in `src/hks/cli.py`
- [X] T029 [US3] Implement dry-run fix planning for rebuild index, orphan vector chunks, orphan graph nodes, and orphan graph edges in `src/hks/lint/fixer.py`
- [X] T030 [US3] Implement `rebuild_index` apply path using `WikiStore.rebuild_index()` in `src/hks/lint/fixer.py`
- [X] T031 [US3] Implement `prune_orphan_vector_chunks` apply path using `VectorStore.delete()` in `src/hks/lint/fixer.py`
- [X] T032 [US3] Implement `prune_orphan_graph_nodes` and `prune_orphan_graph_edges` apply paths in `src/hks/lint/fixer.py`
- [X] T033 [US3] Implement `fixes_skipped[]` for non-allowlisted findings and per-action apply failures in `src/hks/lint/fixer.py`
- [X] T034 [US3] Append `lint | lint_fix_applied` audit log entries with action, target, and outcome in `src/hks/lint/fixer.py`
- [X] T035 [US3] Re-scan after `--fix=apply` before evaluating strict exit in `src/hks/lint/runner.py`
- [X] T036 [P] [US3] Add unit tests for fix planning and allowlist behavior in `tests/unit/lint/test_fixer.py`
- [X] T037 [US3] Add integration tests for dry-run checksum stability and apply behavior in `tests/integration/test_lint_fix.py`

## Phase 6: Polish & Regression

- [X] T038 Add airgapped/no-network lint regression in `tests/integration/test_offline.py`
- [X] T039 Add lint wall-clock regression for medium fixture corpus in `tests/integration/test_lint_performance.py`
- [X] T040 Update `README.md`, `README.en.md`, `docs/main.md`, and `docs/PRD.md` to describe real `ks lint`
- [X] T041 Archive or update `specs/004-phase3-image-ingest` references that still call lint a stub
- [X] T042 Run `.specify/scripts/bash/check-prerequisites.sh --json --include-tasks --require-tasks`
- [X] T043 Run `/speckit.analyze` equivalent consistency check and fix any critical/high artifact drift before implementation
- [X] T044 Run `uv run pytest --tb=short -q`, `uv run ruff check .`, and `uv run mypy src/hks`

## Dependencies

- Phase 1 → Phase 2 → US1 / US2 → US3 → Polish.
- US1 is MVP and must complete before US2/US3 because strict/fix both consume findings.
- US2 depends on US1 output only; it can proceed before US3.
- US3 depends on US1 findings and Phase 2 storage helpers.

## Parallel Opportunities

- T020 / T021 / T022 can run after T014–T019 define the first stable model names.
- T026 / T027 can run in parallel after T023–T025.
- T036 can run in parallel with T037 once `src/hks/lint/fixer.py` has public interfaces.

## MVP Scope

Deliver US1 first: real `ks lint` read-only findings with schema-valid `lint_summary`. That alone replaces the stub and gives agent/CI a consumable report. US2 and US3 layer exit-code policy and safe repair on top.

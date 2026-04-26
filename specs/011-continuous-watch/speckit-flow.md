# Speckit Flow: 011 Continuous update / watch workflow

**Branch**: `011-continuous-watch`  
**Started**: 2026-04-26  
**Status**: Complete; archived and merged to `main`

## 010 pre-check

Before starting 011, the repo was on `main` at `origin/main` with clean tracked state and `010-graphify-pipeline` already archived and listed in `specs/ARCHIVE.md`.

Verification run:

```bash
uv run pytest --tb=short -q
```

Result: `335 passed`.

## /speckit.specify

Command:

```bash
.specify/scripts/bash/create-new-feature.sh --json \
  --short-name "continuous-watch" \
  "Add 011 continuous update and watch workflow for HKS. The feature adds a local-first CLI-first watch/re-ingest orchestration layer that detects changed source inputs, schedules deterministic refresh jobs, reuses existing ingest, LLM extraction, wiki synthesis, and graphify build capabilities, records auditable refresh state, exposes adapter-compatible status/trigger controls, preserves stable HKS output contracts, avoids UI/cloud/multi-user scope, and does not silently mutate authoritative layers without explicit configured mode."
```

Result:

- Branch: `011-continuous-watch`
- Spec file: `specs/011-continuous-watch/spec.md`

## /speckit.clarify

Clarifications recorded in `spec.md`:

- 011 MVP is bounded `scan/run/status`, not a resident daemon.
- Default behavior is plan-first; authoritative mutations require explicit caller mode/profile.

No remaining `[NEEDS CLARIFICATION]` markers were left in the spec.

## /speckit.plan

Command:

```bash
.specify/scripts/bash/setup-plan.sh --json
.specify/scripts/bash/update-agent-context.sh claude
```

Generated artifacts:

- `plan.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/watch-summary-detail.schema.json`
- `contracts/watch-plan.schema.json`
- `contracts/watch-run.schema.json`
- `contracts/watch-latest.schema.json`
- `contracts/mcp-watch-tools.schema.json`
- `contracts/http-watch-api.openapi.yaml`

## /speckit.tasks

Generated `tasks.md` with 65 tasks:

- Setup: T001-T006
- Foundational: T007-T014
- US1 scan plan MVP: T015-T025
- US2 bounded run: T026-T037
- US3 status/lint: T038-T046
- US4 MCP/HTTP parity: T047-T054
- Polish / validation / archive readiness: T055-T065

## /speckit.analyze

Analysis ran after `tasks.md` existed. Result:

- Critical issues: 0
- High issues: 0
- Fixed during analysis: external source changes cannot be detected from manifest alone because manifest stores relpaths, not original source roots. Spec, quickstart, contracts, and tasks now require explicit `source_roots` or saved watch config.
- Fixed during user review: added `artifact_counts` to `watch-plan.schema.json`, added `watch-run.schema.json` and `watch-latest.schema.json`, and pinned watch source/route semantics before implementation.
- Requirement coverage: 15/15 functional requirements mapped to tasks
- Main residual risk: implementation must preserve dry-run/no-mutation boundaries and must update canonical trace schemas when adding `watch_summary`.

## /speckit.implement

Implementation completed:

- Added `src/hks/watch/` domain models, store, scanner, lineage inspection, planner, executor, service, and schema validation.
- Added `ks watch scan|run|status`.
- Added MCP tools `hks_watch_scan`, `hks_watch_run`, `hks_watch_status`.
- Added HTTP endpoints `/watch/scan`, `/watch/run`, `/watch/status`.
- Added watch lint checks for invalid artifacts, corrupt state, partial runs, and latest pointer mismatch.
- Updated canonical trace schema with `watch_summary`.
- Updated README, docs, PRD, contracts, quickstart, and archive index.

Validation gates:

- `uv run ruff check .` -> passed
- `uv run mypy src/hks` -> passed
- Targeted watch contract/unit/integration tests -> `30 passed`
- `uv run pytest --tb=short -q` -> `365 passed`
- Quickstart smoke with `HKS_EMBEDDING_MODEL=simple` and temporary `KS_ROOT` -> passed

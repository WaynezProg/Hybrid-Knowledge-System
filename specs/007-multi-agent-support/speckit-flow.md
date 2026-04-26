# Speckit Flow: 007 multi-agent support

**Branch**: `007-multi-agent-support`
**Status**: Complete; implemented, archived, and merged to `main`.
**Last verified**: 2026-04-26

## Command Flow

### `/speckit.specify`

Executed with local repo script:

```bash
.specify/scripts/bash/create-new-feature.sh \
  --json \
  --allow-existing-branch \
  --number 007 \
  --short-name multi-agent-support \
  "Phase 3 multi-agent support for coordinating multiple local agents around the existing HKS CLI/MCP adapter without adding UI, cloud, RBAC, or hosted orchestration"
```

Evidence:
- Branch: `007-multi-agent-support`
- Spec file: `specs/007-multi-agent-support/spec.md`
- Feature number: `007`

### `/speckit.clarify`

Recorded in [spec.md](./spec.md) under `## Clarifications`.

Resolved decisions:
- 007 multi-agent means coordination primitives, not scheduler / supervisor.
- CLI namespace is `ks coord`, not `ks agent`.
- `agent_id` is a local label, not authentication / authorization.
- HTTP facade is P3 optional and does not block CLI + MCP MVP.

### `/speckit.checklist`

Recorded in [checklists/requirements.md](./checklists/requirements.md).

Checklist scope:
- Clarity
- Completeness
- Consistency
- Testability

### `/speckit.plan`

Recorded in:
- [plan.md](./plan.md)
- [research.md](./research.md)
- [data-model.md](./data-model.md)
- [quickstart.md](./quickstart.md)
- [contracts/](./contracts/)

Plan decisions:
- Add `src/hks/coordination/` as the domain layer.
- Persist state under `KS_ROOT/coordination/`.
- Use local JSON state + JSONL event log.
- Add `coordination_summary` as the trace detail kind for coordination responses.

### `/speckit.tasks`

Recorded in [tasks.md](./tasks.md).

Task phases:
- Setup
- Foundational
- US1 session presence
- US2 atomic leases
- US3 handoff notes
- US4 MCP coordination tools
- Polish and verification

### `/speckit.analyze`

Completed checks:
- Template-token scan: no unresolved template markers.
- JSON schema validation: all 007 contract schemas are valid.
- Sample MCP payload validation: session, lease, handoff, status pass; invalid handoff add is rejected.
- Speckit prerequisites: passed with `--include-tasks --require-tasks`.
- Whitespace check: passed with `git diff --check`.
- Static checks: `uv run ruff check .` and `uv run mypy src/hks` passed.
- Cross-artifact drift repair:
  - `spec.md` status is now aligned with the implemented, archived runtime.
  - `specs/ARCHIVE.md` Active section updated to 007.
  - Temporary FR suffix renumbered to stable FR sequence.
  - Lease conflict exit/error semantics clarified.
  - HTTP facade marked optional after CLI + MCP MVP.

### `/speckit.implement`

Completed checks:
- Implemented local coordination ledger, service layer, CLI namespace, MCP tools, and optional HTTP endpoints.
- Added contract, unit, integration, MCP, HTTP, and 100-claim concurrency regression tests.
- Re-ran 005 lint regression suite after adding `coordination_summary`.
- Re-ran 006 adapter regression suite after adding coordination tools.
- Updated user-facing README files, design docs, PRD, tasks, and archive index.

Evidence:
- `uv run pytest --tb=short -q`
- `uv run ruff check .`
- `uv run mypy src/hks`
- quickstart smoke with `HKS_EMBEDDING_MODEL=simple` and temporary `KS_ROOT`

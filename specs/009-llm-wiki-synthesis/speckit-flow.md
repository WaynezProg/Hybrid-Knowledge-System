# Speckit Flow: 009 LLM-assisted wiki synthesis

**Branch**: `009-llm-wiki-synthesis`  
**Date**: 2026-04-26  
**Status**: Complete through `/speckit.implement`.

## Command Flow

### `/speckit.specify`

Executed with local repo script:

```bash
.specify/scripts/bash/create-new-feature.sh \
  --json \
  --short-name "llm-wiki-synthesis" \
  "Add LLM-assisted wiki synthesis for HKS. The feature consumes 008 LLM extraction artifacts and/or runs the existing fake/offline LLM extraction path to generate schema-validated wiki page candidates, preview diffs, and explicitly apply wiki updates with provenance. It must preserve local-first behavior, HKS top-level response contract, write-back safety, lintability, and adapter parity. It must defer Graphify clustering/visualization/audit report to 010 and continuous watch/re-ingest orchestration to 011."
```

Evidence:

- Branch: `009-llm-wiki-synthesis`
- Spec file: `specs/009-llm-wiki-synthesis/spec.md`
- Feature number: `009`

### `/speckit.clarify`

Verified with local repo script:

```bash
.specify/scripts/bash/check-prerequisites.sh --json --paths-only
```

Recorded in [spec.md](./spec.md) under `## Clarifications`.

Resolved decisions:

- 009 consumes 008 stored extraction artifacts; it does not redo extraction.
- 009 does not implement Graphify clustering, HTML visualization, audit report, watch, or daemon behavior.
- Default mode is `preview`; only explicit `apply` writes wiki.
- `apply` mutates only wiki pages, index, and log; it does not update graph, vector, manifest, or 008 artifacts.
- Hosted/network LLM providers remain optional and env-gated; deterministic fake provider is required for tests.

### `/speckit.checklist`

Recorded in [checklists/requirements.md](./checklists/requirements.md).

Checklist scope:

- Content quality
- Requirement completeness
- Testability
- Constitution alignment

### `/speckit.plan`

Executed with local repo script:

```bash
.specify/scripts/bash/setup-plan.sh --json
.specify/scripts/bash/update-agent-context.sh claude
```

Recorded in:

- [plan.md](./plan.md)
- [research.md](./research.md)
- [data-model.md](./data-model.md)
- [quickstart.md](./quickstart.md)
- [contracts/](./contracts/)

Plan decisions:

- Add `src/hks/wiki_synthesis/` as the domain layer.
- Store 009 candidate artifacts under `KS_ROOT/llm/wiki-candidates/`.
- Add `wiki_synthesis_summary` as the trace detail kind.
- Preserve `trace.route="wiki"` and source semantics without adding a new route/source enum.
- Defer Graphify to 010 and continuous update orchestration to 011.

### `/speckit.tasks`

Verified with local repo script:

```bash
.specify/scripts/bash/check-prerequisites.sh --json --include-tasks --require-tasks
```

Recorded in [tasks.md](./tasks.md).

Task phases:

- Setup
- Foundational
- US1 preview wiki candidate
- US2 store auditable candidate
- US3 explicit wiki apply
- US4 CLI/MCP/HTTP adapter parity
- Polish and verification

### `/speckit.analyze`

Completed checks:

- Speckit prerequisites: passed with `--include-tasks --require-tasks`.
- Template-token scan: no unresolved template markers; only literal examples such as `<source-relpath>` remain.
- JSON contract parse: all 009 JSON contracts parse.
- JSON Schema validation: all 009 JSON schemas pass `Draft202012Validator.check_schema`.
- OpenAPI YAML parse: `http-wiki-api.openapi.yaml` parses.
- Task format validation: 69 tasks, sequential IDs, strict checkbox format.
- Constitution check: no CRITICAL violations found.
- Cross-artifact drift repair:
  - Added `wiki-synthesis-artifact.schema.json` to early contract-test task coverage.
  - Added explicit `trace.route` and `source` semantics coverage for FR-008.
  - Clarified FR-008 as MUST semantics and added a source/route meaning table to `docs/main.md`.
  - Aligned HTTP `AdapterError.error.details` back to `type: object`.
  - Defined required `origin=llm_wiki` frontmatter lineage fields.
  - Clarified lint compatibility with existing 005 finding shapes, strict exit semantics, and fix allowlist behavior.
  - Clarified that 009 `apply` is caller-explicit mutation, not Constitution §V automatic query write-back.
  - Resolved B1-B8 medium findings: lineage equality, stored-candidate-only apply, artifact `mode=store`, non-`llm_wiki` conflict handling, `llm_wiki` lint reconciliation, apply atomicity, and concurrent idempotent apply behavior.
  - Resolved C1-C10 low findings: confidence derivation, reused side-effect finding code, explicit hosted-provider env vars, quickstart failure paths, Phase 6 dependency ordering, exit-code table, and `ks wiki` namespace intent.

### `/speckit.implement`

Completed.

Implementation coverage:

- Added `ks wiki synthesize --mode preview|store|apply` with deterministic fake provider, 008 artifact resolver, stale-source checks, candidate storage, and explicit wiki apply.
- Added `hks_wiki_synthesize` MCP tool and `/wiki/synthesize` HTTP endpoint.
- Added `wiki_synthesis_summary` trace detail support and schema validation for candidate, summary, artifact, MCP, HTTP, and canonical query response contracts.
- Extended wiki storage and lint to support `origin=llm_wiki` pages, provenance frontmatter, candidate artifact validation, and conflict-safe apply.
- Updated README, docs, PRD, and task status to reflect 009 runtime behavior.

Verification evidence:

```bash
uv run pytest tests/contract/test_wiki_synthesis_contract.py \
  tests/contract/test_wiki_synthesis_adapter_contract.py \
  tests/integration/test_wiki_synthesis_cli.py \
  tests/integration/test_wiki_synthesis_store.py \
  tests/integration/test_wiki_synthesis_apply.py \
  tests/integration/test_wiki_synthesis_http.py \
  tests/integration/test_wiki_synthesis_mcp.py \
  --tb=short -q
```

Result: `17 passed`.

Full closeout gates:

```bash
uv run ruff check .
uv run mypy src/hks
uv run python -m compileall -q src/hks
uv run pytest --tb=short -q
```

Result: `307 passed`.

Quickstart smoke coverage:

- preview / store / apply / idempotent apply
- missing candidate exit `66`
- hosted provider opt-in exit `2`
- slug conflict exit `1` with `source=[]` and `apply_result.operation="conflict"`

# Speckit Flow: 010 Graphify pipeline

**Branch**: `010-graphify-pipeline`  
**Date**: 2026-04-26  
**Status**: Complete through `/speckit.implement`.

## Pre-flight

009 and current `main` were checked before starting 010:

```bash
git status --short --branch
git log --oneline --decorate -5
uv run ruff check .
uv run mypy src/hks
uv run pytest --tb=short -q
```

Result: clean `main`, 009 merged to `main` / `origin/main`, `ruff` passed, `mypy` passed, `307 passed`.

## Command Flow

### `/speckit.specify`

Executed with local repo script:

```bash
.specify/scripts/bash/create-new-feature.sh \
  --json \
  --number 10 \
  --short-name "graphify-pipeline" \
  "Add Graphify pipeline for HKS. The feature consumes existing HKS wiki pages, graph data, and 008/009 artifacts to build a deterministic local-first knowledge graph analysis pipeline with community clustering, graph summary artifacts, HTML visualization, JSON export, and audit report. It must be CLI-first and adapter-compatible, preserve stable HKS output contracts, not mutate authoritative wiki/graph/vector/manifest unless an explicit future apply mode is specified, and defer continuous watch/re-ingest orchestration to 011."
```

Evidence:

- Branch: `010-graphify-pipeline`
- Spec file: `specs/010-graphify-pipeline/spec.md`
- Feature number: `010`

### `/speckit.clarify`

Verified with local repo script:

```bash
.specify/scripts/bash/check-prerequisites.sh --json --paths-only
```

Recorded in [spec.md](./spec.md) under `## Clarifications`.

Resolved decisions:

- 010 produces derived Graphify artifacts and does not mutate authoritative `graph/graph.json`.
- 010 reads existing HKS layers and artifacts; it does not re-ingest or re-embed.
- 010 does not implement continuous watch / daemon; 011 owns that.
- LLM-assisted classification is optional and env-gated; deterministic local classification is default.
- Static HTML is an artifact, not a server UI.

### `/speckit.checklist`

Recorded in [checklists/requirements.md](./checklists/requirements.md).

Checklist scope:

- Content quality
- Requirement completeness
- Constitution alignment
- Readiness for planning

### `/speckit.plan`

Executed with local repo script:

```bash
.specify/scripts/bash/setup-plan.sh --json
```

Recorded in:

- [plan.md](./plan.md)
- [research.md](./research.md)
- [data-model.md](./data-model.md)
- [quickstart.md](./quickstart.md)
- [contracts/](./contracts/)

Plan decisions:

- Add `src/hks/graphify/` as derived-analysis domain layer.
- Store runs under `$KS_ROOT/graphify/runs/<run-id>/`.
- Add `graphify_summary` trace detail kind.
- Preserve `trace.route="graph"` and stable `source` enum values.
- Defer watch/re-ingest orchestration to 011.

### `/speckit.tasks`

Generated in [tasks.md](./tasks.md).

Task phases:

- Setup
- Foundational
- US1 preview derived graph
- US2 store JSON/community/audit artifacts
- US3 static HTML and Markdown report
- US4 CLI/MCP/HTTP adapter parity
- Polish and verification

### `/speckit.analyze`

Completed checks:

- Speckit prerequisites: passed with `--include-tasks --require-tasks`.
- Template-token scan: no unresolved template markers.
- JSON contract parse: all 010 JSON contracts parse.
- JSON Schema validation: all 010 JSON schemas pass `Draft202012Validator.check_schema`.
- OpenAPI YAML parse: `http-graphify-api.openapi.yaml` parses.
- Task format validation: 69 tasks, sequential IDs, strict checkbox format.
- Constitution check: no CRITICAL violations found.
- Cross-artifact drift repair: aligned source/route semantics, Graphify PRD surface, README onboarding, runtime docs, contracts, and archive status with the completed 010 implementation.
- Post-analysis repair: aligned MCP schema with 008/009 object-map pattern, pinned confidence semantics, concurrent store reuse, `force_new_run` salt, lint severities, partial-run definition, source semantics, hosted-example provider wording, and static HTML rendering direction.

### `/speckit.implement`

Completed.

Implementation coverage:

- Added `ks graphify build --mode preview|store` with deterministic local builder, clustering, audit summary, static HTML, and Markdown report.
- Added `hks_graphify_build` MCP tool and `/graphify/build` HTTP endpoint.
- Added `graphify_summary` trace detail support and schema validation for graphify summary, run, graph, MCP, HTTP, and canonical query response contracts.
- Extended lint to detect graphify partial runs, corrupt graphify artifacts, invalid graphify graph artifacts, and latest pointer mismatch.
- Updated README, docs, PRD, archive, and task status to reflect 010 runtime behavior.

Verification evidence:

```bash
uv run pytest tests/contract/test_graphify_contract.py \
  tests/contract/test_graphify_adapter_contract.py \
  tests/integration/test_graphify_cli.py \
  tests/integration/test_graphify_store.py \
  tests/integration/test_graphify_lint.py \
  tests/integration/test_graphify_http.py \
  tests/integration/test_graphify_mcp.py \
  tests/integration/test_graphify_adapter_consistency.py \
  tests/unit/graphify \
  --tb=short -q
```

Result: `28 passed`.

Final verification:

```bash
uv run ruff check .
uv run mypy src/hks
uv run python -m compileall -q src/hks
uv run pytest --tb=short -q
```

Result: `ruff` passed, `mypy` passed, `compileall` passed, `335 passed`.

Quickstart smoke:

```bash
export KS_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/hks-010-smoke.XXXXXX")
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid
uv run ks llm classify project-atlas.txt --provider fake --mode store
uv run ks wiki synthesize --source-relpath project-atlas.txt --target-slug project-atlas-synthesis --mode store --provider fake
uv run ks wiki synthesize --candidate-artifact-id "$CANDIDATE_ID" --mode apply --provider fake
uv run ks graphify build --mode preview --provider fake
uv run ks graphify build --mode store --provider fake
uv run ks graphify build --mode store --no-html --provider fake
uv run ks graphify build --mode preview --provider hosted-example
```

Result: preview/store passed, no-html store omitted HTML, hosted provider without opt-in returned exit `2`.

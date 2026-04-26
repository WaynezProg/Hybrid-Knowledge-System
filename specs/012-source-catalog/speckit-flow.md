# Speckit Flow: 012 Source catalog and workspace selection

**Branch**: `012-source-catalog`  
**Date**: 2026-04-26  
**Status**: Complete through `/speckit.implement`.

## Pre-flight

Checked before creating 012:

```bash
git status --short --branch
find specs -maxdepth 2 -type f | sort
rg -n "KS_ROOT|source_root|workspace|catalog|manifest" README.md docs/main.md src tests specs
```

Result: clean `main`; 011 exists and is archived; current runtime boundary remains `KS_ROOT` plus `manifest.json`.

## Command Flow

### `/speckit.specify`

Executed with local repo script:

```bash
.specify/scripts/bash/create-new-feature.sh \
  --json \
  --number 12 \
  --short-name source-catalog \
  "Add HKS source catalog and workspace selection so users and agents can see which HKS runtimes exist, inspect what sources each runtime has ingested, choose a target runtime for query, and expose the same read-only catalog through CLI, MCP, and HTTP without mutating wiki, graph, vector, manifest, or watch state."
```

Evidence:

- Branch: `012-source-catalog`
- Spec file: `specs/012-source-catalog/spec.md`
- Feature number: `012`

### `/speckit.clarify`

Clarifications recorded in [spec.md](./spec.md):

- MVP starts with read-only source catalog over one `KS_ROOT`.
- Multi-runtime selection uses workspace registry that maps ids to `KS_ROOT`.
- CLI cannot mutate parent shell; `workspace use` returns export command / resolved root.
- Catalog and registry commands do not mutate HKS authoritative layers.

### `/speckit.checklist`

Recorded in [checklists/requirements.md](./checklists/requirements.md).

Checklist scope:

- Content quality
- Requirement completeness
- Constitution alignment
- Planning readiness

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

- Add `src/hks/catalog/` for read-only manifest-derived source catalog.
- Add `src/hks/workspace/` for local named `KS_ROOT` registry.
- Add `catalog_summary` trace detail kind for list/show/workspace management commands.
- Keep `ks query` unchanged; add `ks workspace query` as explicit wrapper.
- Defer UI/TUI and hidden global current workspace to future specs.

### `/speckit.tasks`

Generated in [tasks.md](./tasks.md).

Task phases:

- Setup
- Foundational
- US1 source list
- US2 source show
- US3 workspace registry
- US4 workspace query
- US5 MCP/HTTP adapter parity
- Polish and verification

### `/speckit.analyze`

Completed before implementation:

- Speckit prerequisites passed with `--include-tasks --require-tasks`.
- Template-token scan found no unresolved placeholders.
- JSON contracts passed `Draft202012Validator.check_schema`.
- OpenAPI YAML parsed successfully.
- Task IDs were sequential.
- Cross-artifact review aligned runtime contract around `catalog_summary`, `HKS_WORKSPACE_REGISTRY`, source catalog read-only behavior, workspace registry conflict semantics, and workspace query delegation.

### `/speckit.implement`

Completed.

Implementation coverage:

- Added `ks source list|show` over manifest-derived source catalog.
- Added `ks workspace register|list|show|remove|use|query` with local JSON registry.
- Added `hks_source_*` and `hks_workspace_*` MCP tools plus `/catalog/*` and `/workspaces/*` HTTP endpoints.
- Added `catalog_summary` trace kind and 012 contract loaders.
- Extended lint to detect corrupt workspace registry, missing workspace roots, and duplicate roots.
- Updated README, README.en.md, docs/main.md, docs/PRD.md, and archive index.

Verification evidence:

```bash
uv run pytest tests/contract/test_catalog_contract.py \
  tests/contract/test_catalog_adapter_contract.py \
  tests/integration/test_source_catalog_cli.py \
  tests/integration/test_workspace_cli.py \
  tests/integration/test_workspace_query.py \
  tests/integration/test_catalog_lint.py \
  tests/integration/test_catalog_mcp.py \
  tests/integration/test_catalog_http.py \
  tests/integration/test_catalog_adapter_consistency.py \
  tests/unit/catalog \
  tests/unit/workspace \
  --tb=short -q
```

Result: `32 passed`.

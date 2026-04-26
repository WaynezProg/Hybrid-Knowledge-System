# Implementation Plan: Source catalog and workspace selection

**Branch**: `012-source-catalog` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/012-source-catalog/spec.md`

## Summary

012 adds a read-only source catalog over existing `manifest.json` and a local workspace registry for named `KS_ROOT` values. It lets users and agents list what data a runtime has ingested, inspect one source's derived artifacts, register/select project workspaces, and run query against an explicit workspace without mixing knowledge bases or mutating authoritative HKS layers.

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`  
**Primary Dependencies**: existing `typer`, `jsonschema`, `mcp`, `starlette`, `python-slugify`; no mandatory new runtime dependency for 012  
**Storage**: read-only access to existing `$KS_ROOT/manifest.json` and artifacts; workspace registry persisted to a local JSON file resolved by precedence `explicit option → $HKS_WORKSPACE_REGISTRY → $XDG_CONFIG_HOME/hks/workspaces.json → ~/.config/hks/workspaces.json`, never inside any registered `KS_ROOT`  
**Testing**: `pytest`, `jsonschema`, contract tests, CLI/MCP/HTTP integration tests, no-mutation regressions, lint regressions  
**Target Platform**: local macOS/Linux shell and local agent clients  
**Project Type**: Python CLI package with MCP / HTTP adapters  
**Performance Goals**: list 1,000 manifest entries in under 1 second on local fixtures; workspace list over 100 records in under 1 second  
**Constraints**: local-first, no network by default, no UI/TUI, no cloud registry, no RBAC, no mutation of authoritative runtime layers, no new top-level `source` or `route` enum  
**Scale/Scope**: personal local workspaces; many named `KS_ROOT` values, one selected workspace per explicit command

## Constitution Check

- **§I Phase Discipline**: PASS。012 是 post-Phase feature，建立在 Phase 1-3 與 008-011 已完成 runtime 上；不回頭削弱既有 graph、MCP/API、watch、write-back 能力。
- **§II Stable Output Contract**: PASS with MINOR extension。Catalog/workspace management commands 保持 QueryResponse top-level shape，新增 `trace.steps.kind="catalog_summary"`；`trace.route="wiki"`、`source=[]` 表示 operational catalog response，不新增 route/source enum。Workspace query 回傳既有 query response。
- **§III CLI-First & Domain-Agnostic**: PASS。入口以 `ks source ...` 與 `ks workspace ...` 為主；MCP/HTTP 只是 adapter parity。無 UI、cloud、RBAC 或領域 hard-code。
- **§IV Ingest-Time Organization**: PASS。012 不 parse、embed、extract 或 re-chunk；source catalog 只讀 manifest 與 artifact references，refresh 仍交給 `ks ingest` / `ks watch`。
- **§V Write-back Safety**: PASS。Catalog/list/show/use 不 write-back；workspace query 明確委派既有 query，caller 仍可使用 `--writeback=no` 或 adapter default。

## Project Structure

### Documentation (this feature)

```text
specs/012-source-catalog/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── catalog-summary-detail.schema.json
│   ├── source-catalog.schema.json
│   ├── workspace-registry.schema.json
│   ├── mcp-catalog-tools.schema.json
│   └── http-catalog-api.openapi.yaml
├── checklists/
│   └── requirements.md
├── speckit-flow.md
└── tasks.md
```

### Source Code (repository root)

```text
src/hks/
├── cli.py                         # add ks source and ks workspace namespaces
├── adapters/
│   ├── contracts.py               # load 012 schemas
│   ├── core.py                    # shared hks_source_* and hks_workspace_* wrappers
│   ├── mcp_server.py              # expose catalog/workspace tools
│   └── http_server.py             # expose /catalog/* and /workspaces/*
├── commands/
│   ├── source.py                  # CLI command wrappers for source catalog
│   └── workspace.py               # CLI command wrappers for workspace registry/query
├── core/
│   └── schema.py                  # add catalog_summary trace kind
├── lint/
│   ├── checks.py                  # workspace registry lint checks
│   └── runner.py
├── catalog/
│   ├── __init__.py
│   ├── models.py                  # SourceCatalogEntry, SourceDetail, CatalogSummaryDetail
│   ├── service.py                 # source list/show, no-mutation catalog reads
│   └── validation.py              # schema validation and relpath filters
└── workspace/
    ├── __init__.py
    ├── models.py                  # WorkspaceRegistry, WorkspaceRecord, WorkspaceStatus
    ├── registry.py                # atomic registry persistence
    ├── service.py                 # list/register/remove/use/query orchestration
    └── validation.py              # workspace id/root validation

tests/
├── contract/
│   ├── test_catalog_contract.py
│   └── test_catalog_adapter_contract.py
├── integration/
│   ├── test_source_catalog_cli.py
│   ├── test_workspace_cli.py
│   ├── test_workspace_query.py
│   ├── test_catalog_lint.py
│   ├── test_catalog_mcp.py
│   ├── test_catalog_http.py
│   └── test_catalog_adapter_consistency.py
└── unit/
    ├── catalog/
    │   ├── test_catalog_models.py
    │   └── test_catalog_service.py
    └── workspace/
        ├── test_workspace_models.py
        ├── test_workspace_registry.py
        └── test_workspace_validation.py
```

**Structure Decision**: Add separate `catalog` and `workspace` domain modules. `catalog` is read-only and scoped to one `KS_ROOT`; `workspace` owns only the registry and root selection. Existing query/ingest/watch services remain the owners of knowledge mutation.

## Complexity Tracking

No constitution violations.

Schema impact tracked separately: 012 adds `trace.steps.kind="catalog_summary"` and workspace registry schemas. It does not add route/source enum values. Catalog/list/show/workspace management commands use `trace.route="wiki"` and `source=[]`; workspace query delegates to existing query and returns normal query semantics.

Cross-spec contract impact: T004 extends `specs/005-phase3-lint-impl/contracts/query-response.schema.json` with the new trace kind, and T058 extends `specs/005-phase3-lint-impl/contracts/lint-summary-detail.schema.json` with workspace-registry finding categories. Both are MINOR additive extensions of the lint/query response contracts originally owned by 005; 005 remains archived but its contract files are intentionally treated as the canonical schema home and must not be moved as part of 012.

Versioning / release notes: per Constitution §II, the `catalog_summary` trace kind and the lint-summary additive enum are MINOR contract extensions. PR description for 012 MUST link Constitution §II, label the change MINOR (not BREAKING), and the docs tasks (T060/T061) MUST add a release-notes / changelog entry summarizing the new trace kind, exit-code reuse (`66` for register conflict), and `--force` semantics.

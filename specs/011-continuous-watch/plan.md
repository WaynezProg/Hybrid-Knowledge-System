# Implementation Plan: Continuous update / watch workflow

**Branch**: `011-continuous-watch` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/011-continuous-watch/spec.md`

## Summary

011 adds a bounded continuous-update workflow for HKS. It detects changed source inputs from explicit source roots or saved watch config, produces a deterministic refresh plan, optionally executes caller-approved refresh actions through existing ingest / 008 / 009 / 010 services, persists auditable watch state, and exposes CLI/MCP/HTTP scan-run-status surfaces without adding a resident daemon or silently mutating authoritative layers.

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`  
**Primary Dependencies**: existing `typer`, `jsonschema`, `mcp`, `starlette`; no mandatory new runtime dependency for 011  
**Storage**: derived operational artifacts under `$KS_ROOT/watch/{plans,runs,latest.json,events.jsonl,config.json}`; no new authoritative layer  
**Testing**: `pytest`, `jsonschema`, contract tests, CLI/MCP/HTTP integration tests, no-mutation scan regressions, bounded-run idempotency regressions  
**Target Platform**: local macOS/Linux shell and local agent clients  
**Project Type**: Python CLI package with MCP / HTTP adapters  
**Performance Goals**: scan 100 manifest entries in under 3 seconds on local fixtures; unchanged scan returns stable plan fingerprint  
**Constraints**: local-first, no network by default, no UI, no cloud scheduler, no multi-user/RBAC, no always-on daemon in MVP, no new top-level `source` enum  
**Scale/Scope**: one local `KS_ROOT`, personal knowledge base scale, one bounded watch run per lock

## Constitution Check

- **§I Phase Discipline**: PASS。011 是 post-Phase feature，依賴 Phase 1-3 與 008-010 已完成能力；不回頭把 watch 行為塞進 query path。
- **§II Stable Output Contract**: PASS with MINOR extension。成功 response 保持 `QueryResponse`；新增 `trace.steps.kind="watch_summary"`。`ks watch scan`、`ks watch run --mode dry-run`、`ks watch status` 使用 `trace.route="wiki"`、`source=[]`；`ks watch run --mode execute --profile ingest-only` 成功使用 `trace.route="wiki"`、`source=["wiki","graph","vector"]` 表示透過既有 ingest 更新穩定層；`derived-refresh` 若觸發 graphify 仍不得把 `"graphify"` 放入 top-level `source`。
- **§III CLI-First & Domain-Agnostic**: PASS。入口以 `ks watch scan|run|status` 為主；MCP/HTTP 是 adapter parity；無 UI、cloud scheduler 或 domain hard-code。
- **§IV Ingest-Time Organization**: PASS。011 不讓 query 觸發 re-parse / re-embedding；refresh 只透過 caller-approved ingest pipeline。
- **§V Write-back Safety**: PASS。scan read-only；run 需要 explicit execution mode；wiki apply 與 graphify store 只在 caller 指定 profile 時發生。

## Project Structure

### Documentation (this feature)

```text
specs/011-continuous-watch/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── watch-summary-detail.schema.json
│   ├── watch-plan.schema.json
│   ├── mcp-watch-tools.schema.json
│   └── http-watch-api.openapi.yaml
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/hks/
├── cli.py                         # add ks watch scan|run|status namespace
├── adapters/
│   ├── contracts.py               # load 011 schemas
│   ├── core.py                    # shared hks_watch_* adapter wrappers
│   ├── mcp_server.py              # expose hks_watch_scan/run/status
│   └── http_server.py             # expose /watch/scan, /watch/run, /watch/status
├── commands/
│   └── watch.py                   # CLI command wrapper layer
├── core/
│   └── schema.py                  # add watch_summary trace kind
├── lint/
│   ├── checks.py                  # watch artifact/latest/partial-run checks
│   └── runner.py
└── watch/
    ├── __init__.py
    ├── models.py                  # source/plan/action/run/status dataclasses
    ├── scanner.py                 # compare filesystem, manifest, lineage
    ├── lineage.py                 # inspect 008/009/010 derived artifacts
    ├── planner.py                 # deterministic plan and fingerprint
    ├── service.py                 # scan/run/status orchestration
    ├── store.py                   # atomic watch state persistence
    ├── executor.py                # bounded execution through existing services
    └── validation.py              # schema validation

tests/
├── contract/
│   ├── test_watch_contract.py
│   └── test_watch_adapter_contract.py
├── integration/
│   ├── test_watch_cli.py
│   ├── test_watch_run.py
│   ├── test_watch_lint.py
│   ├── test_watch_mcp.py
│   ├── test_watch_http.py
│   └── test_watch_adapter_consistency.py
└── unit/
    └── watch/
        ├── test_watch_models.py
        ├── test_watch_scanner.py
        ├── test_watch_lineage.py
        ├── test_watch_planner.py
        ├── test_watch_store.py
        └── test_watch_executor.py
```

**Structure Decision**: Add `src/hks/watch/` as a derived operational orchestration domain. Keep authoritative mutations inside existing command services and keep watch state under `$KS_ROOT/watch/`.

## Complexity Tracking

No constitution violations.

Schema impact tracked separately: 011 adds `trace.steps.kind="watch_summary"` and a derived runtime area `$KS_ROOT/watch/`. It does not add route/source enum values. Source/route semantics are fixed as: scan/dry-run/status => `route="wiki"`, `source=[]`; execute ingest refresh => `route="wiki"`, `source=["wiki","graph","vector"]`; derived-only outputs remain represented in `watch_summary.artifacts`.

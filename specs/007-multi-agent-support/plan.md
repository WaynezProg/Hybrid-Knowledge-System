# Implementation Plan: Phase 3 階段三 — Multi-agent support

**Branch**: `007-multi-agent-support` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-multi-agent-support/spec.md`

## Summary

007 adds local multi-agent coordination primitives on top of the existing HKS runtime: session identity, heartbeat/status, resource leases, handoff notes, and MCP exposure. It does not launch agents, assign tasks, provide UI, add RBAC, or move state outside `KS_ROOT`. The implementation should add a thin `coord` layer and persist a local append-auditable ledger under `KS_ROOT/coordination/`, protected by file locking and surfaced through the existing `QueryResponse` contract.

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`
**Primary Dependencies**: existing `typer`, `jsonschema`, `mcp`, `starlette`; no new runtime dependency expected
**Storage**: local JSON state + JSONL events under `KS_ROOT/coordination/`
**Testing**: `pytest`, `jsonschema`, in-process MCP adapter tests, concurrency regression tests
**Target Platform**: local macOS/Linux shell and local MCP clients
**Project Type**: Python CLI package with adapter entry points
**Performance Goals**: status / lease expiry over fixture ledger p95 < 1s; wrapper overhead remains below 006 adapter regression budget
**Constraints**: local-first, no UI/cloud/RBAC/scheduler/supervisor, preserve existing CLI/MCP success contracts, coordination writes must not mutate wiki knowledge
**Scale/Scope**: single machine / trusted filesystem, small team of local agents sharing one `KS_ROOT`

## Constitution Check

- **§I Phase Discipline**：PASS。007 是 Phase 3 剩餘 multi-agent scope；005 lint 與 006 adapter 已在 main，007 不回頭改 Phase 1/2 semantics。
- **§II Stable Output Contract**：PASS with MINOR extension。成功 response 仍是 `QueryResponse`；新增 `trace.steps.kind="coordination_summary"` 需更新 canonical schema 與 contract tests。
- **§III CLI-First & Domain-Agnostic**：PASS。入口是 `ks coord` + MCP tools；不做 UI、cloud、RBAC、domain-specific agents。
- **§IV Ingest-Time Organization**：PASS。coordination ledger 不取代 ingestion，不觸發 query-time parse / embedding / extraction。
- **§V Write-back Safety**：PASS。handoff note 寫入 coordination ledger，不等同 wiki write-back；agent read path 仍不默默寫 wiki。

## Project Structure

### Documentation (this feature)

```text
specs/007-multi-agent-support/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── coordination-summary-detail.schema.json
│   ├── coordination-ledger.schema.json
│   └── mcp-coordination-tools.schema.json
└── tasks.md
```

### Source Code (repository root)

```text
src/hks/
├── cli.py                         # add ks coord namespace
├── adapters/
│   ├── contracts.py               # load 007 schemas
│   ├── mcp_server.py              # expose coordination MCP tools
│   └── http_server.py             # optional coordination endpoints
├── commands/
│   └── coord.py                   # CLI command wrapper layer
├── coordination/
│   ├── __init__.py
│   ├── models.py                  # session / lease / handoff dataclasses
│   ├── store.py                   # JSON ledger read/write + locking
│   ├── service.py                 # session/lease/handoff operations
│   └── lint.py                    # ledger consistency checks
└── core/
    └── schema.py                  # add coordination_summary trace kind

tests/
├── contract/
│   └── test_coordination_contract.py
├── integration/
│   ├── test_coordination_cli.py
│   ├── test_coordination_mcp.py
│   └── test_coordination_concurrency.py
└── unit/
    └── coordination/
        ├── test_models.py
        ├── test_store.py
        └── test_service.py
```

**Structure Decision**: Add `src/hks/coordination/` as a domain layer and keep Typer/MCP/HTTP code as adapters. This mirrors existing command/core separation and prevents multi-agent behavior from leaking into ingest/query/lint.

## Complexity Tracking

No constitution violations.

Schema impact tracked separately: 007 adds `trace.steps.kind="coordination_summary"` as a §II-compatible MINOR extension. Reusing `lint_summary` or `ingest_summary` was rejected because it would blur semantics and make agent parsing ambiguous.

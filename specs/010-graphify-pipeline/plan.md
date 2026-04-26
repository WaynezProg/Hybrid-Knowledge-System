# Implementation Plan: Graphify pipeline

**Branch**: `010-graphify-pipeline` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/010-graphify-pipeline/spec.md`

## Summary

010 adds a derived Graphify layer for HKS. It reads existing wiki pages, ingestion graph data, manifest metadata, and optional 008/009 lineage artifacts to produce deterministic graph analysis outputs: derived graph JSON, communities JSON, audit JSON, static HTML visualization, and Markdown report. It is CLI-first, adapter-compatible, local-first, and explicitly does not mutate authoritative wiki/graph/vector/manifest.

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`  
**Primary Dependencies**: existing `typer`, `jsonschema`, `mcp`, `starlette`, `python-slugify`; no mandatory new runtime dependency for 010  
**Storage**: derived artifacts under `$KS_ROOT/graphify/runs/<run-id>/`; latest pointer under `$KS_ROOT/graphify/latest.json`; no writes to authoritative `wiki/`, `graph/`, `vector/`, or `manifest.json`  
**Testing**: `pytest`, `jsonschema`, deterministic clustering/classification, contract tests, CLI/MCP/HTTP integration tests, no-mutation regression tests  
**Target Platform**: local macOS/Linux shell and local agent clients  
**Project Type**: Python CLI package with MCP / HTTP adapters  
**Performance Goals**: fixture preview/store complete within existing test-suite expectations; graphify build must not trigger embedding, raw-source parsing, or query routing  
**Constraints**: local-first, no network by default, no paid API key in tests, no UI framework, no graph database, no watch/daemon, no authoritative graph/vector/wiki mutation  
**Scale/Scope**: one local `KS_ROOT`, personal knowledge base scale, one graphify run per request

## Constitution Check

- **§I Phase Discipline**: PASS。010 是 post-Phase feature；它依賴 Phase 1-3、008、009 已完成 runtime，不回頭改 ingestion/query/write-back baseline，也不偷做 011 watch。
- **§II Stable Output Contract**: PASS with MINOR extension。成功 response 保持 `QueryResponse`；新增 `trace.steps.kind="graphify_summary"`，implementation 時必須更新 canonical schema 與 contract tests。`trace.route` 使用既有 `"graph"`，`source` 只使用既有 enum values。
- **§III CLI-First & Domain-Agnostic**: PASS。入口以 `ks graphify build` 為主；HTML 是 static artifact，不是 web UI；community labels 不綁特定領域。
- **§IV Ingest-Time Organization**: PASS。010 不在 query path re-parse / re-embed；它只讀已整理 runtime layers 並產生 derived artifacts。
- **§V Write-back Safety**: PASS。010 沒有 apply 回 authoritative wiki/graph/vector/manifest 的行為；store mode 只寫 `$KS_ROOT/graphify/` derived outputs。

## Project Structure

### Documentation (this feature)

```text
specs/010-graphify-pipeline/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── graphify-summary-detail.schema.json
│   ├── graphify-run.schema.json
│   ├── graphify-graph.schema.json
│   ├── mcp-graphify-tools.schema.json
│   └── http-graphify-api.openapi.yaml
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/hks/
├── cli.py                         # add ks graphify build namespace
├── adapters/
│   ├── contracts.py               # load 010 schemas
│   ├── mcp_server.py              # expose hks_graphify_build
│   └── http_server.py             # expose loopback /graphify/build
├── commands/
│   └── graphify.py                # CLI command wrapper layer
├── core/
│   └── schema.py                  # add graphify_summary trace kind
├── lint/
│   ├── checks.py                  # graphify artifact/latest/partial-run checks
│   └── runner.py
└── graphify/
    ├── __init__.py
    ├── audit.py                   # audit findings and safety checks
    ├── builder.py                 # read HKS layers and build derived graph
    ├── clustering.py              # deterministic community detection
    ├── config.py                  # provider/env config, inherited 008 gates
    ├── export.py                  # HTML and Markdown report rendering
    ├── models.py                  # request/run/node/edge/community dataclasses
    ├── service.py                 # preview/store orchestration
    ├── store.py                   # run idempotency and atomic finalize
    └── validation.py              # schema validation

tests/
├── contract/
│   ├── test_graphify_contract.py
│   └── test_graphify_adapter_contract.py
├── integration/
│   ├── test_graphify_cli.py
│   ├── test_graphify_store.py
│   ├── test_graphify_lint.py
│   ├── test_graphify_mcp.py
│   ├── test_graphify_http.py
│   └── test_graphify_adapter_consistency.py
└── unit/
    └── graphify/
        ├── test_graphify_builder.py
        ├── test_graphify_clustering.py
        ├── test_graphify_config.py
        ├── test_graphify_export.py
        ├── test_graphify_models.py
        └── test_graphify_store.py
```

**Structure Decision**: Add `src/hks/graphify/` as a derived-analysis domain layer. Keep adapters thin and keep all outputs under `$KS_ROOT/graphify/` so authoritative ingestion graph remains stable.

## Complexity Tracking

No constitution violations.

Schema impact tracked separately: 010 adds `trace.steps.kind="graphify_summary"` and a derived runtime area `$KS_ROOT/graphify/`. It does not add route/source enum values: responses use `trace.route="graph"` and `source` containing stable source layer names actually read, such as `["wiki","graph"]`.

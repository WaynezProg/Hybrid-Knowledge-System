# Implementation Plan: LLM-assisted classification and extraction

**Branch**: `008-llm-classification-extraction` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/008-llm-classification-extraction/spec.md`

## Summary

008 adds a local-first LLM classification/extraction foundation for HKS. The feature introduces a provider abstraction, deterministic fake provider for tests, schema-validated extraction output, preview/read-only default behavior, and explicit storage of versioned extraction artifacts under `KS_ROOT/llm/extractions/`. It does not synthesize wiki pages, apply graph mutations, run Graphify clustering/visualization, or introduce watch/daemon behavior.

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`  
**Primary Dependencies**: existing `typer`, `jsonschema`, `mcp`, `starlette`; no mandatory new runtime dependency for 008  
**Storage**: local JSON artifacts under `KS_ROOT/llm/extractions/`, separate from authoritative `wiki/`, `graph/`, `vector/`, and existing manifest semantics  
**Testing**: `pytest`, `jsonschema`, deterministic fake provider, contract tests, CLI/MCP/HTTP integration tests  
**Target Platform**: local macOS/Linux shell and local agent clients  
**Project Type**: Python CLI package with MCP / HTTP adapters  
**Performance Goals**: fake-provider contract and CLI smoke tests complete under existing test-suite expectations; preview mode does not touch vector embedding or query routing  
**Constraints**: local-first, no network by default, no paid API key in tests, no UI/cloud/RBAC/watch service, no automatic mutation of wiki / graph / vector  
**Scale/Scope**: one local `KS_ROOT`, personal knowledge base scale, one source per extraction request in 008

## Constitution Check

- **§I Phase Discipline**: PASS。Phase 1-3 已完成；008 是 post-Phase feature，且不把 009/010/011 的能力偷做到本 spec。
- **§II Stable Output Contract**: PASS with MINOR extension。成功 response 保持 `QueryResponse`；新增 `trace.steps.kind="llm_extraction_summary"` 與 adapter input schema，implementation 時必須更新 canonical schema 和 contract tests。
- **§III CLI-First & Domain-Agnostic**: PASS。入口以 `ks llm classify` 為主；provider / prompt / taxonomy 不綁特定領域；不做 UI、cloud、RBAC、microservice deployment。
- **§IV Ingest-Time Organization**: PASS。008 只讀已 ingest source 與 manifest；不在 query path 重新 parse / embedding / mutate 三層。stored artifact 是候選資料，不是 authoritative knowledge。
- **§V Write-back Safety**: PASS。預設 preview/read-only；explicit store 只寫 `KS_ROOT/llm/extractions/`，不得自動寫 wiki page、graph edge、vector chunk 或 write-back page。

## Project Structure

### Documentation (this feature)

```text
specs/008-llm-classification-extraction/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── llm-extraction-summary-detail.schema.json
│   ├── llm-extraction-artifact.schema.json
│   ├── mcp-llm-tools.schema.json
│   └── http-llm-api.openapi.yaml
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/hks/
├── cli.py                         # add ks llm namespace
├── adapters/
│   ├── contracts.py               # load 008 schemas
│   ├── mcp_server.py              # expose hks_llm_classify
│   └── http_server.py             # expose loopback /llm/classify
├── commands/
│   └── llm.py                     # CLI command wrapper layer
├── core/
│   └── schema.py                  # add llm_extraction_summary trace kind
└── llm/
    ├── __init__.py
    ├── config.py                  # provider/env config and local-first gates
    ├── models.py                  # request/result/artifact dataclasses
    ├── providers.py               # provider protocol + fake provider
    ├── prompts.py                 # versioned extraction prompt contract
    ├── service.py                 # classify/extract orchestration
    ├── store.py                   # artifact idempotency and JSON writes
    └── validation.py              # schema validation and normalization checks

tests/
├── contract/
│   ├── test_llm_contract.py
│   └── test_llm_adapter_contract.py
├── integration/
│   ├── test_llm_cli.py
│   ├── test_llm_mcp.py
│   └── test_llm_http.py
└── unit/
    └── llm/
        ├── test_config.py
        ├── test_models.py
        ├── test_providers.py
        ├── test_service.py
        └── test_store.py
```

**Structure Decision**: Add `src/hks/llm/` as a feature domain layer and keep Typer/MCP/HTTP code as thin adapters. This mirrors existing `coordination/`, `lint/`, and `graph/` separation while keeping provider behavior out of ingest/query core.

## Complexity Tracking

No constitution violations.

Schema impact tracked separately: 008 adds `trace.steps.kind="llm_extraction_summary"` and a new runtime area `KS_ROOT/llm/extractions/` as §II-compatible MINOR extensions. Reusing `graph_lookup`, `ingest_summary`, or `lint_summary` was rejected because LLM extraction is neither authoritative graph state nor ingest summary.

Runtime layout 延伸（new `KS_ROOT/llm/extractions/`）依憲法 §II MINOR 機制處理。憲法 Technology Stack > Data Layout 目前仍只列 Phase 1 四個 runtime 區，尚未同步補列 007 加入的 `coordination/` 與 008 加入的 `llm/extractions/`；此補列屬下次 minor 憲法修訂的範圍，008 不阻塞此修訂。

Constitution §II `trace.route` / `source` enum 不擴：008 採 FR-021 規則，response 設 `trace.route="wiki"` + `source=[]`，並依靠新 trace step `kind="llm_extraction_summary"` 提供語意，避免一次新增 enum 值（如 `extraction` / `raw_sources`）造成 MAJOR/MINOR 憲法修訂。此選擇於 spec FR-021 留下對 agent 的明確語意說明。

# Implementation Plan: LLM-assisted wiki synthesis

**Branch**: `009-llm-wiki-synthesis` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/009-llm-wiki-synthesis/spec.md`

## Summary

009 adds the LLM Wiki layer on top of 008 extraction artifacts. The feature consumes stored 008 artifacts, synthesizes schema-validated wiki page candidates, supports read-only preview, candidate storage under `KS_ROOT/llm/wiki-candidates/`, and explicit apply of a stored `candidate_artifact_id` to `wiki/pages/` with index/log updates and provenance. It does not update graph/vector, run Graphify, or watch folders.

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`  
**Primary Dependencies**: existing `typer`, `jsonschema`, `mcp`, `starlette`, `python-slugify`; no mandatory new runtime dependency for 009  
**Storage**: local JSON candidate artifacts under `KS_ROOT/llm/wiki-candidates/`; applied pages under existing `KS_ROOT/wiki/pages/`; `wiki/index.md` and `wiki/log.md` updated only in explicit apply mode  
**Testing**: `pytest`, `jsonschema`, deterministic fake synthesizer, contract tests, CLI/MCP/HTTP integration tests, no-mutation regression tests  
**Target Platform**: local macOS/Linux shell and local agent clients  
**Project Type**: Python CLI package with MCP / HTTP adapters  
**Performance Goals**: fake-provider preview/store/apply fixture tests complete under existing test-suite expectations; preview/store do not touch vector embedding or query routing  
**Constraints**: local-first, no network by default, no paid API key in tests, no UI/cloud/RBAC/watch service, no graph/vector/manifest mutation in 009  
**Scale/Scope**: one local `KS_ROOT`, personal knowledge base scale, one source/artifact per synthesis request in 009

## Constitution Check

- **§I Phase Discipline**: PASS。009 是 post-Phase feature；它依賴 008 已完成 artifacts，不回頭改 Phase 1-3 semantics，也不偷做 010/011。
- **§II Stable Output Contract**: PASS with MINOR extension。成功 response 保持 `QueryResponse`；新增 `trace.steps.kind="wiki_synthesis_summary"`，implementation 時必須更新 canonical schema 與 contract tests。
- **§III CLI-First & Domain-Agnostic**: PASS。入口以 `ks wiki synthesize` 為主；prompt / synthesizer 不綁特定領域；不做 UI、cloud、RBAC、microservice deployment。
- **§IV Ingest-Time Organization**: PASS。009 不在 query path re-parse / re-embed；只 consume 008 artifacts，apply 僅修改 wiki layer 並留下 provenance。
- **§V Write-back Safety**: PASS。預設 preview/read-only；只有 caller-explicit `apply` 寫 wiki，並且必須 append `wiki/log.md` 與 trace detail。009 `apply` 不是 §V 所稱 confidence-triggered automatic query write-back。

## Project Structure

### Documentation (this feature)

```text
specs/009-llm-wiki-synthesis/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── wiki-synthesis-summary-detail.schema.json
│   ├── wiki-synthesis-candidate.schema.json
│   ├── wiki-synthesis-artifact.schema.json
│   ├── mcp-wiki-tools.schema.json
│   └── http-wiki-api.openapi.yaml
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/hks/
├── cli.py                         # add ks wiki synthesize namespace
├── adapters/
│   ├── contracts.py               # load 009 schemas
│   ├── mcp_server.py              # expose hks_wiki_synthesize
│   └── http_server.py             # expose loopback /wiki/synthesize
├── commands/
│   └── wiki.py                    # CLI command wrapper layer
├── core/
│   └── schema.py                  # add wiki_synthesis_summary trace kind
├── storage/
│   └── wiki.py                    # allow llm_wiki origin and log metadata
└── wiki_synthesis/
    ├── __init__.py
    ├── config.py                  # provider/env config, inherited 008 gates
    ├── models.py                  # request/candidate/apply result dataclasses
    ├── providers.py               # synthesizer protocol + fake synthesizer
    ├── prompts.py                 # versioned synthesis prompt contract
    ├── resolver.py                # locate/validate 008 extraction artifacts
    ├── service.py                 # preview/store/apply orchestration
    ├── store.py                   # candidate idempotency and JSON writes
    └── validation.py              # schema validation and side-effect filtering

tests/
├── contract/
│   ├── test_wiki_synthesis_contract.py
│   └── test_wiki_synthesis_adapter_contract.py
├── integration/
│   ├── test_wiki_synthesis_cli.py
│   ├── test_wiki_synthesis_store.py
│   ├── test_wiki_synthesis_apply.py
│   ├── test_wiki_synthesis_mcp.py
│   ├── test_wiki_synthesis_http.py
│   └── test_wiki_synthesis_adapter_consistency.py
└── unit/
    └── wiki_synthesis/
        ├── test_wiki_synthesis_config.py
        ├── test_wiki_synthesis_models.py
        ├── test_wiki_synthesis_providers.py
        ├── test_wiki_synthesis_resolver.py
        ├── test_wiki_synthesis_store.py
        ├── test_wiki_synthesis_apply.py
        ├── test_wiki_synthesis_validation.py
        └── test_wiki_synthesis_prompts_domain_agnostic.py
```

**Structure Decision**: Add `src/hks/wiki_synthesis/` as a domain layer and keep Typer/MCP/HTTP code as thin adapters. This prevents 009 synthesis behavior from leaking into query routing or ingestion and keeps 010/011 separate.

## Complexity Tracking

No constitution violations.

Schema impact tracked separately: 009 adds `trace.steps.kind="wiki_synthesis_summary"` and a new runtime candidate area `KS_ROOT/llm/wiki-candidates/` as §II-compatible MINOR extensions. It does not add route/source enum values: preview/store use `trace.route="wiki"` with `source=[]`; apply uses `trace.route="wiki"` with `source=["wiki"]` only after a wiki write succeeds, while apply conflict/error uses `source=[]` when returning an HKS top-level response. It also extends wiki page origin semantics with `origin=llm_wiki`; implementation must update wiki parsing/lint contract tests accordingly.

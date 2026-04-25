# Implementation Plan: Phase 3 階段三 — MCP / API adapter

**Branch**: `006-mcp-api-adapter` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-mcp-api-adapter/spec.md`

## Summary

006 將現有 `ks ingest`、`ks query`、`ks lint` command/core 層包成 local-first adapter。MVP 提供 MCP server，暴露 `hks_query`、`hks_ingest`、`hks_lint` 三個 tools；server 支援 stdio 與 Streamable HTTP transport。HTTP REST endpoint 保留為 P2 optional，不阻塞 MCP MVP。所有成功 payload 維持現有 HKS top-level JSON contract，錯誤則映射既有 CLI exit code 語意。

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`（沿用 `pyproject.toml`）
**Primary Dependencies**: `mcp` official Python SDK（新增）、既有 `typer`、`jsonschema`；HTTP REST P2 若落地，優先使用 `mcp` 依賴鏈提供的 Starlette/Uvicorn 而非 FastAPI
**Storage**: 既有 local `/ks` layout：`raw_sources/`、`wiki/`、`graph/graph.json`、`vector/db/`、`manifest.json`
**Testing**: `pytest`、`jsonschema`、官方 MCP in-process client/session 測試；沿用 no-network monkeypatch
**Target Platform**: 本機 macOS/Linux shell；MCP stdio 與 loopback Streamable HTTP
**Project Type**: Python CLI package + adapter entry points
**Performance Goals**: adapter overhead 對 query/lint p95 < 250ms（不含底層 query/ingest 本身）；不退化既有 query p95 < 3s fixture 目標
**Constraints**: local-first、airgapped 可跑、預設 `writeback=no`、不改現有 JSON schema、不新增 `source` / `trace.route` enum、不做 UI / cloud / RBAC / multi-agent orchestration
**Scale/Scope**: 單機單使用者、單一 `KS_ROOT` context；三個 MCP tools + optional loopback HTTP facade

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **§I Phase Discipline**：PASS。006 是 Phase 3 的 API / MCP adapter；005 lint 已完成並封存，未跨 Phase。
- **§II Stable Output Contract**：PASS。adapter 成功 response 直接回現有 `QueryResponse` payload，不包 adapter-specific envelope，不改欄位、型別、`source` 或 `trace.route` value set；錯誤映射既有 `0/1/2/65/66` exit code 語意。
- **§III CLI-First & Domain-Agnostic**：PASS with scope note。Phase 3 允許 API / MCP adapter；本 spec 不做 UI、cloud、RBAC 或 domain-specific tools。
- **§IV Ingest-Time Organization**：PASS。adapter 只呼叫既有 command/core 層；query tool 不 parse/re-embed，ingest tool 才寫入整理。
- **§V Write-back Safety**：PASS。Phase 2+ 已允許 auto write-back，但 adapter 預設 `writeback=no`，避免 agent 背景查詢靜默污染 wiki。

## Project Structure

### Documentation (this feature)

```text
specs/006-mcp-api-adapter/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── mcp-tools.schema.json
│   ├── adapter-error.schema.json
│   └── http-api.openapi.yaml
└── tasks.md
```

### Source Code (repository root)

```text
src/hks/
├── adapters/
│   ├── __init__.py
│   ├── core.py          # shared adapter request/response wrappers
│   ├── mcp_server.py    # FastMCP tools and stdio/streamable-http entry point
│   └── http_server.py   # optional P2 loopback HTTP facade
├── commands/
│   ├── ingest.py
│   ├── query.py
│   └── lint.py
└── core/
    └── schema.py

tests/
├── contract/
│   ├── test_mcp_contract.py
│   └── test_adapter_error_contract.py
├── integration/
│   ├── test_mcp_adapter.py
│   ├── test_mcp_offline.py
│   └── test_http_adapter.py
└── unit/
    └── adapters/
        └── test_core.py
```

**Structure Decision**: 新增 `src/hks/adapters/` 作為薄 adapter layer；不得把 MCP/HTTP logic 混入 `src/hks/commands/`，也不得複製 query/ingest/lint domain logic。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 新增非 CLI adapter | 006 是 Phase 3 明確範圍：API / MCP adapter | 只靠 shell wrapping 會讓 agent 各自處理 schema、exit code、writeback default，破壞穩定整合 |

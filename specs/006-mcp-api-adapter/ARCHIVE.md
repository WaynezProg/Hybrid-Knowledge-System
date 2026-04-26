# 006 MCP / API Adapter Archive

Status: Complete
Archived on: 2026-04-26
Branch: `006-mcp-api-adapter`
Merged into: `main`

## Scope Delivered

- `hks-mcp` entry point with `stdio` and loopback `streamable-http` transports.
- Base MCP tools for query, ingest, and lint; later archived specs extend the same adapter facade.
- `hks-api` loopback HTTP facade.
- Base HTTP endpoints for `/query`, `/ingest`, and `/lint`; later archived specs extend the same HTTP facade with `/coord/*`, `/llm/classify`, `/wiki/synthesize`, `/graphify/build`, and `/watch/*`.
- Adapter success payloads preserve the HKS top-level JSON response shape.
- Adapter errors use `{ok:false,error:{code,exit_code,message,details},response}`.
- README, docs, PRD, OpenAPI, MCP schema, task, and quickstart updates are complete.

## Verification

- `uv run pytest --tb=short -q`
- `uv run ruff check .`
- `uv run mypy src/hks`
- MCP and HTTP adapter smoke tests with temporary `KS_ROOT`

## Remaining Specs

- No remaining work in 006.

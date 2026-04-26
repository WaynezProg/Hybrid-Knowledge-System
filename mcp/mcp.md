# HKS MCP Server

Use this file only for MCP-capable clients. For plain HTTP clients, prefer `README.md` or `http.md`.

Ready-to-adapt client configs live in:

- `config/stdio.mcp.json`
- `config/streamable-http.mcp.json`

The MCP tool manifest lives in `tools/hks-mcp-tools.json`.

## Start

```bash
uv run hks-mcp --transport stdio
uv run hks-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

## Tool Defaults

- `hks_query` defaults `writeback` to `no`.
- Tool results use the same successful HKS payload shape as CLI.
- Tool errors return an adapter error envelope as structured content.

## Tool Groups

- Query/ingest/lint: `hks_query`, `hks_ingest`, `hks_lint`
- Catalog/workspace: `hks_source_*`, `hks_workspace_*`
- LLM/wiki/graphify/watch: `hks_llm_classify`, `hks_wiki_synthesize`, `hks_graphify_build`, `hks_watch_*`
- Coordination: `hks_coord_*`

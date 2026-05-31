# HKS MCP / HTTP Adapter Guide

This directory contains the real adapter-facing assets for agents and tools. Use it when the caller cannot or should not invoke the `ks` CLI directly.

Primary path for generic tools: HTTP facade via `hks-api`.
Primary path for MCP clients: MCP server via `hks-mcp`.

For normal repo operation, prefer `../skill/hks-knowledge-system/SKILL.md` and the `ks` CLI.

## Directory Layout

```text
mcp/
├── config/
│   ├── stdio.mcp.json
│   └── streamable-http.mcp.json
├── examples/
│   ├── http-graphify-build.json
│   ├── http-query.json
│   └── http-source-list.json
├── tools/
│   └── hks-mcp-tools.json
├── http.md
├── mcp.md
└── README.md
```

- `config/`: MCP client configuration templates.
- `tools/`: tool manifest for the HKS MCP server.
- `examples/`: HTTP facade request bodies.
- `http.md`: HTTP facade usage.
- `mcp.md`: MCP server usage.

## Runtime Status

The adapters are implemented but not resident. Do not assume a background service is already running.

Check whether HTTP ports are active:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN -iTCP:8766 -sTCP:LISTEN
```

Start only while a client needs adapter access.

## Agent profile

For Cursor / Codex / Claude / OpenClaw automation that only ingests **session2memory** exports:

```bash
export HKS_SESSION2MEMORY_EXPORT_ROOT="$HOME/session2memory/export"
export HKS_KS_ROOT_BASE="$HOME/.local/share/hks/workspaces"
export HKS_API_TOKEN='replace-with-local-token'
uv run hks-mcp --profile agent --transport stdio
# or
uv run hks-api --profile agent --host 127.0.0.1 --port 8766
```

Agent profile exposes: `hks_workspace_query`, `hks_workspace_ingest_session_memory`, `hks_workspace_list`, `hks_workspace_show`, `hks_session_memory_summary`, `hks_source_list`, `hks_source_show` (workspace-scoped). Full tools such as `hks_ingest`, `hks_graphify_build`, and `hks_watch_run` are hidden.

HTTP agent routes include `POST /workspaces/{workspace_id}/ingest/session-memory`, `POST /session-memory/summary`, and `POST /workspaces/{workspace_id}/catalog/sources`. Generic `POST /ingest` and `POST /query` return `403` with `AGENT_PROFILE_FORBIDDEN`.

## HTTP First

Start the loopback HTTP facade:

```bash
cd "$(git rev-parse --show-toplevel)"
export HKS_API_TOKEN='replace-with-local-token'
# Required only when HTTP clients call /ingest.
export HKS_API_INGEST_ROOTS='fixtures=/Users/me/hks/tests/fixtures'
uv run hks-api --host 127.0.0.1 --port 8766
```

Default binding is loopback only. Do not use `--allow-non-loopback` unless the user explicitly accepts exposing the service outside the local machine.
Mutating or writeback-capable HTTP endpoints require `Authorization: Bearer $HKS_API_TOKEN`. HTTP `/ingest` is allowlisted: it accepts relative paths under `HKS_API_INGEST_ROOTS`; `source_root_id` is required when multiple roots are configured and optional with one root, but explicit IDs are recommended. MCP `hks_ingest` and CLI `ks ingest` keep trusted local path semantics for arbitrary local paths.

Implemented endpoint groups:

```text
POST /query
POST /ingest
POST /catalog/sources
POST /catalog/sources/{relpath}
POST /workspaces
POST /workspaces/{workspace_id}
POST /workspaces/{workspace_id}/query
POST /workspaces/{workspace_id}/ingest/session-memory
POST /workspaces/{workspace_id}/catalog/sources
POST /session-memory/summary
POST /lint
POST /llm/classify
POST /wiki/synthesize
POST /graphify/build
POST /watch/scan
POST /watch/run
POST /watch/status
POST /coord/session
POST /coord/lease
POST /coord/handoff
POST /coord/status
```

## HTTP Examples

Query without write-back:

```bash
curl -sS http://127.0.0.1:8766/query \
  -H 'Host: 127.0.0.1' \
  -H "Authorization: Bearer $HKS_API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"question":"這批資料的重點是什麼？","writeback":"no","ks_root":null}' | jq .
```

Ingest from an allowlisted HTTP source root:

```bash
curl -sS http://127.0.0.1:8766/ingest \
  -H 'Host: 127.0.0.1' \
  -H "Authorization: Bearer $HKS_API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"source_root_id":"fixtures","path":"valid","ks_root":null}' | jq .
```

List sources:

```bash
curl -sS http://127.0.0.1:8766/catalog/sources \
  -H 'Host: 127.0.0.1' \
  -H 'content-type: application/json' \
  -d '{"ks_root":null}' | jq .
```

Run lint:

```bash
curl -sS http://127.0.0.1:8766/lint \
  -H 'Host: 127.0.0.1' \
  -H 'content-type: application/json' \
  -d '{"strict":true,"ks_root":null}' | jq .
```

Preview LLM extraction:

```bash
curl -sS http://127.0.0.1:8766/llm/classify \
  -H 'Host: 127.0.0.1' \
  -H "Authorization: Bearer $HKS_API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"source_relpath":"project-atlas.txt","mode":"preview","provider":"fake","ks_root":null}' | jq .
```

Build Graphify preview:

```bash
curl -sS http://127.0.0.1:8766/graphify/build \
  -H 'Host: 127.0.0.1' \
  -H "Authorization: Bearer $HKS_API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"mode":"preview","provider":"fake","ks_root":null}' | jq .
```

## Response Contract

Successful adapter responses use the same top-level HKS payload as CLI:

```json
{"answer":"...","source":["wiki","graph","vector"],"confidence":0.0,"trace":{"route":"wiki|graph|vector","steps":[]}}
```

Adapter errors use an envelope:

```json
{"ok":false,"error":{"code":"...","exit_code":1,"message":"...","details":{}},"response":null}
```

HTTP status mapping:

- `400`: usage/data/no-input style adapter errors
- `500`: unexpected server/runtime errors

## MCP Secondary

Use MCP when an agent client expects MCP tools instead of plain HTTP. Start from `config/stdio.mcp.json` unless the client explicitly supports Streamable HTTP.

Stdio transport:

```bash
uv run hks-mcp --transport stdio
```

Streamable HTTP transport:

```bash
uv run hks-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

MCP tools are enumerated in `tools/hks-mcp-tools.json`.

```text
hks_query
hks_ingest
hks_source_list
hks_source_show
hks_workspace_list
hks_workspace_register
hks_workspace_show
hks_workspace_remove
hks_workspace_use
hks_workspace_query
hks_lint
hks_llm_classify
hks_wiki_synthesize
hks_graphify_build
hks_watch_scan
hks_watch_run
hks_watch_status
hks_coord_session
hks_coord_lease
hks_coord_handoff
hks_coord_status
```

## Safety Defaults

- Keep adapter hosts loopback-only.
- Pass `ks_root` explicitly in requests when targeting a specific runtime.
- Use query `writeback:"no"` unless mutation is intended.
- Prefer preview/dry-run modes before apply/execute modes.
- Stop long-running adapter processes after the client no longer needs them.

## Validation

```bash
uv run hks-api --help
uv run hks-mcp --help
uv run pytest tests/integration/test_http_adapter.py tests/integration/test_mcp_query.py --tb=short -q
```

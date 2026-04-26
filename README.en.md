# Hybrid Knowledge System (HKS)

[繁體中文](./README.md)

Hybrid Knowledge System is a CLI-first, domain-agnostic knowledge system. The current runtime has completed Phase 1-3 and 008: ingest supports `txt / md / pdf / docx / xlsx / pptx / png / jpg / jpeg`, query routes across `wiki / graph / vector`, relation-style questions prefer graph, high-confidence answers auto write back by default, and the system ships image ingest, the lint system, multi-agent coordination, local MCP / HTTP adapters, and LLM-assisted classification/extraction candidate artifacts.

## How This Project Runs

HKS is not a daemon by default. The normal workflow is to run `uv run ks ...` only when you need it; each command exits after it finishes, and runtime data is stored under `$KS_ROOT`.

- Humans / shell scripts / Codex / Claude Code / OpenClaw: call `ks ingest`, `ks query`, `ks lint`, `ks coord`, and `ks llm classify` directly
- MCP agent integration: start `hks-mcp`; stdio mode is usually launched by the agent client and lives for that session
- HTTP client integration: start `hks-api` or `hks-mcp --transport streamable-http`; keep that process running only while clients need to call it

## What Ships Today

- `ks ingest <file|dir> [--pptx-notes include|exclude]`: builds `raw_sources/`, `wiki/`, `graph/graph.json`, `vector/db/`, and `manifest.json`
- `ks query "<question>" [--writeback auto|yes|no|ask]`: returns stable JSON; summary prefers wiki, relation prefers graph, detail prefers vector
- `ks lint [--strict] [--severity-threshold error|warning|info] [--fix|--fix=apply]`: checks cross-layer consistency across `wiki / graph / vector / manifest / raw_sources`
- `ks coord session|lease|handoff|status|lint`: provides agent presence, resource leases, handoff notes, and coordination ledger lint
- `ks llm classify <source-relpath> [--mode preview|store] [--provider fake]`: creates LLM classification / summary / fact / entity / relation candidates for an already-ingested source; preview does not mutate wiki / graph / vector, and store only writes `$KS_ROOT/llm/extractions/`
- `hks-mcp --transport stdio|streamable-http`: exposes query / ingest / lint / coordination / LLM extraction tools as local MCP tools
- `hks-api`: optional loopback HTTP facade for `/query`, `/ingest`, `/lint`, `/llm/classify`, and `/coord/*`
- Standalone image ingest now supports `png / jpg / jpeg` via local `tesseract`; `.heic / .webp` and VLM are still out of scope

## Installation

Prerequisites:

- On macOS, use Homebrew for system tools
- Python runtime is managed by `mise`; Python packages are installed by `uv`
- Image ingest requires local `tesseract` and language data
- `jq` is optional, but useful for checking JSON output

```bash
git clone https://github.com/WaynezProg/Hybrid-Knowledge-System.git
cd Hybrid-Knowledge-System
brew install tesseract tesseract-lang jq
mise install
uv sync
make fixtures
```

If you only need text / Office ingest, you can skip `tesseract` until you ingest `png / jpg / jpeg`.

## 5-Minute Quick Start

```bash
export KS_ROOT=$(mktemp -d /tmp/hks.XXXXXX)
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid
uv run ks query "What is the main point of these documents?" --writeback=no | jq .
uv run ks query "Which systems are impacted if Project A slips?" --writeback=no | jq .
uv run ks llm classify project-atlas.txt --provider fake --mode preview | jq .
uv run ks coord session start agent-a | jq .
uv run ks coord lease claim agent-a wiki:atlas | jq .
uv run hks-mcp --help
cat "$KS_ROOT/graph/graph.json" | jq '.nodes | length, .edges | length'
```

`HKS_EMBEDDING_MODEL=simple` is best for CI, demos, and agent smoke tests. For real use, remove it to use the default `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, or point `HKS_EMBEDDING_MODEL` at a local model directory.

## How To Use It

### Ingest

```bash
uv run ks ingest <file-or-dir>
```

- Supports `txt`, `md`, `pdf`, `docx`, `xlsx`, `pptx`, `png`, `jpg`, and `jpeg`
- Uses `SHA256 + parser_fingerprint` for idempotency
- `--pptx-notes=exclude` changes the parser fingerprint and forces pptx re-ingest
- Image ingest requires local `tesseract` + `tesseract-lang`
- `.heic` / `.webp` / gif / tiff / svg are still unsupported

### Query

```bash
uv run ks query "<question>" [--writeback auto|yes|no|ask]
```

- Summary / overview questions prefer wiki
- Relation / impact / dependency / why questions prefer graph, then fall back to vector on miss
- Detail / clause questions prefer vector
- No-hit queries still exit `0`; they just return `source=[]`

### Write-back

- `auto`: default mode; commits automatically when `confidence >= HKS_WRITEBACK_AUTO_THRESHOLD`
- `yes`: force a write-back
- `no`: disable write-back
- `ask`: legacy interactive mode; prompt on TTY, skip on non-TTY

Auto write-back pages include a `## Related` section that links back to existing wiki pages touched by the answer.  
For automation or agent workflows, explicitly using `--writeback=no` is still the safest default.

### Lint

```bash
uv run ks lint
```

It emits `trace.steps[kind="lint_summary"].detail` with `findings`, severity/category counters, and fix plan/apply results.

- Default mode is read-only; findings still exit `0`
- `--strict`: exits `1` when findings meet `--severity-threshold`
- `--fix`: plans safe repairs without writing
- `--fix=apply`: only runs allowlisted actions: rebuild `wiki/index.md`, prune orphan vector chunks, prune orphan graph nodes/edges, and append `wiki/log.md`

### LLM Classification / Extraction

```bash
uv run ks llm classify <source-relpath> --provider fake --mode preview
uv run ks llm classify <source-relpath> --provider fake --mode store
```

- Operates only on source relpaths already present in the `ks ingest` manifest, such as `project-atlas.txt`
- Successful responses keep the HKS top-level JSON shape: `trace.route="wiki"`, `source=[]`, and `trace.steps[kind="llm_extraction_summary"]`
- `preview` is the default and does not write `wiki/`, `graph/graph.json`, `vector/db/`, or `manifest.json`
- `store` only writes versioned candidate artifacts to `$KS_ROOT/llm/extractions/` for later 009 Wiki synthesis, 010 Graphify, and 011 watch/re-ingest work
- The built-in deterministic `fake` provider needs no network or API key
- Hosted/network providers fail closed by default; opt-in must come from environment variables, not CLI/MCP/HTTP request payloads

### Coordination

```bash
uv run ks coord session start agent-a
uv run ks coord session heartbeat agent-a
uv run ks coord lease claim agent-a wiki:atlas --ttl-seconds 1800
uv run ks coord handoff add agent-a --summary "checked" --next-action "review"
uv run ks coord status --agent-id agent-a
uv run ks coord lint
```

Coordination state is stored at `$KS_ROOT/coordination/state.json`; events append to `$KS_ROOT/coordination/events.jsonl`.

- `session`: declares agent presence without duplicating an active session for the same agent
- `lease`: claims ownership for a logical `resource_key`; conflicts exit `1` while stdout remains schema-valid JSON with `trace.steps[kind="coordination_summary"].detail.conflicts`
- `handoff`: records a summary, next action, blocked_by, and references
- `coord lint`: checks missing references and stale active leases

### Agent Integration

Codex, Claude Code, OpenClaw, or any other local agent can use HKS in three ways:

```bash
# 1. Simplest path: the agent runs CLI commands directly
export KS_ROOT=/path/to/hks-runtime
uv run ks query "What are the current Project Atlas risks?" --writeback=no
uv run ks llm classify project-atlas.txt --provider fake --mode preview
uv run ks lint --strict

# 2. MCP stdio: let an MCP-capable agent client launch this server
uv run hks-mcp --transport stdio

# 3. HTTP: for tools that cannot use MCP but can call loopback HTTP
uv run hks-api --host 127.0.0.1 --port 8766
```

Agent read paths should explicitly use `--writeback=no`, or rely on the MCP `hks_query` default, to avoid background queries creating wiki pages. When multiple agents share one `$KS_ROOT`, use `ks coord lease` to claim a logical resource before editing and record handoffs with `ks coord handoff`.

### MCP / HTTP Adapter

```bash
uv run hks-mcp --transport stdio
uv run hks-mcp --transport streamable-http --host 127.0.0.1 --port 8765
uv run hks-api --host 127.0.0.1 --port 8766
```

- MCP tools: `hks_query`, `hks_ingest`, `hks_lint`, `hks_llm_classify`, `hks_coord_session`, `hks_coord_lease`, `hks_coord_handoff`, `hks_coord_status`
- HTTP endpoints: `/query`, `/ingest`, `/lint`, `/llm/classify`, `/coord/session`, `/coord/lease`, `/coord/handoff`, `/coord/status`
- Successful payloads directly use the existing `ks` top-level JSON shape, with no adapter envelope
- Error payloads use `{ok:false,error:{code,exit_code,message,details},response?}`
- The adapter is local-first; Streamable HTTP and the HTTP facade bind to loopback by default
- Agent workflows should keep the `hks_query` default `writeback=no`

## Output Contract

```json
{
  "answer": "...",
  "source": ["graph"],
  "confidence": 0.88,
  "trace": {
    "route": "graph",
    "steps": [
      {"kind": "routing_model", "detail": {}},
      {"kind": "graph_lookup", "detail": {}}
    ]
  }
}
```

`ks ingest`, `ks query`, `ks lint`, `ks coord`, and `ks llm classify` all share the same top-level JSON shape. A successful `ks llm classify` response uses `source=[]`; distinguish it from a `ks query` no-hit by `trace.steps[kind="llm_extraction_summary"]`.

## Exit Codes

- `0`: success, including query no-hit
- `1`: general error
- `2`: CLI usage error
- `65`: ingest data error
- `66`: missing input or uninitialized `KS_ROOT`

## Useful Environment Variables

- `KS_ROOT`: runtime data root, default `./ks`
- `HKS_EMBEDDING_MODEL`: embedding backend; `simple` is best for offline smoke tests and CI
- `HKS_ROUTING_MODEL`: routing backend label and extension point for future local models; default `simple`
- `HKS_WRITEBACK_AUTO_THRESHOLD`: auto write-back threshold, default `0.75`
- `HKS_MAX_FILE_MB`: max `txt / md / pdf` file size for ingest, default `200`; Office and image inputs use their own limits
- `HKS_OFFICE_MAX_FILE_MB`: max Office file size for ingest, default `200`
- `HKS_OFFICE_TIMEOUT_SEC`: Office parser timeout in seconds, default `60`
- `HKS_IMAGE_MAX_FILE_MB`: max image file size for ingest, default `20`
- `HKS_IMAGE_TIMEOUT_SEC`: image OCR timeout in seconds, default `30`
- `HKS_IMAGE_MAX_PIXELS`: max decoded image pixels, default `100000000`
- `HKS_OCR_LANGS`: tesseract language set, default `eng+chi_tra`
- `HKS_ROUTING_RULES`: override the routing rules file path
- `HKS_LLM_PROVIDER`: LLM extraction provider, default `fake`
- `HKS_LLM_MODEL`: LLM extraction model id, default `fake-llm-extractor-v1`
- `HKS_LLM_NETWORK_OPT_IN`: hosted/network provider opt-in; must be `1` before non-fake provider credentials are considered
- `HKS_LLM_PROVIDER_<ID>_API_KEY`: hosted provider credential, e.g. provider id `openai` maps to `HKS_LLM_PROVIDER_OPENAI_API_KEY`
- `HKS_LLM_PROVIDER_<ID>_ENDPOINT`: optional hosted provider endpoint

## Further Reading

- Phase 1 baseline: [specs/001-phase1-cli-mvp/spec.md](./specs/001-phase1-cli-mvp/spec.md)
- Office ingest expansion: [specs/002-phase2-ingest-office/spec.md](./specs/002-phase2-ingest-office/spec.md)
- Phase 2 graph / routing / write-back: [specs/003-phase2-graph-routing/spec.md](./specs/003-phase2-graph-routing/spec.md)
- Phase 3 image ingest: [specs/004-phase3-image-ingest/spec.md](./specs/004-phase3-image-ingest/spec.md)
- Current response contract: [specs/005-phase3-lint-impl/contracts/query-response.schema.json](./specs/005-phase3-lint-impl/contracts/query-response.schema.json)
- Spec archive index: [specs/ARCHIVE.md](./specs/ARCHIVE.md)
- Phase 3 lint system: [specs/005-phase3-lint-impl/spec.md](./specs/005-phase3-lint-impl/spec.md)
- Phase 3 MCP / API adapter: [specs/006-mcp-api-adapter/spec.md](./specs/006-mcp-api-adapter/spec.md)
- Phase 3 multi-agent support: [specs/007-multi-agent-support/spec.md](./specs/007-multi-agent-support/spec.md)
- LLM-assisted classification / extraction: [specs/008-llm-classification-extraction/spec.md](./specs/008-llm-classification-extraction/spec.md)

## Development Checks

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

## License

MIT

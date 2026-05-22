# Hybrid Knowledge System (HKS)

[![ci](https://github.com/WaynezProg/Hybrid-Knowledge-System/actions/workflows/ci.yml/badge.svg)](https://github.com/WaynezProg/Hybrid-Knowledge-System/actions/workflows/ci.yml)

[繁體中文](./README.md)

CLI-first knowledge system: ingest documents into structured wiki / graph / vector layers, then answer questions with fused retrieval. Not a daemon — each command runs and exits.

## Installation

```bash
git clone https://github.com/WaynezProg/Hybrid-Knowledge-System.git
cd Hybrid-Knowledge-System

# System tools (macOS)
brew install tesseract tesseract-lang jq

# Python runtime (managed by mise) + packages (managed by uv)
mise install
uv sync

# Test fixtures
make fixtures
```

> Skip `tesseract` if you only need text / Office ingest. Install it later when you need image ingest.

## Quick Start

```bash
# 1. Set up runtime directory
export KS_ROOT="$PWD/.hks-runs/demo/ks"
export HKS_EMBEDDING_MODEL=simple          # for demo / CI; remove for production

# 2. Ingest documents
uv run ks ingest tests/fixtures/valid

# 3. Query
uv run ks query "What is the main point of these documents?" --writeback=no | jq .

# 4. Browse ingested sources
uv run ks source list | jq .
```

`HKS_EMBEDDING_MODEL=simple` is for demos and CI. For production, remove it to use the default `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, or set `HKS_EMBEDDING_MODEL=openai:text-embedding-3-small` for the OpenAI API.

## Usage

### Ingest

```bash
uv run ks ingest <file-or-dir>
```

Supports `txt`, `md`, `pdf`, `docx`, `xlsx`, `pptx`, `png`, `jpg`, `jpeg`. Uses SHA256 + parser fingerprint for idempotency — re-ingesting the same file is a no-op. Image ingest requires local `tesseract`.

### Daily update workflow

```bash
# initial build
uv run ks ingest ./docs

# daily update
uv run ks update ./docs

# preview changes first
uv run ks update ./docs --dry-run

# update and rebuild derived graph
uv run ks update ./docs --profile derived-refresh

# remove deleted sources
uv run ks update ./docs --prune
```

`ingest` is for the initial runtime build; `update` is for daily synchronization. The authoritative source remains `source-root` / raw files, and update uses the manifest fingerprint to detect stale / new / missing sources. `watch` is the lower-level planning and automation API. Memory / agent event-sourcing is future scope, not part of this workflow.

### Query

```bash
uv run ks query "<question>" [--writeback auto|yes|no|ask]
```

All queries use fused retrieval: candidates are collected from wiki / graph / vector / page_tree simultaneously, then ranked by LLM reranker (RRF fallback without API key). Response includes `evidence[]` for provenance.

Write-back modes:
- `no` (default): disables write-back
- `auto`: explicit opt-in; writes back only when `writeback_eligible=true` and the route-specific `auto_threshold` passes
- `yes` / `no`: force / disable
- `ask`: interactive prompt on TTY

> Agent / automation workflows may omit `--writeback`; use `--writeback=auto` only when automatic write-back is intended.

### Source Catalog & Workspace

```bash
uv run ks source list                         # list ingested sources
uv run ks source show project-atlas.txt       # single source details

# Multi-workspace management
export HKS_WORKSPACE_REGISTRY="$PWD/.hks-runs/workspaces.json"
uv run ks workspace register atlas --ks-root "$PWD/.hks-runs/atlas/ks" --label "Atlas"
uv run ks workspace query atlas "What are the risks?" --writeback=no
```

### LLM Classification & Wiki Synthesis

```bash
# Generate LLM extraction for an ingested source
uv run ks llm classify project-atlas.txt --provider fake --mode preview | jq .
uv run ks llm classify project-atlas.txt --provider fake --mode store

# Generate wiki page from extraction
uv run ks wiki synthesize --source-relpath project-atlas.txt \
  --target-slug project-atlas-synthesis --mode store --provider fake
```

- `preview`: dry run, no writes
- `store`: writes versioned artifact to `$KS_ROOT/llm/`
- Built-in `fake` provider needs no network; hosted providers require env-var opt-in

### Graphify

```bash
uv run ks graphify build --mode store --provider fake | jq .
```

Generates a derived knowledge graph, communities, interactive HTML dashboard, and Markdown report from wiki / graph layers. Writes to `$KS_ROOT/graphify/runs/` without mutating authoritative layers.

### Watch / Refresh

```bash
uv run ks watch scan --source-root <dir>                                    # scan for changes
uv run ks watch run --source-root <dir> --mode execute --profile ingest-only # run refresh
uv run ks watch status                                                       # check state
```

### Coordination (Multi-Agent)

```bash
uv run ks coord session start agent-a
uv run ks coord lease claim agent-a wiki:atlas --ttl-seconds 1800
uv run ks coord handoff add agent-a --summary "checked" --next-action "review"
```

When multiple agents share one `$KS_ROOT`, claim a lease before writing and record handoffs.

### Lint

```bash
uv run ks lint                    # read-only check
uv run ks lint --strict           # exit 1 on findings
uv run ks lint --fix=apply        # auto-fix (rebuild index, prune orphans)
```

## Agent Integration

Three ways to connect:

```bash
# 1. CLI (simplest)
export KS_ROOT="$PWD/.hks-runs/my-runtime/ks"
uv run ks query "Project Atlas risks?" --writeback=no

# 2. MCP stdio (launched by an MCP-capable agent client)
uv run hks-mcp --transport stdio

# 3. HTTP (for tools that cannot use MCP)
uv run hks-api --host 127.0.0.1 --port 8766
```

<details>
<summary>MCP tools</summary>

`hks_query`, `hks_ingest`, `hks_source_list`, `hks_source_show`, `hks_workspace_list`, `hks_workspace_register`, `hks_workspace_show`, `hks_workspace_remove`, `hks_workspace_use`, `hks_workspace_query`, `hks_lint`, `hks_llm_classify`, `hks_wiki_synthesize`, `hks_graphify_build`, `hks_pageindex_show`, `hks_pageindex_enrich`, `hks_watch_scan`, `hks_watch_run`, `hks_watch_status`, `hks_coord_session`, `hks_coord_lease`, `hks_coord_handoff`, `hks_coord_status`

</details>

<details>
<summary>HTTP endpoints</summary>

`/query`, `/ingest`, `/catalog/sources`, `/catalog/sources/{relpath}`, `/workspaces`, `/workspaces/{workspace_id}`, `/workspaces/{workspace_id}/query`, `/lint`, `/llm/classify`, `/wiki/synthesize`, `/graphify/build`, `/pageindex/{relpath}`, `/pageindex/enrich`, `/watch/scan`, `/watch/run`, `/watch/status`, `/coord/session`, `/coord/lease`, `/coord/handoff`, `/coord/status`

</details>

## Output Contract

All commands share the same top-level JSON shape:

```json
{
  "answer": "...",
  "source": ["graph"],
  "confidence": 0.88,
  "retrieval_score": 0.88,
  "calibrated_confidence": 0.88,
  "writeback_eligible": true,
  "evidence": [
    {"source_relpath": "atlas.txt", "route": "graph", "quote": "Atlas depends on Mobile Gateway..."}
  ],
  "trace": {
    "route": "graph",
    "steps": [
      {"kind": "routing_model", "detail": {}},
      {"kind": "wiki_lookup", "detail": {"hit": false}},
      {"kind": "graph_lookup", "detail": {"hit": true, "relpaths": ["atlas.txt"]}},
      {"kind": "vector_lookup", "detail": {}},
      {"kind": "rerank", "detail": {"strategy": "rrf", "status": "primary"}},
      {"kind": "merge", "detail": {"strategy": "rrf", "candidate_count": 3}}
    ]
  }
}
```

- `confidence`: raw retrieval score; `retrieval_score` keeps the same value for migration
- `calibrated_confidence` + `writeback_eligible`: the actual `auto` write-back gate
- `evidence[]`: provenance with `source_relpath`, `route`, `quote`
- `trace.steps`: records each pipeline step
- No-hit queries return `source=[]` and still exit `0`

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (including query no-hit) |
| `1` | General error |
| `2` | CLI usage error |
| `65` | Ingest data error |
| `66` | Missing input or uninitialized `KS_ROOT` |

## Configuration

Full reference: [docs/configuration.md](./docs/configuration.md).

**Common environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `KS_ROOT` | `./ks` | Runtime data root |
| `HKS_EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Embedding backend; use `simple` for CI |
| `HKS_LLM_PROVIDER` | `fake` | LLM provider; `openai` requires API key |
| `HKS_LLM_NETWORK_OPT_IN` | — | Set to `1` to allow non-fake providers |
| `HKS_LLM_PROVIDER_OPENAI_API_KEY` | — | OpenAI API key |
| `HKS_WRITEBACK_AUTO_THRESHOLD` | `0.75` | Legacy auto write-back fallback; `ConfidenceAssessment` uses the route-specific `auto_threshold` and still requires `writeback_eligible=true` |
| `HKS_WORKSPACE_REGISTRY` | user config path | Workspace registry JSON path |

Use `config/hks.yaml` for structured config (copy from `config/hks.yaml.example`). Priority: process env > `config/hks.env` > `config/hks.yaml` / `config/hks.json` > default.

## Using with Obsidian

`$KS_ROOT/wiki/` can be opened directly in Obsidian via `Open folder as vault` — no plugin needed. Do not put human notes in `wiki/pages/` (HKS reads and parses every `*.md` there); use `$KS_ROOT/wiki/manual/`, `$KS_ROOT/wiki/notes/`, or a separate vault instead.

See [docs/obsidian.md](./docs/obsidian.md) for the full guide.

## Development

```bash
uv run pytest --tb=short -q
uv run pytest tests/eval/test_golden_retrieval_quality.py -q
uv run ruff check .
uv run mypy src/hks
```

## Further Reading

<details>
<summary>Spec directory</summary>

- [specs/001-phase1-cli-mvp/spec.md](./specs/001-phase1-cli-mvp/spec.md) — Phase 1 baseline
- [specs/002-phase2-ingest-office/spec.md](./specs/002-phase2-ingest-office/spec.md) — Office ingest
- [specs/003-phase2-graph-routing/spec.md](./specs/003-phase2-graph-routing/spec.md) — Graph / routing / write-back
- [specs/004-phase3-image-ingest/spec.md](./specs/004-phase3-image-ingest/spec.md) — Image ingest
- [specs/005-phase3-lint-impl/spec.md](./specs/005-phase3-lint-impl/spec.md) — Lint system
- [specs/006-mcp-api-adapter/spec.md](./specs/006-mcp-api-adapter/spec.md) — MCP / API adapter
- [specs/007-multi-agent-support/spec.md](./specs/007-multi-agent-support/spec.md) — Multi-agent support
- [specs/008-llm-classification-extraction/spec.md](./specs/008-llm-classification-extraction/spec.md) — LLM classification / extraction
- [specs/009-llm-wiki-synthesis/spec.md](./specs/009-llm-wiki-synthesis/spec.md) — Wiki synthesis
- [specs/010-graphify-pipeline/spec.md](./specs/010-graphify-pipeline/spec.md) — Graphify pipeline
- [specs/011-continuous-watch/spec.md](./specs/011-continuous-watch/spec.md) — Watch / re-ingest
- [specs/012-source-catalog/spec.md](./specs/012-source-catalog/spec.md) — Source catalog / workspace
- [specs/005-phase3-lint-impl/contracts/query-response.schema.json](./specs/005-phase3-lint-impl/contracts/query-response.schema.json) — Response contract
- [specs/ARCHIVE.md](./specs/ARCHIVE.md) — Archive index

</details>

## License

MIT

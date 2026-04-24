# Hybrid Knowledge System (HKS)

[繁體中文](./readme.md)

Hybrid Knowledge System is a CLI-first, domain-agnostic knowledge system. The shipped Phase 1 runtime ingests txt / md / pdf documents into a synchronized wiki + vector store, then answers queries through rule-based routing. Graph is explicitly deferred to Phase 2; Phase 1 JSON output, routing, and runtime paths must not expose any graph code path.

## What Phase 1 Actually Ships

- `ks ingest <file|dir>`: ingest txt / md / pdf and build `raw_sources/`, `wiki/`, `vector/db/`, and `manifest.json`
- `ks query "<question>" [--writeback ask|yes|no]`: return stable JSON and decide write-back from TTY state + explicit flag
- `ks lint`: Phase 1 stub that preserves the future Phase 3 interface

## 5-Minute Quick Start

### 1. Install dependencies

```bash
mise install
uv sync
uv run ks --help
```

### 2. Start with a clean runtime

```bash
export KS_ROOT=$(mktemp -d /tmp/hks.XXXXXX)
export HKS_EMBEDDING_MODEL=simple
```

`HKS_EMBEDDING_MODEL=simple` is the safest setting for smoke tests, CI, and offline verification. For real multilingual embeddings, unset it and the runtime will use the default model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

### 3. Ingest documents

```bash
uv run ks ingest tests/fixtures/valid
```

After a successful ingest, `KS_ROOT` will contain:

```text
raw_sources/
wiki/
vector/
manifest.json
```

### 4. Query the knowledge base

```bash
uv run ks query "What is the main point of these documents?" --writeback=no | jq .
uv run ks query "clause 3.2 text" --writeback=no | jq .
uv run ks query "Which systems are impacted if Project A slips?" --writeback=no | jq .
uv run ks lint | jq .
```

### 5. Inspect generated artifacts

```bash
cat "$KS_ROOT/wiki/index.md"
tail -n 20 "$KS_ROOT/wiki/log.md"
ls "$KS_ROOT/wiki/pages"
```

## How To Use It

### Ingest

```bash
uv run ks ingest <file-or-dir>
```

- Accepts a single file or a directory
- Supports `txt`, `md`, and `pdf`
- Updates `raw_sources/`, `wiki/`, `vector/db/`, and `manifest.json` together
- Re-running ingest on unchanged content will skip by SHA256; changing one file only updates that file's derived artifacts

### Query

```bash
uv run ks query "<question>" [--writeback ask|yes|no]
```

- Summary-style questions prefer wiki
- Detail / clause questions prefer vector
- Relation / impact questions still fall back to vector in Phase 1, and the answer appends a Phase 2 note
- No-hit queries still exit `0`; they just return `source=[]` and `confidence=0.0`

### Write-back

- `ask`: prompt on TTY, skip automatically on non-TTY
- `yes`: write back directly
- `no`: never write back

For automation or agent workflows, default to `--writeback=no` so the process never blocks on an interactive prompt.

### Lint

```bash
uv run ks lint
```

Phase 1 only returns a fixed JSON stub. Real lint functionality is intentionally deferred to Phase 3.

## Output Contract

`ks query` and `ks lint` both write a single JSON object to stdout:

```json
{
  "answer": "...",
  "source": ["wiki", "vector"],
  "confidence": 0.87,
  "trace": {
    "route": "vector",
    "steps": []
  }
}
```

In Phase 1, `source` and `trace.route` will never contain `graph`.

## Exit Codes

- `0`: success, including query no-hit
- `1`: general error
- `2`: CLI usage error
- `65`: ingest data error
- `66`: missing input or uninitialized `KS_ROOT`

Full contract: [specs/001-phase1-cli-mvp/contracts/cli-exit-codes.md](./specs/001-phase1-cli-mvp/contracts/cli-exit-codes.md)

## Useful Environment Variables

- `KS_ROOT`: runtime data root, default `./ks`
- `HKS_EMBEDDING_MODEL`: override the embedding model; set to `simple` for deterministic fallback
- `HKS_MAX_FILE_MB`: max file size for ingest, default `200`
- `HKS_ROUTING_RULES`: override the routing rules file path
- `NO_COLOR`: disable colored stderr output

## Recommended Workflow

1. Start with an isolated runtime via `KS_ROOT=$(mktemp -d ...)`.
2. Run `uv run ks ingest <dir>` and confirm `manifest.json`, `wiki/index.md`, and `vector/db/` exist.
3. In automation or agent usage, start with `uv run ks query "<q>" --writeback=no`.
4. Switch to `ask` or `yes` only when you intentionally want query output written back into wiki pages.

## Further Reading

- Spec: [specs/001-phase1-cli-mvp/spec.md](./specs/001-phase1-cli-mvp/spec.md)
- Design: [specs/001-phase1-cli-mvp/plan.md](./specs/001-phase1-cli-mvp/plan.md)
- Detailed install / testing / E2E: [specs/001-phase1-cli-mvp/quickstart.md](./specs/001-phase1-cli-mvp/quickstart.md)
- JSON schema: [specs/001-phase1-cli-mvp/contracts/query-response.schema.json](./specs/001-phase1-cli-mvp/contracts/query-response.schema.json)

## Development Checks

Run these before submitting changes:

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

## License

MIT

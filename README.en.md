# Hybrid Knowledge System (HKS)

[繁體中文](./readme.md)

Hybrid Knowledge System is a CLI-first, domain-agnostic knowledge system. The current runtime has completed Phase 2: ingest supports `txt / md / pdf / docx / xlsx / pptx`, query can route across `wiki / graph / vector`, relation-style questions prefer graph, and high-confidence answers auto write back by default.

## What Ships Today

- `ks ingest <file|dir> [--pptx-notes include|exclude]`: builds `raw_sources/`, `wiki/`, `graph/graph.json`, `vector/db/`, and `manifest.json`
- `ks query "<question>" [--writeback auto|yes|no|ask]`: returns stable JSON; summary prefers wiki, relation prefers graph, detail prefers vector
- `ks lint`: still a Phase 3 stub
- Standalone image ingest is not implemented yet; a later Phase 3 spec will freeze the accepted raster formats, normalization/conversion strategy, and OCR/VLM flow

## 5-Minute Quick Start

```bash
mise install
uv sync
make fixtures
export KS_ROOT=$(mktemp -d /tmp/hks.XXXXXX)
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid
uv run ks query "What is the main point of these documents?" --writeback=no | jq .
uv run ks query "Which systems are impacted if Project A slips?" --writeback=no | jq .
cat "$KS_ROOT/graph/graph.json" | jq '.nodes | length, .edges | length'
```

## How To Use It

### Ingest

```bash
uv run ks ingest <file-or-dir>
```

- Supports `txt`, `md`, `pdf`, `docx`, `xlsx`, and `pptx`
- Uses `SHA256 + parser_fingerprint` for idempotency
- `--pptx-notes=exclude` changes the parser fingerprint and forces pptx re-ingest
- Standalone image files are not accepted yet; do not treat `png`, `jpg`, `heic`, or `webp` as committed support

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

It still returns the fixed JSON stub. Real linting remains a Phase 3 task.

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

`ks ingest`, `ks query`, and `ks lint` all share the same top-level JSON shape.

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
- `HKS_OFFICE_MAX_FILE_MB`: max Office file size for ingest, default `200`
- `HKS_OFFICE_TIMEOUT_SEC`: Office parser timeout in seconds, default `60`
- `HKS_ROUTING_RULES`: override the routing rules file path

## Further Reading

- Phase 1 baseline: [specs/001-phase1-cli-mvp/spec.md](./specs/001-phase1-cli-mvp/spec.md)
- Office ingest expansion: [specs/002-phase2-ingest-office/spec.md](./specs/002-phase2-ingest-office/spec.md)
- Phase 2 graph / routing / write-back: [specs/003-phase2-graph-routing/spec.md](./specs/003-phase2-graph-routing/spec.md)
- Phase 2 contract: [specs/003-phase2-graph-routing/contracts/query-response.schema.json](./specs/003-phase2-graph-routing/contracts/query-response.schema.json)
- Spec archive index: [specs/ARCHIVE.md](./specs/ARCHIVE.md)
- Phase 3 image ingest is not spec'd yet; only its existence as later work is fixed today

## Development Checks

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

## License

MIT

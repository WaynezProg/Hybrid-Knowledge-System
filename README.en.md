# Hybrid Knowledge System (HKS)

[繁體中文](./readme.md)

Hybrid Knowledge System is a CLI-first, domain-agnostic knowledge system. The current runtime has completed Phase 2 and added Phase 3 image ingest plus the lint system: ingest supports `txt / md / pdf / docx / xlsx / pptx / png / jpg / jpeg`, query routes across `wiki / graph / vector`, relation-style questions prefer graph, and high-confidence answers auto write back by default.

## What Ships Today

- `ks ingest <file|dir> [--pptx-notes include|exclude]`: builds `raw_sources/`, `wiki/`, `graph/graph.json`, `vector/db/`, and `manifest.json`
- `ks query "<question>" [--writeback auto|yes|no|ask]`: returns stable JSON; summary prefers wiki, relation prefers graph, detail prefers vector
- `ks lint [--strict] [--severity-threshold error|warning|info] [--fix|--fix=apply]`: checks cross-layer consistency across `wiki / graph / vector / manifest / raw_sources`
- Standalone image ingest now supports `png / jpg / jpeg` via local `tesseract`; `.heic / .webp` and VLM are still out of scope

## 5-Minute Quick Start

```bash
brew install tesseract tesseract-lang
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
- `HKS_IMAGE_MAX_FILE_MB`: max image file size for ingest, default `20`
- `HKS_IMAGE_TIMEOUT_SEC`: image OCR timeout in seconds, default `30`
- `HKS_IMAGE_MAX_PIXELS`: max decoded image pixels, default `100000000`
- `HKS_OCR_LANGS`: tesseract language set, default `eng+chi_tra`
- `HKS_ROUTING_RULES`: override the routing rules file path

## Further Reading

- Phase 1 baseline: [specs/001-phase1-cli-mvp/spec.md](./specs/001-phase1-cli-mvp/spec.md)
- Office ingest expansion: [specs/002-phase2-ingest-office/spec.md](./specs/002-phase2-ingest-office/spec.md)
- Phase 2 graph / routing / write-back: [specs/003-phase2-graph-routing/spec.md](./specs/003-phase2-graph-routing/spec.md)
- Phase 3 image ingest: [specs/004-phase3-image-ingest/spec.md](./specs/004-phase3-image-ingest/spec.md)
- Current response contract: [specs/005-phase3-lint-impl/contracts/query-response.schema.json](./specs/005-phase3-lint-impl/contracts/query-response.schema.json)
- Spec archive index: [specs/ARCHIVE.md](./specs/ARCHIVE.md)
- Phase 3 lint system: [specs/005-phase3-lint-impl/spec.md](./specs/005-phase3-lint-impl/spec.md)
- Remaining Phase 3 work: MCP / API adapter, multi-agent support

## Development Checks

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

## License

MIT

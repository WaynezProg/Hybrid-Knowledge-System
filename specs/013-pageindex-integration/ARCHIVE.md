# Archive: 013 PageIndex integration

**Status**: Complete  
**Archived on**: 2026-05-23  
**Merged into**: `main`

## Runtime Surface

- Ingest writes PageIndex-style trees under `$KS_ROOT/page_trees/*.json`
- Manifest entries record the tree slug in `derived.page_tree`
- `ks pageindex show <source-relpath>`
- `ks pageindex enrich [--source-relpath <relpath>] --mode preview|store [--provider fake|openai]`
- MCP tools `hks_pageindex_show`, `hks_pageindex_enrich`
- HTTP endpoints `/pageindex/{relpath}`, `/pageindex/enrich`

## Contract Notes

- PageIndex responses use `trace.steps[kind="pageindex_summary"]`.
- Query may return route/source `page_tree` after fused retrieval.
- Page tree evidence may include `section_path` and `page_range`.
- `pageindex enrich --mode store` updates only page_tree artifacts; it does not mutate wiki / graph / vector.

## Verification

Current verification should use focused pageindex tests plus the normal repo gates:

```bash
uv run pytest tests/integration/test_pageindex_cli.py tests/integration/test_pageindex_adapters.py tests/unit/page_tree -q
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

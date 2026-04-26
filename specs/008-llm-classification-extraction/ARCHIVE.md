# 008 LLM Classification / Extraction Archive

Status: Complete
Archived on: 2026-04-26
Branch: `008-llm-classification-extraction`
Merged into: `main`

## Scope Delivered

- `ks llm classify <source-relpath> --mode preview|store`
- Deterministic `fake` provider for offline tests and agent smoke.
- Local-first hosted provider gates via environment variables only.
- Stored extraction artifacts under `$KS_ROOT/llm/extractions/`
- Response detail under `trace.steps[kind="llm_extraction_summary"]`
- MCP tool `hks_llm_classify`
- HTTP endpoint `/llm/classify`
- No-mutation guarantees for preview and store modes against authoritative wiki / graph / vector / manifest layers.
- README, docs, PRD, contract, task, and quickstart updates are complete.

## Verification

- `uv run pytest --tb=short -q`
- `uv run ruff check .`
- `uv run mypy src/hks`
- 008 quickstart CLI smoke with `HKS_EMBEDDING_MODEL=simple`, fake provider, and temporary `KS_ROOT`

## Remaining Specs

- No remaining work in 008.

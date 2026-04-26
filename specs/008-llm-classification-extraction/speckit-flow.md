# Speckit Flow: 008 LLM-assisted classification and extraction

**Branch**: `008-llm-classification-extraction`  
**Date**: 2026-04-26  
**Status**: Implementation complete; pending merge to `main`

## Commands / Gates

- `create-new-feature.sh --json --short-name "llm-classification-extraction" ...`
- `check-prerequisites.sh --json --paths-only`
- `setup-plan.sh --json`
- `update-agent-context.sh claude`
- `check-prerequisites.sh --json --include-tasks --require-tasks`
- Speckit analyze equivalent: placeholder scan, task format validation, JSON/YAML contract parse, cross-artifact drift repair
- 008 focused tests: `uv run pytest tests/contract/test_llm_contract.py tests/contract/test_llm_adapter_contract.py tests/unit/llm tests/integration/test_llm_cli.py tests/integration/test_llm_no_mutation.py tests/integration/test_llm_store.py tests/integration/test_llm_mcp.py tests/integration/test_llm_http.py tests/integration/test_llm_adapter_consistency.py --tb=short -q`
- 005/006 regression tests: `uv run pytest tests/contract/test_lint_contract.py tests/integration/test_lint_findings.py tests/integration/test_lint_fix.py tests/integration/test_lint_strict.py tests/contract/test_mcp_contract.py tests/integration/test_mcp_query.py tests/integration/test_mcp_ingest_lint.py tests/integration/test_http_adapter.py tests/integration/test_mcp_performance.py --tb=short -q`
- Quickstart smoke with temporary `KS_ROOT`, `HKS_EMBEDDING_MODEL=simple`, fake provider preview + store
- Full verification: `uv run pytest --tb=short -q`, `uv run ruff check .`, `uv run mypy src/hks`

## Implementation Boundary

008 implements LLM-assisted classification/extraction candidate generation and optional artifact storage only. It does not implement 009 wiki synthesis, 010 Graphify clustering/visualization/audit report, or 011 watch/re-ingest orchestration.

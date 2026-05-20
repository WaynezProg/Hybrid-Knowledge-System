# Fused Retrieval, Evidence Aggregation, and LLM Provider — Design Spec

> **Date:** 2026-05-20
> **Status:** Draft
> **Depends on:** 013-pageindex-integration (completed phases 1-4)

## Problem Statement

The HKS query pipeline has three gaps:

1. **No fused retrieval**: wiki, graph, and vector sources are tried sequentially with fallback. A primary miss triggers a secondary, then vector. Candidates from different sources are never compared or ranked together.
2. **No structured evidence**: `QueryResponse.source` is `list[Route]` (e.g. `["vector"]`). Consumers cannot see which file, section, page range, or original text snippet the answer came from.
3. **No real LLM provider**: `PageIndex.enrich` only works with `FakeProvider`. `_llm_summarize` and `_llm_restructure` raise `NotImplementedError` for any non-fake provider.

## Design

### Feature 1: OpenAI-compatible LLM Provider

**This is the foundation layer — features 2 and 3 depend on it.**

#### Changes

**`src/hks/llm/providers.py`** — Add `OpenAIProvider`:

```python
@dataclass(frozen=True, slots=True)
class OpenAIProvider:
    api_key: str
    endpoint: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout_seconds: int = 30

    def extract(self, request: LlmExtractionRequest, *, content: str) -> dict[str, Any]:
        # httpx.post to /v1/chat/completions with JSON response format
        ...
```

- Reads config via existing `HKS_LLM_PROVIDER_OPENAI_API_KEY` (or `OPENAI_API_KEY`) and `HKS_LLM_PROVIDER_OPENAI_ENDPOINT` env vars, which are already mapped in `core/config.py`.
- `provider_for()` gains an `"openai"` branch. Falls back to `FakeProvider` when no API key is set.
- JSON mode via `response_format: {"type": "json_object"}`.

**`src/hks/page_tree/enrich.py`** — Replace `NotImplementedError`:

- `_llm_summarize(text, title, provider, model)`: Calls OpenAI chat completion with a system prompt requesting a one-sentence summary. Returns the summary string.
- `_llm_restructure(tree, source_text, provider, model)`: Calls OpenAI with a prompt requesting a JSON array of `{title, start_offset, end_offset}` sections. Parses response into `TreeNode` list and returns a new `PageTree`.
- Provider resolution: reads `HKS_LLM_PROVIDER_OPENAI_API_KEY` from config. If absent and provider is not "fake", raises a clear error.

**`pyproject.toml`** — Add `httpx` dependency.

#### New shared helper

Add a thin `_openai_chat(api_key, endpoint, model, messages, timeout)` function in `llm/providers.py` that both `OpenAIProvider.extract()` and the reranker can call. Returns parsed JSON dict.

### Feature 2: Fused Retrieval + LLM Reranker

#### Data model

```python
@dataclass(slots=True)
class Candidate:
    text: str
    source_route: Route
    score: float
    metadata: dict[str, Any]  # source_relpath, section_path, page_range, etc.
```

#### Query pipeline rewrite

`src/hks/commands/query.py` `run()` becomes:

1. **Collect**: Call `_collect_wiki_candidates()`, `_collect_graph_candidates()`, `_collect_vector_candidates()`. Each returns `list[Candidate]` (may be empty). All three always run — no early return.
2. **Page tree boost**: For each candidate with `source_relpath` in metadata, look up the page tree and enrich metadata with `section_path` and `page_range`. Existing `_vector_section_context()` logic is generalized.
3. **Rerank**:
   - If `HKS_LLM_PROVIDER_OPENAI_API_KEY` is set: LLM rerank. Send question + top-N candidate texts (capped at 10 candidates to control token usage) to `/v1/chat/completions`, ask for a JSON array of ranked indices with relevance scores. Use `_openai_chat()`.
   - Otherwise: RRF. Each source ranks its own candidates independently; RRF score = Σ 1/(60 + rank_i). No candidate cap needed for RRF.
4. **Build response**: Top candidate → `answer`, `source`, `confidence`. Trace includes a `merge` step with `strategy: "llm-rerank"` or `"rrf"`.

#### Trace step

```json
{
  "kind": "merge",
  "detail": {
    "strategy": "llm-rerank",
    "candidate_count": 7,
    "top_candidate": {"route": "graph", "score": 0.92},
    "rerank_model": "gpt-4o-mini"
  }
}
```

#### Backward compatibility

- `RouteDecision.route` and `.secondary` still inform which sources to prioritize in candidate collection order, but all three sources always produce candidates.
- If total candidates is 0, falls back to existing no-hit response.

### Feature 3: Evidence Aggregation

#### Schema change

`query-response.schema.json` adds an optional `evidence` property:

```json
"evidence": {
  "type": "array",
  "items": {
    "type": "object",
    "required": ["source_relpath", "route"],
    "properties": {
      "source_relpath": {"type": "string"},
      "section_path": {"type": "array", "items": {"type": "string"}},
      "page_range": {
        "type": "object",
        "properties": {
          "start": {"type": "integer"},
          "end": {"type": "integer"}
        }
      },
      "quote": {"type": "string", "maxLength": 240},
      "route": {"type": "string", "enum": ["wiki", "graph", "vector"]}
    }
  }
}
```

#### Implementation

- `QueryResponse.to_dict()` calls `_aggregate_evidence(self.trace.steps)` → `list[dict]`.
- Aggregation logic per trace step kind:
  - `wiki_lookup` (hit=true): `source_relpath` from detail. Quote is not available at trace level (wiki returns title+summary, not a snippet), so `quote` is omitted for wiki evidence.
  - `graph_lookup` (hit=true): expand `relpaths` list, one evidence entry per relpath. Quote from the top edge's evidence text (already stored in graph edges).
  - `vector_lookup` (chosen_hit present): `source_relpath`, `section_path`, `page_range` from detail. Quote from the chosen hit's original text[:240].
- Evidence list is deduped by `(source_relpath, route)`.
- If evidence is empty, the field is omitted from output.
- `QueryResponse` dataclass is NOT modified — evidence is purely a serialization concern.

### Feature 4: Eval Set

Three JSONL files:

1. **`evals/pageindex_enrich.jsonl`** — Tests summarize + restructure quality.
   - Fields: `input` (source_text, tree_json), `expected` (summary_contains, node_count_range), `provider`.
   - 5-10 test cases covering: short text, long text, degenerate single-node tree, structured multi-section doc.

2. **`evals/rerank.jsonl`** — Tests LLM reranker output quality.
   - Fields: `question`, `candidates` (text, route, score), `expected_top_route`, `expected_top_contains`.
   - 5-10 test cases covering: clear wiki winner, graph relation query, ambiguous multi-source.

3. **`evals/e2e_query.jsonl`** — Tests end-to-end query pipeline.
   - Fields: `question`, `expected_route`, `expected_answer_contains`, `expected_evidence_relpath`.
   - 5-10 test cases.

Each eval has a corresponding pytest test in `tests/eval/` that is env-gated: skipped when `HKS_LLM_PROVIDER_OPENAI_API_KEY` is not set.

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `evals/pageindex_enrich.jsonl` | Enrich eval cases |
| `evals/rerank.jsonl` | Reranker eval cases |
| `evals/e2e_query.jsonl` | E2E query eval cases |
| `tests/eval/test_enrich_eval.py` | Enrich eval runner |
| `tests/eval/test_rerank_eval.py` | Reranker eval runner |
| `tests/eval/test_e2e_query_eval.py` | E2E query eval runner |
| `tests/eval/__init__.py` | Module marker |
| `tests/eval/conftest.py` | Shared eval fixtures + skip logic |

### Modified Files

| File | Change |
|------|--------|
| `pyproject.toml` | Add `httpx` dependency |
| `src/hks/llm/providers.py` | Add `OpenAIProvider`, `_openai_chat()`, update `provider_for()` |
| `src/hks/page_tree/enrich.py` | Replace `NotImplementedError` with real LLM calls |
| `src/hks/commands/query.py` | Rewrite to fused retrieval + reranker pipeline |
| `src/hks/core/schema.py` | Add `_aggregate_evidence()`, modify `to_dict()` |
| `specs/005-phase3-lint-impl/contracts/query-response.schema.json` | Add optional `evidence` property |
| `tests/unit/commands/test_query_vector_selection.py` | Update for new candidate-based API |
| `tests/unit/commands/test_command_dispatch.py` | Update for new query flow |

## Testing Strategy

- **Unit tests**: Mock LLM responses for reranker and enrich. Test RRF fallback without any mock.
- **Contract tests**: Validate evidence schema compliance.
- **Eval tests**: Real LLM calls, env-gated, not part of CI.
- **Existing test suite**: 272 unit tests must continue passing.

## Non-Goals

- Async/parallel execution of source collection (sequential is fine for now).
- Custom reranker model training.
- Changing the `source: list[Route]` field (kept for backward compatibility).

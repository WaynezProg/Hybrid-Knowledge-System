# Fused Retrieval, Evidence Aggregation & LLM Provider — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the sequential-fallback query pipeline with fused retrieval + LLM reranker, add evidence auto-aggregation to QueryResponse, and implement an OpenAI-compatible LLM provider for PageIndex enrich and reranking.

**Architecture:** A shared `_openai_chat()` helper in `llm/providers.py` powers both the reranker and the PageIndex enrichment. The query pipeline changes from primary→fallback to collect-all→page-tree-boost→rerank. Evidence is dynamically aggregated from trace steps during `to_dict()` serialization — no new dataclass fields needed.

**Tech Stack:** Python 3.12, httpx (new dependency), existing HKS infrastructure (chromadb, sentence-transformers, typer)

**Spec:** `docs/superpowers/specs/2026-05-20-fused-retrieval-evidence-llm-provider-design.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `evals/pageindex_enrich.jsonl` | Eval cases for LLM summarize + restructure |
| `evals/rerank.jsonl` | Eval cases for LLM reranker |
| `evals/e2e_query.jsonl` | Eval cases for end-to-end query pipeline |
| `tests/eval/__init__.py` | Module marker |
| `tests/eval/conftest.py` | Shared eval fixtures + env-gate skip logic |
| `tests/eval/test_enrich_eval.py` | Enrich eval runner |
| `tests/eval/test_rerank_eval.py` | Reranker eval runner |
| `tests/eval/test_e2e_query_eval.py` | E2E query eval runner |
| `tests/unit/llm/test_openai_provider.py` | Unit tests for OpenAIProvider |
| `tests/unit/commands/test_fused_retrieval.py` | Unit tests for fused retrieval pipeline |

### Modified Files

| File | Change |
|------|--------|
| `pyproject.toml:11-26` | Add `httpx` dependency |
| `src/hks/llm/providers.py` | Add `OpenAIProvider`, `_openai_chat()`, update `provider_for()` |
| `src/hks/llm/config.py:18` | Add `"openai"` to `SUPPORTED_PROVIDERS`, update `build_provider_config()` |
| `src/hks/page_tree/enrich.py:106-118` | Replace `NotImplementedError` with real LLM calls |
| `src/hks/commands/query.py` | Rewrite to fused retrieval + reranker pipeline |
| `src/hks/core/schema.py:58-77` | Add `_aggregate_evidence()`, modify `to_dict()` |
| `specs/005-phase3-lint-impl/contracts/query-response.schema.json` | Add optional `evidence` property |
| `tests/unit/page_tree/test_enrich.py:169-173` | Update test for openai provider |
| `tests/unit/commands/test_query_vector_selection.py` | Update imports for refactored query module |
| `tests/unit/commands/test_command_dispatch.py` | Keep as-is (mocks `run()` at module boundary) |

---

## Task 1: Add httpx dependency

**Files:**
- Modify: `pyproject.toml:11-26`

- [ ] **Step 1: Add httpx to dependencies**

In `pyproject.toml`, add `"httpx"` to the `dependencies` list:

```toml
dependencies = [
  "chromadb",
  "httpx",
  "jsonschema",
  "markdown-it-py",
  ...
]
```

- [ ] **Step 2: Install and verify**

Run: `pip install -e .`
Expected: clean install with httpx resolved

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add httpx dependency for OpenAI-compatible LLM client"
```

---

## Task 2: OpenAI-compatible LLM provider

**Files:**
- Modify: `src/hks/llm/providers.py`
- Modify: `src/hks/llm/config.py:18`
- Create: `tests/unit/llm/test_openai_provider.py`

- [ ] **Step 1: Write failing tests for `_openai_chat` and `OpenAIProvider`**

Create `tests/unit/llm/test_openai_provider.py`:

```python
"""Unit tests for OpenAI-compatible LLM provider."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from hks.llm.providers import OpenAIProvider, _openai_chat, provider_for
from hks.llm.models import LlmExtractionRequest, LlmProviderConfig


class TestOpenAIChat:
    def test_returns_parsed_json(self) -> None:
        mock_response = {
            "choices": [{"message": {"content": '{"summary": "test summary"}'}}]
        }

        with patch("hks.llm.providers.httpx") as mock_httpx:
            mock_httpx.Client.return_value.__enter__ = lambda s: s
            mock_httpx.Client.return_value.__exit__ = lambda s, *a: None
            mock_httpx.Client.return_value.post.return_value.status_code = 200
            mock_httpx.Client.return_value.post.return_value.json.return_value = (
                mock_response
            )
            mock_httpx.Client.return_value.post.return_value.raise_for_status = (
                lambda: None
            )

            result = _openai_chat(
                api_key="test-key",
                endpoint="https://api.openai.com/v1",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "test"}],
                timeout=30,
            )

        assert result == {"summary": "test summary"}

    def test_raises_on_non_json_content(self) -> None:
        mock_response = {
            "choices": [{"message": {"content": "not json"}}]
        }

        with patch("hks.llm.providers.httpx") as mock_httpx:
            mock_httpx.Client.return_value.__enter__ = lambda s: s
            mock_httpx.Client.return_value.__exit__ = lambda s, *a: None
            mock_httpx.Client.return_value.post.return_value.status_code = 200
            mock_httpx.Client.return_value.post.return_value.json.return_value = (
                mock_response
            )
            mock_httpx.Client.return_value.post.return_value.raise_for_status = (
                lambda: None
            )

            with pytest.raises(ValueError, match="JSON"):
                _openai_chat(
                    api_key="test-key",
                    endpoint="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "test"}],
                    timeout=30,
                )


class TestOpenAIProvider:
    def test_extract_calls_openai_chat(self) -> None:
        provider = OpenAIProvider(
            api_key="test-key",
            endpoint="https://api.openai.com/v1",
            model="gpt-4o-mini",
        )
        fake_extraction = {
            "classification": [{"label": "general", "confidence": 0.8, "evidence": []}],
            "confidence": 0.8,
        }
        request = LlmExtractionRequest(
            source_relpath="doc.md",
            provider=LlmProviderConfig(provider_id="openai", model_id="gpt-4o-mini"),
        )

        with patch("hks.llm.providers._openai_chat", return_value=fake_extraction):
            result = provider.extract(request, content="test content")

        assert result["confidence"] == 0.8


class TestProviderFor:
    def test_openai_provider_returned_when_api_key_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("HKS_LLM_NETWORK_OPT_IN", "1")
        request = LlmExtractionRequest(
            source_relpath="doc.md",
            provider=LlmProviderConfig(
                provider_id="openai",
                model_id="gpt-4o-mini",
                credential_status="present",
                network_opt_in=True,
            ),
        )

        result = provider_for(request)

        assert isinstance(result, OpenAIProvider)

    def test_fake_provider_for_fake_id(self) -> None:
        from hks.llm.providers import FakeProvider

        request = LlmExtractionRequest(source_relpath="doc.md")

        result = provider_for(request)

        assert isinstance(result, FakeProvider)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/llm/test_openai_provider.py -v`
Expected: FAIL — `OpenAIProvider` and `_openai_chat` not defined

- [ ] **Step 3: Implement `_openai_chat` and `OpenAIProvider`**

Replace `src/hks/llm/providers.py` content with:

```python
"""LLM provider protocol and deterministic fake provider."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from hks.llm.models import DEFAULT_FAKE_MODEL, LlmExtractionRequest


class LlmProvider(Protocol):
    def extract(self, request: LlmExtractionRequest, *, content: str) -> dict[str, Any]:
        """Return provider-native JSON-like extraction output."""


def _openai_chat(
    *,
    api_key: str,
    endpoint: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: int = 30,
) -> dict[str, Any]:
    url = f"{endpoint.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
    content_str = response.json()["choices"][0]["message"]["content"]
    try:
        parsed: dict[str, Any] = json.loads(content_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {content_str[:200]}") from exc
    return parsed


@dataclass(frozen=True, slots=True)
class OpenAIProvider:
    api_key: str
    endpoint: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout_seconds: int = 30

    def extract(self, request: LlmExtractionRequest, *, content: str) -> dict[str, Any]:
        from hks.llm.prompts import extraction_system_prompt, extraction_user_prompt

        messages = [
            {"role": "system", "content": extraction_system_prompt(request)},
            {"role": "user", "content": extraction_user_prompt(content)},
        ]
        return _openai_chat(
            api_key=self.api_key,
            endpoint=self.endpoint,
            model=self.model,
            messages=messages,
            timeout=self.timeout_seconds,
        )


@dataclass(frozen=True, slots=True)
class FakeProvider:
    malformed: bool = False
    side_effect: bool = False

    def extract(self, request: LlmExtractionRequest, *, content: str) -> dict[str, Any]:
        if self.malformed:
            return {"classification": "not-an-array", "confidence": 2.0}

        quote = _first_sentence(content) or request.source_relpath
        payload: dict[str, Any] = {
            "classification": [
                {
                    "label": _classify_label(content),
                    "confidence": 0.82,
                    "evidence": [_evidence(request.source_relpath, quote)],
                }
            ],
            "summary_candidate": _summary(content, request.source_relpath),
            "key_facts": [
                {
                    "fact": _summary(content, request.source_relpath),
                    "confidence": 0.78,
                    "evidence": [_evidence(request.source_relpath, quote)],
                }
            ],
            "entity_candidates": [
                {
                    "candidate_id": "entity:source",
                    "type": "Document",
                    "label": request.source_relpath,
                    "aliases": [],
                    "confidence": 0.9,
                    "evidence": [_evidence(request.source_relpath, quote)],
                },
                {
                    "candidate_id": "entity:concept",
                    "type": "Concept",
                    "label": _concept_label(content),
                    "aliases": [],
                    "confidence": 0.72,
                    "evidence": [_evidence(request.source_relpath, quote)],
                },
            ],
            "relation_candidates": [
                {
                    "candidate_id": "relation:references",
                    "type": "references",
                    "source_candidate_id": "entity:source",
                    "target_candidate_id": "entity:concept",
                    "confidence": 0.7,
                    "evidence": [_evidence(request.source_relpath, quote)],
                }
            ],
            "confidence": 0.8,
        }
        if self.side_effect:
            payload["side_effect_text"] = "ALSO write to wiki/pages/generated.md"
        return payload


def provider_for(request: LlmExtractionRequest) -> LlmProvider:
    provider_id = request.provider.provider_id
    if provider_id == "fake-malformed":
        return FakeProvider(malformed=True)
    if provider_id == "fake-side-effect":
        return FakeProvider(side_effect=True)
    if provider_id == "openai":
        from hks.core.config import config_value

        api_key = (
            config_value("HKS_LLM_PROVIDER_OPENAI_API_KEY")
            or config_value("OPENAI_API_KEY")
        )
        if not api_key:
            return FakeProvider()
        endpoint = (
            config_value("HKS_LLM_PROVIDER_OPENAI_ENDPOINT")
            or "https://api.openai.com/v1"
        )
        return OpenAIProvider(
            api_key=api_key,
            endpoint=endpoint,
            model=request.provider.model_id,
            timeout_seconds=request.provider.timeout_seconds,
        )
    return FakeProvider()


def fake_model_id() -> str:
    return DEFAULT_FAKE_MODEL


def _evidence(source_relpath: str, quote: str) -> dict[str, Any]:
    return {
        "source_relpath": source_relpath,
        "chunk_id": None,
        "quote": quote[:240] or source_relpath,
        "start_offset": 0,
        "end_offset": min(len(quote), 240) if quote else None,
    }


def _first_sentence(content: str) -> str:
    for line in content.splitlines():
        normalized = line.strip()
        if normalized:
            return normalized[:240]
    return ""


def _summary(content: str, fallback: str) -> str:
    first = _first_sentence(content)
    if not first:
        return f"{fallback} extraction candidate"
    return first[:240]


def _concept_label(content: str) -> str:
    lowered = content.lower()
    if "atlas" in lowered:
        return "Project Atlas"
    if "borealis" in lowered:
        return "Project Borealis"
    if "risk" in lowered:
        return "Risk"
    return "Knowledge Item"


def _classify_label(content: str) -> str:
    lowered = content.lower()
    if "dependency" in lowered:
        return "dependency"
    if "risk" in lowered:
        return "risk"
    if "project" in lowered:
        return "project"
    return "general"
```

- [ ] **Step 4: Update `llm/config.py` — add `"openai"` to `SUPPORTED_PROVIDERS` and update `build_provider_config()`**

In `src/hks/llm/config.py`, change line 18:

```python
SUPPORTED_PROVIDERS: frozenset[str] = frozenset(("fake", "fake-malformed", "fake-side-effect", "openai"))
```

And replace lines 74-79 (the final raise in `build_provider_config`) with:

```python
    return LlmProviderConfig(
        provider_id=provider,
        model_id=model,
        endpoint=endpoint,
        network_opt_in=network_opt_in,
        timeout_seconds=timeout_seconds,
        credential_status="present" if api_key else "missing",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/llm/test_openai_provider.py -v`
Expected: PASS

Run: `pytest tests/ -x -q`
Expected: All 272+ tests pass (no regressions)

- [ ] **Step 6: Commit**

```bash
git add src/hks/llm/providers.py src/hks/llm/config.py tests/unit/llm/test_openai_provider.py
git commit -m "feat(llm): add OpenAI-compatible provider with httpx client"
```

---

## Task 3: Replace NotImplementedError in PageIndex enrich

**Files:**
- Modify: `src/hks/page_tree/enrich.py:106-118`
- Modify: `tests/unit/page_tree/test_enrich.py:169-173`

- [ ] **Step 1: Update the existing test to expect success with mocked provider**

In `tests/unit/page_tree/test_enrich.py`, replace `test_non_fake_provider_is_not_implemented`:

```python
    def test_openai_provider_calls_llm_summarize(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tree = _rule_tree()
        source_text = "Chapter 1 content. " * 5 + "Section 1.1 detail. " * 3

        def mock_summarize(text: str, title: str, provider: str, model: str | None) -> str:
            return f"LLM summary of {title}"

        monkeypatch.setattr(
            "hks.page_tree.enrich._llm_summarize", mock_summarize
        )

        enriched = enrich_tree(tree, source_text, provider="openai")

        assert enriched.build_method == "llm"
        assert enriched.root_nodes[0].summary == "LLM summary of Chapter 1"
        assert enriched.root_nodes[0].children[0].summary == "LLM summary of Section 1.1"

    def test_openai_provider_restructures_degenerate_tree(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree = _degenerate_tree()

        def mock_restructure(
            tree: Any, source_text: str, provider: str, model: str | None
        ) -> Any:
            from hks.page_tree.model import PageTree, TreeNode
            from hks.core.manifest import utc_now_iso

            nodes = [
                TreeNode(
                    node_id="llm-n1", title="Introduction", level=1,
                    start_offset=0, end_offset=250, children=[], summary="Intro",
                ),
                TreeNode(
                    node_id="llm-n2", title="Body", level=1,
                    start_offset=250, end_offset=500, children=[], summary="Body",
                ),
            ]
            return PageTree(
                source_relpath=tree.source_relpath,
                source_format=tree.source_format,
                doc_title=tree.doc_title,
                root_nodes=nodes,
                build_method="llm",
                built_at=utc_now_iso(),
                total_nodes=2,
                source_sha256=tree.source_sha256,
            )

        monkeypatch.setattr(
            "hks.page_tree.enrich._llm_restructure", mock_restructure
        )

        enriched = enrich_tree(tree, "A" * 500, provider="openai")

        assert enriched.build_method == "llm"
        assert enriched.total_nodes == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/page_tree/test_enrich.py -v`
Expected: FAIL — still hits `NotImplementedError`

- [ ] **Step 3: Implement `_llm_summarize` and `_llm_restructure`**

In `src/hks/page_tree/enrich.py`, replace lines 106-118:

```python
def _llm_restructure(
    tree: PageTree,
    source_text: str,
    provider: str,
    model: str | None,
) -> PageTree:
    from hks.llm.providers import _openai_chat
    from hks.core.config import config_value

    api_key = config_value("HKS_LLM_PROVIDER_OPENAI_API_KEY") or config_value("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(f"LLM restructure requires API key for provider={provider}")
    endpoint = config_value("HKS_LLM_PROVIDER_OPENAI_ENDPOINT") or "https://api.openai.com/v1"

    messages = [
        {
            "role": "system",
            "content": (
                "You are a document structure analyzer. Given a document's full text, "
                "split it into 2-5 logical sections. Return JSON: "
                '{"sections": [{"title": "...", "start_offset": N, "end_offset": N}]}'
            ),
        },
        {"role": "user", "content": source_text[:8000]},
    ]
    result = _openai_chat(
        api_key=api_key,
        endpoint=endpoint,
        model=model or "gpt-4o-mini",
        messages=messages,
        timeout=60,
    )
    sections = result.get("sections", [])
    if not sections:
        return _fake_restructure(tree, source_text)

    nodes: list[TreeNode] = []
    for index, section in enumerate(sections):
        start = int(section.get("start_offset", 0))
        end = int(section.get("end_offset", len(source_text)))
        title = str(section.get("title", f"Section {index + 1}"))
        text_slice = source_text[start:end]
        summary = _llm_summarize(text_slice, title, provider, model) if text_slice.strip() else f"Summary of: {title}"
        nodes.append(
            TreeNode(
                node_id=f"llm-n{index + 1}",
                title=title,
                level=1,
                start_offset=start,
                end_offset=end,
                children=[],
                summary=summary,
            )
        )

    return PageTree(
        source_relpath=tree.source_relpath,
        source_format=tree.source_format,
        doc_title=tree.doc_title,
        root_nodes=nodes,
        build_method="llm",
        built_at=utc_now_iso(),
        total_nodes=_count_nodes(nodes),
        source_sha256=tree.source_sha256,
    )


def _llm_summarize(text: str, title: str, provider: str, model: str | None) -> str:
    from hks.llm.providers import _openai_chat
    from hks.core.config import config_value

    api_key = config_value("HKS_LLM_PROVIDER_OPENAI_API_KEY") or config_value("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(f"LLM summarize requires API key for provider={provider}")
    endpoint = config_value("HKS_LLM_PROVIDER_OPENAI_ENDPOINT") or "https://api.openai.com/v1"

    messages = [
        {
            "role": "system",
            "content": (
                "Summarize the following document section in one concise sentence. "
                'Return JSON: {"summary": "..."}'
            ),
        },
        {"role": "user", "content": f"Section: {title}\n\n{text[:4000]}"},
    ]
    result = _openai_chat(
        api_key=api_key,
        endpoint=endpoint,
        model=model or "gpt-4o-mini",
        messages=messages,
        timeout=30,
    )
    return str(result.get("summary", f"Summary of: {title}"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/page_tree/test_enrich.py -v`
Expected: PASS (new tests use monkeypatch, old tests still use fake provider)

Run: `pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/hks/page_tree/enrich.py tests/unit/page_tree/test_enrich.py
git commit -m "feat(page_tree): implement LLM summarize and restructure for enrich"
```

---

## Task 4: Evidence auto-aggregation in QueryResponse

**Files:**
- Modify: `src/hks/core/schema.py:58-77`
- Modify: `specs/005-phase3-lint-impl/contracts/query-response.schema.json`
- Create: `tests/unit/core/test_evidence_aggregation.py`

- [ ] **Step 1: Write failing tests for evidence aggregation**

Create `tests/unit/core/test_evidence_aggregation.py`:

```python
"""Unit tests for evidence auto-aggregation from trace steps."""

from __future__ import annotations

from hks.core.schema import QueryResponse, Trace, TraceStep


class TestEvidenceAggregation:
    def test_wiki_hit_produces_evidence(self) -> None:
        response = QueryResponse(
            answer="Atlas summary",
            source=["wiki"],
            confidence=1.0,
            trace=Trace(
                route="wiki",
                steps=[
                    TraceStep(
                        kind="wiki_lookup",
                        detail={
                            "slug": "atlas",
                            "hit": True,
                            "source_relpath": "atlas.md",
                        },
                    )
                ],
            ),
        )

        payload = response.to_dict()

        assert "evidence" in payload
        assert len(payload["evidence"]) == 1
        assert payload["evidence"][0]["source_relpath"] == "atlas.md"
        assert payload["evidence"][0]["route"] == "wiki"

    def test_graph_hit_expands_relpaths(self) -> None:
        response = QueryResponse(
            answer="graph answer",
            source=["graph"],
            confidence=0.88,
            trace=Trace(
                route="graph",
                steps=[
                    TraceStep(
                        kind="graph_lookup",
                        detail={
                            "hit": True,
                            "relpaths": ["dep-map.md", "impact.pdf"],
                            "node_ids": ["n1"],
                            "edge_ids": ["e1"],
                            "relations": ["impacts"],
                        },
                    )
                ],
            ),
        )

        payload = response.to_dict()

        assert len(payload["evidence"]) == 2
        relpaths = [e["source_relpath"] for e in payload["evidence"]]
        assert "dep-map.md" in relpaths
        assert "impact.pdf" in relpaths
        assert all(e["route"] == "graph" for e in payload["evidence"])

    def test_vector_hit_includes_section_and_page(self) -> None:
        response = QueryResponse(
            answer="vector text",
            source=["vector"],
            confidence=0.75,
            trace=Trace(
                route="vector",
                steps=[
                    TraceStep(
                        kind="vector_lookup",
                        detail={
                            "top_k": 5,
                            "top_similarity": 0.8,
                            "source_relpath": "report.pdf",
                            "section_path": "Chapter 1 > Methods",
                            "page_range": {"start": 3, "end": 5},
                        },
                    )
                ],
            ),
        )

        payload = response.to_dict()

        assert len(payload["evidence"]) == 1
        ev = payload["evidence"][0]
        assert ev["source_relpath"] == "report.pdf"
        assert ev["section_path"] == "Chapter 1 > Methods"
        assert ev["page_range"] == {"start": 3, "end": 5}
        assert ev["route"] == "vector"

    def test_no_hit_omits_evidence(self) -> None:
        response = QueryResponse(
            answer="not found",
            source=[],
            confidence=0.0,
            trace=Trace(
                route="vector",
                steps=[
                    TraceStep(
                        kind="vector_lookup",
                        detail={"top_k": 5, "top_similarity": 0.1},
                    )
                ],
            ),
        )

        payload = response.to_dict()

        assert "evidence" not in payload

    def test_dedupes_by_relpath_and_route(self) -> None:
        response = QueryResponse(
            answer="combined",
            source=["wiki", "vector"],
            confidence=0.9,
            trace=Trace(
                route="wiki",
                steps=[
                    TraceStep(
                        kind="wiki_lookup",
                        detail={"hit": True, "source_relpath": "atlas.md"},
                    ),
                    TraceStep(
                        kind="vector_lookup",
                        detail={
                            "top_k": 5,
                            "top_similarity": 0.8,
                            "source_relpath": "atlas.md",
                        },
                    ),
                ],
            ),
        )

        payload = response.to_dict()

        assert len(payload["evidence"]) == 2
        routes = {e["route"] for e in payload["evidence"]}
        assert routes == {"wiki", "vector"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/core/test_evidence_aggregation.py -v`
Expected: FAIL — `evidence` not in payload

- [ ] **Step 3: Implement `_aggregate_evidence` and update `to_dict()`**

In `src/hks/core/schema.py`, add a module-level function and modify `QueryResponse.to_dict()`:

Add before the `QueryResponse` class:

```python
def _aggregate_evidence(steps: list[TraceStep]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for step in steps:
        if step.kind == "wiki_lookup" and step.detail.get("hit"):
            relpath = step.detail.get("source_relpath")
            if isinstance(relpath, str):
                key = (relpath, "wiki")
                if key not in seen:
                    seen.add(key)
                    evidence.append({"source_relpath": relpath, "route": "wiki"})

        elif step.kind == "graph_lookup" and step.detail.get("hit"):
            for relpath in step.detail.get("relpaths", []):
                if isinstance(relpath, str):
                    key = (relpath, "graph")
                    if key not in seen:
                        seen.add(key)
                        evidence.append({"source_relpath": relpath, "route": "graph"})

        elif step.kind == "vector_lookup":
            relpath = step.detail.get("source_relpath")
            if isinstance(relpath, str):
                key = (relpath, "vector")
                if key not in seen:
                    seen.add(key)
                    entry: dict[str, Any] = {"source_relpath": relpath, "route": "vector"}
                    section_path = step.detail.get("section_path")
                    if section_path is not None:
                        entry["section_path"] = section_path
                    page_range = step.detail.get("page_range")
                    if isinstance(page_range, dict):
                        entry["page_range"] = page_range
                    evidence.append(entry)

    return evidence
```

Modify `QueryResponse.to_dict()`:

```python
    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "answer": self.answer,
            "source": self.source,
            "confidence": self.confidence,
            "trace": self.trace.to_dict(),
        }
        evidence = _aggregate_evidence(self.trace.steps)
        if evidence:
            payload["evidence"] = evidence
        return payload
```

- [ ] **Step 4: Update JSON schema**

In `specs/005-phase3-lint-impl/contracts/query-response.schema.json`, add `"evidence"` to the `properties` object (after `"trace"`):

```json
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["source_relpath", "route"],
        "additionalProperties": true,
        "properties": {
          "source_relpath": { "type": "string" },
          "section_path": { "type": "string" },
          "page_range": {
            "type": "object",
            "properties": {
              "start": { "type": "integer" },
              "end": { "type": "integer" }
            }
          },
          "quote": { "type": "string", "maxLength": 240 },
          "route": { "type": "string", "enum": ["wiki", "graph", "vector"] }
        }
      }
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/core/test_evidence_aggregation.py -v`
Expected: PASS

Run: `pytest tests/ -x -q`
Expected: All tests pass (contract tests still validate — evidence is optional)

- [ ] **Step 6: Commit**

```bash
git add src/hks/core/schema.py specs/005-phase3-lint-impl/contracts/query-response.schema.json tests/unit/core/test_evidence_aggregation.py
git commit -m "feat(schema): add evidence auto-aggregation from trace steps"
```

---

## Task 5: Fused retrieval — Candidate model and collector functions

**Files:**
- Modify: `src/hks/commands/query.py`
- Create: `tests/unit/commands/test_fused_retrieval.py`

- [ ] **Step 1: Write failing tests for candidate collection**

Create `tests/unit/commands/test_fused_retrieval.py`:

```python
"""Unit tests for fused retrieval pipeline."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from hks.commands.query import Candidate, _collect_wiki_candidates, _collect_graph_candidates, _collect_vector_candidates
from hks.storage.vector import SearchHit


class TestCandidate:
    def test_candidate_fields(self) -> None:
        c = Candidate(
            text="answer text",
            source_route="wiki",
            score=0.9,
            metadata={"source_relpath": "doc.md"},
        )
        assert c.text == "answer text"
        assert c.source_route == "wiki"
        assert c.score == 0.9
        assert c.metadata["source_relpath"] == "doc.md"


class TestCollectWikiCandidates:
    def test_returns_candidate_on_hit(self) -> None:
        wiki_store = MagicMock()
        page = MagicMock()
        page.title = "Atlas"
        page.summary = "Atlas project summary"
        page.source_relpath = "atlas.md"
        page.slug = "atlas"
        wiki_store.search.return_value = page

        candidates, steps = _collect_wiki_candidates("Atlas 摘要", wiki_store=wiki_store)

        assert len(candidates) == 1
        assert candidates[0].source_route == "wiki"
        assert "Atlas" in candidates[0].text
        assert candidates[0].metadata["source_relpath"] == "atlas.md"

    def test_returns_empty_on_miss(self) -> None:
        wiki_store = MagicMock()
        wiki_store.search.return_value = None
        wiki_store.overview.return_value = None

        candidates, steps = _collect_wiki_candidates("random question", wiki_store=wiki_store)

        assert len(candidates) == 0


class TestCollectGraphCandidates:
    def test_returns_candidate_on_hit(self) -> None:
        graph_store = MagicMock()
        mock_result = MagicMock()
        mock_result.answer = "A impacts B"
        mock_result.confidence = 0.88
        mock_result.relpaths = ["dep.md"]
        mock_result.node_ids = ["n1", "n2"]
        mock_result.edge_ids = ["e1"]
        mock_result.relations = ["impacts"]

        with MagicMock() as mock_answer_query:
            import hks.commands.query as qmod

            original = qmod.answer_query
            qmod.answer_query = lambda q, gs: mock_result

            candidates, steps = _collect_graph_candidates(
                "impact analysis", graph_store=graph_store
            )

            qmod.answer_query = original

        assert len(candidates) == 1
        assert candidates[0].source_route == "graph"

    def test_returns_empty_on_miss(self) -> None:
        graph_store = MagicMock()

        import hks.commands.query as qmod

        original = qmod.answer_query
        qmod.answer_query = lambda q, gs: None

        candidates, steps = _collect_graph_candidates("no match", graph_store=graph_store)

        qmod.answer_query = original

        assert len(candidates) == 0


class TestCollectVectorCandidates:
    def test_returns_multiple_candidates(self) -> None:
        vector_store = MagicMock()
        vector_store.count.return_value = 10
        vector_store.search.return_value = [
            SearchHit(chunk_id="c1", text="matching text alpha", similarity=0.85, metadata={"source_relpath": "a.md"}),
            SearchHit(chunk_id="c2", text="matching text beta", similarity=0.72, metadata={"source_relpath": "b.md"}),
        ]

        manifest = MagicMock()
        candidates, steps = _collect_vector_candidates(
            "matching text",
            vector_store=vector_store,
            manifest=manifest,
        )

        assert len(candidates) >= 1
        assert all(c.source_route == "vector" for c in candidates)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/commands/test_fused_retrieval.py -v`
Expected: FAIL — `Candidate` and `_collect_*_candidates` not defined

- [ ] **Step 3: Add `Candidate` dataclass and `_collect_*` functions to `query.py`**

In `src/hks/commands/query.py`, add after the existing imports:

```python
from dataclasses import dataclass

@dataclass(slots=True)
class Candidate:
    text: str
    source_route: Route
    score: float
    metadata: dict[str, object]
```

Add three new functions (keep the existing `_try_*` functions for now — they will be removed in Task 6):

```python
def _collect_wiki_candidates(
    question: str,
    *,
    wiki_store: WikiStore,
) -> tuple[list[Candidate], list[TraceStep]]:
    steps: list[TraceStep] = []
    candidates: list[Candidate] = []

    page = wiki_store.search(question)
    if page is not None:
        steps.append(
            TraceStep(
                kind="wiki_lookup",
                detail={"slug": page.slug, "hit": True, "source_relpath": page.source_relpath},
            )
        )
        candidates.append(
            Candidate(
                text=f"{page.title}: {page.summary}",
                source_route="wiki",
                score=1.0,
                metadata={"source_relpath": page.source_relpath, "slug": page.slug},
            )
        )
    else:
        overview = wiki_store.overview()
        if overview and _has_wiki_secondary_intent(question):
            steps.append(
                TraceStep(kind="wiki_lookup", detail={"slug": None, "hit": True, "mode": "overview"})
            )
            candidates.append(
                Candidate(text=overview, source_route="wiki", score=0.7, metadata={})
            )
        else:
            steps.append(TraceStep(kind="wiki_lookup", detail={"hit": False}))

    return candidates, steps


def _collect_graph_candidates(
    question: str,
    *,
    graph_store: GraphStore,
) -> tuple[list[Candidate], list[TraceStep]]:
    steps: list[TraceStep] = []
    candidates: list[Candidate] = []

    graph_result = answer_query(question, graph_store)
    if graph_result is None:
        steps.append(TraceStep(kind="graph_lookup", detail={"hit": False}))
        return candidates, steps

    steps.append(
        TraceStep(
            kind="graph_lookup",
            detail=_graph_trace_detail(
                relpaths=graph_result.relpaths,
                node_ids=graph_result.node_ids,
                edge_ids=graph_result.edge_ids,
                relations=graph_result.relations,
            ),
        )
    )
    candidates.append(
        Candidate(
            text=graph_result.answer,
            source_route="graph",
            score=graph_result.confidence,
            metadata={"relpaths": graph_result.relpaths},
        )
    )
    return candidates, steps


def _collect_vector_candidates(
    question: str,
    *,
    vector_store: VectorStore,
    manifest: Manifest,
) -> tuple[list[Candidate], list[TraceStep]]:
    steps: list[TraceStep] = []
    candidates: list[Candidate] = []

    candidate_limit = max(5, min(50, vector_store.count()))
    hits = vector_store.search(question, top_k=candidate_limit)
    top_similarity = hits[0].similarity if hits else 0.0

    relevant_hits = [hit for hit in hits if _vector_hit_is_relevant(question, hit)]
    tree_store = TreeStore(vector_store.paths)

    for hit in relevant_hits[:5]:
        metadata: dict[str, object] = dict(hit.metadata)
        section_ctx = _vector_section_context(
            chosen_hit=hit, manifest=manifest, tree_store=tree_store
        )
        metadata.update(section_ctx)
        candidates.append(
            Candidate(
                text=hit.text,
                source_route="vector",
                score=hit.similarity,
                metadata=metadata,
            )
        )

    detail = _vector_trace_detail(
        top_k=candidate_limit,
        top_similarity=top_similarity,
        chosen_hit=relevant_hits[0] if relevant_hits else None,
        manifest=manifest,
        tree_store=tree_store,
    )
    steps.append(TraceStep(kind="vector_lookup", detail=detail))

    return candidates, steps
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/commands/test_fused_retrieval.py -v`
Expected: PASS

Run: `pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/hks/commands/query.py tests/unit/commands/test_fused_retrieval.py
git commit -m "feat(query): add Candidate model and collector functions for fused retrieval"
```

---

## Task 6: Fused retrieval — Reranker and pipeline rewrite

**Files:**
- Modify: `src/hks/commands/query.py`
- Modify: `tests/unit/commands/test_fused_retrieval.py`

- [ ] **Step 1: Write failing tests for RRF reranker and LLM reranker**

Add to `tests/unit/commands/test_fused_retrieval.py`:

```python
from hks.commands.query import _rrf_rerank, _llm_rerank, _rerank_candidates


class TestRRFRerank:
    def test_ranks_by_reciprocal_fusion(self) -> None:
        candidates = [
            Candidate(text="wiki hit", source_route="wiki", score=1.0, metadata={}),
            Candidate(text="vector hit", source_route="vector", score=0.9, metadata={}),
            Candidate(text="graph hit", source_route="graph", score=0.7, metadata={}),
        ]

        ranked = _rrf_rerank(candidates)

        assert len(ranked) == 3
        assert ranked[0].score >= ranked[1].score >= ranked[2].score

    def test_empty_candidates(self) -> None:
        assert _rrf_rerank([]) == []


class TestRerankCandidates:
    def test_uses_rrf_when_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        candidates = [
            Candidate(text="a", source_route="wiki", score=1.0, metadata={}),
            Candidate(text="b", source_route="vector", score=0.5, metadata={}),
        ]

        ranked, strategy = _rerank_candidates("question", candidates)

        assert strategy == "rrf"
        assert len(ranked) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/commands/test_fused_retrieval.py::TestRRFRerank -v`
Expected: FAIL — `_rrf_rerank` not defined

- [ ] **Step 3: Implement reranker functions**

Add to `src/hks/commands/query.py`:

```python
def _rrf_rerank(candidates: list[Candidate], *, k: int = 60) -> list[Candidate]:
    if not candidates:
        return []

    source_groups: dict[Route, list[Candidate]] = {}
    for c in candidates:
        source_groups.setdefault(c.source_route, []).append(c)

    for route_candidates in source_groups.values():
        route_candidates.sort(key=lambda c: c.score, reverse=True)

    rrf_scores: dict[int, float] = {}
    for route_candidates in source_groups.values():
        for rank, c in enumerate(route_candidates):
            idx = candidates.index(c)
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (k + rank + 1)

    ranked_indices = sorted(rrf_scores, key=lambda i: rrf_scores[i], reverse=True)
    return [
        Candidate(
            text=candidates[i].text,
            source_route=candidates[i].source_route,
            score=round(rrf_scores[i], 6),
            metadata=candidates[i].metadata,
        )
        for i in ranked_indices
    ]


def _llm_rerank(
    question: str,
    candidates: list[Candidate],
) -> list[Candidate]:
    from hks.llm.providers import _openai_chat
    from hks.core.config import config_value

    api_key = config_value("HKS_LLM_PROVIDER_OPENAI_API_KEY") or config_value("OPENAI_API_KEY")
    if not api_key:
        return _rrf_rerank(candidates)
    endpoint = config_value("HKS_LLM_PROVIDER_OPENAI_ENDPOINT") or "https://api.openai.com/v1"
    model = config_value("HKS_LLM_MODEL") or "gpt-4o-mini"

    capped = candidates[:10]
    snippet_list = "\n".join(
        f"[{i}] ({c.source_route}) {c.text[:200]}" for i, c in enumerate(capped)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a relevance ranker. Given a question and numbered text snippets, "
                "return a JSON object with a 'ranking' key containing an array of snippet "
                "indices sorted by relevance (most relevant first). "
                'Example: {"ranking": [2, 0, 1]}'
            ),
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nSnippets:\n{snippet_list}",
        },
    ]

    try:
        result = _openai_chat(
            api_key=api_key,
            endpoint=endpoint,
            model=model,
            messages=messages,
            timeout=30,
        )
        ranking = result.get("ranking", [])
        if not isinstance(ranking, list):
            return _rrf_rerank(candidates)

        ranked: list[Candidate] = []
        seen: set[int] = set()
        for idx in ranking:
            if isinstance(idx, int) and 0 <= idx < len(capped) and idx not in seen:
                seen.add(idx)
                ranked.append(
                    Candidate(
                        text=capped[idx].text,
                        source_route=capped[idx].source_route,
                        score=round(1.0 - (len(ranked) * 0.05), 4),
                        metadata=capped[idx].metadata,
                    )
                )
        for i, c in enumerate(capped):
            if i not in seen:
                ranked.append(c)
        return ranked
    except Exception:
        return _rrf_rerank(candidates)


def _rerank_candidates(
    question: str,
    candidates: list[Candidate],
) -> tuple[list[Candidate], str]:
    from hks.core.config import config_value

    api_key = config_value("HKS_LLM_PROVIDER_OPENAI_API_KEY") or config_value("OPENAI_API_KEY")
    if api_key:
        ranked = _llm_rerank(question, candidates)
        return ranked, "llm-rerank"
    ranked = _rrf_rerank(candidates)
    return ranked, "rrf"
```

- [ ] **Step 4: Rewrite `run()` to use the fused pipeline**

Replace the `run()` function in `src/hks/commands/query.py`:

```python
def run(question: str, *, writeback: str = "auto") -> QueryResponse:
    paths = runtime_paths()
    if not paths.manifest.exists():
        raise KSError(
            "/ks/ 尚未初始化，請先執行 ks ingest <path>",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks ingest <path>`",
        )

    manifest = resume_or_rebuild(paths)
    if not manifest.entries:
        raise KSError(
            "/ks/ 尚未初始化，請先執行 ks ingest <path>",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks ingest <path>`",
        )

    rule_set = load_rules(paths.root)
    decision = route_query(question, rule_set)
    steps = list(decision.steps)
    wiki_store = WikiStore(paths)
    graph_store = GraphStore(paths)
    vector_store = VectorStore(paths)

    # Collect candidates from all sources
    all_candidates: list[Candidate] = []

    wiki_candidates, wiki_steps = _collect_wiki_candidates(question, wiki_store=wiki_store)
    all_candidates.extend(wiki_candidates)
    steps.extend(wiki_steps)

    graph_candidates, graph_steps = _collect_graph_candidates(question, graph_store=graph_store)
    all_candidates.extend(graph_candidates)
    steps.extend(graph_steps)

    vector_candidates, vector_steps = _collect_vector_candidates(
        question, vector_store=vector_store, manifest=manifest
    )
    all_candidates.extend(vector_candidates)
    steps.extend(vector_steps)

    if not all_candidates:
        response = _build_no_hit_response(decision.route, steps)
        return _maybe_writeback(
            question=question, response=response, writeback=writeback, wiki_store=wiki_store
        )

    # Rerank
    ranked, strategy = _rerank_candidates(question, all_candidates)
    steps.append(
        TraceStep(
            kind="merge",
            detail={
                "strategy": strategy,
                "candidate_count": len(all_candidates),
                "top_candidate": {
                    "route": ranked[0].source_route,
                    "score": ranked[0].score,
                },
            },
        )
    )

    winner = ranked[0]
    final_route = winner.source_route

    response = QueryResponse(
        answer=winner.text,
        source=[winner.source_route],
        confidence=winner.score,
        trace=Trace(route=final_route, steps=steps),
    )
    return _maybe_writeback(
        question=question, response=response, writeback=writeback, wiki_store=wiki_store
    )
```

Remove the old `_try_route`, `_secondary_fallback_route`, `_append_fallback` functions and the old `run()` body. Keep `_try_wiki`, `_try_graph`, `_try_vector` only if needed by other code; otherwise remove them.

- [ ] **Step 5: Update `test_query_vector_selection.py` if imports break**

Check that `_choose_vector_hit` is still importable. If it was removed, update the test to import from the new location or keep the function.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/hks/commands/query.py tests/unit/commands/test_fused_retrieval.py tests/unit/commands/test_query_vector_selection.py
git commit -m "feat(query): rewrite pipeline to fused retrieval with LLM rerank + RRF fallback"
```

---

## Task 7: Eval set — JSONL files and runners

**Files:**
- Create: `evals/pageindex_enrich.jsonl`
- Create: `evals/rerank.jsonl`
- Create: `evals/e2e_query.jsonl`
- Create: `tests/eval/__init__.py`
- Create: `tests/eval/conftest.py`
- Create: `tests/eval/test_enrich_eval.py`
- Create: `tests/eval/test_rerank_eval.py`
- Create: `tests/eval/test_e2e_query_eval.py`

- [ ] **Step 1: Create eval JSONL files**

Create `evals/pageindex_enrich.jsonl`:

```jsonl
{"id": "enrich-01", "input": {"source_text": "Introduction\n\nThis document describes the Atlas project. Atlas is a distributed data platform designed for real-time analytics.\n\nArchitecture\n\nAtlas uses a microservices architecture with three main components.", "tree_json": {"source_relpath": "atlas.md", "total_nodes": 1}}, "expected": {"summary_contains": "Atlas", "node_count_min": 2}}
{"id": "enrich-02", "input": {"source_text": "Risk Assessment Report\n\nThe following risks have been identified:\n1. Supply chain delays\n2. Data anonymization incomplete\n3. Budget overrun potential", "tree_json": {"source_relpath": "risks.md", "total_nodes": 1}}, "expected": {"summary_contains": "risk", "node_count_min": 2}}
{"id": "enrich-03", "input": {"source_text": "Short note about meeting.", "tree_json": {"source_relpath": "note.md", "total_nodes": 2}}, "expected": {"summary_contains": "meeting"}}
{"id": "enrich-04", "input": {"source_text": "Chapter 1: Background\nThe project was initiated in 2024.\n\nChapter 2: Methods\nWe used quantitative analysis.\n\nChapter 3: Results\nKey findings include improved latency.", "tree_json": {"source_relpath": "report.md", "total_nodes": 3}}, "expected": {"summary_contains": "project", "node_count_min": 2}}
{"id": "enrich-05", "input": {"source_text": "API Reference\n\nGET /users - List all users\nPOST /users - Create user\nDELETE /users/:id - Delete user", "tree_json": {"source_relpath": "api.md", "total_nodes": 1}}, "expected": {"summary_contains": "API", "node_count_min": 2}}
```

Create `evals/rerank.jsonl`:

```jsonl
{"id": "rerank-01", "question": "Atlas 的架構是什麼？", "candidates": [{"text": "Atlas uses microservices architecture", "route": "wiki", "score": 1.0}, {"text": "Risk assessment for Q4", "route": "vector", "score": 0.8}], "expected_top_route": "wiki"}
{"id": "rerank-02", "question": "A 影響了哪些服務？", "candidates": [{"text": "A impacts checkout service", "route": "graph", "score": 0.88}, {"text": "Service overview document", "route": "wiki", "score": 1.0}], "expected_top_route": "graph"}
{"id": "rerank-03", "question": "supply chain delay risk", "candidates": [{"text": "Supply chain delays identified as key risk", "route": "vector", "score": 0.75}, {"text": "Project timeline overview", "route": "wiki", "score": 0.6}], "expected_top_route": "vector"}
{"id": "rerank-04", "question": "dependency between Atlas and Borealis", "candidates": [{"text": "Atlas depends on Borealis data feed", "route": "graph", "score": 0.9}, {"text": "Atlas project summary", "route": "wiki", "score": 1.0}, {"text": "Borealis integration notes", "route": "vector", "score": 0.7}], "expected_top_route": "graph"}
{"id": "rerank-05", "question": "專案總結", "candidates": [{"text": "Project Atlas: distributed analytics platform", "route": "wiki", "score": 1.0}, {"text": "Atlas architecture diagram", "route": "vector", "score": 0.5}], "expected_top_route": "wiki"}
```

Create `evals/e2e_query.jsonl`:

```jsonl
{"id": "e2e-01", "question": "Atlas 的摘要", "expected_route": "wiki", "expected_answer_contains": "Atlas"}
{"id": "e2e-02", "question": "A 影響了什麼服務？", "expected_route": "graph", "expected_answer_contains": "影響"}
{"id": "e2e-03", "question": "supply chain risk", "expected_route": "vector"}
{"id": "e2e-04", "question": "Atlas 的依賴關係", "expected_route": "graph"}
{"id": "e2e-05", "question": "專案總結", "expected_route": "wiki"}
```

- [ ] **Step 2: Create eval test infrastructure**

Create `tests/eval/__init__.py` (empty file).

Create `tests/eval/conftest.py`:

```python
"""Shared eval fixtures and env-gate skip logic."""

from __future__ import annotations

import os

import pytest

OPENAI_KEY_ENV = "HKS_LLM_PROVIDER_OPENAI_API_KEY"

requires_openai = pytest.mark.skipif(
    not os.environ.get(OPENAI_KEY_ENV) and not os.environ.get("OPENAI_API_KEY"),
    reason=f"Set {OPENAI_KEY_ENV} or OPENAI_API_KEY to run eval tests",
)
```

- [ ] **Step 3: Create eval test runners**

Create `tests/eval/test_enrich_eval.py`:

```python
"""Eval runner for PageIndex enrich quality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.conftest import requires_openai

EVAL_PATH = Path(__file__).resolve().parents[2] / "evals" / "pageindex_enrich.jsonl"


def _load_cases() -> list[dict]:
    if not EVAL_PATH.exists():
        return []
    return [json.loads(line) for line in EVAL_PATH.read_text().splitlines() if line.strip()]


@requires_openai
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_enrich_eval(case: dict) -> None:
    from hks.page_tree.enrich import enrich_tree
    from hks.page_tree.model import PageTree, TreeNode

    source_text = case["input"]["source_text"]
    tree_json = case["input"]["tree_json"]
    total_nodes = tree_json.get("total_nodes", 1)

    nodes = [
        TreeNode(
            node_id="n1",
            title="Root",
            level=1,
            start_offset=0,
            end_offset=len(source_text),
            children=[],
        )
    ]
    tree = PageTree(
        source_relpath=tree_json["source_relpath"],
        source_format="md",
        doc_title="Eval",
        root_nodes=nodes,
        build_method="rule",
        built_at="2026-01-01T00:00:00Z",
        total_nodes=total_nodes,
        source_sha256="eval",
    )

    enriched = enrich_tree(tree, source_text, provider="openai", force=True)

    expected = case["expected"]
    if "summary_contains" in expected:
        all_summaries = " ".join(n.summary.lower() for n in enriched.flat_nodes())
        assert expected["summary_contains"].lower() in all_summaries, (
            f"Expected '{expected['summary_contains']}' in summaries"
        )
    if "node_count_min" in expected:
        assert enriched.total_nodes >= expected["node_count_min"]
```

Create `tests/eval/test_rerank_eval.py`:

```python
"""Eval runner for LLM reranker quality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.conftest import requires_openai

EVAL_PATH = Path(__file__).resolve().parents[2] / "evals" / "rerank.jsonl"


def _load_cases() -> list[dict]:
    if not EVAL_PATH.exists():
        return []
    return [json.loads(line) for line in EVAL_PATH.read_text().splitlines() if line.strip()]


@requires_openai
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_rerank_eval(case: dict) -> None:
    from hks.commands.query import Candidate, _llm_rerank

    candidates = [
        Candidate(
            text=c["text"],
            source_route=c["route"],
            score=c["score"],
            metadata={},
        )
        for c in case["candidates"]
    ]

    ranked = _llm_rerank(case["question"], candidates)

    assert ranked[0].source_route == case["expected_top_route"], (
        f"Expected top route {case['expected_top_route']}, got {ranked[0].source_route}"
    )
```

Create `tests/eval/test_e2e_query_eval.py`:

```python
"""Eval runner for end-to-end query pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.conftest import requires_openai

EVAL_PATH = Path(__file__).resolve().parents[2] / "evals" / "e2e_query.jsonl"


def _load_cases() -> list[dict]:
    if not EVAL_PATH.exists():
        return []
    return [json.loads(line) for line in EVAL_PATH.read_text().splitlines() if line.strip()]


@requires_openai
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_e2e_query_eval(case: dict, tmp_path: Path) -> None:
    pytest.skip("E2E eval requires a fully ingested KS root — run manually with a prepared fixture")
```

- [ ] **Step 4: Run eval tests (should skip without API key)**

Run: `pytest tests/eval/ -v`
Expected: All tests SKIPPED (no API key set in CI/local)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All tests pass (evals skipped)

- [ ] **Step 6: Commit**

```bash
git add evals/ tests/eval/
git commit -m "feat(evals): add eval JSONL and runners for enrich, rerank, and e2e query"
```

---

## Task 8: Final cleanup and verification

**Files:**
- Modify: `src/hks/commands/query.py` (remove dead code)

- [ ] **Step 1: Remove unused functions from `query.py`**

Remove these functions that are no longer called after the pipeline rewrite:
- `_try_wiki`
- `_try_graph`
- `_try_vector`
- `_try_route`
- `_secondary_fallback_route`
- `_append_fallback`
- The old `run()` body (already replaced in Task 6)

Keep:
- `_lexical_terms`, `_vector_hit_is_relevant`, `_vector_hit_lexical_score`, `_choose_vector_hit` (used by `_collect_vector_candidates` and test)
- `_build_no_hit_response`, `_vector_trace_detail`, `_vector_section_context`, `_graph_trace_detail`
- `_has_wiki_secondary_intent`
- `_maybe_writeback`, `_build_writeback_context`
- All new functions: `Candidate`, `_collect_*`, `_rrf_rerank`, `_llm_rerank`, `_rerank_candidates`, `run()`

- [ ] **Step 2: Run mypy**

Run: `mypy src/hks/commands/query.py src/hks/llm/providers.py src/hks/page_tree/enrich.py src/hks/core/schema.py --ignore-missing-imports`
Expected: No errors

- [ ] **Step 3: Run ruff**

Run: `ruff check src/hks/commands/query.py src/hks/llm/providers.py src/hks/page_tree/enrich.py src/hks/core/schema.py`
Expected: No errors

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/hks/commands/query.py
git commit -m "refactor(query): remove dead fallback code after fused retrieval rewrite"
```

---

## Verification Checklist

After all tasks complete, confirm:

- [ ] `pytest tests/ -q` — all tests pass
- [ ] `mypy src/hks/ --ignore-missing-imports` — no type errors
- [ ] `ruff check src/hks/` — no lint errors
- [ ] `ks query "Atlas 摘要"` with a real KS root — produces evidence in output
- [ ] Trace contains `merge` step with strategy field
- [ ] Without API key: rerank falls back to RRF
- [ ] `ks pageindex enrich --provider openai` with API key — no `NotImplementedError`

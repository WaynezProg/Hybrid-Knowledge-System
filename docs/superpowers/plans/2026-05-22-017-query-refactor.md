# 017 Query Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the large `src/hks/commands/query.py` into focused retriever, rerank, evidence, and orchestration modules without changing public query behavior.

**Architecture:** 017 is a behavior-preserving refactor and must only start after 014-016 are green. Move data structures and pure helpers first, then route collectors, then rerankers, and leave `commands/query.py` as the orchestration layer: load runtime, collect candidates, rerank, assess confidence, build response, and call writeback. The 016 golden retrieval quality gate must pass before and after the refactor.

**Tech Stack:** Python 3.12, dataclasses, existing `hks.core.schema`, existing `hks.commands.query.run`, existing 016 `hks.evaluation` gate.

**Spec:** `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md` § 017.

---

## File Map

### New Files

| File | Responsibility |
|---|---|
| `src/hks/retrieval/models.py` | Shared `Candidate` dataclass |
| `src/hks/retrieval/evidence.py` | Candidate-to-evidence helpers and quote normalization |
| `src/hks/retrievers/__init__.py` | Retriever package marker |
| `src/hks/retrievers/wiki.py` | Wiki candidate collector |
| `src/hks/retrievers/graph.py` | Graph candidate collector and trace detail helper |
| `src/hks/retrievers/vector.py` | Vector candidate collector, lexical relevance, section context |
| `src/hks/retrievers/page_tree.py` | PageTree candidate collector and node scoring |
| `src/hks/rerank/__init__.py` | Rerank package marker |
| `src/hks/rerank/rrf.py` | Deterministic RRF reranker |
| `src/hks/rerank/llm.py` | LLM reranker, fallback detail, error classification |
| `tests/unit/retrievers/__init__.py` | Retriever unit-test package marker |
| `tests/unit/retrievers/test_wiki.py` | Migrated wiki collector tests |
| `tests/unit/retrievers/test_graph.py` | Migrated graph collector tests |
| `tests/unit/retrievers/test_vector.py` | Migrated vector collector and lexical selection tests |
| `tests/unit/retrievers/test_page_tree.py` | Migrated PageTree collector tests |
| `tests/unit/rerank/__init__.py` | Rerank unit-test package marker |
| `tests/unit/rerank/test_rrf.py` | Migrated RRF tests |
| `tests/unit/rerank/test_llm.py` | Migrated LLM fallback/detail tests |
| `tests/unit/retrieval/test_evidence.py` | Migrated evidence-generation tests |

### Modified Files

| File | Change |
|---|---|
| `src/hks/commands/query.py` | Reduce to orchestration and writeback helpers |
| `tests/unit/commands/test_fused_retrieval.py` | Remove tests for private helpers moved to module-level tests; keep orchestration-level smoke only if needed |
| `tests/unit/commands/test_page_tree_retrieval.py` | Move assertions to `tests/unit/retrievers/test_page_tree.py` |
| `tests/unit/commands/test_query_vector_selection.py` | Move assertions to `tests/unit/retrievers/test_vector.py` |
| `tests/eval/test_rerank_eval.py` | Import `_llm_rerank` replacement from `hks.rerank.llm` |
| `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md` | Mark 017 implemented after completion |

---

## Task 0: Pre-Refactor Guard

**Files:**
- No file changes

- [x] **Step 1: Prove 016 gate is green before moving code**

Run:

```bash
uv run pytest tests/eval/test_golden_retrieval_quality.py -q
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

Expected: all pass. Stop if the 016 gate is missing or failing.

---

## Task 1: Shared Candidate And Evidence Modules

**Files:**
- Create: `src/hks/retrieval/models.py`
- Create: `src/hks/retrieval/evidence.py`
- Create: `tests/unit/retrieval/test_evidence.py`
- Modify: `src/hks/commands/query.py`
- Modify: `tests/unit/commands/test_fused_retrieval.py`

- [x] **Step 1: Write the evidence unit tests against the new module path**

Create `tests/unit/retrieval/test_evidence.py`:

```python
"""Unit tests for candidate evidence generation."""

from __future__ import annotations

from hks.retrieval.evidence import candidate_evidence, evidence_quote
from hks.retrieval.models import Candidate


def test_evidence_quote_normalizes_whitespace_and_caps_length() -> None:
    text = "  alpha\\n\\n beta   gamma  "
    assert evidence_quote(text, limit=12) == "alpha beta g"


def test_wiki_candidate_evidence_uses_source_relpath_and_quote_metadata() -> None:
    candidate = Candidate(
        text="Atlas summary",
        source_route="wiki",
        score=1.0,
        metadata={
            "source_relpath": "project-atlas.txt",
            "quote": "Project Atlas 目前處於設計收斂階段。",
        },
    )

    assert candidate_evidence(candidate) == [
        {
            "source_relpath": "project-atlas.txt",
            "route": "wiki",
            "quote": "Project Atlas 目前處於設計收斂階段。",
        }
    ]


def test_graph_candidate_evidence_uses_edge_quotes_per_relpath() -> None:
    candidate = Candidate(
        text="Atlas 會影響 Billing API",
        source_route="graph",
        score=0.88,
        metadata={
            "relpaths": ["dependency-map.md"],
            "evidence_by_relpath": {
                "dependency-map.md": "Project Atlas affects Billing API."
            },
        },
    )

    assert candidate_evidence(candidate) == [
        {
            "source_relpath": "dependency-map.md",
            "route": "graph",
            "quote": "Project Atlas affects Billing API.",
        }
    ]


def test_vector_candidate_evidence_includes_winning_quote_and_location() -> None:
    candidate = Candidate(
        text="clause 7.4 requires risk controls before launch.",
        source_route="vector",
        score=0.91,
        metadata={
            "source_relpath": "reports/launch-plan.md",
            "section_path": "Launch Plan > Risk Controls",
            "page_range": {"start": 4, "end": 6},
        },
    )

    assert candidate_evidence(candidate) == [
        {
            "source_relpath": "reports/launch-plan.md",
            "route": "vector",
            "section_path": "Launch Plan > Risk Controls",
            "page_range": {"start": 4, "end": 6},
            "quote": "clause 7.4 requires risk controls before launch.",
        }
    ]


def test_page_tree_candidate_evidence_includes_section_path_and_page_range() -> None:
    candidate = Candidate(
        text="Nebula arbitration requires coordinator approval.",
        source_route="page_tree",
        score=0.6,
        metadata={
            "source_relpath": "project-atlas.txt",
            "section_path": "Nebula Arbitration",
            "page_range": {"start": 12, "end": 14},
        },
    )

    assert candidate_evidence(candidate) == [
        {
            "source_relpath": "project-atlas.txt",
            "route": "page_tree",
            "quote": "Nebula arbitration requires coordinator approval.",
            "section_path": "Nebula Arbitration",
            "page_range": {"start": 12, "end": 14},
        }
    ]
```

Run: `uv run pytest tests/unit/retrieval/test_evidence.py -q`

Expected: fails because `hks.retrieval.models` and `hks.retrieval.evidence` do not exist.

- [x] **Step 2: Add shared Candidate model**

Create `src/hks/retrieval/models.py`:

```python
"""Shared retrieval data models."""

from __future__ import annotations

from dataclasses import dataclass

from hks.core.schema import Route


@dataclass(slots=True)
class Candidate:
    text: str
    source_route: Route
    score: float
    metadata: dict[str, object]
```

- [x] **Step 3: Move evidence helpers**

Create `src/hks/retrieval/evidence.py`:

```python
"""Convert winning retrieval candidates into response evidence."""

from __future__ import annotations

from hks.retrieval.models import Candidate


def evidence_quote(text: object, *, limit: int = 240) -> str:
    normalized = " ".join(str(text or "").split())
    return normalized[:limit]


def metadata_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    if candidate.source_route == "wiki":
        return _wiki_candidate_evidence(candidate)
    if candidate.source_route == "graph":
        return _graph_candidate_evidence(candidate)
    if candidate.source_route == "page_tree":
        return _page_tree_candidate_evidence(candidate)
    return _vector_candidate_evidence(candidate)


def _wiki_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpath = metadata_str(candidate.metadata, "source_relpath")
    quote = evidence_quote(candidate.metadata.get("quote") or candidate.text)
    if relpath is None or not quote:
        return []
    return [{"source_relpath": relpath, "route": "wiki", "quote": quote}]


def _graph_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpaths = candidate.metadata.get("relpaths")
    evidence_by_relpath = candidate.metadata.get("evidence_by_relpath")
    if not isinstance(relpaths, list):
        return []
    quotes = evidence_by_relpath if isinstance(evidence_by_relpath, dict) else {}
    evidence: list[dict[str, object]] = []
    seen: set[str] = set()
    for relpath in relpaths:
        if not isinstance(relpath, str) or relpath in seen:
            continue
        seen.add(relpath)
        quote = evidence_quote(quotes.get(relpath) or candidate.text)
        if quote:
            evidence.append({"source_relpath": relpath, "route": "graph", "quote": quote})
    return evidence


def _vector_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpath = metadata_str(candidate.metadata, "source_relpath")
    quote = evidence_quote(candidate.text)
    if relpath is None or not quote:
        return []

    entry: dict[str, object] = {
        "source_relpath": relpath,
        "route": "vector",
        "quote": quote,
    }
    section_path = metadata_str(candidate.metadata, "section_path")
    if section_path is not None:
        entry["section_path"] = section_path
    page_range = candidate.metadata.get("page_range")
    if isinstance(page_range, dict):
        entry["page_range"] = page_range
    return [entry]


def _page_tree_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpath = metadata_str(candidate.metadata, "source_relpath")
    if relpath is None:
        return []
    entry: dict[str, object] = {
        "source_relpath": relpath,
        "route": "page_tree",
        "quote": evidence_quote(candidate.text),
    }
    section_path = metadata_str(candidate.metadata, "section_path")
    if section_path is not None:
        entry["section_path"] = section_path
    page_range = candidate.metadata.get("page_range")
    if isinstance(page_range, dict):
        entry["page_range"] = page_range
    return [entry]
```

- [x] **Step 4: Update imports and remove duplicate helpers from `commands/query.py`**

In `src/hks/commands/query.py`:

```python
from hks.retrieval.evidence import (
    candidate_evidence,
    evidence_quote as _evidence_quote,
    metadata_str as _metadata_str,
)
from hks.retrieval.models import Candidate
```

Replace:

```python
evidence = _candidate_evidence(winner)
```

with:

```python
evidence = candidate_evidence(winner)
```

Delete from `commands/query.py`:

- local `Candidate` dataclass
- `_candidate_evidence`
- `_wiki_candidate_evidence`
- `_graph_candidate_evidence`
- `_vector_candidate_evidence`
- `_page_tree_candidate_evidence`

Keep the alias imports `evidence_quote as _evidence_quote` and `metadata_str as _metadata_str` until Tasks 2-3 move the remaining collectors out of `commands/query.py`; that keeps the intermediate state testable.

- [x] **Step 5: Verify Task 1**

Run:

```bash
uv run pytest tests/unit/retrieval/test_evidence.py tests/unit/commands/test_fused_retrieval.py -q
uv run ruff check src/hks/retrieval src/hks/commands/query.py tests/unit/retrieval/test_evidence.py
uv run mypy src/hks/retrieval src/hks/commands/query.py
```

Expected: all pass.

---

## Task 2: Extract Wiki And Graph Retrievers

**Files:**
- Create: `src/hks/retrievers/__init__.py`
- Create: `src/hks/retrievers/wiki.py`
- Create: `src/hks/retrievers/graph.py`
- Create: `tests/unit/retrievers/__init__.py`
- Create: `tests/unit/retrievers/test_wiki.py`
- Create: `tests/unit/retrievers/test_graph.py`
- Modify: `src/hks/commands/query.py`
- Modify: `tests/unit/commands/test_fused_retrieval.py`

- [x] **Step 1: Create migrated wiki and graph tests**

Create `tests/unit/retrievers/__init__.py` as an empty file.

Create `tests/unit/retrievers/test_wiki.py`:

```python
"""Unit tests for wiki candidate retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock

from hks.retrievers.wiki import collect_wiki_candidates, has_wiki_secondary_intent


def test_has_wiki_secondary_intent_accepts_summary_terms() -> None:
    assert has_wiki_secondary_intent("Atlas 摘要")
    assert has_wiki_secondary_intent("project overview")


def test_collect_wiki_returns_candidate_on_hit() -> None:
    wiki_store = MagicMock()
    page = MagicMock()
    page.title = "Atlas"
    page.summary = "Atlas project summary"
    page.body = "Atlas body"
    page.source_relpath = "atlas.md"
    page.slug = "atlas"
    wiki_store.search.return_value = page

    candidates, steps = collect_wiki_candidates("Atlas 摘要", wiki_store=wiki_store)

    assert len(candidates) == 1
    assert candidates[0].source_route == "wiki"
    assert candidates[0].metadata["source_relpath"] == "atlas.md"
    assert steps[0].kind == "wiki_lookup"
    assert steps[0].detail["hit"] is True


def test_collect_wiki_returns_empty_on_miss() -> None:
    wiki_store = MagicMock()
    wiki_store.search.return_value = None
    wiki_store.overview.return_value = None

    candidates, steps = collect_wiki_candidates("random question", wiki_store=wiki_store)

    assert candidates == []
    assert steps[0].detail["hit"] is False
```

Create `tests/unit/retrievers/test_graph.py`:

```python
"""Unit tests for graph candidate retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hks.retrievers.graph import collect_graph_candidates


def test_collect_graph_returns_candidate_on_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    graph_store = MagicMock()
    edge = MagicMock()
    edge.evidence = "A impacts B"
    edge.source_relpath = "dep.md"
    graph_payload = MagicMock()
    graph_payload.edges = {"e1": edge}
    graph_store.load.return_value = graph_payload

    mock_result = MagicMock()
    mock_result.answer = "A impacts B"
    mock_result.confidence = 0.88
    mock_result.relpaths = ["dep.md"]
    mock_result.node_ids = ["n1", "n2"]
    mock_result.edge_ids = ["e1"]
    mock_result.relations = ["impacts"]

    monkeypatch.setattr("hks.retrievers.graph.answer_query", lambda q, gs: mock_result)

    candidates, steps = collect_graph_candidates("impact analysis", graph_store=graph_store)

    assert len(candidates) == 1
    assert candidates[0].source_route == "graph"
    assert candidates[0].metadata["edge_ids"] == ["e1"]
    assert candidates[0].metadata["evidence_by_relpath"] == {"dep.md": "A impacts B"}
    assert steps[0].kind == "graph_lookup"
    assert steps[0].detail["hit"] is True


def test_collect_graph_returns_empty_on_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    graph_store = MagicMock()
    monkeypatch.setattr("hks.retrievers.graph.answer_query", lambda q, gs: None)

    candidates, steps = collect_graph_candidates("no match", graph_store=graph_store)

    assert candidates == []
    assert steps[0].kind == "graph_lookup"
    assert steps[0].detail["hit"] is False
```

Run:

```bash
uv run pytest tests/unit/retrievers/test_wiki.py tests/unit/retrievers/test_graph.py -q
```

Expected: fails because retriever modules do not exist.

- [x] **Step 2: Implement wiki retriever**

Create `src/hks/retrievers/__init__.py` as an empty file.

Create `src/hks/retrievers/wiki.py`:

```python
"""Wiki candidate retrieval."""

from __future__ import annotations

from hks.core.schema import TraceStep
from hks.retrieval.evidence import evidence_quote
from hks.retrieval.models import Candidate
from hks.storage.wiki import WikiStore


def has_wiki_secondary_intent(question: str) -> bool:
    lowered = question.lower()
    return any(
        keyword in lowered
        for keyword in ("summary", "overview", "摘要", "總結", "重點", "說明")
    )


def collect_wiki_candidates(
    question: str,
    *,
    wiki_store: WikiStore,
    require_secondary_intent: bool = False,
    is_primary: bool = False,
) -> tuple[list[Candidate], list[TraceStep]]:
    steps: list[TraceStep] = []
    candidates: list[Candidate] = []

    if require_secondary_intent and not has_wiki_secondary_intent(question):
        steps.append(
            TraceStep(
                kind="wiki_lookup",
                detail={"hit": False, "reason": "secondary-intent-miss"},
            )
        )
        return candidates, steps

    page = wiki_store.search(question)
    if page is not None:
        quote = evidence_quote(page.summary or page.body)
        steps.append(
            TraceStep(
                kind="wiki_lookup",
                detail={
                    "slug": page.slug,
                    "hit": True,
                    "source_relpath": page.source_relpath,
                    "quote": quote,
                },
            )
        )
        candidates.append(
            Candidate(
                text=f"{page.title}: {page.summary}",
                source_route="wiki",
                score=1.0 if is_primary else 0.65,
                metadata={
                    "source_relpath": page.source_relpath,
                    "slug": page.slug,
                    "quote": quote,
                },
            )
        )
    else:
        overview = wiki_store.overview()
        if overview and has_wiki_secondary_intent(question):
            steps.append(
                TraceStep(
                    kind="wiki_lookup",
                    detail={"slug": None, "hit": True, "mode": "overview"},
                )
            )
            candidates.append(
                Candidate(text=overview, source_route="wiki", score=0.7, metadata={})
            )
        else:
            steps.append(TraceStep(kind="wiki_lookup", detail={"hit": False}))

    return candidates, steps
```

- [x] **Step 3: Implement graph retriever**

Create `src/hks/retrievers/graph.py`:

```python
"""Graph candidate retrieval."""

from __future__ import annotations

from collections.abc import Sequence

from hks.core.schema import TraceStep
from hks.graph.query import answer_query
from hks.graph.store import GraphStore
from hks.retrieval.models import Candidate


def graph_trace_detail(
    *,
    relpaths: list[str],
    node_ids: list[str],
    edge_ids: list[str],
    relations: Sequence[str],
    evidence_by_relpath: dict[str, str] | None = None,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "hit": True,
        "relpaths": relpaths,
        "node_ids": node_ids,
        "edge_ids": edge_ids,
        "relations": relations,
    }
    if evidence_by_relpath:
        detail["evidence_by_relpath"] = evidence_by_relpath
    return detail


def collect_graph_candidates(
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

    graph_payload = graph_store.load()
    evidence_by_relpath: dict[str, str] = {}
    for edge_id in graph_result.edge_ids:
        edge = graph_payload.edges.get(edge_id)
        if edge is not None and edge.evidence:
            evidence_by_relpath.setdefault(edge.source_relpath, edge.evidence)

    steps.append(
        TraceStep(
            kind="graph_lookup",
            detail=graph_trace_detail(
                relpaths=graph_result.relpaths,
                node_ids=graph_result.node_ids,
                edge_ids=graph_result.edge_ids,
                relations=graph_result.relations,
                evidence_by_relpath=evidence_by_relpath,
            ),
        )
    )
    candidates.append(
        Candidate(
            text=graph_result.answer,
            source_route="graph",
            score=graph_result.confidence,
            metadata={
                "relpaths": graph_result.relpaths,
                "edge_ids": graph_result.edge_ids,
                "evidence_by_relpath": evidence_by_relpath,
            },
        )
    )
    return candidates, steps
```

- [x] **Step 4: Update query orchestration imports**

In `src/hks/commands/query.py`, import:

```python
from hks.retrievers.graph import collect_graph_candidates
from hks.retrievers.wiki import collect_wiki_candidates
```

Replace calls:

```python
wiki_candidates, wiki_steps = collect_wiki_candidates(...)
graph_candidates, graph_steps = collect_graph_candidates(...)
```

Delete from `commands/query.py`:

- `_graph_trace_detail`
- `_has_wiki_secondary_intent`
- `_collect_wiki_candidates`
- `_collect_graph_candidates`

Keep `_evidence_quote` and `_metadata_str` alias imports because vector and page_tree code still uses them until Task 3.

- [x] **Step 5: Verify Task 2**

Run:

```bash
uv run pytest tests/unit/retrievers/test_wiki.py tests/unit/retrievers/test_graph.py -q
uv run pytest tests/unit/commands/test_fused_retrieval.py -q
uv run pytest tests/eval/test_golden_retrieval_quality.py -q
uv run ruff check src/hks/retrievers src/hks/commands/query.py tests/unit/retrievers
uv run mypy src/hks/retrievers src/hks/commands/query.py
```

Expected: all pass.

---

## Task 3: Extract Vector And PageTree Retrievers

**Files:**
- Create: `src/hks/retrievers/vector.py`
- Create: `src/hks/retrievers/page_tree.py`
- Create: `tests/unit/retrievers/test_vector.py`
- Create: `tests/unit/retrievers/test_page_tree.py`
- Modify: `src/hks/commands/query.py`
- Modify: `tests/unit/commands/test_page_tree_retrieval.py`
- Modify: `tests/unit/commands/test_query_vector_selection.py`

- [x] **Step 1: Move vector tests to retriever module**

Create `tests/unit/retrievers/test_vector.py`:

```python
"""Unit tests for vector candidate retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock

from hks.retrievers.vector import (
    choose_vector_hit,
    collect_vector_candidates,
    lexical_terms,
    vector_hit_is_relevant,
)
from hks.storage.vector import SearchHit


def test_lexical_terms_extracts_english_and_chinese_bigrams() -> None:
    assert "atlas" in lexical_terms("Atlas risk")
    assert "風險" in lexical_terms("風險評估")


def test_vector_hit_selection_prefers_more_lexical_matches_over_similarity_noise() -> None:
    broad_hit = SearchHit(
        chunk_id="png:0",
        text="Owner Iris appears in the PNG image.",
        similarity=0.99,
        metadata={"source_format": "png"},
    )
    precise_hit = SearchHit(
        chunk_id="jpg:0",
        text="Owner Mia appears in the JPG image.",
        similarity=0.91,
        metadata={"source_format": "jpg"},
    )

    assert choose_vector_hit("detail Owner Mia", [broad_hit, precise_hit]) == precise_hit


def test_vector_hit_is_relevant_requires_lexical_overlap_when_query_has_terms() -> None:
    hit = SearchHit(
        chunk_id="c1",
        text="unrelated text",
        similarity=0.99,
        metadata={},
    )
    assert vector_hit_is_relevant("Owner Mia", hit) is False


def test_collect_vector_returns_candidates_for_relevant_hits() -> None:
    vector_store = MagicMock()
    vector_store.count.return_value = 10
    vector_store.search.return_value = [
        SearchHit(
            chunk_id="c1",
            text="matching text alpha",
            similarity=0.85,
            metadata={"source_relpath": "a.md"},
        )
    ]
    vector_store.paths = MagicMock()
    manifest = MagicMock()
    manifest.entries = {}

    candidates, steps = collect_vector_candidates(
        "matching text",
        vector_store=vector_store,
        manifest=manifest,
    )

    assert len(candidates) == 1
    assert candidates[0].source_route == "vector"
    assert steps[0].kind == "vector_lookup"
```

- [x] **Step 2: Move PageTree tests to retriever module**

Create `tests/unit/retrievers/test_page_tree.py` by moving the current assertions from `tests/unit/commands/test_page_tree_retrieval.py`, changing imports to:

```python
from hks.retrieval.evidence import candidate_evidence
from hks.retrieval.models import Candidate
from hks.retrievers.page_tree import (
    collect_page_tree_candidates,
    page_tree_node_score,
)
```

In the moved file, update function calls:

```python
score = page_tree_node_score("Atlas overview", node)
candidates, steps = collect_page_tree_candidates(...)
assert candidate_evidence(candidate) == [...]
```

Run:

```bash
uv run pytest tests/unit/retrievers/test_vector.py tests/unit/retrievers/test_page_tree.py -q
```

Expected: fails because new retriever modules do not exist.

- [x] **Step 3: Implement vector retriever**

Create `src/hks/retrievers/vector.py` by moving the current vector helpers from `commands/query.py`. Public names in the new module must be:

```python
lexical_terms
vector_hit_is_relevant
vector_hit_lexical_score
choose_vector_hit
vector_trace_detail
vector_section_context
collect_vector_candidates
```

Use this import set:

```python
from __future__ import annotations

import re

from hks.core.manifest import Manifest
from hks.core.schema import TraceStep
from hks.page_tree.store import TreeStore
from hks.retrieval.evidence import evidence_quote
from hks.retrieval.models import Candidate
from hks.storage.vector import SearchHit, VectorStore
```

Keep function bodies byte-for-byte equivalent except for renamed helpers:

```python
_lexical_terms -> lexical_terms
_vector_hit_is_relevant -> vector_hit_is_relevant
_vector_hit_lexical_score -> vector_hit_lexical_score
_choose_vector_hit -> choose_vector_hit
_vector_trace_detail -> vector_trace_detail
_vector_section_context -> vector_section_context
_collect_vector_candidates -> collect_vector_candidates
_evidence_quote -> evidence_quote
```

- [x] **Step 4: Implement PageTree retriever**

Create `src/hks/retrievers/page_tree.py` by moving PageTree helpers from `commands/query.py`. Public names in the new module must be:

```python
page_tree_node_score
collect_page_tree_candidates
```

Use this import set:

```python
from __future__ import annotations

from hks.core.manifest import Manifest
from hks.core.schema import TraceStep
from hks.page_tree.model import TreeNode
from hks.page_tree.store import TreeStore
from hks.retrievers.vector import lexical_terms
from hks.retrieval.models import Candidate
```

Keep function bodies equivalent except for renamed helpers:

```python
_page_tree_node_score -> page_tree_node_score
_collect_page_tree_candidates -> collect_page_tree_candidates
_lexical_terms -> lexical_terms
```

- [x] **Step 5: Update query orchestration imports and delete moved code**

In `src/hks/commands/query.py`, import:

```python
from hks.retrievers.page_tree import collect_page_tree_candidates
from hks.retrievers.vector import collect_vector_candidates
```

Replace calls:

```python
vector_candidates, vector_steps = collect_vector_candidates(...)
page_tree_candidates, page_tree_steps = collect_page_tree_candidates(...)
```

Delete from `commands/query.py`:

- `_lexical_terms`
- `_vector_hit_is_relevant`
- `_vector_hit_lexical_score`
- `_choose_vector_hit`
- `_vector_trace_detail`
- `_vector_section_context`
- `_page_tree_node_score`
- `_collect_vector_candidates`
- `_collect_page_tree_candidates`
- `evidence_quote as _evidence_quote` import if unused
- `metadata_str as _metadata_str` import if unused

- [x] **Step 6: Delete or shrink old command-level tests**

In `tests/unit/commands/test_page_tree_retrieval.py`, remove the moved tests or replace the file with:

```python
"""PageTree retrieval tests moved to tests/unit/retrievers/test_page_tree.py."""
```

In `tests/unit/commands/test_query_vector_selection.py`, remove the moved test or replace the file with:

```python
"""Vector retrieval tests moved to tests/unit/retrievers/test_vector.py."""
```

In `tests/unit/commands/test_fused_retrieval.py`, remove imports and tests for moved collector helpers. Keep tests only for command orchestration if there is a public behavior assertion. If the file becomes empty, delete it.

- [x] **Step 7: Verify Task 3**

Run:

```bash
uv run pytest tests/unit/retrievers tests/unit/retrieval/test_evidence.py -q
uv run pytest tests/eval/test_golden_retrieval_quality.py -q
uv run ruff check src/hks/retrievers src/hks/retrieval src/hks/commands/query.py tests/unit/retrievers
uv run mypy src/hks/retrievers src/hks/retrieval src/hks/commands/query.py
```

Expected: all pass.

---

## Task 4: Extract Rerank Modules

**Files:**
- Create: `src/hks/rerank/__init__.py`
- Create: `src/hks/rerank/rrf.py`
- Create: `src/hks/rerank/llm.py`
- Create: `tests/unit/rerank/__init__.py`
- Create: `tests/unit/rerank/test_rrf.py`
- Create: `tests/unit/rerank/test_llm.py`
- Modify: `src/hks/commands/query.py`
- Modify: `tests/eval/test_rerank_eval.py`
- Modify: `tests/unit/commands/test_fused_retrieval.py`

- [x] **Step 1: Write migrated rerank tests**

Create `tests/unit/rerank/__init__.py` as an empty file.

Create `tests/unit/rerank/test_rrf.py`:

```python
"""Unit tests for deterministic RRF reranker."""

from __future__ import annotations

from hks.rerank.rrf import rrf_rerank
from hks.retrieval.models import Candidate


def test_rrf_ranks_by_reciprocal_fusion() -> None:
    candidates = [
        Candidate(text="wiki hit", source_route="wiki", score=1.0, metadata={}),
        Candidate(text="vector hit", source_route="vector", score=0.9, metadata={}),
        Candidate(text="graph hit", source_route="graph", score=0.7, metadata={}),
    ]

    ranked = rrf_rerank(candidates)

    assert len(ranked) == 3
    assert ranked[0].score >= ranked[1].score >= ranked[2].score


def test_rrf_empty_candidates() -> None:
    assert rrf_rerank([]) == []


def test_rrf_preserves_equal_duplicate_candidates() -> None:
    candidates = [
        Candidate(text="same", source_route="vector", score=0.8, metadata={}),
        Candidate(text="same", source_route="vector", score=0.8, metadata={}),
    ]

    assert len(rrf_rerank(candidates)) == 2
```

Create `tests/unit/rerank/test_llm.py`:

```python
"""Unit tests for LLM reranker fallback behavior."""

from __future__ import annotations

import pytest

from hks.rerank.llm import classify_rerank_error, llm_rerank, rerank_candidates
from hks.retrieval.models import Candidate


def test_rerank_candidates_uses_rrf_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    candidates = [
        Candidate(text="a", source_route="wiki", score=1.0, metadata={}),
        Candidate(text="b", source_route="vector", score=0.5, metadata={}),
    ]

    ranked, strategy, detail = rerank_candidates("question", candidates)

    assert strategy == "rrf"
    assert detail["strategy"] == "rrf"
    assert ranked[0].text == "a"


def test_llm_fallback_captures_timeout_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HKS_LLM_NETWORK_OPT_IN", "1")
    monkeypatch.setenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", "sk-test")

    def mock_openai_chat(**_kwargs: object) -> object:
        raise TimeoutError("mock timeout")

    monkeypatch.setattr("hks.rerank.llm._openai_chat", mock_openai_chat)

    candidates = [Candidate(text="a", source_route="wiki", score=1.0, metadata={})]
    ranked, detail = llm_rerank("q", candidates)

    assert ranked[0].text == "a"
    assert detail["strategy"] == "llm"
    assert detail["status"] == "fallback"
    assert detail["fallback_strategy"] == "rrf"
    assert detail["reason"] == "openai_timeout"


def test_classify_rerank_error_maps_value_error_to_invalid_ranking() -> None:
    assert classify_rerank_error(ValueError("bad")) == "openai_invalid_ranking"
```

Run:

```bash
uv run pytest tests/unit/rerank -q
```

Expected: fails because `hks.rerank` does not exist.

- [x] **Step 2: Implement RRF module**

Create `src/hks/rerank/__init__.py` as an empty file.

Create `src/hks/rerank/rrf.py`:

```python
"""Deterministic reciprocal-rank-fusion reranker."""

from __future__ import annotations

from hks.retrieval.models import Candidate


def rrf_rerank(candidates: list[Candidate], *, k: int = 60) -> list[Candidate]:
    if not candidates:
        return []

    source_groups: dict[str, list[tuple[int, Candidate]]] = {}
    for index, candidate in enumerate(candidates):
        source_groups.setdefault(candidate.source_route, []).append((index, candidate))

    for route_candidates in source_groups.values():
        route_candidates.sort(key=lambda item: item[1].score, reverse=True)

    rrf_scores: dict[int, float] = {}
    for route_candidates in source_groups.values():
        for rank, (index, _candidate) in enumerate(route_candidates):
            rrf_scores[index] = rrf_scores.get(index, 0.0) + 1.0 / (k + rank + 1)

    ranked_indices = sorted(
        rrf_scores,
        key=lambda i: (rrf_scores[i], candidates[i].score),
        reverse=True,
    )
    return [
        Candidate(
            text=candidates[i].text,
            source_route=candidates[i].source_route,
            score=candidates[i].score,
            metadata=candidates[i].metadata,
        )
        for i in ranked_indices
    ]
```

- [x] **Step 3: Implement LLM rerank module**

Create `src/hks/rerank/llm.py` by moving `_llm_rerank`, `_classify_rerank_error`, and `_rerank_candidates` from `commands/query.py`. Public names must be:

```python
llm_rerank
classify_rerank_error
rerank_candidates
```

Use this import set:

```python
from __future__ import annotations

import json

import httpx

from hks.core.config import config_value
from hks.llm.config import hosted_provider_ready
from hks.llm.providers import _openai_chat
from hks.rerank.rrf import rrf_rerank
from hks.retrieval.models import Candidate
```

Rename helpers:

```python
_llm_rerank -> llm_rerank
_classify_rerank_error -> classify_rerank_error
_rerank_candidates -> rerank_candidates
_rrf_rerank -> rrf_rerank
```

Keep fallback detail values unchanged:

```python
{"strategy": "rrf", "status": "primary"}
{"strategy": "llm", "status": "fallback", "fallback_strategy": "rrf", "reason": "openai_timeout"}
```

- [x] **Step 4: Update query orchestration and eval import**

In `src/hks/commands/query.py`, import:

```python
from hks.rerank.llm import rerank_candidates
```

Replace:

```python
ranked, strategy, rerank_detail = _rerank_candidates(question, all_candidates)
```

with:

```python
ranked, strategy, rerank_detail = rerank_candidates(question, all_candidates)
```

Delete from `commands/query.py`:

- `json` import if unused
- `httpx` import if unused
- `_rrf_rerank`
- `_llm_rerank`
- `_classify_rerank_error`
- `_rerank_candidates`

In `tests/eval/test_rerank_eval.py`, replace:

```python
from hks.commands.query import Candidate, _llm_rerank
```

with:

```python
from hks.rerank.llm import llm_rerank
from hks.retrieval.models import Candidate
```

And replace:

```python
ranked, detail = _llm_rerank(case["question"], candidates)
```

with:

```python
ranked, detail = llm_rerank(case["question"], candidates)
```

- [x] **Step 5: Verify Task 4**

Run:

```bash
uv run pytest tests/unit/rerank tests/eval/test_rerank_eval.py -q
uv run pytest tests/eval/test_golden_retrieval_quality.py -q
uv run ruff check src/hks/rerank src/hks/commands/query.py tests/unit/rerank tests/eval/test_rerank_eval.py
uv run mypy src/hks/rerank src/hks/commands/query.py
```

Expected: all pass. Hosted rerank eval remains skipped unless OpenAI env is set.

---

## Task 5: Final Query Orchestration Cleanup

**Files:**
- Modify: `src/hks/commands/query.py`
- Modify: `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md`

- [x] **Step 1: Confirm `commands/query.py` is orchestration-only**

After Tasks 1-4, `src/hks/commands/query.py` should contain only:

- imports
- `run()`
- `_build_no_hit_response()`
- `_maybe_writeback()`
- `_record_forced_writeback_event()`
- `_build_writeback_context()`

Run:

```bash
rg -n "def _collect|def _rrf|def _llm|def _lexical|def _candidate_evidence|class Candidate" src/hks/commands/query.py
```

Expected: no matches.

- [x] **Step 2: Verify public behavior did not change**

Run:

```bash
uv run pytest tests/eval/test_golden_retrieval_quality.py -q
uv run pytest tests/integration/test_writeback.py tests/integration/test_query_flows.py tests/integration/test_workspace_query.py -q
```

Expected: all pass.

- [x] **Step 3: Mark 017 implemented**

Under the 017 section in `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md`, add:

```markdown
> **Status:** Implemented — see `docs/superpowers/plans/2026-05-22-017-query-refactor.md`.
```

- [x] **Step 4: Final verification**

Run:

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

Expected: all pass.

- [ ] **Step 5: Commit** (skipped per user instruction: no commit, no stage)

```bash
git add \
  docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md \
  docs/superpowers/plans/2026-05-22-017-query-refactor.md \
  src/hks/commands/query.py \
  src/hks/retrieval/models.py \
  src/hks/retrieval/evidence.py \
  src/hks/retrievers \
  src/hks/rerank \
  tests/unit/retrieval/test_evidence.py \
  tests/unit/retrievers \
  tests/unit/rerank \
  tests/unit/commands/test_fused_retrieval.py \
  tests/unit/commands/test_page_tree_retrieval.py \
  tests/unit/commands/test_query_vector_selection.py \
  tests/eval/test_rerank_eval.py
git commit -m "refactor(017): split query pipeline into retrievers and rerank modules"
```

---

## Risk Notes

1. Do not start 017 until 016 is merged and `tests/eval/test_golden_retrieval_quality.py` is green.
2. Do not change `QueryResponse`, trace schema, route names, writeback statuses, or evidence shape in 017.
3. RRF ordering must remain equivalent. If the 016 gate catches a ranking problem, fix behavior in a separate feature or explicitly document why it belongs in 017.
4. Private helper imports in tests should move to the new modules; avoid keeping compatibility aliases in `commands/query.py`, or the refactor will not actually reduce coupling.

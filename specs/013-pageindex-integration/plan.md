# PageIndex Integration & System-wide Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate hierarchical document tree (PageIndex concept) into HKS, fix document structure loss, improve routing and graph extraction, and close test coverage gaps.

**Architecture:** New `page_tree` module provides per-document hierarchical JSON trees built at ingest time (rule-based, zero LLM). Trees are stored as `$KS_ROOT/page_trees/*.json` alongside existing wiki/graph/vector artifacts. PDF parser enhanced with PyMuPDF for TOC/heading extraction. Vector chunk metadata enriched with `tree_node_id`. Optional LLM enrichment via `ks pageindex enrich`. Phase 2 improves routing with tree-aware search and multi-layer fusion. Phase 3 strengthens graph extraction using tree context. Phase 4 closes test gaps.

**Tech Stack:** Python 3.12, PyMuPDF (pymupdf), Typer CLI, FastMCP, existing HKS infrastructure (chromadb, sentence-transformers, pypdf, python-docx, python-pptx, openpyxl)

**Spec:** `specs/013-pageindex-integration/spec.md`

---

## File Map

### New Files (Phase 1)

| File | Responsibility |
|------|---------------|
| `src/hks/page_tree/__init__.py` | Module marker |
| `src/hks/page_tree/model.py` | `PageTree`, `TreeNode` dataclasses + JSON serialization |
| `src/hks/page_tree/build.py` | Rule-based builders per format + dispatch |
| `src/hks/page_tree/store.py` | Read/write/delete tree JSON in `$KS_ROOT/page_trees/` |
| `src/hks/page_tree/enrich.py` | LLM enrichment logic |
| `src/hks/commands/pageindex.py` | CLI `ks pageindex show|enrich` |
| `tests/unit/page_tree/test_model.py` | Model round-trip tests |
| `tests/unit/page_tree/test_build.py` | Per-format builder tests |
| `tests/unit/page_tree/test_page_tree_store.py` | Store CRUD tests |
| `tests/unit/page_tree/test_enrich.py` | LLM enrichment tests |
| `tests/unit/ingest/parsers/test_pdf_segments.py` | PDF segment extraction tests |
| `tests/integration/test_pageindex_cli.py` | CLI integration tests |
| `tests/integration/test_ingest_tree.py` | Ingest pipeline + tree integration |
| `tests/fixtures/valid/with-toc.pdf` | PDF fixture with TOC bookmarks |
| `tests/fixtures/valid/no-toc-headings.pdf` | PDF fixture with font-size headings |
| `tests/fixtures/valid/plain-text.pdf` | PDF fixture with no structure |

### Modified Files (Phase 1)

| File | Change |
|------|--------|
| `pyproject.toml` | Add `pymupdf` dependency + mypy override |
| `src/hks/core/paths.py:11-21` | Add `page_trees` field to `RuntimePaths` |
| `src/hks/core/manifest.py:35-58` | Add `page_tree` field to `DerivedArtifacts` |
| `src/hks/core/schema.py:16-33` | Add `"pageindex_summary"` to `TraceKind` |
| `src/hks/ingest/parsers/pdf.py` | Rewrite with PyMuPDF for segment extraction |
| `src/hks/ingest/pipeline.py:374-464` | Insert tree build + attach node_ids to chunks |
| `src/hks/ingest/pipeline.py:117-131` | Add tree cleanup to `delete_artifacts` |
| `src/hks/lint/rules.py` (or equivalent) | Add tree lint rules |
| `src/hks/cli.py` | Register `pageindex` sub-app |
| `src/hks/adapters/core.py` | Add `hks_pageindex_show`, `hks_pageindex_enrich` |
| `src/hks/adapters/mcp_server.py` | Register `pageindex_show`, `pageindex_enrich` tools |
| `src/hks/adapters/http_server.py` | Add `/pageindex/*` routes |

### Modified Files (Phase 2)

| File | Change |
|------|--------|
| `src/hks/storage/wiki.py:310-346` | Two-stage search with tree summary scan |
| `src/hks/routing/router.py:14-18` | Add `secondary` to `RouteDecision` |
| `src/hks/routing/rules.py:17-24` | Add `secondary_route` to `RoutingRule` |
| `config/routing_rules.yaml` | Add `secondary` fields |
| `src/hks/commands/query.py` | Add `section_path` + `page_range` to response |

### Modified Files (Phase 3)

| File | Change |
|------|--------|
| `src/hks/graph/extract.py:31-127` | Add `page_tree` parameter, section-scoped extraction |
| `src/hks/graph/extract.py` | Add `causes`, `contradicts`, `succeeds` patterns |
| `src/hks/ingest/pipeline.py:440-445` | Pass `page_tree` to `extract_document_graph` |

---

## Phase 1: PageIndex Tree + Document Structure

### Task 1: PageTree Data Model

**Files:**
- Create: `src/hks/page_tree/__init__.py`
- Create: `src/hks/page_tree/model.py`
- Test: `tests/unit/page_tree/test_model.py`

- [x] **Step 1: Write failing test for TreeNode + PageTree serialization**

```python
# tests/unit/page_tree/test_model.py
"""Unit tests for page_tree data model."""

from __future__ import annotations

import json

import pytest

from hks.page_tree.model import PageTree, TreeNode


class TestTreeNode:
    def test_leaf_node_to_dict(self) -> None:
        node = TreeNode(
            node_id="n1",
            title="Introduction",
            level=1,
            start_offset=0,
            end_offset=500,
            children=[],
        )
        result = node.to_dict()
        assert result["node_id"] == "n1"
        assert result["title"] == "Introduction"
        assert result["level"] == 1
        assert result["start_offset"] == 0
        assert result["end_offset"] == 500
        assert result["children"] == []
        assert result["summary"] == ""
        assert result["metadata"] == {}

    def test_nested_node_to_dict(self) -> None:
        child = TreeNode(
            node_id="n1.1",
            title="Background",
            level=2,
            start_offset=0,
            end_offset=200,
            children=[],
        )
        parent = TreeNode(
            node_id="n1",
            title="Introduction",
            level=1,
            start_offset=0,
            end_offset=500,
            children=[child],
        )
        result = parent.to_dict()
        assert len(result["children"]) == 1
        assert result["children"][0]["node_id"] == "n1.1"

    def test_node_with_metadata(self) -> None:
        node = TreeNode(
            node_id="n2",
            title="Chapter 2",
            level=1,
            start_offset=500,
            end_offset=1200,
            children=[],
            metadata={"page_start": 4, "page_end": 7},
        )
        result = node.to_dict()
        assert result["metadata"]["page_start"] == 4

    def test_from_dict_round_trip(self) -> None:
        node = TreeNode(
            node_id="n1",
            title="Test",
            level=1,
            start_offset=0,
            end_offset=100,
            children=[
                TreeNode(
                    node_id="n1.1",
                    title="Sub",
                    level=2,
                    start_offset=0,
                    end_offset=50,
                    children=[],
                    summary="A sub-section.",
                )
            ],
            summary="Top level.",
            metadata={"page_start": 1},
        )
        restored = TreeNode.from_dict(node.to_dict())
        assert restored.node_id == node.node_id
        assert restored.children[0].summary == "A sub-section."
        assert restored.metadata == {"page_start": 1}


class TestPageTree:
    def test_to_dict(self) -> None:
        tree = PageTree(
            source_relpath="report.pdf",
            source_format="pdf",
            doc_title="Q1 Report",
            root_nodes=[
                TreeNode(
                    node_id="n1",
                    title="Summary",
                    level=1,
                    start_offset=0,
                    end_offset=300,
                    children=[],
                )
            ],
            build_method="rule",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=1,
            source_sha256="abc123",
        )
        result = tree.to_dict()
        assert result["source_relpath"] == "report.pdf"
        assert result["total_nodes"] == 1
        assert len(result["root_nodes"]) == 1

    def test_from_dict_round_trip(self) -> None:
        tree = PageTree(
            source_relpath="doc.md",
            source_format="md",
            doc_title="Doc",
            root_nodes=[],
            build_method="rule",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=0,
            source_sha256="def456",
        )
        restored = PageTree.from_dict(tree.to_dict())
        assert restored.source_relpath == tree.source_relpath
        assert restored.build_method == tree.build_method

    def test_json_round_trip(self) -> None:
        tree = PageTree(
            source_relpath="slides.pptx",
            source_format="pptx",
            doc_title="Slides",
            root_nodes=[
                TreeNode(
                    node_id="n1",
                    title="Slide 1",
                    level=1,
                    start_offset=0,
                    end_offset=100,
                    children=[],
                    metadata={"slide_index": 0},
                )
            ],
            build_method="rule",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=1,
            source_sha256="ghi789",
        )
        json_str = tree.to_json()
        restored = PageTree.from_json(json_str)
        assert restored.root_nodes[0].metadata["slide_index"] == 0

    def test_flat_nodes(self) -> None:
        child = TreeNode(
            node_id="n1.1", title="Sub", level=2,
            start_offset=0, end_offset=50, children=[],
        )
        parent = TreeNode(
            node_id="n1", title="Top", level=1,
            start_offset=0, end_offset=100, children=[child],
        )
        tree = PageTree(
            source_relpath="t.txt", source_format="txt", doc_title="T",
            root_nodes=[parent], build_method="rule",
            built_at="2026-05-19T00:00:00Z", total_nodes=2,
            source_sha256="x",
        )
        flat = tree.flat_nodes()
        assert len(flat) == 2
        assert flat[0].node_id == "n1"
        assert flat[1].node_id == "n1.1"

    def test_find_node_for_offset(self) -> None:
        child = TreeNode(
            node_id="n1.1", title="Sub", level=2,
            start_offset=0, end_offset=50, children=[],
        )
        parent = TreeNode(
            node_id="n1", title="Top", level=1,
            start_offset=0, end_offset=100, children=[child],
        )
        tree = PageTree(
            source_relpath="t.txt", source_format="txt", doc_title="T",
            root_nodes=[parent], build_method="rule",
            built_at="2026-05-19T00:00:00Z", total_nodes=2,
            source_sha256="x",
        )
        assert tree.find_node_for_offset(25).node_id == "n1.1"
        assert tree.find_node_for_offset(75).node_id == "n1"
        assert tree.find_node_for_offset(150) is None

    def test_section_path(self) -> None:
        child = TreeNode(
            node_id="n2.1", title="Revenue", level=2,
            start_offset=100, end_offset=200, children=[],
        )
        parent = TreeNode(
            node_id="n2", title="Finance", level=1,
            start_offset=100, end_offset=300, children=[child],
        )
        tree = PageTree(
            source_relpath="r.pdf", source_format="pdf", doc_title="R",
            root_nodes=[parent], build_method="rule",
            built_at="2026-05-19T00:00:00Z", total_nodes=2,
            source_sha256="x",
        )
        assert tree.section_path("n2.1") == "Finance > Revenue"
        assert tree.section_path("n2") == "Finance"
        assert tree.section_path("n999") is None
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /Users/waynetu/claw_prog/projects/04-kurisu-github/hks/.claude/worktrees/funny-jemison-5ae174 && uv run pytest tests/unit/page_tree/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hks.page_tree'`

- [x] **Step 3: Implement PageTree data model**

```python
# src/hks/page_tree/__init__.py
"""Hierarchical document tree (PageIndex integration)."""

# src/hks/page_tree/model.py
"""PageTree and TreeNode data model with JSON serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TreeNode:
    node_id: str
    title: str
    level: int
    start_offset: int
    end_offset: int
    children: list[TreeNode]
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "title": self.title,
            "level": self.level,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "summary": self.summary,
            "metadata": dict(self.metadata),
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TreeNode:
        return cls(
            node_id=data["node_id"],
            title=data["title"],
            level=data["level"],
            start_offset=data["start_offset"],
            end_offset=data["end_offset"],
            summary=data.get("summary", ""),
            metadata=data.get("metadata", {}),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )


@dataclass(frozen=True, slots=True)
class PageTree:
    source_relpath: str
    source_format: str
    doc_title: str
    root_nodes: list[TreeNode]
    build_method: str
    built_at: str
    total_nodes: int
    source_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_relpath": self.source_relpath,
            "source_format": self.source_format,
            "doc_title": self.doc_title,
            "build_method": self.build_method,
            "built_at": self.built_at,
            "total_nodes": self.total_nodes,
            "source_sha256": self.source_sha256,
            "root_nodes": [node.to_dict() for node in self.root_nodes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageTree:
        return cls(
            source_relpath=data["source_relpath"],
            source_format=data["source_format"],
            doc_title=data["doc_title"],
            root_nodes=[TreeNode.from_dict(n) for n in data.get("root_nodes", [])],
            build_method=data["build_method"],
            built_at=data["built_at"],
            total_nodes=data["total_nodes"],
            source_sha256=data["source_sha256"],
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> PageTree:
        return cls.from_dict(json.loads(text))

    def flat_nodes(self) -> list[TreeNode]:
        result: list[TreeNode] = []
        def _walk(nodes: list[TreeNode]) -> None:
            for node in nodes:
                result.append(node)
                _walk(node.children)
        _walk(self.root_nodes)
        return result

    def find_node_for_offset(self, offset: int) -> TreeNode | None:
        def _search(nodes: list[TreeNode]) -> TreeNode | None:
            for node in nodes:
                if node.start_offset <= offset < node.end_offset:
                    deeper = _search(node.children)
                    return deeper if deeper is not None else node
            return None
        return _search(self.root_nodes)

    def section_path(self, node_id: str) -> str | None:
        path: list[str] = []
        def _find(nodes: list[TreeNode]) -> bool:
            for node in nodes:
                path.append(node.title)
                if node.node_id == node_id:
                    return True
                if _find(node.children):
                    return True
                path.pop()
            return False
        if _find(self.root_nodes):
            return " > ".join(path)
        return None
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd /Users/waynetu/claw_prog/projects/04-kurisu-github/hks/.claude/worktrees/funny-jemison-5ae174 && uv run pytest tests/unit/page_tree/test_model.py -v`
Expected: all PASS

- [x] **Step 5: Commit**

```bash
git add src/hks/page_tree/__init__.py src/hks/page_tree/model.py tests/unit/page_tree/test_model.py
git commit -m "feat(page_tree): add PageTree and TreeNode data model with serialization"
```

---

### Task 2: Tree Store

**Files:**
- Create: `src/hks/page_tree/store.py`
- Test: `tests/unit/page_tree/test_page_tree_store.py`
- Modify: `src/hks/core/paths.py:11-21`

- [x] **Step 1: Write failing test for TreeStore**

```python
# tests/unit/page_tree/test_page_tree_store.py
"""Unit tests for page_tree store."""

from __future__ import annotations

import pytest

from hks.core.paths import RuntimePaths
from hks.page_tree.model import PageTree, TreeNode
from hks.page_tree.store import TreeStore


def _sample_tree(relpath: str = "doc.md") -> PageTree:
    return PageTree(
        source_relpath=relpath,
        source_format="md",
        doc_title="Test Doc",
        root_nodes=[
            TreeNode(
                node_id="n1", title="Intro", level=1,
                start_offset=0, end_offset=100, children=[],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00Z",
        total_nodes=1,
        source_sha256="abc123",
    )


class TestTreeStore:
    def test_save_and_load(self, tmp_path: pytest.TempPathFactory) -> None:
        paths = RuntimePaths.from_root(tmp_path / "ks")
        store = TreeStore(paths)
        tree = _sample_tree()
        slug = store.save("doc.md", tree)
        loaded = store.load(slug)
        assert loaded.source_relpath == "doc.md"
        assert loaded.total_nodes == 1

    def test_delete(self, tmp_path: pytest.TempPathFactory) -> None:
        paths = RuntimePaths.from_root(tmp_path / "ks")
        store = TreeStore(paths)
        tree = _sample_tree()
        slug = store.save("doc.md", tree)
        assert store.exists(slug)
        store.delete(slug)
        assert not store.exists(slug)

    def test_list_trees(self, tmp_path: pytest.TempPathFactory) -> None:
        paths = RuntimePaths.from_root(tmp_path / "ks")
        store = TreeStore(paths)
        store.save("a.md", _sample_tree("a.md"))
        store.save("b.md", _sample_tree("b.md"))
        slugs = store.list_slugs()
        assert len(slugs) == 2

    def test_load_nonexistent_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        paths = RuntimePaths.from_root(tmp_path / "ks")
        store = TreeStore(paths)
        with pytest.raises(FileNotFoundError):
            store.load("nonexistent")
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/page_tree/test_page_tree_store.py -v`
Expected: FAIL — `ImportError`

- [x] **Step 3: Add `page_trees` to RuntimePaths**

In `src/hks/core/paths.py`, add the `page_trees` field to the `RuntimePaths` dataclass and update the factory method `from_root` (or the equivalent construction logic) to set `page_trees = root / "page_trees"`. Also update `runtime_paths()` to include `page_trees`.

Check the exact factory pattern in paths.py first — if it uses `__post_init__` or a classmethod, follow that pattern.

- [x] **Step 4: Implement TreeStore**

```python
# src/hks/page_tree/store.py
"""Persistent storage for page trees."""

from __future__ import annotations

from pathlib import Path

from hks.core.paths import RuntimePaths
from hks.page_tree.model import PageTree
from hks.storage.wiki import WikiStore


class TreeStore:
    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self._dir = paths.page_trees

    def _ensure(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _slug_for(self, relpath: str) -> str:
        wiki_store = WikiStore(self.paths)
        return wiki_store.slug_base(Path(relpath).stem)

    def _path_for(self, slug: str) -> Path:
        return self._dir / f"{slug}.json"

    def save(self, relpath: str, tree: PageTree) -> str:
        self._ensure()
        slug = self._slug_for(relpath)
        self._path_for(slug).write_text(tree.to_json(), encoding="utf-8")
        return slug

    def load(self, slug: str) -> PageTree:
        path = self._path_for(slug)
        if not path.exists():
            raise FileNotFoundError(f"page tree not found: {slug}")
        return PageTree.from_json(path.read_text(encoding="utf-8"))

    def delete(self, slug: str) -> None:
        path = self._path_for(slug)
        if path.exists():
            path.unlink()

    def exists(self, slug: str) -> bool:
        return self._path_for(slug).exists()

    def list_slugs(self) -> list[str]:
        self._ensure()
        return sorted(p.stem for p in self._dir.glob("*.json"))
```

- [x] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/page_tree/test_page_tree_store.py -v`
Expected: all PASS

- [x] **Step 6: Commit**

```bash
git add src/hks/page_tree/store.py tests/unit/page_tree/test_page_tree_store.py src/hks/core/paths.py
git commit -m "feat(page_tree): add TreeStore with CRUD and RuntimePaths.page_trees"
```

---

### Task 3: Manifest Extension

**Files:**
- Modify: `src/hks/core/manifest.py:35-58`

- [x] **Step 1: Add `page_tree` field to DerivedArtifacts**

In `src/hks/core/manifest.py`, add to the `DerivedArtifacts` dataclass:

```python
@dataclass(slots=True)
class DerivedArtifacts:
    wiki_pages: list[str] = field(default_factory=list)
    graph_nodes: list[str] = field(default_factory=list)
    graph_edges: list[str] = field(default_factory=list)
    vector_ids: list[str] = field(default_factory=list)
    page_tree: str | None = None  # tree JSON slug (without .json)
```

Also update `to_dict()` and `from_dict()` (or equivalent serialization) to handle the new field. Ensure backward compatibility: missing `page_tree` in existing manifests → `None`.

- [x] **Step 2: Run existing manifest tests to verify no regression**

Run: `uv run pytest tests/ -k manifest -v`
Expected: all existing tests PASS

- [x] **Step 3: Commit**

```bash
git add src/hks/core/manifest.py
git commit -m "feat(manifest): add page_tree field to DerivedArtifacts"
```

---

### Task 4: Rule-based Tree Builders

**Files:**
- Create: `src/hks/page_tree/build.py`
- Test: `tests/unit/page_tree/test_build.py`

- [x] **Step 1: Write failing tests for each format builder**

```python
# tests/unit/page_tree/test_page_tree_build.py
"""Unit tests for rule-based tree builders."""

from __future__ import annotations

import pytest

from hks.ingest.models import ParsedDocument
from hks.ingest.office_common import Segment
from hks.page_tree.build import build_page_tree


class TestMdBuilder:
    def test_headings_create_hierarchy(self) -> None:
        body = "# Chapter 1\n\nIntro text.\n\n## Section 1.1\n\nDetail.\n\n# Chapter 2\n\nMore."
        parsed = ParsedDocument(title="Doc", body=body, format="md")
        nodes = build_page_tree(parsed, body)
        assert len(nodes) == 2
        assert nodes[0].title == "Chapter 1"
        assert nodes[0].level == 1
        assert len(nodes[0].children) == 1
        assert nodes[0].children[0].title == "Section 1.1"
        assert nodes[1].title == "Chapter 2"

    def test_no_headings_single_root(self) -> None:
        body = "Just plain text without headings."
        parsed = ParsedDocument(title="Plain", body=body, format="md")
        nodes = build_page_tree(parsed, body)
        assert len(nodes) == 1
        assert nodes[0].title == "Plain"
        assert nodes[0].start_offset == 0


class TestTxtBuilder:
    def test_always_single_root(self) -> None:
        body = "Some text content."
        parsed = ParsedDocument(title="Notes", body=body, format="txt")
        nodes = build_page_tree(parsed, body)
        assert len(nodes) == 1
        assert nodes[0].title == "Notes"
        assert nodes[0].end_offset == len(body)


class TestDocxBuilder:
    def test_heading_segments_build_tree(self) -> None:
        segments = [
            Segment(kind="heading", text="Overview", metadata={"level": 1}),
            Segment(kind="paragraph", text="Intro paragraph."),
            Segment(kind="heading", text="Details", metadata={"level": 2}),
            Segment(kind="paragraph", text="Detail paragraph."),
            Segment(kind="heading", text="Conclusion", metadata={"level": 1}),
            Segment(kind="paragraph", text="Closing."),
        ]
        body = "\n\n".join(s.text for s in segments)
        parsed = ParsedDocument(
            title="Report", body=body, format="docx", segments=segments,
        )
        nodes = build_page_tree(parsed, body)
        assert len(nodes) == 2
        assert nodes[0].title == "Overview"
        assert len(nodes[0].children) == 1
        assert nodes[0].children[0].title == "Details"
        assert nodes[1].title == "Conclusion"

    def test_no_heading_segments_single_root(self) -> None:
        segments = [Segment(kind="paragraph", text="Just text.")]
        parsed = ParsedDocument(
            title="Flat", body="Just text.", format="docx", segments=segments,
        )
        nodes = build_page_tree(parsed, "Just text.")
        assert len(nodes) == 1
        assert nodes[0].title == "Flat"


class TestPptxBuilder:
    def test_slides_become_nodes(self) -> None:
        segments = [
            Segment(kind="slide_header", text="## Slide 1", metadata={"slide_index": 0}),
            Segment(kind="heading", text="### Welcome", metadata={"slide_index": 0}),
            Segment(kind="paragraph", text="Content.", metadata={"slide_index": 0}),
            Segment(kind="slide_header", text="## Slide 2", metadata={"slide_index": 1}),
            Segment(kind="paragraph", text="More.", metadata={"slide_index": 1}),
        ]
        body = "\n\n".join(s.text for s in segments)
        parsed = ParsedDocument(
            title="Deck", body=body, format="pptx", segments=segments,
        )
        nodes = build_page_tree(parsed, body)
        assert len(nodes) == 2
        assert nodes[0].title == "Slide 1"
        assert nodes[0].metadata.get("slide_index") == 0
        assert len(nodes[0].children) == 1
        assert nodes[0].children[0].title == "Welcome"


class TestXlsxBuilder:
    def test_sheets_become_nodes(self) -> None:
        segments = [
            Segment(kind="sheet_header", text="## Revenue", metadata={"sheet_name": "Revenue"}),
            Segment(kind="table_row", text="Q1: 100", metadata={"sheet_name": "Revenue"}),
            Segment(kind="sheet_header", text="## Costs", metadata={"sheet_name": "Costs"}),
            Segment(kind="table_row", text="Q1: 80", metadata={"sheet_name": "Costs"}),
        ]
        body = "\n\n".join(s.text for s in segments)
        parsed = ParsedDocument(
            title="Finance", body=body, format="xlsx", segments=segments,
        )
        nodes = build_page_tree(parsed, body)
        assert len(nodes) == 2
        assert nodes[0].title == "Revenue"
        assert nodes[0].metadata.get("sheet_name") == "Revenue"


class TestImageBuilder:
    def test_single_root(self) -> None:
        segments = [Segment(kind="ocr_text", text="OCR content.")]
        parsed = ParsedDocument(
            title="photo", body="OCR content.", format="png", segments=segments,
        )
        nodes = build_page_tree(parsed, "OCR content.")
        assert len(nodes) == 1
        assert nodes[0].title == "photo"
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/page_tree/test_build.py -v`
Expected: FAIL — `ImportError`

- [x] **Step 3: Implement build_page_tree with per-format dispatch**

```python
# src/hks/page_tree/build.py
"""Rule-based tree builders per document format."""

from __future__ import annotations

import re
from typing import Any

from hks.ingest.models import ParsedDocument
from hks.ingest.office_common import Segment
from hks.page_tree.model import TreeNode


def build_page_tree(parsed: ParsedDocument, normalized_text: str) -> list[TreeNode]:
    builder = _BUILDERS.get(parsed.format, _build_single_root)
    return builder(parsed, normalized_text)


def _build_single_root(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    return [
        TreeNode(
            node_id="n1",
            title=parsed.title or "Untitled",
            level=1,
            start_offset=0,
            end_offset=len(text),
            children=[],
        )
    ]


def _build_md(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(text))
    if not matches:
        return _build_single_root(parsed, text)

    raw_headings: list[tuple[int, str, int]] = []
    for match in matches:
        level = len(match.group(1))
        title = match.group(2).strip()
        offset = match.start()
        raw_headings.append((level, title, offset))

    return _headings_to_tree(raw_headings, text)


def _build_docx(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    if not parsed.segments:
        return _build_single_root(parsed, text)

    headings = _extract_heading_segments(parsed.segments, text)
    if not headings:
        return _build_single_root(parsed, text)

    return _headings_to_tree(headings, text)


def _build_pptx(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    if not parsed.segments:
        return _build_single_root(parsed, text)

    slides: dict[int, list[Segment]] = {}
    for seg in parsed.segments:
        idx = seg.metadata.get("slide_index", 0)
        slides.setdefault(idx, []).append(seg)

    nodes: list[TreeNode] = []
    counter = 1
    for slide_idx in sorted(slides):
        segs = slides[slide_idx]
        slide_header = next((s for s in segs if s.kind == "slide_header"), None)
        slide_title = _clean_slide_title(slide_header.text) if slide_header else f"Slide {slide_idx + 1}"

        heading_children: list[TreeNode] = []
        child_counter = 1
        for seg in segs:
            if seg.kind == "heading":
                title = seg.text.lstrip("#").strip()
                heading_children.append(TreeNode(
                    node_id=f"n{counter}.{child_counter}",
                    title=title,
                    level=2,
                    start_offset=text.find(seg.text),
                    end_offset=text.find(seg.text) + len(seg.text),
                    children=[],
                    metadata={"slide_index": slide_idx},
                ))
                child_counter += 1

        start = text.find(segs[0].text) if segs else 0
        end_seg = segs[-1]
        end = text.find(end_seg.text) + len(end_seg.text) if segs else len(text)

        nodes.append(TreeNode(
            node_id=f"n{counter}",
            title=slide_title,
            level=1,
            start_offset=max(0, start),
            end_offset=min(len(text), end),
            children=heading_children,
            metadata={"slide_index": slide_idx},
        ))
        counter += 1

    return nodes


def _build_xlsx(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    if not parsed.segments:
        return _build_single_root(parsed, text)

    sheets: dict[str, list[Segment]] = {}
    for seg in parsed.segments:
        name = seg.metadata.get("sheet_name", "Sheet")
        sheets.setdefault(name, []).append(seg)

    nodes: list[TreeNode] = []
    counter = 1
    for sheet_name in sheets:
        segs = sheets[sheet_name]
        start = text.find(segs[0].text) if segs else 0
        end_seg = segs[-1]
        end = text.find(end_seg.text) + len(end_seg.text) if segs else len(text)

        nodes.append(TreeNode(
            node_id=f"n{counter}",
            title=sheet_name,
            level=1,
            start_offset=max(0, start),
            end_offset=min(len(text), end),
            children=[],
            metadata={"sheet_name": sheet_name},
        ))
        counter += 1

    return nodes


def _build_image(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    return _build_single_root(parsed, text)


def _extract_heading_segments(
    segments: list[Segment], text: str,
) -> list[tuple[int, str, int]]:
    headings: list[tuple[int, str, int]] = []
    pos = 0
    for seg in segments:
        idx = text.find(seg.text, pos)
        if idx >= 0:
            pos = idx
        if seg.kind == "heading":
            level = seg.metadata.get("level", 1)
            headings.append((level, seg.text, max(0, idx)))
    return headings


def _headings_to_tree(
    headings: list[tuple[int, str, int]], text: str,
) -> list[TreeNode]:
    nodes: list[TreeNode] = []
    stack: list[tuple[int, list[TreeNode]]] = []
    counters: list[int] = [0]

    for i, (level, title, start) in enumerate(headings):
        end = headings[i + 1][2] if i + 1 < len(headings) else len(text)

        while stack and stack[-1][0] >= level:
            stack.pop()
            counters.pop()

        if not counters:
            counters = [0]

        counters[-1] += 1
        node_id = ".".join(f"n{c}" if j == 0 else str(c) for j, c in enumerate(counters))

        node = TreeNode(
            node_id=node_id,
            title=title,
            level=level,
            start_offset=start,
            end_offset=end,
            children=[],
        )

        if stack:
            parent_children = stack[-1][1]
            parent_children.append(node)
        else:
            nodes.append(node)

        stack.append((level, node.children))
        counters.append(0)

    return nodes


def _clean_slide_title(text: str) -> str:
    return re.sub(r"^#+\s*", "", text).strip() or "Untitled Slide"


_BUILDERS = {
    "txt": _build_single_root,
    "md": _build_md,
    "docx": _build_docx,
    "pptx": _build_pptx,
    "xlsx": _build_xlsx,
    "png": _build_image,
    "jpg": _build_image,
    "jpeg": _build_image,
    "pdf": _build_single_root,  # PDF gets its own builder after Task 5
}
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/page_tree/test_build.py -v`
Expected: all PASS

- [x] **Step 5: Commit**

```bash
git add src/hks/page_tree/build.py tests/unit/page_tree/test_build.py
git commit -m "feat(page_tree): rule-based tree builders for md/txt/docx/pptx/xlsx/image"
```

---

### Task 5: PDF Parser Enhancement

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/hks/ingest/parsers/pdf.py`
- Create: `tests/unit/ingest/parsers/test_pdf_segments.py`
- Create: `tests/fixtures/valid/with-toc.pdf` (generated programmatically in test)

- [x] **Step 1: Add pymupdf dependency**

In `pyproject.toml`, add `"pymupdf"` to the `dependencies` list. Also add `"fitz"` to the mypy `ignore_missing_imports` override list.

```bash
uv add pymupdf
```

- [x] **Step 2: Write failing test for PDF segment extraction**

```python
# tests/unit/ingest/parsers/test_pdf_segments.py
"""Tests for PDF parser segment extraction via PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import pytest

from hks.ingest.models import ParsedDocument
from hks.ingest.parsers import pdf as pdf_parser


class TestPdfSegments:
    def test_parse_returns_parsed_document(self, tmp_path: Path) -> None:
        _create_simple_pdf(tmp_path / "simple.pdf", ["Hello world"])
        result = pdf_parser.parse(tmp_path / "simple.pdf")
        assert isinstance(result, ParsedDocument)
        assert result.format == "pdf"
        assert "Hello" in result.body

    def test_toc_pdf_produces_heading_segments(self, tmp_path: Path) -> None:
        _create_toc_pdf(tmp_path / "toc.pdf")
        result = pdf_parser.parse(tmp_path / "toc.pdf")
        heading_segments = [s for s in result.segments if s.kind == "heading"]
        assert len(heading_segments) >= 1

    def test_no_toc_font_heuristic(self, tmp_path: Path) -> None:
        _create_heading_pdf(tmp_path / "headings.pdf")
        result = pdf_parser.parse(tmp_path / "headings.pdf")
        # Should produce at least some segments (headings or paragraphs)
        assert len(result.segments) >= 1

    def test_plain_pdf_no_segments(self, tmp_path: Path) -> None:
        _create_simple_pdf(tmp_path / "plain.pdf", ["Just text. " * 20])
        result = pdf_parser.parse(tmp_path / "plain.pdf")
        # Plain uniform text → no reliable headings → may have zero segments
        # (fallback to body-only like before)
        assert result.body.strip() != ""


def _create_simple_pdf(path: Path, texts: list[str]) -> None:
    """Create a minimal PDF with uniform text using PyMuPDF."""
    import fitz
    doc = fitz.open()
    for text in texts:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    doc.save(str(path))
    doc.close()


def _create_toc_pdf(path: Path) -> None:
    """Create a PDF with TOC bookmarks."""
    import fitz
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Chapter 1: Introduction", fontsize=18)
    page1.insert_text((72, 120), "Some introductory text here.", fontsize=11)
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Chapter 2: Methods", fontsize=18)
    page2.insert_text((72, 120), "Methodology description.", fontsize=11)
    doc.set_toc([
        [1, "Chapter 1: Introduction", 1],
        [1, "Chapter 2: Methods", 2],
    ])
    doc.save(str(path))
    doc.close()


def _create_heading_pdf(path: Path) -> None:
    """Create a PDF with large-font headings but no TOC."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Big Heading", fontsize=24)
    page.insert_text((72, 120), "Normal body text. " * 10, fontsize=11)
    page.insert_text((72, 300), "Another Heading", fontsize=24)
    page.insert_text((72, 348), "More body text. " * 10, fontsize=11)
    doc.save(str(path))
    doc.close()
```

- [x] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingest/parsers/test_pdf_segments.py -v`
Expected: FAIL — segments not produced by current parser

- [x] **Step 4: Rewrite PDF parser with PyMuPDF segment extraction**

```python
# src/hks/ingest/parsers/pdf.py
"""PDF parser with structural segment extraction via PyMuPDF."""

from __future__ import annotations

import statistics
from pathlib import Path

import fitz

from hks.core.config import config_value
from hks.errors import ExitCode, KSError
from hks.ingest.models import ParsedDocument
from hks.ingest.office_common import Segment


def max_file_mb() -> int:
    return int(config_value("HKS_MAX_FILE_MB") or "200")


def parse(path: Path) -> ParsedDocument:
    size_limit = max_file_mb() * 1024 * 1024
    if path.stat().st_size > size_limit:
        raise KSError(
            f"檔案超過大小上限：{path}",
            exit_code=ExitCode.DATAERR,
            code="OVERSIZED",
            details=[f"limit_mb={max_file_mb()}"],
        )

    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise KSError(
            f"無法解析 PDF {path}",
            exit_code=ExitCode.DATAERR,
            code="PDF_READ_ERROR",
            details=[str(exc)],
        ) from exc

    try:
        toc = doc.get_toc()
        if toc:
            segments = _segments_from_toc(doc, toc)
        else:
            segments = _segments_from_font_heuristic(doc)

        if segments:
            body = "\n\n".join(s.text for s in segments if s.text.strip())
        else:
            body = "\n\n".join(
                (page.get_text() or "") for page in doc
            )
    finally:
        doc.close()

    return ParsedDocument(
        title=path.stem, body=body, format="pdf", segments=segments,
    )


def _segments_from_toc(
    doc: fitz.Document, toc: list[list],
) -> list[Segment]:
    segments: list[Segment] = []
    for i, entry in enumerate(toc):
        level, title, page_num = entry[0], entry[1], entry[2]
        next_page = toc[i + 1][2] if i + 1 < len(toc) else len(doc) + 1

        segments.append(Segment(
            kind="heading",
            text=title,
            metadata={"level": level, "page_number": page_num},
        ))

        body_parts: list[str] = []
        for pg_idx in range(page_num - 1, min(next_page - 1, len(doc))):
            text = doc[pg_idx].get_text() or ""
            body_parts.append(text.strip())

        body_text = "\n".join(body_parts).strip()
        if body_text:
            segments.append(Segment(
                kind="paragraph",
                text=body_text,
                metadata={
                    "page_start": page_num,
                    "page_end": min(next_page - 1, len(doc)),
                },
            ))

    return segments


def _segments_from_font_heuristic(doc: fitz.Document) -> list[Segment]:
    spans_info: list[tuple[float, str, int]] = []
    for page_idx, page in enumerate(doc):
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    size = span.get("size", 0.0)
                    if text and size > 0:
                        spans_info.append((size, text, page_idx + 1))

    if not spans_info:
        return []

    sizes = [s[0] for s in spans_info]
    if len(set(sizes)) < 2:
        return []

    median_size = statistics.median(sizes)
    h1_threshold = median_size * 1.5
    h2_threshold = median_size * 1.3

    segments: list[Segment] = []
    current_body: list[str] = []
    current_page_start: int = 1

    for size, text, page_num in spans_info:
        if _is_header_noise(text):
            continue

        if size >= h1_threshold:
            if current_body:
                segments.append(Segment(
                    kind="paragraph",
                    text="\n".join(current_body),
                    metadata={"page_start": current_page_start, "page_end": page_num},
                ))
                current_body = []
            segments.append(Segment(
                kind="heading",
                text=text,
                metadata={"level": 1, "page_number": page_num},
            ))
            current_page_start = page_num
        elif size >= h2_threshold:
            if current_body:
                segments.append(Segment(
                    kind="paragraph",
                    text="\n".join(current_body),
                    metadata={"page_start": current_page_start, "page_end": page_num},
                ))
                current_body = []
            segments.append(Segment(
                kind="heading",
                text=text,
                metadata={"level": 2, "page_number": page_num},
            ))
            current_page_start = page_num
        else:
            current_body.append(text)

    if current_body:
        last_page = spans_info[-1][2] if spans_info else 1
        segments.append(Segment(
            kind="paragraph",
            text="\n".join(current_body),
            metadata={"page_start": current_page_start, "page_end": last_page},
        ))

    heading_count = sum(1 for s in segments if s.kind == "heading")
    if heading_count == 0:
        return []

    return segments


def _is_header_noise(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.isdigit():
        return True
    if len(stripped) <= 1:
        return True
    return False
```

- [x] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/ingest/parsers/test_pdf_segments.py -v`
Expected: all PASS

- [x] **Step 6: Run full existing PDF tests for regression**

Run: `uv run pytest tests/ -k pdf -v`
Expected: all PASS

- [x] **Step 7: Update PDF builder in build.py**

In `src/hks/page_tree/build.py`, update the `_BUILDERS` dict to use the heading segments that the new PDF parser now produces:

```python
# Change in _BUILDERS:
"pdf": _build_pdf,

# Add new function:
def _build_pdf(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    if not parsed.segments:
        return _build_single_root(parsed, text)
    headings = _extract_heading_segments(parsed.segments, text)
    if not headings:
        return _build_single_root(parsed, text)
    return _headings_to_tree(headings, text)
```

- [x] **Step 8: Commit**

```bash
git add pyproject.toml src/hks/ingest/parsers/pdf.py src/hks/page_tree/build.py tests/unit/ingest/parsers/test_pdf_segments.py
git commit -m "feat(pdf): rewrite PDF parser with PyMuPDF TOC + font-size heading extraction"
```

---

### Task 6: Pipeline Integration

**Files:**
- Modify: `src/hks/ingest/pipeline.py`
- Test: `tests/integration/test_ingest_tree.py`

- [x] **Step 1: Write failing integration test**

```python
# tests/integration/test_ingest_tree.py
"""Integration test: ingest pipeline produces page trees + enriched chunk metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from hks.core.manifest import resume_or_rebuild
from hks.core.paths import runtime_paths
from hks.ingest.pipeline import ingest
from hks.page_tree.store import TreeStore


@pytest.fixture
def ks_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ks_root = tmp_path / "ks"
    monkeypatch.setenv("KS_ROOT", str(ks_root))
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", "simple")
    return ks_root


class TestIngestProducesTree:
    def test_md_ingest_creates_tree(self, ks_env: Path, tmp_path: Path) -> None:
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Chapter 1\n\nText.\n\n## Section 1.1\n\nDetail.")
        summary = ingest(md_file)
        assert len(summary.created) == 1

        paths = runtime_paths()
        store = TreeStore(paths)
        slugs = store.list_slugs()
        assert len(slugs) == 1

        tree = store.load(slugs[0])
        assert tree.source_format == "md"
        assert tree.total_nodes >= 2

    def test_txt_ingest_creates_degenerate_tree(self, ks_env: Path, tmp_path: Path) -> None:
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("Plain text without structure.")
        summary = ingest(txt_file)
        assert len(summary.created) == 1

        paths = runtime_paths()
        store = TreeStore(paths)
        tree = store.load(store.list_slugs()[0])
        assert tree.total_nodes == 1

    def test_manifest_records_page_tree(self, ks_env: Path, tmp_path: Path) -> None:
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Heading\n\nBody.")
        ingest(md_file)

        paths = runtime_paths()
        manifest = resume_or_rebuild(paths)
        entry = manifest.entries["doc.md"]
        assert entry.derived.page_tree is not None

    def test_chunk_metadata_has_tree_node_id(self, ks_env: Path, tmp_path: Path) -> None:
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Chapter\n\n" + "Word " * 200)
        ingest(md_file)

        paths = runtime_paths()
        import chromadb
        client = chromadb.PersistentClient(path=str(paths.vector_db))
        collection = client.get_collection("hks")
        results = collection.get(include=["metadatas"])
        assert any(
            "tree_node_id" in meta
            for meta in results["metadatas"]
        )
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_ingest_tree.py -v`
Expected: FAIL — tree not produced

- [x] **Step 3: Modify pipeline.py to build tree and attach node_ids**

In `src/hks/ingest/pipeline.py`, make these changes:

1. Add imports at top:
```python
from hks.page_tree.build import build_page_tree
from hks.page_tree.model import PageTree
from hks.page_tree.store import TreeStore
from hks.core.manifest import utc_now_iso
```

2. In `ingest()`, after `vector_store = VectorStore(...)`, add:
```python
tree_store = TreeStore(paths)
```

3. In the per-file loop, after `extracted = extractor.extract(...)` (line ~381) and before `raw_target = ...` (line ~383), insert:
```python
tree_nodes = build_page_tree(parsed, normalized_text)
page_tree = PageTree(
    source_relpath=relpath,
    source_format=source_format,
    doc_title=extracted.title,
    root_nodes=tree_nodes,
    build_method="rule",
    built_at=utc_now_iso(),
    total_nodes=_count_nodes(tree_nodes),
    source_sha256=sha256,
)
tree_slug = tree_store.save(relpath, page_tree)
```

4. In the `vector_chunks` list comprehension (line ~405-424), add `tree_node_id` and `tree_node_title` to chunk metadata:
```python
**_tree_node_metadata(page_tree, chunk_text, normalized_text, index, extracted.chunks),
```

5. In the `ManifestEntry` construction (line ~450-463), add:
```python
page_tree=tree_slug,
```

6. In the rollback `except` block (line ~465-488), add before existing rollback:
```python
tree_store.delete(tree_slug if tree_slug else "")
```

7. In `delete_artifacts()` (line ~117-131), add tree deletion:
```python
if hasattr(paths, 'page_trees'):
    tree_store = TreeStore(paths)
    # find and delete tree for this relpath
```

8. Add helper functions:
```python
def _count_nodes(nodes: list) -> int:
    count = 0
    for node in nodes:
        count += 1
        count += _count_nodes(node.children)
    return count

def _tree_node_metadata(
    tree: PageTree, chunk_text: str, full_text: str,
    chunk_idx: int, all_chunks: list[str],
) -> dict[str, str]:
    offset = _estimate_chunk_offset(full_text, all_chunks, chunk_idx)
    node = tree.find_node_for_offset(offset)
    if node is None:
        return {}
    return {
        "tree_node_id": node.node_id,
        "tree_node_title": node.title,
    }

def _estimate_chunk_offset(full_text: str, chunks: list[str], idx: int) -> int:
    offset = 0
    for i in range(idx):
        pos = full_text.find(chunks[i], offset)
        if pos >= 0:
            offset = pos + len(chunks[i])
    pos = full_text.find(chunks[idx], offset)
    return pos if pos >= 0 else offset
```

- [x] **Step 4: Run integration test to verify it passes**

Run: `uv run pytest tests/integration/test_ingest_tree.py -v`
Expected: all PASS

- [x] **Step 5: Run full test suite for regression**

Run: `uv run pytest tests/ -x --timeout=120`
Expected: all PASS

- [x] **Step 6: Commit**

```bash
git add src/hks/ingest/pipeline.py tests/integration/test_ingest_tree.py
git commit -m "feat(pipeline): integrate page tree build + chunk tree_node_id into ingest"
```

---

### Task 7: LLM Tree Enrichment

**Files:**
- Create: `src/hks/page_tree/enrich.py`
- Test: `tests/unit/page_tree/test_enrich.py`

- [x] **Step 1: Write failing test**

```python
# tests/unit/page_tree/test_enrich.py
"""Unit tests for LLM tree enrichment."""

from __future__ import annotations

import pytest

from hks.page_tree.enrich import enrich_tree
from hks.page_tree.model import PageTree, TreeNode


def _rule_tree() -> PageTree:
    return PageTree(
        source_relpath="doc.md",
        source_format="md",
        doc_title="Doc",
        root_nodes=[
            TreeNode(
                node_id="n1", title="Chapter 1", level=1,
                start_offset=0, end_offset=100,
                children=[
                    TreeNode(
                        node_id="n1.1", title="Section 1.1", level=2,
                        start_offset=0, end_offset=50, children=[],
                    )
                ],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00Z",
        total_nodes=2,
        source_sha256="abc",
    )


def _degenerate_tree() -> PageTree:
    return PageTree(
        source_relpath="flat.txt",
        source_format="txt",
        doc_title="Flat",
        root_nodes=[
            TreeNode(
                node_id="n1", title="Flat", level=1,
                start_offset=0, end_offset=500, children=[],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00Z",
        total_nodes=1,
        source_sha256="def",
    )


class TestEnrichTree:
    def test_fake_provider_fills_summaries(self) -> None:
        tree = _rule_tree()
        source_text = "Chapter 1 content. " * 5 + "Section 1.1 detail. " * 3
        enriched = enrich_tree(tree, source_text, provider="fake")
        assert enriched.build_method == "llm"
        for node in enriched.flat_nodes():
            assert node.summary != ""

    def test_fake_provider_preserves_structure(self) -> None:
        tree = _rule_tree()
        source_text = "x" * 100
        enriched = enrich_tree(tree, source_text, provider="fake")
        assert enriched.total_nodes == tree.total_nodes
        assert enriched.root_nodes[0].node_id == "n1"
        assert enriched.root_nodes[0].children[0].node_id == "n1.1"

    def test_degenerate_tree_restructured(self) -> None:
        tree = _degenerate_tree()
        source_text = "A" * 500
        enriched = enrich_tree(tree, source_text, provider="fake")
        assert enriched.build_method == "llm"
        # Fake restructure splits into 3 sections
        assert enriched.total_nodes == 3

    def test_already_llm_skips(self) -> None:
        tree = _rule_tree()
        llm_tree = PageTree(
            source_relpath=tree.source_relpath,
            source_format=tree.source_format,
            doc_title=tree.doc_title,
            root_nodes=tree.root_nodes,
            build_method="llm",
            built_at=tree.built_at,
            total_nodes=tree.total_nodes,
            source_sha256=tree.source_sha256,
        )
        result = enrich_tree(llm_tree, "text", provider="fake", force=False)
        assert result is llm_tree  # unchanged, skipped
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/page_tree/test_enrich.py -v`
Expected: FAIL — `ImportError`

- [x] **Step 3: Implement enrich_tree**

```python
# src/hks/page_tree/enrich.py
"""LLM tree enrichment: fill summaries and restructure degenerate trees."""

from __future__ import annotations

from hks.core.manifest import utc_now_iso
from hks.page_tree.model import PageTree, TreeNode


def enrich_tree(
    tree: PageTree,
    source_text: str,
    *,
    provider: str = "fake",
    model: str | None = None,
    force: bool = False,
) -> PageTree:
    if tree.build_method == "llm" and not force:
        return tree

    if tree.total_nodes == 1 and provider == "fake":
        return _fake_restructure(tree, source_text)

    if tree.total_nodes == 1:
        return _llm_restructure(tree, source_text, provider, model)

    enriched_nodes = _fill_summaries(tree.root_nodes, source_text, provider, model)
    count = _count_nodes(enriched_nodes)
    return PageTree(
        source_relpath=tree.source_relpath,
        source_format=tree.source_format,
        doc_title=tree.doc_title,
        root_nodes=enriched_nodes,
        build_method="llm",
        built_at=utc_now_iso(),
        total_nodes=count,
        source_sha256=tree.source_sha256,
    )


def _fill_summaries(
    nodes: list[TreeNode],
    source_text: str,
    provider: str,
    model: str | None,
) -> list[TreeNode]:
    result: list[TreeNode] = []
    for node in nodes:
        text_slice = source_text[node.start_offset:node.end_offset]
        if provider == "fake":
            summary = f"Summary of: {node.title}"
        else:
            summary = _llm_summarize(text_slice, node.title, provider, model)
        children = _fill_summaries(node.children, source_text, provider, model)
        result.append(TreeNode(
            node_id=node.node_id,
            title=node.title,
            level=node.level,
            start_offset=node.start_offset,
            end_offset=node.end_offset,
            children=children,
            summary=summary,
            metadata=node.metadata,
        ))
    return result


def _fake_restructure(tree: PageTree, source_text: str) -> PageTree:
    chunk_size = max(1, len(source_text) // 3)
    nodes: list[TreeNode] = []
    for i in range(3):
        start = i * chunk_size
        end = min((i + 1) * chunk_size, len(source_text))
        nodes.append(TreeNode(
            node_id=f"n{i + 1}",
            title=f"Section {i + 1}",
            level=1,
            start_offset=start,
            end_offset=end,
            children=[],
            summary=f"Summary of: Section {i + 1}",
        ))
    return PageTree(
        source_relpath=tree.source_relpath,
        source_format=tree.source_format,
        doc_title=tree.doc_title,
        root_nodes=nodes,
        build_method="llm",
        built_at=utc_now_iso(),
        total_nodes=3,
        source_sha256=tree.source_sha256,
    )


def _llm_restructure(
    tree: PageTree, source_text: str, provider: str, model: str | None,
) -> PageTree:
    # Delegates to LLM provider for real restructuring.
    # Uses same provider interface as hks.llm module.
    raise NotImplementedError(f"LLM restructure not yet implemented for provider={provider}")


def _llm_summarize(text: str, title: str, provider: str, model: str | None) -> str:
    # Delegates to LLM provider for real summarization.
    raise NotImplementedError(f"LLM summarize not yet implemented for provider={provider}")


def _count_nodes(nodes: list[TreeNode]) -> int:
    count = 0
    for node in nodes:
        count += 1 + _count_nodes(node.children)
    return count
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/page_tree/test_enrich.py -v`
Expected: all PASS

- [x] **Step 5: Commit**

```bash
git add src/hks/page_tree/enrich.py tests/unit/page_tree/test_enrich.py
git commit -m "feat(page_tree): LLM tree enrichment with fake provider"
```

---

### Task 8: CLI Commands

**Files:**
- Create: `src/hks/commands/pageindex.py`
- Modify: `src/hks/cli.py`
- Modify: `src/hks/core/schema.py:16-33`
- Test: `tests/integration/test_pageindex_cli.py`

- [x] **Step 1: Add `pageindex_summary` to TraceKind**

In `src/hks/core/schema.py`, add `"pageindex_summary"` to the `TraceKind` literal type.

- [x] **Step 2: Create pageindex command module**

```python
# src/hks/commands/pageindex.py
"""Command wrappers for PageIndex tree operations."""

from __future__ import annotations

import json

from hks.core.manifest import resume_or_rebuild
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.page_tree.enrich import enrich_tree
from hks.page_tree.store import TreeStore
from hks.storage.wiki import WikiStore


def run_show(*, source_relpath: str) -> QueryResponse:
    paths = runtime_paths()
    store = TreeStore(paths)
    manifest = resume_or_rebuild(paths)
    entry = manifest.entries.get(source_relpath)
    if entry is None or entry.derived.page_tree is None:
        return QueryResponse(
            answer=f"找不到 {source_relpath} 的 page tree",
            source=[],
            confidence=0.0,
            trace=Trace(route="wiki", steps=[TraceStep(kind="pageindex_summary", detail={"found": False})]),
        )
    tree = store.load(entry.derived.page_tree)
    detail = tree.to_dict()
    return QueryResponse(
        answer=f"page tree for {source_relpath}: {tree.total_nodes} nodes, build_method={tree.build_method}",
        source=["wiki"],
        confidence=1.0,
        trace=Trace(route="wiki", steps=[TraceStep(kind="pageindex_summary", detail=detail)]),
    )


def run_enrich(
    *,
    source_relpath: str | None = None,
    mode: str = "preview",
    provider: str = "fake",
    model: str | None = None,
    force: bool = False,
) -> QueryResponse:
    paths = runtime_paths()
    store = TreeStore(paths)
    wiki_store = WikiStore(paths)
    manifest = resume_or_rebuild(paths)

    targets: list[str] = []
    if source_relpath:
        targets = [source_relpath]
    else:
        targets = [
            rp for rp, entry in manifest.entries.items()
            if entry.derived.page_tree is not None
        ]

    enriched_count = 0
    skipped_count = 0

    for rp in targets:
        entry = manifest.entries.get(rp)
        if entry is None or entry.derived.page_tree is None:
            skipped_count += 1
            continue

        tree = store.load(entry.derived.page_tree)
        raw_path = paths.raw_sources / rp
        source_text = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""

        enriched = enrich_tree(tree, source_text, provider=provider, model=model, force=force)
        if enriched is tree:
            skipped_count += 1
            continue

        if mode == "store":
            store.save(rp, enriched)
        enriched_count += 1

    detail = {
        "enriched": enriched_count,
        "skipped": skipped_count,
        "mode": mode,
        "provider": provider,
    }
    return QueryResponse(
        answer=f"pageindex enrich {mode}: {enriched_count} enriched, {skipped_count} skipped",
        source=["wiki"],
        confidence=1.0,
        trace=Trace(route="wiki", steps=[TraceStep(kind="pageindex_summary", detail=detail)]),
    )
```

- [x] **Step 3: Register in cli.py**

In `src/hks/cli.py`, add:
```python
from hks.commands import pageindex as pageindex_command

pageindex_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(pageindex_app, name="pageindex")

@pageindex_app.command("show")
def pageindex_show(source_relpath: str) -> None:
    result = pageindex_command.run_show(source_relpath=source_relpath)
    typer.echo(result.to_json())

@pageindex_app.command("enrich")
def pageindex_enrich(
    source_relpath: str | None = None,
    mode: str = "preview",
    provider: str = "fake",
    model: str | None = None,
    force: bool = False,
) -> None:
    result = pageindex_command.run_enrich(
        source_relpath=source_relpath, mode=mode,
        provider=provider, model=model, force=force,
    )
    typer.echo(result.to_json())
```

- [x] **Step 4: Write integration test**

```python
# tests/integration/test_pageindex_cli.py
"""Integration tests for ks pageindex CLI commands."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def ks_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ks_root = tmp_path / "ks"
    monkeypatch.setenv("KS_ROOT", str(ks_root))
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", "simple")
    return ks_root


class TestPageindexShow:
    def test_show_after_ingest(self, ks_env: Path, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Heading\n\nBody text.")
        from hks.ingest.pipeline import ingest
        ingest(md)

        from hks.commands.pageindex import run_show
        result = run_show(source_relpath="doc.md")
        assert result.confidence == 1.0
        detail = result.trace.steps[0].detail
        assert detail["total_nodes"] >= 1

    def test_show_missing_source(self, ks_env: Path) -> None:
        from hks.commands.pageindex import run_show
        result = run_show(source_relpath="nonexistent.md")
        assert result.confidence == 0.0


class TestPageindexEnrich:
    def test_enrich_preview(self, ks_env: Path, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Chapter\n\nContent.")
        from hks.ingest.pipeline import ingest
        ingest(md)

        from hks.commands.pageindex import run_enrich
        result = run_enrich(mode="preview", provider="fake")
        detail = result.trace.steps[0].detail
        assert detail["enriched"] >= 1
        assert detail["mode"] == "preview"

    def test_enrich_store(self, ks_env: Path, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Chapter\n\nContent.")
        from hks.ingest.pipeline import ingest
        ingest(md)

        from hks.commands.pageindex import run_enrich
        run_enrich(mode="store", provider="fake")

        from hks.page_tree.store import TreeStore
        from hks.core.paths import runtime_paths
        store = TreeStore(runtime_paths())
        tree = store.load(store.list_slugs()[0])
        assert tree.build_method == "llm"
```

- [x] **Step 5: Run tests**

Run: `uv run pytest tests/integration/test_pageindex_cli.py -v`
Expected: all PASS

- [x] **Step 6: Commit**

```bash
git add src/hks/commands/pageindex.py src/hks/cli.py src/hks/core/schema.py tests/integration/test_pageindex_cli.py
git commit -m "feat(cli): add ks pageindex show|enrich commands"
```

---

### Task 9: Lint Rules + Adapter Integration

**Files:**
- Modify: lint rules file (find exact path in `src/hks/lint/`)
- Modify: `src/hks/adapters/core.py`
- Modify: `src/hks/adapters/mcp_server.py`
- Modify: `src/hks/adapters/http_server.py`

- [x] **Step 1: Add tree lint rules**

Find the lint rules registration in `src/hks/lint/`. Add four new rules:

- `tree_missing` (warning): manifest has `page_tree` but file doesn't exist
- `tree_orphan` (warning): file exists in `page_trees/` but no manifest entry references it
- `tree_offset_mismatch` (info): any node's `end_offset > len(normalized_text)`
- `tree_node_chunk_gap` (info): chunk offset doesn't fall in any tree node range

Follow the existing lint rule pattern exactly.

- [x] **Step 2: Add adapter functions in core.py**

In `src/hks/adapters/core.py`, add:

```python
def hks_pageindex_show(
    *,
    source_relpath: str,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return _run_command(
        lambda: pageindex_command.run_show(source_relpath=source_relpath),
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_pageindex_enrich(
    *,
    source_relpath: str | None = None,
    mode: str = "preview",
    provider: str = "fake",
    model: str | None = None,
    force: bool = False,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    _require_choice(mode, {"preview", "store"}, "mode")
    _require_choice(provider, {"fake", "openai"}, "provider")
    return _run_command(
        lambda: pageindex_command.run_enrich(
            source_relpath=source_relpath, mode=mode,
            provider=provider, model=model, force=force,
        ),
        ks_root=ks_root,
        request_id=request_id,
    )
```

- [x] **Step 3: Register MCP tools in mcp_server.py**

```python
@server.tool()
def hks_pageindex_show(
    source_relpath: str,
    ks_root: str | None = None,
) -> Any:
    """Show the page tree for a specific source."""
    try:
        return core.hks_pageindex_show(source_relpath=source_relpath, ks_root=ks_root)
    except AdapterToolError as error:
        return _error_result(error)

@server.tool()
def hks_pageindex_enrich(
    source_relpath: str | None = None,
    mode: str = "preview",
    provider: str = "fake",
    model: str | None = None,
    force: bool = False,
    ks_root: str | None = None,
) -> Any:
    """Enrich page trees with LLM summaries."""
    try:
        return core.hks_pageindex_enrich(
            source_relpath=source_relpath, mode=mode,
            provider=provider, model=model, force=force, ks_root=ks_root,
        )
    except AdapterToolError as error:
        return _error_result(error)
```

- [x] **Step 4: Add HTTP routes in http_server.py**

Follow existing route pattern to add `GET /pageindex/{relpath}` and `POST /pageindex/enrich`.

- [x] **Step 5: Run lint and adapter tests**

Run: `uv run pytest tests/ -k "lint or mcp or http" -v`
Expected: all PASS

- [x] **Step 6: Commit**

```bash
git add src/hks/lint/ src/hks/adapters/core.py src/hks/adapters/mcp_server.py src/hks/adapters/http_server.py
git commit -m "feat(adapters): add pageindex lint rules + MCP/HTTP endpoints"
```

---

## Phase 2: Routing Improvements

### Task 10: Wiki Search Tree Summary Scan

**Files:**
- Modify: `src/hks/storage/wiki.py:310-346`
- Test: `tests/unit/storage/test_wiki_tree_search.py`

- [x] **Step 1: Write failing test**

```python
# tests/unit/storage/test_wiki_tree_search.py
"""Test tree-assisted wiki search."""

from __future__ import annotations

from pathlib import Path

import pytest

from hks.core.paths import RuntimePaths
from hks.page_tree.model import PageTree, TreeNode
from hks.page_tree.store import TreeStore
from hks.storage.wiki import WikiStore


class TestTreeAssistedSearch:
    def test_tree_summaries_boost_search(self, tmp_path: Path) -> None:
        paths = RuntimePaths.from_root(tmp_path / "ks")
        wiki_store = WikiStore(paths)
        tree_store = TreeStore(paths)

        wiki_store.write_page(
            title="Finance Report",
            summary="Quarterly results",
            body="Revenue details for Q1.",
            source_relpath="finance.pdf",
            origin="ingest",
        )
        tree_store.save("finance.pdf", PageTree(
            source_relpath="finance.pdf",
            source_format="pdf",
            doc_title="Finance Report",
            root_nodes=[
                TreeNode(
                    node_id="n1", title="Revenue Breakdown", level=1,
                    start_offset=0, end_offset=100, children=[],
                    summary="Detailed quarterly revenue by product line.",
                )
            ],
            build_method="llm",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=1,
            source_sha256="x",
        ))

        result = wiki_store.search("revenue breakdown", tree_store=tree_store)
        assert result is not None
        assert result.title == "Finance Report"
```

- [x] **Step 2: Implement tree-assisted search**

Modify `WikiStore.search()` to accept optional `tree_store: TreeStore | None = None`. When provided:

1. Stage 1: scan all tree nodes' `title` + `summary` for keyword matches
2. Stage 2: only score wiki pages whose `source_relpath` matched in Stage 1
3. Combine tree score and wiki score

- [x] **Step 3: Run tests, commit**

Run: `uv run pytest tests/unit/storage/test_wiki_tree_search.py tests/ -k wiki -v`

```bash
git commit -m "feat(wiki): tree-assisted search with summary scan"
```

---

### Task 11: Multi-layer Fusion

**Files:**
- Modify: `src/hks/routing/router.py:14-18`
- Modify: `src/hks/routing/rules.py:17-24`
- Modify: `config/routing_rules.yaml`
- Test: `tests/unit/routing/test_fusion.py`

- [x] **Step 1: Write failing test**

```python
# tests/unit/routing/test_fusion.py
"""Test multi-layer routing fusion."""

from __future__ import annotations

from hks.routing.router import RouteDecision, route
from hks.routing.rules import RoutingRule, RoutingRuleSet


class TestMultiLayerFusion:
    def test_route_decision_has_secondary(self) -> None:
        rules = RoutingRuleSet(
            version=2,
            default_route="vector",
            rules=(
                RoutingRule(
                    id="graph-relation",
                    priority=1,
                    target_route="graph",
                    keywords_zh=("關係", "影響"),
                    keywords_en=("relation", "impact"),
                    secondary_route="wiki",
                ),
            ),
        )
        decision = route("What is the impact?", rules)
        assert decision.route == "graph"
        assert decision.secondary == "wiki"
```

- [x] **Step 2: Add `secondary` to RouteDecision and RoutingRule**

In `router.py`:
```python
@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: Route
    steps: list[TraceStep]
    matched_rule_id: str | None = None
    secondary: Route | None = None  # new
```

In `rules.py`:
```python
@dataclass(frozen=True, slots=True)
class RoutingRule:
    id: str
    priority: int
    target_route: Route
    keywords_zh: tuple[str, ...]
    keywords_en: tuple[str, ...]
    secondary_route: Route | None = None  # new
```

- [x] **Step 3: Update routing_rules.yaml**

Add `secondary` to relevant rules, e.g. graph rules get `secondary: wiki`.

- [x] **Step 4: Update query command to use secondary fallback**

In `src/hks/commands/query.py`, when primary route misses, try `decision.secondary` before falling back to vector.

- [x] **Step 5: Run tests, commit**

```bash
git commit -m "feat(routing): multi-layer fusion with primary + secondary route"
```

---

### Task 12: Vector Hit Section Context

**Files:**
- Modify: `src/hks/commands/query.py`
- Test: `tests/integration/test_query_section_path.py`

- [x] **Step 1: Write failing test**

Test that query response includes `section_path` and `page_range` when vector chunks have `tree_node_id`.

- [x] **Step 2: Implement section_path in query response**

In `query.py`, after vector retrieval returns chunks with `tree_node_id` metadata:
1. Load the PageTree for each source
2. Call `tree.section_path(node_id)` to build the path
3. Read `page_start`/`page_end` from node metadata
4. Add to response trace detail

- [x] **Step 3: Run tests, commit**

```bash
git commit -m "feat(query): add section_path and page_range to vector hit responses"
```

---

## Phase 3: Graph Extraction Enhancement

### Task 13: Tree-aware Graph Extraction

**Files:**
- Modify: `src/hks/graph/extract.py:31-127`
- Modify: `src/hks/ingest/pipeline.py:440-445`
- Test: `tests/unit/graph/test_tree_aware_extract.py`

- [x] **Step 1: Write failing test**

```python
# tests/unit/graph/test_tree_aware_extract.py
"""Test tree-aware graph extraction."""

from __future__ import annotations

from hks.graph.extract import extract_document_graph
from hks.page_tree.model import PageTree, TreeNode


class TestTreeAwareExtraction:
    def test_tree_nodes_become_entities(self) -> None:
        tree = PageTree(
            source_relpath="doc.md", source_format="md", doc_title="Doc",
            root_nodes=[
                TreeNode(
                    node_id="n1", title="Project Atlas", level=1,
                    start_offset=0, end_offset=100, children=[],
                ),
            ],
            build_method="rule", built_at="2026-05-19T00:00:00Z",
            total_nodes=1, source_sha256="x",
        )
        result = extract_document_graph(
            relpath="doc.md", title="Doc",
            body="Project Atlas impacts System B. Atlas depends on System C.",
            wiki_slug="doc",
            page_tree=tree,
        )
        node_ids = [n.id for n in result.nodes]
        assert any("project-atlas" in nid.lower() or "atlas" in nid.lower() for nid in node_ids)
        # Section node should appear as belongs_to edge
        edge_types = [e.relation for e in result.edges]
        assert "belongs_to" in edge_types or "references" in edge_types
```

- [x] **Step 2: Add `page_tree` parameter to extract_document_graph**

```python
def extract_document_graph(
    *,
    relpath: str,
    title: str,
    body: str,
    wiki_slug: str,
    page_tree: PageTree | None = None,  # new
) -> GraphDocumentArtifacts:
```

When `page_tree` is provided:
- Add each tree node as a `belongs_to` edge (section → document)
- Run regex extraction per-section (within `start_offset:end_offset`)
- Add section context to edge evidence

- [x] **Step 3: Pass page_tree in pipeline.py**

Update the `extract_document_graph()` call in pipeline.py to include `page_tree=page_tree`.

- [x] **Step 4: Run tests, commit**

```bash
git commit -m "feat(graph): tree-aware extraction with section entities"
```

---

### Task 14: New Relation Types + Entity Heuristics

**Files:**
- Modify: `src/hks/graph/extract.py`
- Test: `tests/unit/graph/test_new_relations.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/graph/test_new_relations.py
"""Test new relation types: causes, contradicts, succeeds."""

from __future__ import annotations

from hks.graph.extract import extract_document_graph


class TestNewRelationTypes:
    def test_causes_relation(self) -> None:
        result = extract_document_graph(
            relpath="t.md", title="T",
            body="供應鏈中斷導致出貨延遲。Supply chain disruption causes shipping delay.",
            wiki_slug="t",
        )
        relation_types = {e.relation for e in result.edges}
        assert "causes" in relation_types

    def test_contradicts_relation(self) -> None:
        result = extract_document_graph(
            relpath="t.md", title="T",
            body="報告指出成長，但實際數據與預期矛盾。The report shows growth however actual data contradicts projections.",
            wiki_slug="t",
        )
        relation_types = {e.relation for e in result.edges}
        assert "contradicts" in relation_types

    def test_succeeds_relation(self) -> None:
        result = extract_document_graph(
            relpath="t.md", title="T",
            body="Phase 1 之後接續 Phase 2。Phase 1 followed by Phase 2.",
            wiki_slug="t",
        )
        relation_types = {e.relation for e in result.edges}
        assert "succeeds" in relation_types
```

- [ ] **Step 2: Add new regex patterns**

Add bilingual patterns for `causes`, `contradicts`, `succeeds` following the existing pattern structure in `extract.py`.

- [ ] **Step 3: Add entity type contextual heuristics**

After regex extraction:
- Entity in tree node title → bias toward `Project`/`Document`
- Entity as `causes`/`impacts` subject → bias toward `Event`
- Entity with multiple `depends_on` inbound → bias toward `System`/`Concept`

- [ ] **Step 4: Run tests, commit**

```bash
git commit -m "feat(graph): add causes/contradicts/succeeds relations + entity heuristics"
```

---

## Phase 4: Test Coverage

### Task 15: Close Existing Test Gaps

**Files:**
- Create: `tests/unit/commands/test_command_dispatch.py`
- Create: `tests/unit/graph/test_extract_edge_cases.py`
- Create: PDF test fixtures (programmatic)

- [ ] **Step 1: Write commands/ dispatch tests**

Test that CLI commands parse arguments correctly and call the right `run()` functions. Use Typer's `CliRunner` to test each command without side effects.

- [ ] **Step 2: Write graph/extract.py edge case tests**

Test regex extraction edge cases:
- Comma-separated targets: "A impacts B, C, and D"
- Nested entity names: "Project Atlas Phase 2"
- Empty body
- Body with only Chinese text
- Body with only English text

- [ ] **Step 3: Create PDF fixture generation**

Write a `conftest.py` helper that generates the three PDF fixtures programmatically using PyMuPDF (as shown in Task 5's test helpers). These are reusable across all PDF tests.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: all PASS, coverage ≥ 80%

- [ ] **Step 5: Run type checking and linting**

```bash
uv run mypy src/hks/
uv run ruff check src/hks/
```
Expected: clean

- [ ] **Step 6: Final commit**

```bash
git commit -m "test: close coverage gaps for commands, graph edge cases, PDF fixtures"
```

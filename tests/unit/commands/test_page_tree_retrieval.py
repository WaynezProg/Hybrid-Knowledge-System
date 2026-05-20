"""Unit tests for page_tree candidate collector and evidence generation."""

from __future__ import annotations

from unittest.mock import MagicMock

from hks.commands.query import (
    Candidate,
    _candidate_evidence,
    _collect_page_tree_candidates,
    _page_tree_node_score,
)
from hks.page_tree.model import PageTree, TreeNode


def _make_node(
    *,
    node_id: str = "n1",
    title: str = "Section Title",
    summary: str = "",
    level: int = 1,
) -> TreeNode:
    return TreeNode(
        node_id=node_id,
        title=title,
        level=level,
        start_offset=0,
        end_offset=100,
        children=[],
        summary=summary,
    )


def _make_tree(
    nodes: list[TreeNode],
    *,
    source_relpath: str = "doc.md",
) -> PageTree:
    return PageTree(
        source_relpath=source_relpath,
        source_format="md",
        doc_title="Doc",
        root_nodes=nodes,
        build_method="test",
        built_at="2025-01-01T00:00:00Z",
        total_nodes=len(nodes),
        source_sha256="abc123",
    )


class TestPageTreeNodeScore:
    def test_title_match_scores_positive(self) -> None:
        node = _make_node(title="Atlas Project Overview")
        score = _page_tree_node_score("Atlas overview", node)
        assert score > 0

    def test_summary_match_adds_to_score(self) -> None:
        node_title_only = _make_node(title="Atlas", summary="")
        node_with_summary = _make_node(
            title="Atlas", summary="Project Atlas risk analysis and timeline"
        )
        score_title = _page_tree_node_score("Atlas risk", node_title_only)
        score_both = _page_tree_node_score("Atlas risk", node_with_summary)
        assert score_both > score_title

    def test_no_match_returns_zero(self) -> None:
        node = _make_node(title="Billing API", summary="Payment processing")
        score = _page_tree_node_score("Atlas overview", node)
        assert score == 0.0

    def test_empty_question_returns_zero(self) -> None:
        node = _make_node(title="Atlas", summary="Atlas summary")
        score = _page_tree_node_score("", node)
        assert score == 0.0

    def test_chinese_terms_match(self) -> None:
        node = _make_node(title="風險登記", summary="專案風險評估")
        score = _page_tree_node_score("風險評估", node)
        assert score > 0


class TestCollectPageTreeCandidates:
    def _mock_manifest_and_store(
        self, trees: dict[str, PageTree]
    ) -> tuple[MagicMock, MagicMock]:
        """Create mock manifest+tree_store that serve the given trees."""
        manifest = MagicMock()
        entries = {}
        for slug, tree in trees.items():
            entry = MagicMock()
            entry.derived.page_tree = slug
            entries[tree.source_relpath] = entry
        manifest.entries = entries

        tree_store = MagicMock()
        tree_store.load.side_effect = lambda s: trees[s]
        return manifest, tree_store

    def test_returns_candidates_with_summary(self) -> None:
        node = _make_node(
            node_id="n1",
            title="Risk Register",
            summary="Atlas has two main risks: supplier delay and test data anonymization.",
        )
        tree = _make_tree([node], source_relpath="risk.md")
        manifest, tree_store = self._mock_manifest_and_store({"risk-tree": tree})

        candidates, steps = _collect_page_tree_candidates(
            "Atlas risk",
            tree_store=tree_store,
            manifest=manifest,
        )

        assert len(candidates) == 1
        assert candidates[0].source_route == "page_tree"
        assert "risk" in candidates[0].text.lower()
        assert candidates[0].metadata["source_relpath"] == "risk.md"

    def test_skips_nodes_without_summary(self) -> None:
        """Nodes without LLM-enriched summary should not produce candidates."""
        node = _make_node(node_id="n1", title="project atlas", summary="")
        tree = _make_tree([node], source_relpath="atlas.txt")
        manifest, tree_store = self._mock_manifest_and_store({"atlas-tree": tree})

        candidates, steps = _collect_page_tree_candidates(
            "Atlas",
            tree_store=tree_store,
            manifest=manifest,
        )

        assert len(candidates) == 0

    def test_skips_nodes_with_zero_score(self) -> None:
        node = _make_node(
            node_id="n1",
            title="Billing API",
            summary="Payment processing module for e-commerce",
        )
        tree = _make_tree([node], source_relpath="billing.md")
        manifest, tree_store = self._mock_manifest_and_store({"billing-tree": tree})

        candidates, steps = _collect_page_tree_candidates(
            "Atlas risk",
            tree_store=tree_store,
            manifest=manifest,
        )

        assert len(candidates) == 0

    def test_caps_at_five_candidates(self) -> None:
        nodes = [
            _make_node(
                node_id=f"n{i}",
                title=f"Atlas Section {i}",
                summary=f"Atlas project section {i} details and analysis.",
                level=i,
            )
            for i in range(10)
        ]
        tree = _make_tree(nodes, source_relpath="big-doc.md")
        manifest, tree_store = self._mock_manifest_and_store({"big-tree": tree})

        candidates, steps = _collect_page_tree_candidates(
            "Atlas section",
            tree_store=tree_store,
            manifest=manifest,
        )

        assert len(candidates) <= 5

    def test_score_normalized_and_capped(self) -> None:
        node = _make_node(
            node_id="n1",
            title="Atlas",
            summary="Atlas project overview summary Atlas Atlas Atlas",
        )
        tree = _make_tree([node], source_relpath="atlas.md")
        manifest, tree_store = self._mock_manifest_and_store({"atlas-tree": tree})

        candidates, _ = _collect_page_tree_candidates(
            "Atlas summary overview",
            tree_store=tree_store,
            manifest=manifest,
        )

        assert len(candidates) == 1
        assert 0 < candidates[0].score <= 0.85

    def test_trace_step_always_present(self) -> None:
        manifest = MagicMock()
        manifest.entries = {}
        tree_store = MagicMock()

        candidates, steps = _collect_page_tree_candidates(
            "anything",
            tree_store=tree_store,
            manifest=manifest,
        )

        assert len(steps) == 1
        assert steps[0].kind == "page_tree_lookup"
        assert steps[0].detail["hit"] is False
        assert steps[0].detail["candidate_count"] == 0

    def test_gracefully_handles_tree_load_failure(self) -> None:
        manifest = MagicMock()
        entry = MagicMock()
        entry.derived.page_tree = "broken-tree"
        manifest.entries = {"broken.md": entry}

        tree_store = MagicMock()
        tree_store.load.side_effect = FileNotFoundError("missing")

        candidates, steps = _collect_page_tree_candidates(
            "Atlas",
            tree_store=tree_store,
            manifest=manifest,
        )

        assert len(candidates) == 0
        assert steps[0].detail["hit"] is False


class TestPageTreeCandidateEvidence:
    def test_evidence_includes_relpath_and_section(self) -> None:
        candidate = Candidate(
            text="Atlas has two main risks.",
            source_route="page_tree",
            score=0.4,
            metadata={
                "source_relpath": "risk-register.md",
                "section_path": "Risk Register > Main Risks",
                "page_range": {"start": 1, "end": 3},
            },
        )

        evidence = _candidate_evidence(candidate)

        assert len(evidence) == 1
        assert evidence[0]["source_relpath"] == "risk-register.md"
        assert evidence[0]["route"] == "page_tree"
        assert evidence[0]["section_path"] == "Risk Register > Main Risks"
        assert evidence[0]["page_range"] == {"start": 1, "end": 3}

    def test_evidence_omits_missing_optional_fields(self) -> None:
        candidate = Candidate(
            text="Atlas project summary.",
            source_route="page_tree",
            score=0.3,
            metadata={"source_relpath": "atlas.md"},
        )

        evidence = _candidate_evidence(candidate)

        assert len(evidence) == 1
        assert "section_path" not in evidence[0]
        assert "page_range" not in evidence[0]

    def test_no_evidence_when_relpath_missing(self) -> None:
        candidate = Candidate(
            text="orphan node",
            source_route="page_tree",
            score=0.2,
            metadata={},
        )

        evidence = _candidate_evidence(candidate)

        assert evidence == []

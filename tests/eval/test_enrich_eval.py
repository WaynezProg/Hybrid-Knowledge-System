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

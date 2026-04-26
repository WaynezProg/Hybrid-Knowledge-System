from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hks.adapters import core
from hks.adapters.contracts import validate_graphify_graph, validate_graphify_run


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists():
        return ""
    for child in sorted(path.rglob("*")):
        if child.is_file():
            digest.update(child.relative_to(path).as_posix().encode("utf-8"))
            digest.update(child.read_bytes())
    return digest.hexdigest()


def _knowledge_snapshot(root: Path) -> dict[str, object]:
    return {
        "wiki": _tree_digest(root / "wiki"),
        "graph": (root / "graph" / "graph.json").read_bytes(),
        "vector": _tree_digest(root / "vector" / "db"),
        "manifest": (root / "manifest.json").read_bytes(),
        "llm": _tree_digest(root / "llm"),
    }


@pytest.mark.integration
def test_graphify_store_writes_valid_run_without_mutating_authoritative_layers(
    working_docs,
    tmp_ks_root,
) -> None:
    core.hks_ingest(path=str(working_docs))
    before = _knowledge_snapshot(tmp_ks_root)

    payload = core.hks_graphify_build(mode="store")

    detail = payload["trace"]["steps"][0]["detail"]
    run_path = Path(detail["artifacts"]["run_path"])
    assert run_path.exists()
    validate_graphify_graph(json.loads((run_path / "graphify.json").read_text(encoding="utf-8")))
    validate_graphify_run(json.loads((run_path / "manifest.json").read_text(encoding="utf-8")))
    assert (run_path / "graph.html").exists()
    assert (run_path / "GRAPH_REPORT.md").exists()
    assert (tmp_ks_root / "graphify" / "latest.json").exists()
    assert _knowledge_snapshot(tmp_ks_root) == before


@pytest.mark.integration
def test_graphify_store_reuses_existing_run(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    first = core.hks_graphify_build(mode="store")
    second = core.hks_graphify_build(mode="store")

    first_detail = first["trace"]["steps"][0]["detail"]
    second_detail = second["trace"]["steps"][0]["detail"]
    assert first_detail["artifacts"]["run_id"] == second_detail["artifacts"]["run_id"]
    assert second_detail["idempotent_reuse"] is True


@pytest.mark.integration
def test_graphify_store_can_disable_html(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    payload = core.hks_graphify_build(mode="store", include_html=False)

    detail = payload["trace"]["steps"][0]["detail"]
    run_path = Path(detail["artifacts"]["run_path"])
    assert detail["artifacts"]["html"] is None
    assert not (run_path / "graph.html").exists()
    assert (run_path / "GRAPH_REPORT.md").exists()

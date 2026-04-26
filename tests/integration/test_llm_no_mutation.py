from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hks.adapters import core


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists():
        return ""
    for child in sorted(path.rglob("*")):
        if child.is_file():
            digest.update(child.relative_to(path).as_posix().encode("utf-8"))
            digest.update(child.read_bytes())
    return digest.hexdigest()


@pytest.mark.integration
def test_llm_preview_does_not_mutate_knowledge_layers(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))
    before = {
        "wiki": _tree_digest(tmp_ks_root / "wiki"),
        "graph": (tmp_ks_root / "graph" / "graph.json").read_bytes(),
        "vector": _tree_digest(tmp_ks_root / "vector" / "db"),
        "manifest": (tmp_ks_root / "manifest.json").read_bytes(),
    }

    payload = core.hks_llm_classify(source_relpath="project-atlas.txt")

    assert payload["trace"]["steps"][0]["kind"] == "llm_extraction_summary"
    assert before == {
        "wiki": _tree_digest(tmp_ks_root / "wiki"),
        "graph": (tmp_ks_root / "graph" / "graph.json").read_bytes(),
        "vector": _tree_digest(tmp_ks_root / "vector" / "db"),
        "manifest": (tmp_ks_root / "manifest.json").read_bytes(),
    }

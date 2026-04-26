from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hks.adapters import core
from hks.adapters.contracts import validate_wiki_artifact


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
    }


@pytest.mark.integration
def test_wiki_synthesis_store_writes_valid_candidate_without_mutating_knowledge_layers(
    working_docs,
    tmp_ks_root,
) -> None:
    core.hks_ingest(path=str(working_docs))
    core.hks_llm_classify(source_relpath="project-atlas.txt", mode="store")
    before = _knowledge_snapshot(tmp_ks_root)

    payload = core.hks_wiki_synthesize(
        source_relpath="project-atlas.txt",
        target_slug="project-atlas-synthesis",
        mode="store",
    )

    artifact_ref = payload["trace"]["steps"][0]["detail"]["artifact"]
    artifact_path = Path(artifact_ref["artifact_path"])
    assert artifact_path.exists()
    validate_wiki_artifact(json.loads(artifact_path.read_text(encoding="utf-8")))
    assert _knowledge_snapshot(tmp_ks_root) == before


@pytest.mark.integration
def test_lint_detects_corrupt_wiki_synthesis_artifact(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))
    corrupt_dir = tmp_ks_root / "llm" / "wiki-candidates"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "bad.json").write_text("{", encoding="utf-8")

    payload = core.hks_lint()

    findings = payload["trace"]["steps"][0]["detail"]["findings"]
    assert any(finding["category"] == "wiki_candidate_artifact_corrupt" for finding in findings)

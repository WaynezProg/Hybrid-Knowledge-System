from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from hks.adapters import core
from hks.adapters.contracts import validate_llm_artifact


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
def test_llm_store_writes_valid_artifact_without_mutating_knowledge_layers(
    working_docs,
    tmp_ks_root,
) -> None:
    core.hks_ingest(path=str(working_docs))
    before = _knowledge_snapshot(tmp_ks_root)

    payload = core.hks_llm_classify(source_relpath="project-atlas.txt", mode="store")

    artifact_ref = payload["trace"]["steps"][0]["detail"]["artifact"]
    artifact_path = Path(artifact_ref["artifact_path"])
    assert artifact_path.exists()
    validate_llm_artifact(json.loads(artifact_path.read_text(encoding="utf-8")))
    assert _knowledge_snapshot(tmp_ks_root) == before


@pytest.mark.integration
def test_llm_store_reuses_existing_artifact(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    first = core.hks_llm_classify(source_relpath="project-atlas.txt", mode="store")
    second = core.hks_llm_classify(source_relpath="project-atlas.txt", mode="store")

    first_ref = first["trace"]["steps"][0]["detail"]["artifact"]
    second_ref = second["trace"]["steps"][0]["detail"]["artifact"]
    assert first_ref["artifact_id"] == second_ref["artifact_id"]
    assert second_ref["idempotent_reuse"] is True


@pytest.mark.integration
def test_llm_store_concurrent_calls_converge_to_one_artifact(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))

    def run_once() -> str:
        payload = core.hks_llm_classify(source_relpath="project-atlas.txt", mode="store")
        return str(payload["trace"]["steps"][0]["detail"]["artifact"]["artifact_id"])

    with ThreadPoolExecutor(max_workers=4) as executor:
        artifact_ids = list(executor.map(lambda _: run_once(), range(8)))

    assert len(set(artifact_ids)) == 1
    assert len(list((tmp_ks_root / "llm" / "extractions").glob("*.json"))) == 1


@pytest.mark.integration
def test_lint_detects_corrupt_llm_artifact(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))
    corrupt_dir = tmp_ks_root / "llm" / "extractions"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "bad.json").write_text("{", encoding="utf-8")

    payload = core.hks_lint()

    findings = payload["trace"]["steps"][0]["detail"]["findings"]
    assert any(finding["category"] == "llm_artifact_corrupt" for finding in findings)

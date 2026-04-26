from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hks.cli import app
from hks.core.schema import validate


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
        "watch": _tree_digest(root / "watch"),
    }


@pytest.mark.integration
def test_source_list_returns_manifest_entries_without_mutation(
    cli_runner,
    working_docs,
    tmp_ks_root,
) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0
    before = _knowledge_snapshot(tmp_ks_root)

    result = cli_runner.invoke(app, ["source", "list"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    validate(payload)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["source"] == []
    assert payload["trace"]["steps"][0]["kind"] == "catalog_summary"
    assert detail["command"] == "source.list"
    assert detail["total_count"] == len(detail["sources"])
    assert [entry["relpath"] for entry in detail["sources"]] == sorted(
        entry["relpath"] for entry in detail["sources"]
    )
    assert _knowledge_snapshot(tmp_ks_root) == before


@pytest.mark.integration
def test_source_list_filters_by_format_and_relpath(cli_runner, working_docs) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(
        app,
        ["source", "list", "--format", "md", "--relpath-query", "risk"],
    )

    assert result.exit_code == 0
    sources = json.loads(result.stdout)["trace"]["steps"][0]["detail"]["sources"]
    assert [source["relpath"] for source in sources] == ["risk-register.md"]
    assert sources[0]["format"] == "md"


@pytest.mark.integration
def test_source_show_returns_artifact_references(cli_runner, working_docs) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(app, ["source", "show", "project-atlas.txt"])

    assert result.exit_code == 0
    source = json.loads(result.stdout)["trace"]["steps"][0]["detail"]["source"]
    assert source["relpath"] == "project-atlas.txt"
    assert source["raw_source_path"].endswith("/raw_sources/project-atlas.txt")
    assert source["derived"]["wiki_pages"]
    assert source["derived_counts"]["vector_ids"] >= 1


@pytest.mark.integration
def test_source_show_unknown_relpath_returns_noinput(cli_runner, working_docs) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(app, ["source", "show", "missing.txt"])

    assert result.exit_code == 66
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][0]["detail"]["code"] == "SOURCE_NOT_FOUND"


@pytest.mark.integration
def test_source_list_missing_manifest_returns_noinput(cli_runner) -> None:
    result = cli_runner.invoke(app, ["source", "list"])

    assert result.exit_code == 66


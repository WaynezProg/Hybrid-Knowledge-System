"""Integration tests for ks pageindex CLI commands."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from hks.cli import app
from hks.core.manifest import load_manifest
from hks.core.paths import runtime_paths
from hks.core.schema import validate
from hks.errors import ExitCode, KSError
from hks.ingest.pipeline import ingest
from hks.page_tree.store import TreeStore


def _write_source(tmp_path: Path, name: str = "doc.md") -> Path:
    source = tmp_path / name
    source.write_text(
        "# Chapter\n\nContent.\n\n## Section\n\nMore detail.",
        encoding="utf-8",
    )
    return source


def _payload(response: Any) -> dict[str, Any]:
    payload = response.to_dict()
    validate(payload)
    return payload


def _tree_for(relpath: str) -> Any:
    paths = runtime_paths()
    entry = load_manifest(paths.manifest).entries[relpath]
    assert entry.derived.page_tree is not None
    return TreeStore(paths).load(entry.derived.page_tree)


@pytest.mark.integration
def test_run_show_returns_tree_detail(tmp_path: Path) -> None:
    ingest(_write_source(tmp_path))

    from hks.commands.pageindex import run_show

    payload = _payload(run_show(source_relpath="doc.md"))

    assert payload["confidence"] == 1.0
    assert payload["source"] == ["wiki"]
    assert payload["trace"]["steps"][0]["kind"] == "pageindex_summary"
    detail = payload["trace"]["steps"][0]["detail"]
    assert detail["found"] is True
    assert detail["tree"]["source_relpath"] == "doc.md"
    assert detail["tree"]["total_nodes"] >= 1


@pytest.mark.integration
def test_run_show_missing_source_returns_not_found_detail() -> None:
    from hks.commands.pageindex import run_show

    payload = _payload(run_show(source_relpath="missing.md"))

    assert payload["confidence"] == 0.0
    assert payload["source"] == []
    assert payload["trace"]["steps"][0]["detail"] == {
        "found": False,
        "source_relpath": "missing.md",
    }


@pytest.mark.integration
def test_run_enrich_preview_does_not_mutate_tree_build_method(tmp_path: Path) -> None:
    ingest(_write_source(tmp_path))

    from hks.commands.pageindex import run_enrich

    before = _tree_for("doc.md")
    payload = _payload(run_enrich(mode="preview", provider="fake"))
    after = _tree_for("doc.md")

    assert before.build_method == "rule"
    assert after.build_method == "rule"
    assert payload["trace"]["steps"][0]["detail"]["mode"] == "preview"
    assert payload["trace"]["steps"][0]["detail"]["enriched"] == 1


@pytest.mark.integration
def test_run_enrich_store_writes_llm_tree(tmp_path: Path) -> None:
    ingest(_write_source(tmp_path))

    from hks.commands.pageindex import run_enrich

    payload = _payload(run_enrich(source_relpath="doc.md", mode="store", provider="fake"))
    tree = _tree_for("doc.md")

    assert tree.build_method == "llm"
    assert payload["trace"]["steps"][0]["detail"]["mode"] == "store"
    assert payload["trace"]["steps"][0]["detail"]["enriched"] == 1


@pytest.mark.integration
def test_run_enrich_missing_target_counts_skipped(tmp_path: Path) -> None:
    ingest(_write_source(tmp_path))

    from hks.commands.pageindex import run_enrich

    payload = _payload(
        run_enrich(source_relpath="missing.md", mode="preview", provider="fake")
    )

    detail = payload["trace"]["steps"][0]["detail"]
    assert detail["enriched"] == 0
    assert detail["skipped"] == 1
    assert detail["targets"] == ["missing.md"]


@pytest.mark.integration
def test_run_enrich_invalid_mode_is_usage_error_without_mutation(tmp_path: Path) -> None:
    ingest(_write_source(tmp_path))

    from hks.commands.pageindex import run_enrich

    before = _tree_for("doc.md").to_dict()
    with pytest.raises(KSError) as exc_info:
        run_enrich(source_relpath="doc.md", mode="bogus", provider="fake")

    assert exc_info.value.exit_code == ExitCode.USAGE
    assert _tree_for("doc.md").to_dict() == before


@pytest.mark.integration
def test_cli_show_emits_schema_valid_json(cli_runner, tmp_path: Path) -> None:
    ingest(_write_source(tmp_path))

    result = cli_runner.invoke(app, ["pageindex", "show", "doc.md"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    validate(payload)
    assert payload["trace"]["steps"][0]["kind"] == "pageindex_summary"


@pytest.mark.integration
def test_subprocess_cli_show_emits_schema_valid_json(
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    source = _write_source(tmp_path)
    ingest(source)

    env = os.environ.copy()
    env["KS_ROOT"] = str(tmp_ks_root)
    env["HKS_EMBEDDING_MODEL"] = "simple"
    result = subprocess.run(
        ["uv", "run", "ks", "pageindex", "show", "doc.md"],
        check=False,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    validate(payload)
    assert payload["confidence"] == 1.0

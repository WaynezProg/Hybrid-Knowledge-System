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
        "graphify": _tree_digest(root / "graphify"),
    }


@pytest.mark.integration
def test_watch_scan_detects_stale_source_without_authoritative_mutation(
    cli_runner,
    tmp_path,
    tmp_ks_root,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "a.md"
    source.write_text("Alpha owns Atlas.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    before = _knowledge_snapshot(tmp_ks_root)
    source.write_text("Alpha owns Atlas. Atlas depends on Beta.\n", encoding="utf-8")

    result = cli_runner.invoke(app, ["watch", "scan", "--source-root", str(docs)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    validate(payload)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["source"] == []
    assert payload["trace"]["route"] == "wiki"
    assert payload["trace"]["steps"][0]["kind"] == "watch_summary"
    assert detail["source_counts"]["stale"] == 1
    assert detail["action_counts"]["planned"] == 1
    assert _knowledge_snapshot(tmp_ks_root) == before


@pytest.mark.integration
def test_watch_status_after_scan_reports_latest_plan(cli_runner, tmp_path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("Alpha owns Atlas.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    (docs / "a.md").write_text("Alpha owns Atlas v2.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["watch", "scan", "--source-root", str(docs)]).exit_code == 0

    result = cli_runner.invoke(app, ["watch", "status"])

    assert result.exit_code == 0
    detail = json.loads(result.stdout)["trace"]["steps"][0]["detail"]
    assert detail["operation"] == "status"
    assert detail["plan_id"].startswith("plan-")


@pytest.mark.integration
def test_watch_scan_raw_sources_fallback(cli_runner, working_docs) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(app, ["watch", "scan"])

    assert result.exit_code == 0
    detail = json.loads(result.stdout)["trace"]["steps"][0]["detail"]
    assert detail["source_counts"]["unchanged"] > 0

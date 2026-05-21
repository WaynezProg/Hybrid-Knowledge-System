from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from hks.cli import app
from hks.core.manifest import load_manifest
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


def _authoritative_snapshot(root: Path) -> dict[str, bytes | str]:
    return {
        "wiki": _tree_digest(root / "wiki"),
        "vector": _tree_digest(root / "vector" / "db"),
        "manifest": (root / "manifest.json").read_bytes(),
    }


def _payload(result: Any) -> dict[str, Any]:
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    validate(payload)
    return payload


@pytest.mark.integration
def test_update_help_describes_daily_workflow(cli_runner) -> None:
    result = cli_runner.invoke(app, ["update", "--help"])

    assert result.exit_code == 0
    assert "每天變動的文件知識庫" in result.stdout
    assert "manifest" in result.stdout
    assert "fingerprint" in result.stdout
    assert "先看會改什麼" in result.stdout
    assert "missing source" in result.stdout


@pytest.mark.integration
def test_update_dry_run_writes_plan_without_authoritative_mutation(
    cli_runner,
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "a.md"
    source.write_text("Alpha owns Atlas.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    before = _authoritative_snapshot(tmp_ks_root)
    source.write_text("Alpha owns Atlas v2.\n", encoding="utf-8")

    result = cli_runner.invoke(app, ["update", str(docs), "--dry-run"])

    payload = _payload(result)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["trace"]["steps"][0]["kind"] == "update_summary"
    assert detail["operation"] == "update"
    assert detail["mode"] == "dry-run"
    assert detail["profile"] == "ingest-only"
    assert detail["source_roots"] == [docs.resolve().as_posix()]
    assert detail["source_counts"]["stale"] == 1
    assert detail["action_counts"]["planned"] == 1
    assert detail["artifacts"]["plan"]
    assert Path(detail["artifacts"]["plan"]).exists()
    assert _authoritative_snapshot(tmp_ks_root) == before


@pytest.mark.integration
def test_update_execute_refreshes_modified_source_manifest_and_wiki(
    cli_runner,
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "a.md"
    source.write_text("# Alpha\n\nAlpha owns Atlas.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    before_sha = load_manifest(tmp_ks_root / "manifest.json").entries["a.md"].sha256
    source.write_text("# Alpha\n\nAlpha owns Atlas v2.\n", encoding="utf-8")

    result = cli_runner.invoke(app, ["update", str(docs)])

    payload = _payload(result)
    detail = payload["trace"]["steps"][0]["detail"]
    after = load_manifest(tmp_ks_root / "manifest.json")
    wiki_text = "\n".join(
        page.read_text(encoding="utf-8")
        for page in sorted((tmp_ks_root / "wiki" / "pages").glob("*.md"))
    )
    assert payload["answer"].startswith("update 完成")
    assert payload["source"] == ["wiki", "graph", "vector"]
    assert detail["source_counts"]["stale"] == 1
    assert detail["action_counts"]["completed"] == 1
    assert after.entries["a.md"].sha256 != before_sha
    assert "Atlas v2" in wiki_text


@pytest.mark.integration
def test_update_execute_ingests_new_source(
    cli_runner,
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("Alpha owns Atlas.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    (docs / "b.md").write_text("Beta depends on Atlas.\n", encoding="utf-8")

    result = cli_runner.invoke(app, ["update", str(docs)])

    detail = _payload(result)["trace"]["steps"][0]["detail"]
    manifest = load_manifest(tmp_ks_root / "manifest.json")
    assert detail["source_counts"]["new"] == 1
    assert detail["action_counts"]["completed"] == 1
    assert "b.md" in manifest.entries


@pytest.mark.integration
def test_update_missing_without_prune_preserves_existing_artifacts(
    cli_runner,
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "remove-me.md"
    source.write_text("# Remove Me\n\nContent.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    before = _authoritative_snapshot(tmp_ks_root)
    source.unlink()

    result = cli_runner.invoke(app, ["update", str(docs)])

    payload = _payload(result)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["source"] == []
    assert detail["source_counts"]["missing"] == 1
    assert detail["action_counts"]["planned"] == 0
    assert "remove-me.md" in load_manifest(tmp_ks_root / "manifest.json").entries
    assert _authoritative_snapshot(tmp_ks_root) == before


@pytest.mark.integration
def test_update_missing_with_prune_uses_existing_prune_behavior(
    cli_runner,
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "remove-me.md"
    source.write_text("# Remove Me\n\nContent.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    entry = load_manifest(tmp_ks_root / "manifest.json").entries["remove-me.md"]
    stale_pages = [
        tmp_ks_root / "wiki" / "pages" / f"{slug}.md"
        for slug in entry.derived.wiki_pages
    ]
    source.unlink()

    result = cli_runner.invoke(app, ["update", str(docs), "--prune"])

    detail = _payload(result)["trace"]["steps"][0]["detail"]
    assert detail["source_counts"]["missing"] == 1
    assert detail["action_counts"]["completed"] == 1
    assert "remove-me.md" not in load_manifest(tmp_ks_root / "manifest.json").entries
    assert all(not page.exists() for page in stale_pages)


@pytest.mark.integration
def test_update_derived_refresh_triggers_graphify_build_action(
    cli_runner,
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "a.md"
    source.write_text("Alpha owns Atlas.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    source.write_text("Alpha owns Atlas v2.\n", encoding="utf-8")

    result = cli_runner.invoke(app, ["update", str(docs), "--profile", "derived-refresh"])

    detail = _payload(result)["trace"]["steps"][0]["detail"]
    run_payload = json.loads(Path(detail["artifacts"]["run"]).read_text(encoding="utf-8"))
    assert detail["profile"] == "derived-refresh"
    assert detail["action_counts"]["completed"] == 2
    assert (tmp_ks_root / "graphify" / "latest.json").exists()
    assert any(
        action["kind"] == "graphify_build" and action["status"] == "completed"
        for action in run_payload["actions"]
    )

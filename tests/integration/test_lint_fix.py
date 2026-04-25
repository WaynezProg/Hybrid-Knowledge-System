from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from hks.cli import app
from hks.core.manifest import load_manifest, save_manifest
from hks.core.paths import runtime_paths
from hks.storage.vector import VectorChunk, VectorStore


def _ingest(cli_runner, working_docs) -> None:
    result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert result.exit_code == 0, result.stdout


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _lint(cli_runner, *args: str) -> dict[str, Any]:
    result = cli_runner.invoke(app, ["lint", *args])
    assert result.exit_code == 0, result.stdout
    return json.loads(result.stdout)


def _add_fixable_findings(tmp_ks_root: Path) -> None:
    paths = runtime_paths(tmp_ks_root)
    (paths.wiki_pages / "orphan-page.md").write_text(
        "---\n"
        "slug: orphan-page\n"
        "title: Orphan Page\n"
        "summary: Orphan Page\n"
        "source: raw_sources/project-atlas.txt\n"
        "origin: ingest\n"
        "updated_at: 2026-04-26T00:00:00+00:00\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    with paths.wiki.joinpath("index.md").open("a", encoding="utf-8") as handle:
        handle.write("- [Missing](pages/missing-page.md) — missing\n")
    VectorStore(paths).add_chunks(
        [
            VectorChunk(
                id="orphan-vector-id",
                text="orphan vector",
                metadata={"source_relpath": "project-atlas.txt", "chunk_idx": 99},
            )
        ]
    )
    graph_payload = json.loads(paths.graph_file.read_text(encoding="utf-8"))
    relpath = next(iter(load_manifest(paths.manifest).entries))
    graph_payload["edges"]["edge:lint-dangling"] = {
        "id": "edge:lint-dangling",
        "relation": "references",
        "source": "missing-node",
        "target": "also-missing",
        "source_relpath": relpath,
        "evidence": "broken",
    }
    paths.graph_file.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2))


@pytest.mark.integration
def test_lint_fix_dry_run_does_not_write(cli_runner, working_docs, tmp_ks_root: Path) -> None:
    _ingest(cli_runner, working_docs)
    _add_fixable_findings(tmp_ks_root)
    before = _tree_hash(tmp_ks_root)

    payload = _lint(cli_runner, "--fix")

    detail = payload["trace"]["steps"][0]["detail"]
    assert detail["fixes_planned"]
    assert detail["fixes_applied"] == []
    assert _tree_hash(tmp_ks_root) == before


@pytest.mark.integration
def test_lint_fix_apply_repairs_allowlisted_findings(
    cli_runner,
    working_docs,
    tmp_ks_root: Path,
) -> None:
    _ingest(cli_runner, working_docs)
    _add_fixable_findings(tmp_ks_root)

    payload = _lint(cli_runner, "--fix=apply")

    detail = payload["trace"]["steps"][0]["detail"]
    assert detail["fixes_applied"]
    categories = {finding["category"] for finding in detail["findings"]}
    assert "orphan_vector_chunk" not in categories
    assert "dead_link" not in categories
    assert "orphan_page" not in categories
    assert "lint_fix_applied" in (tmp_ks_root / "wiki" / "log.md").read_text(encoding="utf-8")


@pytest.mark.integration
def test_lint_fix_apply_keeps_manifest_truth_unknown(
    cli_runner,
    working_docs,
    tmp_ks_root: Path,
) -> None:
    _ingest(cli_runner, working_docs)
    paths = runtime_paths(tmp_ks_root)
    manifest = load_manifest(paths.manifest)
    next(iter(manifest.entries.values())).derived.wiki_pages.append("missing-page")
    save_manifest(manifest, paths.manifest)

    payload = _lint(cli_runner, "--fix=apply")

    detail = payload["trace"]["steps"][0]["detail"]
    assert any(finding["category"] == "manifest_wiki_mismatch" for finding in detail["findings"])
    assert any(skip["reason"] == "manifest_truth_unknown" for skip in detail["fixes_skipped"])

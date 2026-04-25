from __future__ import annotations

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


def _lint(cli_runner, *args: str) -> dict[str, Any]:
    result = cli_runner.invoke(app, ["lint", *args])
    assert result.exit_code == 0, result.stdout
    return json.loads(result.stdout)


def _findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload["trace"]["steps"][0]["detail"]["findings"]  # type: ignore[no-any-return]


@pytest.mark.integration
def test_lint_clean_runtime_has_no_findings(cli_runner, working_docs) -> None:
    _ingest(cli_runner, working_docs)

    payload = _lint(cli_runner)

    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["answer"] == "lint 完成：0 issues"
    assert detail["findings"] == []
    assert detail["severity_counts"] == {"error": 0, "warning": 0, "info": 0}


@pytest.mark.integration
def test_lint_reports_all_core_categories(cli_runner, working_docs, tmp_ks_root: Path) -> None:
    _ingest(cli_runner, working_docs)
    paths = runtime_paths(tmp_ks_root)

    orphan = paths.wiki_pages / "orphan-page.md"
    orphan.write_text(
        "---\n"
        "slug: orphan-page\n"
        "title: Orphan Page\n"
        "summary: Orphan Page\n"
        "source: raw_sources/orphan.md\n"
        "origin: ingest\n"
        "updated_at: 2026-04-26T00:00:00+00:00\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    with paths.wiki.joinpath("index.md").open("a", encoding="utf-8") as handle:
        handle.write("- [Missing](pages/missing-page.md) — missing\n")
        handle.write("- [Duplicate](pages/missing-page.md) — duplicate\n")

    manifest = load_manifest(paths.manifest)
    relpath, entry = next(iter(manifest.entries.items()))
    entry.derived.wiki_pages.append("missing-manifest-page")
    entry.derived.vector_ids.append("missing-vector-id")
    entry.parser_fingerprint = "txt:v0:"
    missing_raw = paths.raw_sources / relpath
    missing_raw.unlink()
    (paths.raw_sources / "orphan-raw.txt").write_text("orphan", encoding="utf-8")
    save_manifest(manifest, paths.manifest)

    VectorStore(paths).add_chunks(
        [
            VectorChunk(
                id="orphan-vector-id",
                text="orphan vector",
                metadata={"source_relpath": "orphan-raw.txt", "chunk_idx": 0},
            )
        ]
    )

    graph_payload = json.loads(paths.graph_file.read_text(encoding="utf-8"))
    graph_payload["edges"]["edge:lint-dangling"] = {
        "id": "edge:lint-dangling",
        "relation": "references",
        "source": "missing-node",
        "target": "also-missing",
        "source_relpath": relpath,
        "evidence": "broken",
    }
    paths.graph_file.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2))

    payload = _lint(cli_runner)
    by_category = {finding["category"]: finding for finding in _findings(payload)}

    assert by_category["orphan_page"]["severity"] == "warning"
    assert by_category["dead_link"]["severity"] == "warning"
    assert by_category["duplicate_slug"]["severity"] == "warning"
    assert by_category["manifest_wiki_mismatch"]["severity"] == "error"
    assert by_category["wiki_source_mismatch"]["severity"] == "error"
    assert by_category["dangling_manifest_entry"]["severity"] == "error"
    assert by_category["orphan_raw_source"]["severity"] == "warning"
    assert by_category["manifest_vector_mismatch"]["severity"] == "error"
    assert by_category["orphan_vector_chunk"]["severity"] == "warning"
    assert by_category["graph_drift"]["severity"] == "error"
    assert by_category["fingerprint_drift"]["severity"] == "info"


@pytest.mark.integration
def test_lint_graph_corruption_returns_general(cli_runner, working_docs, tmp_ks_root: Path) -> None:
    _ingest(cli_runner, working_docs)
    runtime_paths(tmp_ks_root).graph_file.write_text("{not json", encoding="utf-8")

    result = cli_runner.invoke(app, ["lint"])

    assert result.exit_code == 1
    assert result.stderr.splitlines()[0].startswith("[ks:lint] error:")
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][0]["kind"] == "error"

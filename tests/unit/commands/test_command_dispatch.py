"""Unit tests for CLI command dispatch wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from hks.cli import app
from hks.commands import ingest as ingest_command
from hks.commands import pageindex as pageindex_command
from hks.commands import query as query_command
from hks.commands import source as source_command
from hks.core.schema import QueryResponse, Trace, TraceStep


def _response(answer: str = "ok") -> QueryResponse:
    return QueryResponse(
        answer=answer,
        source=[],
        confidence=1.0,
        trace=Trace(route="wiki", steps=[TraceStep(kind="catalog_summary", detail={})]),
    )


def _stdout_json(result: Any) -> dict[str, Any]:
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def test_ingest_dispatches_path_and_flags(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(path: Path, *, prune: bool = False, pptx_notes: bool = True) -> QueryResponse:
        calls.append({"path": path, "prune": prune, "pptx_notes": pptx_notes})
        return _response("ingested")

    monkeypatch.setattr(ingest_command, "run", fake_run)

    source = tmp_path / "docs"
    result = cli_runner.invoke(
        app,
        ["ingest", str(source), "--prune", "--pptx-notes", "exclude"],
    )

    assert _stdout_json(result)["answer"] == "ingested"
    assert calls == [{"path": source, "prune": True, "pptx_notes": False}]


def test_query_dispatches_question_and_writeback(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(question: str, *, writeback: str = "auto") -> QueryResponse:
        calls.append({"question": question, "writeback": writeback})
        return _response("answered")

    monkeypatch.setattr(query_command, "run", fake_run)

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback", "no"])

    assert _stdout_json(result)["answer"] == "answered"
    assert calls == [{"question": "summary Atlas", "writeback": "no"}]


def test_pageindex_enrich_dispatches_options(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_enrich(
        *,
        source_relpath: str | None = None,
        mode: str = "preview",
        provider: str = "fake",
        model: str | None = None,
        force: bool = False,
    ) -> QueryResponse:
        calls.append(
            {
                "source_relpath": source_relpath,
                "mode": mode,
                "provider": provider,
                "model": model,
                "force": force,
            }
        )
        return _response("enriched")

    monkeypatch.setattr(pageindex_command, "run_enrich", fake_run_enrich)

    result = cli_runner.invoke(
        app,
        [
            "pageindex",
            "enrich",
            "--source-relpath",
            "doc.pdf",
            "--mode",
            "store",
            "--provider",
            "fake",
            "--model",
            "m1",
            "--force",
        ],
    )

    assert _stdout_json(result)["answer"] == "enriched"
    assert calls == [
        {
            "source_relpath": "doc.pdf",
            "mode": "store",
            "provider": "fake",
            "model": "m1",
            "force": True,
        }
    ]


def test_source_list_dispatches_filters(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_list(
        *,
        ks_root: Path | None = None,
        format: str | None = None,
        relpath_query: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> QueryResponse:
        calls.append(
            {
                "ks_root": ks_root,
                "format": format,
                "relpath_query": relpath_query,
                "limit": limit,
                "offset": offset,
            }
        )
        return _response("listed")

    monkeypatch.setattr(source_command, "run_list", fake_run_list)
    ks_root = tmp_path / "ks"

    result = cli_runner.invoke(
        app,
        [
            "source",
            "list",
            "--ks-root",
            str(ks_root),
            "--format",
            "pdf",
            "--relpath-query",
            "report",
            "--limit",
            "5",
            "--offset",
            "2",
        ],
    )

    assert _stdout_json(result)["answer"] == "listed"
    assert calls == [
        {
            "ks_root": ks_root,
            "format": "pdf",
            "relpath_query": "report",
            "limit": 5,
            "offset": 2,
        }
    ]

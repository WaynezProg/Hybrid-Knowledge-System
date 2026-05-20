from __future__ import annotations

import pytest

from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.storage.wiki import WikiStore
from hks.writeback.writer import WritebackContext, commit


def _response() -> QueryResponse:
    return QueryResponse(
        answer="Atlas summary answer",
        source=["wiki"],
        confidence=1.0,
        trace=Trace(route="wiki", steps=[]),
    )


@pytest.mark.unit
@pytest.mark.us3
def test_writer_commit_persists_page_and_log(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    store = WikiStore(paths)

    steps = commit(query="Project A summary", response=_response(), wiki_store=store)

    assert steps == [
        TraceStep(
            kind="writeback",
            detail={
                "status": "committed",
                "slug": "project-a-summary",
                "path": "pages/project-a-summary.md",
                "related": [],
            },
        )
    ]
    page_path = paths.wiki_pages / "project-a-summary.md"
    assert page_path.exists()
    assert "Project A summary" in page_path.read_text(encoding="utf-8")
    assert "writeback" in paths.wiki.joinpath("log.md").read_text(encoding="utf-8")


@pytest.mark.unit
@pytest.mark.us3
def test_writer_commit_propagates_log_failure(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = runtime_paths(tmp_path / "ks")
    store = WikiStore(paths)

    def fail_append_log(*_args, **_kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(store, "append_log", fail_append_log)

    with pytest.raises(OSError, match="disk full"):
        commit(query="Project A summary", response=_response(), wiki_store=store)


@pytest.mark.unit
def test_writer_related_link_escapes_brackets_and_backslashes(tmp_path) -> None:
    """Related link text must escape [, ], and \\ for valid Markdown."""
    paths = runtime_paths(tmp_path / "ks")
    store = WikiStore(paths)

    store.write_page(
        title="Project [A]\\Beta",
        summary="summary",
        body="# Project [A]\\Beta\n\ncontent",
        source_relpath="project-ab.md",
        origin="ingest",
    )

    context = WritebackContext(related_slugs=["project-a-beta"])
    steps = commit(
        query="test query",
        response=_response(),
        context=context,
        wiki_store=store,
    )

    slug = steps[0].detail["slug"]
    page_text = (paths.wiki_pages / f"{slug}.md").read_text(encoding="utf-8")
    assert "- [Project \\[A\\]\\\\Beta](project-a-beta.md)" in page_text.splitlines()

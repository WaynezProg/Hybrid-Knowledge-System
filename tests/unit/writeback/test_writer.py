from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from hks.core.lock import file_lock
from hks.core.manifest import Manifest, ManifestEntry, compute_sha256, save_manifest, utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import ExitCode, KSError
from hks.storage.wiki import WikiStore
from hks.writeback import writer
from hks.writeback.queue import WritebackQueueItem, build_item
from hks.writeback.writer import promote


def _item(
    *,
    question: str = "Project A summary",
    answer: str = "Atlas summary answer",
    evidence: list[dict[str, object]] | None = None,
) -> WritebackQueueItem:
    return build_item(
        question=question,
        answer=answer,
        route="wiki",
        source=["wiki"],
        evidence=(
            evidence
            if evidence is not None
            else [
                {
                    "source_relpath": "atlas.txt",
                    "route": "wiki",
                    "quote": "Atlas source quote",
                }
            ]
        ),
        retrieval_score=0.9,
        writeback_eligible=True,
    )


def _seed_source(paths: RuntimePaths, relpath: str = "atlas.txt") -> None:
    raw_path = paths.raw_sources / relpath
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("Atlas source quote", encoding="utf-8")
    save_manifest(
        Manifest(
            entries={
                relpath: ManifestEntry(
                    relpath=relpath,
                    sha256=compute_sha256(raw_path),
                    format="txt",
                    size_bytes=raw_path.stat().st_size,
                    ingested_at=utc_now_iso(),
                )
            }
        ),
        paths.manifest,
    )


@pytest.mark.unit
@pytest.mark.us3
def test_promote_persists_evidence_backed_page_log_and_related_links(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    _seed_source(paths)
    store = WikiStore(paths)
    store.write_page(
        title="Project [A]\\Beta",
        summary="summary",
        body="# Project [A]\\Beta\n\ncontent",
        source_relpath="atlas.txt",
        origin="ingest",
    )

    steps = promote(item=_item(), wiki_store=store)

    assert steps[0].detail == {
        "status": "approved",
        "slug": "project-a-summary",
        "path": "pages/project-a-summary.md",
        "source_relpath": "atlas.txt",
        "related": ["project-a-beta"],
    }
    page = store.load_page("project-a-summary")
    assert page.title == "Project A summary"
    assert page.source_relpath == "atlas.txt"
    assert page.origin == "writeback"
    assert page.metadata["writeback_query"] == "Project A summary"
    assert page.body.splitlines() == [
        "# Project A summary",
        "",
        "Atlas summary answer",
        "",
        "## 來源依據",
        "",
        '- atlas.txt — "Atlas source quote"',
        "",
        "## Related",
        "",
        "- [Project \\[A\\]\\\\Beta](project-a-beta.md)",
    ]
    log_text = paths.wiki.joinpath("log.md").read_text(encoding="utf-8")
    assert "writeback | approved" in log_text
    assert "- query: Project A summary" in log_text
    assert "- pages touched: pages/project-a-summary.md" in log_text


@pytest.mark.unit
@pytest.mark.parametrize(
    "evidence",
    [
        [],
        [{"route": "wiki", "quote": "Atlas source quote"}],
        [{"route": "wiki", "source_relpath": "atlas.txt"}],
        [{"route": "wiki", "source_relpath": "<writeback>", "quote": "synthetic"}],
    ],
)
def test_promote_requires_real_source_evidence(tmp_path, evidence) -> None:
    store = WikiStore(runtime_paths(tmp_path / "ks"))

    with pytest.raises(KSError) as exc_info:
        promote(item=_item(evidence=evidence), wiki_store=store)

    assert exc_info.value.code == "WRITEBACK_EVIDENCE_REQUIRED"
    assert not list(store.paths.wiki_pages.glob("*.md"))


@pytest.mark.unit
def test_promote_conflicts_with_existing_ingest_page(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    _seed_source(paths)
    store = WikiStore(paths)
    store.write_page(
        title="Project A summary",
        summary="ingested",
        body="# Project A summary\n\noriginal",
        source_relpath="atlas.txt",
        origin="ingest",
    )

    with pytest.raises(KSError) as exc_info:
        promote(item=_item(), wiki_store=store)

    assert exc_info.value.code == "CONFLICT"
    assert store.load_page("project-a-summary").origin == "ingest"


@pytest.mark.unit
@pytest.mark.parametrize("origin", ["writeback", "llm_wiki"])
def test_promote_overwrites_existing_generated_page_same_slug(tmp_path, origin) -> None:
    paths = runtime_paths(tmp_path / "ks")
    _seed_source(paths)
    store = WikiStore(paths)
    store.write_page(
        title="Project A summary",
        summary="old",
        body="# Project A summary\n\nold",
        source_relpath="atlas.txt",
        origin=origin,
    )

    steps = promote(item=_item(), wiki_store=store)

    assert steps[0].detail["slug"] == "project-a-summary"
    page = store.load_page("project-a-summary")
    assert page.origin == "writeback"
    assert page.summary == "Atlas summary answer"
    assert "Atlas source quote" in page.body


@pytest.mark.unit
def test_promote_rejects_evidence_source_missing_from_manifest_and_raw_sources(tmp_path) -> None:
    store = WikiStore(runtime_paths(tmp_path / "ks"))

    with pytest.raises(KSError) as exc_info:
        promote(
            item=_item(
                evidence=[
                    {
                        "source_relpath": "does-not-exist.md",
                        "route": "wiki",
                        "quote": "Invented source quote",
                    }
                ]
            ),
            wiki_store=store,
        )

    assert exc_info.value.code == "WRITEBACK_EVIDENCE_REQUIRED"
    assert not list(store.paths.wiki_pages.glob("*.md"))


@pytest.mark.unit
def test_promote_acquires_the_shared_runtime_write_lock(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = runtime_paths(tmp_path / "ks")
    _seed_source(paths)
    acquired: list[object] = []

    @contextmanager
    def fake_file_lock(path: object) -> Iterator[None]:
        acquired.append(path)
        yield

    monkeypatch.setattr(writer, "file_lock", fake_file_lock)

    promote(item=_item(), wiki_store=WikiStore(paths))

    assert acquired == [paths.lock]


@pytest.mark.unit
def test_promote_is_refused_while_another_writer_holds_the_runtime_lock(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    _seed_source(paths)
    store = WikiStore(paths)

    with file_lock(paths.lock), pytest.raises(KSError) as exc_info:
        promote(item=_item(), wiki_store=store)

    assert exc_info.value.code == "LOCKED"
    assert exc_info.value.exit_code == ExitCode.GENERAL
    assert not (paths.wiki_pages / "project-a-summary.md").exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("# Atlas Migration The cutover is in March.", "Atlas Migration The cutover is in March."),
        ("#Risks The main risk is the exporter.", "Risks The main risk is the exporter."),
        ("## Plan\nStep one.\n### Detail\nStep two.", "Plan\nStep one.\nDetail\nStep two."),
        ("Plan\n====\nStep one.\nNotes\n-----\nStep two.", "Plan\nStep one.\nNotes\nStep two."),
        ("Issue #42 is fixed; see C# notes.", "Issue #42 is fixed; see C# notes."),
        ("Atlas: # Atlas The cutover is in March.", "Atlas: # Atlas The cutover is in March."),
    ],
)
def test_plain_answer_takes_heading_markers_off_and_keeps_the_wording(
    answer: str, expected: str
) -> None:
    assert writer.plain_answer(answer) == expected


@pytest.mark.unit
def test_promote_writes_a_single_h1_when_the_answer_is_a_raw_chunk(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    _seed_source(paths)
    store = WikiStore(paths)
    item = _item(
        question="Atlas migration plan",
        answer="# Atlas Migration\nThe Atlas cutover is in March.\n## Rollback\nNeeds approval.",
        evidence=[
            {
                "source_relpath": "atlas.txt",
                "route": "vector",
                "quote": "# Atlas Migration\n- The Atlas cutover is in March.",
            }
        ],
    )

    promote(item=item, wiki_store=store)

    page = store.load_page("atlas-migration-plan")
    headings = [line for line in page.body.splitlines() if line.startswith("#")]
    assert headings == ["# Atlas migration plan", "## 來源依據"]
    assert "Atlas Migration\nThe Atlas cutover is in March.\nRollback\nNeeds approval." in page.body
    assert page.summary == "Atlas Migration The Atlas cutover is in March. Rollback Needs approval."
    # 引文是單行，不會把來源清單斷開。
    assert '- atlas.txt — "# Atlas Migration - The Atlas cutover is in March."' in page.body


def _approved_page(store: WikiStore) -> None:
    promote(
        item=_item(question="Project A summary", answer="Atlas summary answer"),
        wiki_store=store,
    )


@pytest.mark.unit
def test_writeback_page_behind_recognises_evidence_read_from_a_writeback_page(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    _seed_source(paths)
    store = WikiStore(paths)
    store.write_page(
        title="Atlas",
        summary="Atlas source quote",
        body="# Atlas\n\nAtlas source quote",
        source_relpath="atlas.txt",
        origin="ingest",
    )
    _approved_page(store)

    def evidence(route: str, quote: str) -> dict[str, object]:
        return {"source_relpath": "atlas.txt", "route": route, "quote": quote}

    from_writeback = evidence("wiki", "Atlas summary answer")
    from_ingest = evidence("wiki", "Atlas source quote")
    from_vector = evidence("vector", "Atlas summary answer")

    behind = writer.writeback_page_behind(store, from_writeback)
    assert behind is not None and behind.slug == "project-a-summary"
    assert writer.writeback_page_behind(store, from_ingest) is None
    assert writer.writeback_page_behind(store, from_vector) is None


@pytest.mark.unit
def test_promote_refuses_an_item_whose_only_evidence_is_a_writeback_page_summary(
    tmp_path,
) -> None:
    paths = runtime_paths(tmp_path / "ks")
    _seed_source(paths)
    store = WikiStore(paths)
    _approved_page(store)
    derived = _item(
        question="What about Project A?",
        answer="Project A summary: Atlas summary answer",
        evidence=[
            {"source_relpath": "atlas.txt", "route": "wiki", "quote": "Atlas summary answer"}
        ],
    )

    with pytest.raises(KSError) as exc_info:
        promote(item=derived, wiki_store=store)

    assert exc_info.value.code == "WRITEBACK_EVIDENCE_REQUIRED"
    assert exc_info.value.details == ["evidence 只引用既有 writeback 頁的摘要，不是來源段落"]
    assert not (paths.wiki_pages / "what-about-project-a.md").exists()


@pytest.mark.unit
def test_promote_uses_the_real_source_evidence_and_drops_the_derived_one(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    _seed_source(paths)
    store = WikiStore(paths)
    _approved_page(store)
    mixed = _item(
        question="What about Project A?",
        answer="Atlas is active.",
        evidence=[
            {"source_relpath": "atlas.txt", "route": "wiki", "quote": "Atlas summary answer"},
            {"source_relpath": "atlas.txt", "route": "vector", "quote": "Atlas source quote"},
        ],
    )

    promote(item=mixed, wiki_store=store)

    body = store.load_page("what-about-project-a").body
    assert '- atlas.txt — "Atlas source quote"' in body
    assert '"Atlas summary answer"' not in body

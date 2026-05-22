from __future__ import annotations

import pytest

from hks.core.manifest import Manifest, ManifestEntry, compute_sha256, save_manifest, utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import KSError
from hks.storage.wiki import WikiStore
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

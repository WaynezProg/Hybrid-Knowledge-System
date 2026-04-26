from __future__ import annotations

from pathlib import Path

import pytest

from hks.core.paths import runtime_paths
from hks.storage.wiki import MAX_SLUG_CHARS, WikiStore


@pytest.mark.unit
def test_wiki_store_appends_numeric_suffix_for_collisions(tmp_ks_root: Path) -> None:
    store = WikiStore(runtime_paths(tmp_ks_root))

    first = store.write_page(
        title="Project A",
        summary="first",
        body="# Project A\n\nfirst",
        source_relpath="a.txt",
        origin="ingest",
    )
    second = store.write_page(
        title="Project A",
        summary="second",
        body="# Project A\n\nsecond",
        source_relpath="b.txt",
        origin="ingest",
    )

    assert first.slug == "project-a"
    assert second.slug == "project-a-2"


@pytest.mark.unit
def test_wiki_store_falls_back_when_slugify_is_empty(tmp_ks_root: Path) -> None:
    store = WikiStore(runtime_paths(tmp_ks_root))

    page = store.write_page(
        title="😀😀",
        summary="emoji",
        body="# Emoji\n\nemoji",
        source_relpath="emoji.txt",
        origin="ingest",
    )

    assert page.slug.startswith("untitled")


@pytest.mark.unit
def test_wiki_store_caps_very_long_slug(tmp_ks_root: Path) -> None:
    store = WikiStore(runtime_paths(tmp_ks_root))
    title = " ".join(["marp true theme default paginate true backgroundcolor ffffff"] * 20)

    page = store.write_page(
        title=title,
        summary="long",
        body=f"# {title}\n\nlong",
        source_relpath="long-title.md",
        origin="ingest",
    )

    assert len(page.slug) <= MAX_SLUG_CHARS
    assert (tmp_ks_root / "wiki" / "pages" / f"{page.slug}.md").exists()


@pytest.mark.unit
def test_wiki_store_caps_collision_suffix_for_long_slug(tmp_ks_root: Path) -> None:
    store = WikiStore(runtime_paths(tmp_ks_root))
    title = " ".join(["same very long heading"] * 30)

    first = store.write_page(
        title=title,
        summary="first",
        body=f"# {title}\n\nfirst",
        source_relpath="first.md",
        origin="ingest",
    )
    second = store.write_page(
        title=title,
        summary="second",
        body=f"# {title}\n\nsecond",
        source_relpath="second.md",
        origin="ingest",
    )

    assert len(first.slug) <= MAX_SLUG_CHARS
    assert len(second.slug) <= MAX_SLUG_CHARS
    assert second.slug.endswith("-2")


@pytest.mark.unit
def test_wiki_store_collapses_frontmatter_newlines(tmp_ks_root: Path) -> None:
    store = WikiStore(runtime_paths(tmp_ks_root))

    page = store.write_page(
        title="line one\nline two",
        summary="summary one\nsummary two",
        body="# Body\n\ncontent",
        source_relpath="frontmatter.md",
        origin="ingest",
    )

    loaded = store.load_page(page.slug)

    assert loaded.title == "line one line two"
    assert loaded.summary == "summary one summary two"

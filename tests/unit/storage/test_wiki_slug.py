from __future__ import annotations

from pathlib import Path

import pytest

from hks.core.paths import runtime_paths
from hks.storage.wiki import WikiStore


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

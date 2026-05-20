from __future__ import annotations

from pathlib import Path

import pytest
from ruamel.yaml import YAML

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


@pytest.mark.unit
def test_wiki_frontmatter_quotes_yaml_sensitive_values(tmp_ks_root: Path) -> None:
    store = WikiStore(runtime_paths(tmp_ks_root))

    page = store.write_page(
        title="Architecture: Summary",
        summary="Architecture summary: pricing API and deployment checklist.",
        body="# Architecture\n\ncontent",
        source_relpath="architecture-summary.md",
        origin="ingest",
        metadata={"note": "owner: platform team"},
    )

    text = (tmp_ks_root / "wiki" / "pages" / f"{page.slug}.md").read_text(
        encoding="utf-8"
    )
    frontmatter = text.split("---", 2)[1]
    parsed = YAML(typ="safe").load(frontmatter)
    loaded = store.load_page(page.slug)

    assert parsed["title"] == "Architecture: Summary"
    assert parsed["summary"] == "Architecture summary: pricing API and deployment checklist."
    assert parsed["note"] == "owner: platform team"
    assert loaded.title == "Architecture: Summary"
    assert loaded.summary == "Architecture summary: pricing API and deployment checklist."
    assert loaded.metadata["note"] == "owner: platform team"


@pytest.mark.unit
def test_wiki_index_uses_obsidian_readable_relative_links(tmp_ks_root: Path) -> None:
    store = WikiStore(runtime_paths(tmp_ks_root))

    store.write_page(
        title="Project A",
        summary="summary",
        body="# Project A\n\nsummary",
        source_relpath="project-a.md",
        origin="ingest",
    )

    index = (tmp_ks_root / "wiki" / "index.md").read_text(encoding="utf-8")

    assert "- [Project A](pages/project-a.md) — summary" in index


@pytest.mark.unit
def test_wiki_frontmatter_always_quotes_all_strings(tmp_ks_root: Path) -> None:
    """Every frontmatter scalar must be JSON-quoted to prevent YAML type coercion."""
    store = WikiStore(runtime_paths(tmp_ks_root))

    page = store.write_page(
        title="true",
        summary="false",
        body="# true\n\ncontent",
        source_relpath="tricky.md",
        origin="ingest",
        metadata={
            "nullable": "null",
            "date_like": "2026-05-20",
            "numeric": "123",
            "colon_val": "owner: platform team",
            "hash_val": "has # tag",
        },
    )

    text = (tmp_ks_root / "wiki" / "pages" / f"{page.slug}.md").read_text(
        encoding="utf-8"
    )
    frontmatter = text.split("---", 2)[1]
    parsed = YAML(typ="safe").load(frontmatter)

    # YAML must parse every value as str, not bool/null/date/int.
    assert parsed["title"] == "true"
    assert isinstance(parsed["title"], str)
    assert parsed["summary"] == "false"
    assert isinstance(parsed["summary"], str)
    assert parsed["nullable"] == "null"
    assert isinstance(parsed["nullable"], str)
    assert parsed["date_like"] == "2026-05-20"
    assert isinstance(parsed["date_like"], str)
    assert parsed["numeric"] == "123"
    assert isinstance(parsed["numeric"], str)
    assert parsed["colon_val"] == "owner: platform team"
    assert isinstance(parsed["colon_val"], str)
    assert parsed["hash_val"] == "has # tag"
    assert isinstance(parsed["hash_val"], str)
    assert parsed["origin"] == "ingest"
    assert isinstance(parsed["origin"], str)
    assert isinstance(parsed["updated_at"], str)

    # Roundtrip through load_page must preserve values.
    loaded = store.load_page(page.slug)
    assert loaded.title == "true"
    assert loaded.summary == "false"
    assert loaded.metadata["nullable"] == "null"
    assert loaded.metadata["date_like"] == "2026-05-20"
    assert loaded.metadata["numeric"] == "123"
    assert loaded.metadata["colon_val"] == "owner: platform team"
    assert loaded.metadata["hash_val"] == "has # tag"


@pytest.mark.unit
def test_wiki_frontmatter_backward_compatible_with_unquoted(
    tmp_ks_root: Path,
) -> None:
    """Old pages written without quotes must still load correctly."""
    store = WikiStore(runtime_paths(tmp_ks_root))
    store.ensure()

    legacy_md = (
        "---\n"
        "slug: legacy-page\n"
        "title: Legacy Title\n"
        "summary: Just a plain summary\n"
        "source: raw_sources/legacy.md\n"
        "origin: ingest\n"
        "updated_at: 2025-01-01T00:00:00Z\n"
        "---\n\n"
        "Legacy body.\n"
    )
    (tmp_ks_root / "wiki" / "pages" / "legacy-page.md").write_text(
        legacy_md, encoding="utf-8"
    )

    loaded = store.load_page("legacy-page")
    assert loaded.title == "Legacy Title"
    assert loaded.summary == "Just a plain summary"
    assert loaded.source_relpath == "legacy.md"
    assert loaded.origin == "ingest"


@pytest.mark.unit
def test_wiki_index_escapes_brackets_and_backslashes(tmp_ks_root: Path) -> None:
    """Index link text must escape [, ], and \\ to render valid Markdown links."""
    store = WikiStore(runtime_paths(tmp_ks_root))

    store.write_page(
        title="Project [A]\\Beta",
        summary="summary",
        body="# Project [A]\\Beta\n\ncontent",
        source_relpath="project-ab.md",
        origin="ingest",
    )

    index = (tmp_ks_root / "wiki" / "index.md").read_text(encoding="utf-8")

    assert "Project \\[A\\]\\\\Beta" in index
    assert "(pages/" in index

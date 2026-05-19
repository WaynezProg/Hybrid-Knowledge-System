"""Persistent storage for page trees."""

from __future__ import annotations

from pathlib import Path

from hks.core.manifest import atomic_write
from hks.core.paths import RuntimePaths
from hks.page_tree.model import PageTree
from hks.storage.wiki import WikiStore


class TreeStore:
    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self._dir = paths.page_trees

    def _ensure(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _slug_for(self, relpath: str) -> str:
        wiki_store = WikiStore(self.paths)
        relpath_without_suffix = Path(relpath).with_suffix("").as_posix()
        return wiki_store.slug_base(relpath_without_suffix)

    def _validate_slug(self, slug: str) -> None:
        if (
            slug in {"", ".", ".."}
            or "/" in slug
            or "\\" in slug
            or Path(slug).is_absolute()
        ):
            raise ValueError(f"invalid page tree slug: {slug!r}")

    def _path_for(self, slug: str) -> Path:
        self._validate_slug(slug)
        return self._dir / f"{slug}.json"

    def save(self, relpath: str, tree: PageTree) -> str:
        self._ensure()
        slug = self._slug_for(relpath)
        atomic_write(self._path_for(slug), tree.to_json())
        return slug

    def load(self, slug: str) -> PageTree:
        path = self._path_for(slug)
        if not path.exists():
            raise FileNotFoundError(f"page tree not found: {slug}")
        return PageTree.from_json(path.read_text(encoding="utf-8"))

    def delete(self, slug: str) -> None:
        path = self._path_for(slug)
        if path.exists():
            path.unlink()

    def exists(self, slug: str) -> bool:
        return self._path_for(slug).exists()

    def list_slugs(self) -> list[str]:
        self._ensure()
        return sorted(path.stem for path in self._dir.glob("*.json"))

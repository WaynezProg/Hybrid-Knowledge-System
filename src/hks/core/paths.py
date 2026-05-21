"""Runtime path helpers for the filesystem contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hks.core.config import config_value
from hks.core.runtime_context import current_ks_root


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    root: Path
    raw_sources: Path
    wiki: Path
    wiki_pages: Path
    page_trees: Path
    graph_dir: Path
    graph_file: Path
    vector_db: Path
    manifest: Path
    lock: Path


def resolve_ks_root(root: Path | str | None = None) -> Path:
    """Resolve the runtime root, defaulting to ./ks in the current workspace."""

    if root is not None:
        return Path(root).expanduser().resolve(strict=False)

    scoped_root = current_ks_root()
    if scoped_root is not None:
        return scoped_root

    env_root = config_value("KS_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve(strict=False)

    return (Path.cwd() / "ks").resolve(strict=False)


def assert_runtime_path_allowed(path: Path, *, ks_root: Path | str | None = None) -> Path:
    """Reject any path outside the supported /ks layout."""

    candidate = path.expanduser().resolve(strict=False)
    paths = runtime_paths(ks_root)
    if candidate == paths.root:
        return candidate
    allowed_dirs = (
        paths.raw_sources,
        paths.wiki,
        paths.wiki_pages,
        paths.page_trees,
        paths.graph_dir,
        paths.vector_db,
    )
    allowed_files = (paths.manifest, paths.lock, paths.graph_file)
    if candidate in allowed_files:
        return candidate
    if any(
        candidate == allowed_dir or allowed_dir in candidate.parents for allowed_dir in allowed_dirs
    ):
        return candidate
    raise AssertionError("Phase 1 runtime path is outside the allowed /ks layout")


def runtime_paths(root: Path | str | None = None) -> RuntimePaths:
    """Build the allowed runtime path set for the current process."""

    ks_root = resolve_ks_root(root)
    return RuntimePaths(
        root=ks_root,
        raw_sources=ks_root / "raw_sources",
        wiki=ks_root / "wiki",
        wiki_pages=ks_root / "wiki" / "pages",
        page_trees=ks_root / "page_trees",
        graph_dir=ks_root / "graph",
        graph_file=ks_root / "graph" / "graph.json",
        vector_db=ks_root / "vector" / "db",
        manifest=ks_root / "manifest.json",
        lock=ks_root / ".lock",
    )

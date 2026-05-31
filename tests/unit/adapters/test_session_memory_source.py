from __future__ import annotations

from pathlib import Path

import pytest

from hks.adapters.session_memory_source import (
    SessionMemorySourceError,
    assert_session_memory_tree,
    resolve_export_path,
)


def test_resolve_export_path_under_workspace(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    workspace_id = "hks"
    daily = export_root / workspace_id / "daily" / "2026-05-31.md"
    daily.parent.mkdir(parents=True)
    daily.write_text(
        "---\nsource_domain: session_memory\ngenerator: session2memory\n---\n# day\n",
        encoding="utf-8",
    )
    resolved = resolve_export_path(
        export_root=export_root,
        workspace_id=workspace_id,
        path="daily/2026-05-31.md",
    )
    assert resolved == daily.resolve()


def test_reject_path_outside_workspace(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    other = export_root / "other" / "x.md"
    other.parent.mkdir(parents=True)
    other.write_text("x", encoding="utf-8")
    with pytest.raises(SessionMemorySourceError) as exc:
        resolve_export_path(
            export_root=export_root,
            workspace_id="hks",
            path=str(other),
        )
    assert exc.value.code == "WORKSPACE_PATH_OUT_OF_ROOT"


def test_reject_non_session2memory_md(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    bad = export_root / "hks" / "raw.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("# no frontmatter\n", encoding="utf-8")
    with pytest.raises(SessionMemorySourceError) as exc:
        assert_session_memory_tree(
            root=bad.parent,
            workspace_id="hks",
        )
    assert exc.value.code == "INGEST_SOURCE_DISALLOWED"


def test_reject_workspace_id_mismatch(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    daily = export_root / "hks" / "daily" / "2026-05-31.md"
    daily.parent.mkdir(parents=True)
    daily.write_text(
        "---\nsource_domain: session_memory\n"
        "generator: session2memory\n"
        "workspace_id: other\n"
        "---\n# day\n",
        encoding="utf-8",
    )
    with pytest.raises(SessionMemorySourceError) as exc:
        assert_session_memory_tree(root=daily, workspace_id="hks")
    assert exc.value.code == "WORKSPACE_ID_MISMATCH"

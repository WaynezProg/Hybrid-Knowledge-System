from __future__ import annotations

from pathlib import Path

import pytest

from hks.adapters.workspace_id import slugify_workspace_id


@pytest.mark.parametrize(
    ("basename", "expected"),
    [
        ("hks", "hks"),
        ("My Project", "my-project"),
        ("foo__bar", "foo-bar"),
        ("!!!", "project"),
    ],
)
def test_slugify_workspace_id(basename: str, expected: str) -> None:
    assert slugify_workspace_id(basename) == expected


def test_slugify_workspace_id_collision_suffix() -> None:
    root = Path("/tmp/aaa/hks")
    slug = slugify_workspace_id("hks", project_root=root, reserved={})
    assert slug == "hks"
    other = Path("/tmp/bbb/hks")
    slug2 = slugify_workspace_id(
        "hks",
        project_root=other,
        reserved={"hks": root},
    )
    assert slug2.startswith("hks-")
    assert len(slug2) == len("hks-") + 8

"""Contract schemas and routing rules are found in a checkout and in a built wheel."""

from __future__ import annotations

from pathlib import Path

import pytest

from hks.core import resources
from hks.core.schema import contract_schema_path
from hks.routing.rules import default_rules_path


def test_a_checkout_reads_the_repository_files() -> None:
    root = resources.resource_root()

    assert (root / "specs").is_dir()
    assert contract_schema_path().is_file()
    assert default_rules_path().is_file()


def test_outside_a_checkout_the_packaged_copy_is_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # As installed from a wheel: site-packages/hks/core/resources.py, no specs/ above it.
    module = tmp_path / "lib" / "site-packages" / "hks" / "core" / "resources.py"
    module.parent.mkdir(parents=True)
    module.write_text("", encoding="utf-8")
    monkeypatch.setattr(resources, "__file__", str(module))
    monkeypatch.setattr(resources, "PACKAGED", module.parents[1] / "_resources")
    resources.resource_root.cache_clear()
    try:
        assert resources.resource_root() == module.parents[1] / "_resources"
    finally:
        resources.resource_root.cache_clear()

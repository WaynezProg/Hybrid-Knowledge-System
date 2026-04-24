from __future__ import annotations

from pathlib import Path

import pytest

from hks.errors import KSError
from hks.routing.rules import load_rules


@pytest.mark.unit
def test_load_rules_from_runtime_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ks_root = tmp_path / "ks"
    config_dir = ks_root / "config"
    config_dir.mkdir(parents=True)
    config_dir.joinpath("routing_rules.yaml").write_text(
        """
version: 1
default_route: wiki
rules:
  - id: summary
    priority: 1
    target_route: wiki
    phase2_note: false
    keywords:
      zh: [摘要]
      en: [summary]
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("KS_ROOT", str(ks_root))

    rules = load_rules()

    assert rules.default_route == "wiki"
    assert rules.rules[0].id == "summary"


@pytest.mark.unit
def test_load_rules_rejects_graph_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rules_path = tmp_path / "routing_rules.yaml"
    rules_path.write_text(
        """
version: 1
default_route: wiki
rules:
  - id: relation
    priority: 1
    target_route: graph
    phase2_note: false
    keywords:
      zh: [關係]
      en: [relation]
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("HKS_ROUTING_RULES", str(rules_path))

    with pytest.raises(KSError):
        load_rules()

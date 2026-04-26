from __future__ import annotations

from hks.graphify.audit import side_effect_finding


def test_graphify_side_effect_finding_reuses_008_code() -> None:
    finding = side_effect_finding("ignored")

    assert finding.code == "side_effect_text_ignored"

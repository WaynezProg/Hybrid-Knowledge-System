from __future__ import annotations

import pytest

from hks.adapters import core


@pytest.mark.integration
def test_lint_detects_partial_graphify_run(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))
    partial = tmp_ks_root / "graphify" / "runs" / "partial-run"
    partial.mkdir(parents=True)
    (partial / "graphify.json").write_text("{}", encoding="utf-8")

    payload = core.hks_lint()

    findings = payload["trace"]["steps"][0]["detail"]["findings"]
    assert any(finding["category"] == "graphify_partial_run" for finding in findings)

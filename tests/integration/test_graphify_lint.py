from __future__ import annotations

import json
import shutil
from pathlib import Path

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


def test_graphify_latest_survives_runtime_move(working_docs, tmp_ks_root, tmp_path) -> None:
    core.hks_ingest(path=str(working_docs))
    core.hks_graphify_build(mode="store")
    latest = json.loads((tmp_ks_root / "graphify/latest.json").read_text())
    assert not Path(latest["run_manifest_path"]).is_absolute()
    relocated = tmp_path / "relocated"
    shutil.move(str(tmp_ks_root), relocated)
    payload = core.hks_lint(ks_root=str(relocated))
    findings = payload["trace"]["steps"][0]["detail"]["findings"]
    assert not any(f["category"] == "graphify_latest_mismatch" for f in findings)


def test_legacy_absolute_graphify_pointer_is_supported(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))
    core.hks_graphify_build(mode="store")
    path = tmp_ks_root / "graphify/latest.json"
    latest = json.loads(path.read_text())
    latest["run_manifest_path"] = str(tmp_ks_root / latest["run_manifest_path"])
    path.write_text(json.dumps(latest))
    payload = core.hks_lint()
    findings = payload["trace"]["steps"][0]["detail"]["findings"]
    assert not any(f["category"] == "graphify_latest_mismatch" for f in findings)

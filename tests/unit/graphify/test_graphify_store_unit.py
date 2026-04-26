from __future__ import annotations

from hks.adapters import core


def test_graphify_store_writes_latest_pointer(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))

    core.hks_graphify_build(mode="store")

    latest = tmp_ks_root / "graphify" / "latest.json"
    assert latest.exists()
    assert "run_manifest_path" in latest.read_text(encoding="utf-8")

from __future__ import annotations

import json

from hks.core.paths import runtime_paths
from hks.watch.lineage import inspect_lineage
from hks.watch.models import WatchSource


def test_lineage_marks_llm_artifact_stale(tmp_ks_root) -> None:
    paths = runtime_paths(tmp_ks_root)
    artifact_dir = tmp_ks_root / "llm" / "extractions"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "a.json").write_text(
        json.dumps({"source_relpath": "a.md"}),
        encoding="utf-8",
    )

    counts, issues = inspect_lineage(
        paths=paths,
        sources=[WatchSource(relpath="a.md", state="stale")],
    )

    assert counts["llm_extraction_stale"] == 1
    assert issues[0].code == "llm_extraction_stale"

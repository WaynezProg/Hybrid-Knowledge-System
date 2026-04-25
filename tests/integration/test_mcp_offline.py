from __future__ import annotations

import pytest

from hks.adapters import core


@pytest.mark.integration
def test_adapter_core_ingest_query_lint_runs_with_simple_model(working_docs, monkeypatch) -> None:
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", "simple")

    ingest_payload = core.hks_ingest(path=str(working_docs), pptx_notes="include")
    query_payload = core.hks_query(question="Project Atlas summary")
    lint_payload = core.hks_lint()

    assert ingest_payload["trace"]["steps"][0]["kind"] == "ingest_summary"
    assert query_payload["source"] == ["wiki"]
    assert lint_payload["trace"]["steps"][0]["kind"] == "lint_summary"

from __future__ import annotations

import json

import pytest

from hks.adapters import core


@pytest.mark.integration
def test_lint_detects_partial_watch_run(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))
    runs = tmp_ks_root / "watch" / "runs"
    runs.mkdir(parents=True)
    (runs / "partial.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "partial",
                "created_at": "2026-04-26T00:00:00+00:00",
                "completed_at": None,
                "status": "partial",
                "plan_id": "plan-missing",
                "plan_fingerprint": "fingerprint",
                "mode": "execute",
                "profile": "ingest-only",
                "requested_by": None,
                "actions": [],
                "summary": {
                    "kind": "watch_summary",
                    "operation": "run",
                    "mode": "execute",
                    "profile": "ingest-only",
                    "plan_id": "plan-missing",
                    "run_id": "partial",
                    "plan_fingerprint": "fingerprint",
                    "source_counts": {
                        "unchanged": 0,
                        "stale": 0,
                        "new": 0,
                        "missing": 0,
                        "unsupported": 0,
                        "corrupt": 0,
                    },
                    "action_counts": {
                        "planned": 0,
                        "skipped": 0,
                        "running": 0,
                        "completed": 0,
                        "failed": 0,
                    },
                    "artifacts": {"plan": None, "run": None, "latest": None},
                    "idempotent_reuse": False,
                    "confidence": 1.0,
                },
            }
        ),
        encoding="utf-8",
    )

    payload = core.hks_lint()

    findings = payload["trace"]["steps"][0]["detail"]["findings"]
    assert any(finding["category"] == "watch_partial_run" for finding in findings)

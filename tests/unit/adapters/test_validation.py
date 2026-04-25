from __future__ import annotations

import pytest

from hks.adapters import core
from hks.adapters.models import AdapterToolError


@pytest.mark.parametrize(
    ("callable_", "kwargs", "field"),
    [
        (core.hks_query, {"question": "x", "writeback": "later"}, "writeback"),
        (core.hks_ingest, {"path": "/tmp/source", "pptx_notes": "all"}, "pptx_notes"),
        (core.hks_lint, {"severity_threshold": "fatal"}, "severity_threshold"),
        (core.hks_lint, {"fix": "force"}, "fix"),
    ],
)
def test_usage_validation_errors_return_adapter_tool_error(callable_, kwargs, field: str) -> None:
    with pytest.raises(AdapterToolError) as exc_info:
        callable_(**kwargs)

    envelope = exc_info.value.to_dict()
    assert envelope["error"]["code"] == "USAGE"
    assert envelope["error"]["exit_code"] == 2
    assert field in envelope["error"]["message"]


def test_ingest_path_can_point_outside_ks_without_exposing_runtime_read_api(tmp_path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# External source\n\nadapter should ingest this file\n", encoding="utf-8")

    payload = core.hks_ingest(path=str(source))

    assert payload["trace"]["steps"][0]["kind"] == "ingest_summary"

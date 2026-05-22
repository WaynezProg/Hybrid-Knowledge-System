"""Command-level smoke tests for query orchestration."""

from __future__ import annotations

from hks.commands.query import _build_no_hit_response


def test_build_no_hit_response_keeps_public_shape() -> None:
    response = _build_no_hit_response("wiki", [])

    assert response.answer == "未能於現有知識中找到答案"
    assert response.source == []
    assert response.confidence == 0.0
    assert response.trace.route == "wiki"

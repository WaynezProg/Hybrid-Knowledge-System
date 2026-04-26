from __future__ import annotations

import pytest

from hks.routing.router import route
from hks.routing.rules import RoutingRule, RoutingRuleSet


class _RecordingBackend:
    model_names: list[str] = []

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name
        self.model_names.append(str(model_name))

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(index + 1), 0.0] for index, _ in enumerate(texts)]


@pytest.mark.unit
def test_router_matches_summary_rule() -> None:
    rules = RoutingRuleSet(
        version=1,
        default_route="vector",
        rules=(
            RoutingRule(
                id="summary",
                priority=10,
                target_route="wiki",
                keywords_zh=("摘要",),
                keywords_en=("summary",),
            ),
        ),
    )

    decision = route("請給我摘要", rules)

    assert decision.route == "wiki"
    assert decision.matched_rule_id == "summary"
    assert decision.steps[0].kind == "routing_model"


@pytest.mark.unit
def test_router_uses_default_when_no_keyword_matches() -> None:
    rules = RoutingRuleSet(version=1, default_route="vector", rules=())

    decision = route("unmatched text", rules)

    assert decision.route == "vector"
    assert decision.matched_rule_id == "default"


@pytest.mark.unit
def test_router_uses_configured_routing_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hks.routing.router as router

    _RecordingBackend.model_names = []
    monkeypatch.setenv("HKS_ROUTING_MODEL", "openai:text-embedding-3-small")
    monkeypatch.setattr(router, "TextModelBackend", _RecordingBackend)
    rules = RoutingRuleSet(
        version=1,
        default_route="vector",
        rules=(
            RoutingRule(
                id="summary",
                priority=10,
                target_route="wiki",
                keywords_zh=("摘要",),
                keywords_en=("summary",),
            ),
        ),
    )

    decision = route("summary", rules)

    assert _RecordingBackend.model_names == ["openai:text-embedding-3-small"]
    assert decision.steps[0].detail["backend"] == "openai:text-embedding-3-small"

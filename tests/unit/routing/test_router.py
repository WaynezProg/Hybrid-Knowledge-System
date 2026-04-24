from __future__ import annotations

import pytest

from hks.routing.router import route
from hks.routing.rules import RoutingRule, RoutingRuleSet


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

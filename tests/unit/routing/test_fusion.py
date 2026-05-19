"""Test multi-layer routing fusion."""

from __future__ import annotations

import pytest

from hks.routing.router import route
from hks.routing.rules import RoutingRule, RoutingRuleSet


@pytest.mark.unit
class TestMultiLayerFusion:
    def test_route_decision_has_secondary(self) -> None:
        rules = RoutingRuleSet(
            version=2,
            default_route="vector",
            rules=(
                RoutingRule(
                    id="graph-relation",
                    priority=1,
                    target_route="graph",
                    keywords_zh=("關係", "影響"),
                    keywords_en=("relation", "impact"),
                    secondary_route="wiki",
                ),
            ),
        )

        decision = route("What is the impact?", rules)

        assert decision.route == "graph"
        assert decision.secondary == "wiki"

    def test_default_route_has_no_secondary(self) -> None:
        rules = RoutingRuleSet(version=2, default_route="vector", rules=())

        decision = route("unmatched text", rules)

        assert decision.route == "vector"
        assert decision.secondary is None

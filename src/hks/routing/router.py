"""Rule-based routing for Phase 1 query dispatch."""

from __future__ import annotations

from dataclasses import dataclass

from hks.core.schema import Route, TraceStep
from hks.routing.rules import RoutingRuleSet


@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: Route
    steps: list[TraceStep]
    phase2_note: bool = False
    matched_rule_id: str | None = None


def route(query: str, rules: RoutingRuleSet) -> RouteDecision:
    lowered_query = query.lower()
    for rule in rules.rules:
        for keyword in rule.keywords_zh:
            if keyword and keyword in query:
                return RouteDecision(
                    route=rule.target_route,
                    phase2_note=rule.phase2_note,
                    matched_rule_id=rule.id,
                    steps=[
                        TraceStep(
                            kind="rule_match",
                            detail={
                                "rule_id": rule.id,
                                "keyword": keyword,
                                "lang": "zh",
                                "target_route": rule.target_route,
                            },
                        )
                    ],
                )
        for keyword in rule.keywords_en:
            if keyword and keyword in lowered_query:
                return RouteDecision(
                    route=rule.target_route,
                    phase2_note=rule.phase2_note,
                    matched_rule_id=rule.id,
                    steps=[
                        TraceStep(
                            kind="rule_match",
                            detail={
                                "rule_id": rule.id,
                                "keyword": keyword,
                                "lang": "en",
                                "target_route": rule.target_route,
                            },
                        )
                    ],
                )

    return RouteDecision(
        route=rules.default_route,
        matched_rule_id="default",
        steps=[
            TraceStep(
                kind="rule_match",
                detail={
                    "rule_id": "default",
                    "keyword": None,
                    "lang": None,
                    "target_route": rules.default_route,
                },
            )
        ],
    )

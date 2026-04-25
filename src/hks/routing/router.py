"""Semantic routing for Phase 2 query dispatch."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import cast

from hks.core.schema import Route, TraceStep
from hks.core.text_models import TextModelBackend
from hks.routing.rules import RoutingRuleSet


@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: Route
    steps: list[TraceStep]
    matched_rule_id: str | None = None


def route(query: str, rules: RoutingRuleSet) -> RouteDecision:
    backend_name = os.environ.get("HKS_ROUTING_MODEL", "simple")
    backend = TextModelBackend()
    prototype_texts = [
        " ".join((*rule.keywords_zh, *rule.keywords_en)).strip() or rule.id for rule in rules.rules
    ]
    embeddings = backend.embed_texts([query, *prototype_texts])
    query_embedding = embeddings[0]
    best_rule_id = "default"
    best_route = rules.default_route
    best_score = -1.0
    first_lexical_match: tuple[str, Route] | None = None
    ranked_scores: list[dict[str, object]] = []

    lowered_query = query.lower()
    for rule, prototype_embedding in zip(rules.rules, embeddings[1:], strict=False):
        lexical_hits = sum(1 for keyword in rule.keywords_zh if keyword and keyword in query) + sum(
            1 for keyword in rule.keywords_en if keyword and keyword in lowered_query
        )
        semantic_score = _cosine_similarity(query_embedding, prototype_embedding)
        score = semantic_score + (lexical_hits * 0.35)
        ranked_scores.append(
            {
                "rule_id": rule.id,
                "target_route": rule.target_route,
                "score": round(score, 4),
                "lexical_hits": lexical_hits,
            }
        )
        if score > best_score:
            best_rule_id = rule.id
            best_route = rule.target_route
            best_score = score
        if lexical_hits and first_lexical_match is None:
            first_lexical_match = (rule.id, rule.target_route)

    if first_lexical_match is not None:
        best_rule_id, best_route = first_lexical_match
    elif best_score <= 0:
        best_rule_id = "default"
        best_route = rules.default_route

    ranked_scores.sort(key=lambda item: cast(float, item["score"]), reverse=True)
    return RouteDecision(
        route=best_route,
        matched_rule_id=best_rule_id,
        steps=[
            TraceStep(
                kind="routing_model",
                detail={
                    "backend": backend_name,
                    "rule_id": best_rule_id,
                    "target_route": best_route,
                    "scores": ranked_scores[:3],
                },
            )
        ],
    )


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(numerator / (left_norm * right_norm))

"""Deterministic golden-query retrieval quality metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from hks.core.schema import Route

_VALID_ROUTES = {"wiki", "graph", "vector", "page_tree"}
_VALID_FIELDS = {
    "id",
    "question",
    "expected_route",
    "expected_source_relpath",
    "expected_evidence_quote",
    "expected_answer_contains",
    "expected_trace_hit_kind",
    "writeback_allowed",
    "expect_no_hit",
}


@dataclass(frozen=True, slots=True)
class GoldenQueryCase:
    id: str
    question: str
    expected_route: Route | None = None
    expected_source_relpath: str | None = None
    expected_evidence_quote: str | None = None
    expected_answer_contains: str | None = None
    expected_trace_hit_kind: str | None = None
    writeback_allowed: bool = False
    expect_no_hit: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GoldenQueryCase:
        _validate_case_payload(payload)
        route = payload.get("expected_route")
        return cls(
            id=cast(str, payload["id"]),
            question=cast(str, payload["question"]),
            expected_route=cast(Route | None, route),
            expected_source_relpath=_optional_str(payload.get("expected_source_relpath")),
            expected_evidence_quote=_optional_str(payload.get("expected_evidence_quote")),
            expected_answer_contains=_optional_str(payload.get("expected_answer_contains")),
            expected_trace_hit_kind=_optional_str(payload.get("expected_trace_hit_kind")),
            writeback_allowed=bool(payload.get("writeback_allowed", False)),
            expect_no_hit=bool(payload.get("expect_no_hit", False)),
        )


@dataclass(frozen=True, slots=True)
class QueryObservation:
    case: GoldenQueryCase
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MetricThresholds:
    route_accuracy: float = 0.70
    precision_at_1: float = 0.70
    evidence_hit_rate: float = 0.80
    answer_contains_rate: float = 1.00
    trace_hit_rate: float = 1.00
    no_hit_precision: float = 1.00
    writeback_false_positive_rate: float = 0.00


@dataclass(frozen=True, slots=True)
class MetricReport:
    total: int
    route_accuracy: float
    precision_at_1: float
    evidence_hit_rate: float
    answer_contains_rate: float
    trace_hit_rate: float
    no_hit_precision: float
    writeback_false_positive_rate: float
    failures: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "route_accuracy": self.route_accuracy,
            "precision_at_1": self.precision_at_1,
            "evidence_hit_rate": self.evidence_hit_rate,
            "answer_contains_rate": self.answer_contains_rate,
            "trace_hit_rate": self.trace_hit_rate,
            "no_hit_precision": self.no_hit_precision,
            "writeback_false_positive_rate": self.writeback_false_positive_rate,
            "failures": self.failures,
        }


def load_golden_cases(path: Path) -> list[GoldenQueryCase]:
    cases: list[GoldenQueryCase] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise TypeError("case must be a JSON object")
            cases.append(GoldenQueryCase.from_dict(payload))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid golden query case at {path}:{line_no}: {exc}") from exc
    return cases


def evidence_matches(
    payload: dict[str, Any],
    *,
    expected_source_relpath: str | None,
    expected_evidence_quote: str | None,
) -> bool:
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return expected_source_relpath is None and expected_evidence_quote is None

    return any(
        _evidence_item_matches(
            item,
            expected_source_relpath=expected_source_relpath,
            expected_evidence_quote=expected_evidence_quote,
        )
        for item in evidence
    )


def compute_metrics(observations: list[QueryObservation]) -> MetricReport:
    failures: dict[str, list[str]] = {
        "route_accuracy": [],
        "precision_at_1": [],
        "evidence_hit_rate": [],
        "answer_contains_rate": [],
        "trace_hit_rate": [],
        "no_hit_precision": [],
        "writeback_false_positive": [],
    }

    route_total = route_correct = 0
    precision_total = precision_correct = 0
    evidence_total = evidence_correct = 0
    answer_total = answer_correct = 0
    trace_hit_total = trace_hit_correct = 0
    no_hit_total = no_hit_correct = 0
    writeback_disallowed_total = writeback_false_positive = 0

    for observation in observations:
        case = observation.case
        payload = observation.payload

        if case.expected_route is not None:
            route_total += 1
            if _route_matches(payload, case.expected_route):
                route_correct += 1
            else:
                failures["route_accuracy"].append(case.id)

        if case.expect_no_hit:
            no_hit_total += 1
            if _is_no_hit_payload(payload):
                no_hit_correct += 1
            else:
                failures["no_hit_precision"].append(case.id)

        if case.expected_source_relpath is not None or case.expected_evidence_quote is not None:
            precision_total += 1
            if _top_evidence_matches(
                payload,
                expected_source_relpath=case.expected_source_relpath,
                expected_evidence_quote=case.expected_evidence_quote,
            ):
                precision_correct += 1
            else:
                failures["precision_at_1"].append(case.id)

            evidence_total += 1
            if evidence_matches(
                payload,
                expected_source_relpath=case.expected_source_relpath,
                expected_evidence_quote=case.expected_evidence_quote,
            ):
                evidence_correct += 1
            else:
                failures["evidence_hit_rate"].append(case.id)

        if case.expected_answer_contains is not None:
            answer_total += 1
            if _answer_contains(payload, case.expected_answer_contains):
                answer_correct += 1
            else:
                failures["answer_contains_rate"].append(case.id)

        if case.expected_trace_hit_kind is not None:
            trace_hit_total += 1
            if _trace_kind_hit(payload, case.expected_trace_hit_kind):
                trace_hit_correct += 1
            else:
                failures["trace_hit_rate"].append(case.id)

        if not case.writeback_allowed:
            writeback_disallowed_total += 1
            if bool(payload.get("writeback_eligible")) or _auto_committed(payload):
                writeback_false_positive += 1
                failures["writeback_false_positive"].append(case.id)

    return MetricReport(
        total=len(observations),
        route_accuracy=_ratio(route_correct, route_total),
        precision_at_1=_ratio(precision_correct, precision_total),
        evidence_hit_rate=_ratio(evidence_correct, evidence_total),
        answer_contains_rate=_ratio(answer_correct, answer_total),
        trace_hit_rate=_ratio(trace_hit_correct, trace_hit_total),
        no_hit_precision=_ratio(no_hit_correct, no_hit_total),
        writeback_false_positive_rate=_ratio(
            writeback_false_positive,
            writeback_disallowed_total,
        ),
        failures={key: value for key, value in failures.items() if value},
    )


def assert_thresholds(report: MetricReport, thresholds: MetricThresholds) -> None:
    checks = {
        "route_accuracy": (report.route_accuracy, thresholds.route_accuracy, ">="),
        "precision_at_1": (report.precision_at_1, thresholds.precision_at_1, ">="),
        "evidence_hit_rate": (report.evidence_hit_rate, thresholds.evidence_hit_rate, ">="),
        "answer_contains_rate": (
            report.answer_contains_rate,
            thresholds.answer_contains_rate,
            ">=",
        ),
        "trace_hit_rate": (report.trace_hit_rate, thresholds.trace_hit_rate, ">="),
        "no_hit_precision": (report.no_hit_precision, thresholds.no_hit_precision, ">="),
        "writeback_false_positive_rate": (
            report.writeback_false_positive_rate,
            thresholds.writeback_false_positive_rate,
            "<=",
        ),
    }
    failed: list[str] = []
    for name, (actual, expected, operator) in checks.items():
        if operator == ">=" and actual < expected:
            failed.append(f"{name}: {actual:.3f} < {expected:.3f}")
        if operator == "<=" and actual > expected:
            failed.append(f"{name}: {actual:.3f} > {expected:.3f}")
    if failed:
        raise AssertionError(
            "retrieval quality gate failed: "
            + "; ".join(failed)
            + f"; failing_cases={report.failures}"
        )


def _validate_case_payload(payload: dict[str, Any]) -> None:
    unknown = set(payload) - _VALID_FIELDS
    if unknown:
        raise ValueError(f"unknown fields: {sorted(unknown)}")
    for field_name in ("id", "question"):
        value = payload.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must be a non-empty string")
    route = payload.get("expected_route")
    if route is not None and route not in _VALID_ROUTES:
        raise ValueError(f"invalid expected_route for {payload['id']}: {route}")
    for field_name in (
        "expected_source_relpath",
        "expected_evidence_quote",
        "expected_answer_contains",
        "expected_trace_hit_kind",
    ):
        value = payload.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string or null")
    for field_name in ("writeback_allowed", "expect_no_hit"):
        value = payload.get(field_name)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{field_name} must be a boolean")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _first_source(payload: dict[str, Any]) -> str | None:
    source = payload.get("source")
    if not isinstance(source, list) or not source:
        return None
    first = source[0]
    return first if isinstance(first, str) else None


def _trace_route(payload: dict[str, Any]) -> str | None:
    trace = payload.get("trace")
    if not isinstance(trace, dict):
        return None
    route = trace.get("route")
    return route if isinstance(route, str) else None


def _route_matches(payload: dict[str, Any], expected_route: Route) -> bool:
    return _first_source(payload) == expected_route and _trace_route(payload) == expected_route


def _answer_contains(payload: dict[str, Any], expected_answer_contains: str) -> bool:
    answer = payload.get("answer")
    if not isinstance(answer, str):
        return False
    return expected_answer_contains.casefold() in answer.casefold()


def _is_no_hit_payload(payload: dict[str, Any]) -> bool:
    source = payload.get("source")
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        return False
    return source == [] and confidence == 0.0


def _trace_kind_hit(payload: dict[str, Any], expected_kind: str) -> bool:
    trace = payload.get("trace")
    if not isinstance(trace, dict):
        return False
    steps = trace.get("steps")
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") != expected_kind:
            continue
        detail = step.get("detail")
        return isinstance(detail, dict) and detail.get("hit") is True
    return False


def _top_evidence_matches(
    payload: dict[str, Any],
    *,
    expected_source_relpath: str | None,
    expected_evidence_quote: str | None,
) -> bool:
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return expected_source_relpath is None and expected_evidence_quote is None
    return _evidence_item_matches(
        evidence[0],
        expected_source_relpath=expected_source_relpath,
        expected_evidence_quote=expected_evidence_quote,
    )


def _evidence_item_matches(
    item: object,
    *,
    expected_source_relpath: str | None,
    expected_evidence_quote: str | None,
) -> bool:
    if not isinstance(item, dict):
        return False
    if (
        expected_source_relpath is not None
        and item.get("source_relpath") != expected_source_relpath
    ):
        return False
    if expected_evidence_quote is not None:
        quote = str(item.get("quote", ""))
        if expected_evidence_quote.casefold() not in quote.casefold():
            return False
    return True


def _auto_committed(payload: dict[str, Any]) -> bool:
    trace = payload.get("trace")
    if not isinstance(trace, dict):
        return False
    steps = trace.get("steps")
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") != "writeback":
            continue
        detail = step.get("detail")
        if isinstance(detail, dict) and detail.get("status") == "auto-committed":
            return True
    return False


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator

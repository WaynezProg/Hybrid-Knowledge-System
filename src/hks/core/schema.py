"""Stable JSON response contract helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import jsonschema

from hks.errors import ExitCode

type Route = Literal["wiki", "graph", "vector"]
type TraceKind = Literal[
    "routing_model",
    "wiki_lookup",
    "graph_lookup",
    "vector_lookup",
    "fallback",
    "merge",
    "writeback",
    "error",
    "ingest_summary",
    "lint_summary",
    "coordination_summary",
    "llm_extraction_summary",
    "wiki_synthesis_summary",
    "graphify_summary",
]


@dataclass(slots=True)
class TraceStep:
    kind: TraceKind
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail}


@dataclass(slots=True)
class Trace:
    route: Route
    steps: list[TraceStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(slots=True)
class QueryResponse:
    answer: str
    source: list[Route]
    confidence: float
    trace: Trace

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "source": self.source,
            "confidence": self.confidence,
            "trace": self.trace.to_dict(),
        }

    def to_json(self) -> str:
        payload = self.to_dict()
        validate(payload)
        return json.dumps(payload, ensure_ascii=False, indent=2)


def contract_schema_path() -> Path:
    """Locate the canonical contract file inside the repository."""

    return (
        Path(__file__).resolve().parents[3]
        / "specs"
        / "005-phase3-lint-impl"
        / "contracts"
        / "query-response.schema.json"
    )


@lru_cache(maxsize=1)
def load_contract_schema() -> dict[str, Any]:
    """Load and memoize the JSON schema used by runtime and tests."""

    schema_path = contract_schema_path()
    schema: dict[str, Any] = json.loads(schema_path.read_text(encoding="utf-8"))
    return schema


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a response payload against the public contract."""

    jsonschema.validate(instance=payload, schema=load_contract_schema())
    return payload


def build_error_response(
    message: str,
    *,
    route: Route = "wiki",
    code: str,
    exit_code: ExitCode,
    hint: str | None = None,
) -> QueryResponse:
    """Build a schema-valid error response for non-usage failures."""

    detail: dict[str, Any] = {"code": code, "exit_code": int(exit_code)}
    if hint:
        detail["hint"] = hint
    return QueryResponse(
        answer=message,
        source=[],
        confidence=0.0,
        trace=Trace(route=route, steps=[TraceStep(kind="error", detail=detail)]),
    )

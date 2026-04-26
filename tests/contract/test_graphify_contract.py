from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_graphify_graph_schema,
    load_graphify_run_schema,
    load_graphify_summary_schema,
    validate_graphify_graph,
    validate_graphify_run,
    validate_graphify_summary,
)
from hks.core.schema import QueryResponse, Trace, TraceStep, validate


def _graph() -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": "2026-04-26T00:00:00+00:00",
        "input_layers": ["wiki", "graph"],
        "nodes": [
            {
                "id": "wiki:project-atlas",
                "label": "Project Atlas",
                "kind": "wiki_page",
                "source_layer": "wiki",
                "source_ref": "wiki/pages/project-atlas.md",
                "provenance": {
                    "source_relpath": "project-atlas.txt",
                    "wiki_page": "project-atlas",
                    "artifact_id": None,
                    "source_fingerprint": "sha",
                },
                "community_id": "community:001",
            }
        ],
        "edges": [],
        "communities": [
            {
                "community_id": "community:001",
                "label": "Project Atlas",
                "summary": "Project Atlas community",
                "node_ids": ["wiki:project-atlas"],
                "representative_edge_ids": [],
                "classification_method": "deterministic",
                "confidence_score": 1.0,
                "provenance": {
                    "source_relpath": None,
                    "wiki_page": None,
                    "artifact_id": None,
                    "source_fingerprint": None,
                },
            }
        ],
        "audit_findings": [],
    }


def _summary() -> dict[str, object]:
    return {
        "operation": "graphify_build",
        "mode": "store",
        "input_fingerprint": "fingerprint",
        "node_count": 1,
        "edge_count": 0,
        "community_count": 1,
        "audit_summary": {"info": 0, "warning": 0, "error": 0},
        "artifacts": {
            "run_id": "run-1",
            "run_path": "/tmp/run-1",
            "graph": "/tmp/run-1/graphify.json",
            "communities": "/tmp/run-1/communities.json",
            "audit": "/tmp/run-1/audit.json",
            "manifest": "/tmp/run-1/manifest.json",
            "html": None,
            "report": None,
        },
        "idempotent_reuse": False,
        "confidence": 1.0,
    }


@pytest.mark.contract
def test_graphify_schemas_are_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(load_graphify_graph_schema())
    jsonschema.Draft202012Validator.check_schema(load_graphify_run_schema())
    jsonschema.Draft202012Validator.check_schema(load_graphify_summary_schema())


@pytest.mark.contract
def test_graphify_summary_detail_contract_accepts_expected_payload() -> None:
    validate_graphify_summary(_summary())


@pytest.mark.contract
def test_graphify_graph_contract_accepts_expected_payload() -> None:
    validate_graphify_graph(_graph())


@pytest.mark.contract
def test_graphify_run_contract_accepts_expected_payload() -> None:
    validate_graphify_run(
        {
            "run_id": "run-1",
            "schema_version": 1,
            "created_at": "2026-04-26T00:00:00+00:00",
            "status": "valid",
            "idempotency_key": "key",
            "input_fingerprint": "fingerprint",
            "algorithm_version": "graphify-v1",
            "request": {
                "mode": "store",
                "provider_id": "fake",
                "model_id": "fake-graphify-classifier-v1",
                "include_html": True,
                "include_report": True,
                "force_new_run": False,
                "requested_by": None,
            },
            "artifacts": {
                "graph": "graphify.json",
                "communities": "communities.json",
                "audit": "audit.json",
                "manifest": "manifest.json",
                "html": "graph.html",
                "report": "GRAPH_REPORT.md",
            },
        }
    )


@pytest.mark.contract
def test_query_response_contract_allows_graphify_summary_step() -> None:
    response = QueryResponse(
        answer="graphify 完成",
        source=["wiki", "graph"],
        confidence=1.0,
        trace=Trace(route="graph", steps=[TraceStep(kind="graphify_summary", detail=_summary())]),
    )

    validate(response.to_dict())

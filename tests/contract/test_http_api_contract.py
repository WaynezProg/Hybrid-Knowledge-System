from __future__ import annotations

import pytest

from hks.adapters.contracts import load_http_openapi

GUARDED_OPERATIONS = {
    ("/query", "post"),
    ("/ingest", "post"),
    ("/pageindex/enrich", "post"),
    ("/coord/session", "post"),
    ("/coord/lease", "post"),
    ("/coord/handoff", "post"),
}

READ_ONLY_OPERATIONS = {
    ("/lint", "post"),
    ("/pageindex/{relpath}", "get"),
    ("/coord/status", "post"),
}


@pytest.mark.contract
def test_http_openapi_contract_has_expected_paths_and_schemas() -> None:
    spec = load_http_openapi()

    assert spec["openapi"] == "3.1.0"
    assert spec["servers"][0]["url"] == "http://127.0.0.1:8766"
    assert set(spec["paths"]) == {
        "/query",
        "/ingest",
        "/lint",
        "/pageindex/{relpath}",
        "/pageindex/enrich",
        "/coord/session",
        "/coord/lease",
        "/coord/handoff",
        "/coord/status",
    }

    for path in spec["paths"]:
        method = "get" if path == "/pageindex/{relpath}" else "post"
        operation = spec["paths"][path][method]
        assert "200" in operation["responses"]
        assert "400" in operation["responses"]
        assert "500" in operation["responses"]

    schemas = spec["components"]["schemas"]
    assert set(schemas) >= {
        "HksQueryInput",
        "HksIngestInput",
        "HksLintInput",
        "HksPageIndexShowInput",
        "HksPageIndexEnrichInput",
        "HksCoordSessionInput",
        "HksCoordLeaseInput",
        "HksCoordHandoffInput",
        "HksCoordStatusInput",
        "QueryResponse",
        "AdapterError",
    }


@pytest.mark.contract
def test_http_openapi_contract_documents_http_security_boundaries() -> None:
    spec = load_http_openapi()

    assert spec["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "description": (
            "Local bearer token supplied through HKS_API_TOKEN for guarded HTTP operations."
        ),
    }

    for path, method in GUARDED_OPERATIONS:
        operation = spec["paths"][path][method]
        assert operation["security"] == [{"BearerAuth": []}]

    for path, method in READ_ONLY_OPERATIONS:
        operation = spec["paths"][path][method]
        assert "security" not in operation

    ingest_properties = spec["components"]["schemas"]["HksIngestInput"]["properties"]
    assert "source_root_id" in ingest_properties

from __future__ import annotations

import pytest

from hks.adapters.contracts import load_http_openapi


@pytest.mark.contract
def test_http_openapi_contract_has_expected_paths_and_schemas() -> None:
    spec = load_http_openapi()

    assert spec["openapi"] == "3.1.0"
    assert spec["servers"][0]["url"] == "http://127.0.0.1:8766"
    assert set(spec["paths"]) == {
        "/query",
        "/ingest",
        "/lint",
        "/coord/session",
        "/coord/lease",
        "/coord/handoff",
        "/coord/status",
    }

    for path in spec["paths"]:
        operation = spec["paths"][path]["post"]
        assert "200" in operation["responses"]
        assert "400" in operation["responses"]
        assert "500" in operation["responses"]

    schemas = spec["components"]["schemas"]
    assert set(schemas) >= {
        "HksQueryInput",
        "HksIngestInput",
        "HksLintInput",
        "HksCoordSessionInput",
        "HksCoordLeaseInput",
        "HksCoordHandoffInput",
        "HksCoordStatusInput",
        "QueryResponse",
        "AdapterError",
    }

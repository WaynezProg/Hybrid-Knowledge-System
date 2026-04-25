from __future__ import annotations

import pytest

from hks.adapters.contracts import load_http_openapi


@pytest.mark.contract
def test_http_openapi_contract_has_expected_paths_and_schemas() -> None:
    spec = load_http_openapi()

    assert spec["openapi"] == "3.1.0"
    assert set(spec["paths"]) == {"/query", "/ingest", "/lint"}

    for path in ("/query", "/ingest", "/lint"):
        operation = spec["paths"][path]["post"]
        assert "requestBody" in operation
        assert "200" in operation["responses"]
        assert "400" in operation["responses"]

    schemas = spec["components"]["schemas"]
    assert set(schemas) >= {
        "HksQueryInput",
        "HksIngestInput",
        "HksLintInput",
        "QueryResponse",
        "AdapterError",
    }

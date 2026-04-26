from __future__ import annotations

from hks.catalog.models import CatalogSummaryDetail


def test_catalog_summary_serializes_contract_fields() -> None:
    payload = CatalogSummaryDetail(
        operation="source.list",
        total_count=0,
        filtered_count=0,
        filter=None,
    ).to_dict()

    assert payload["kind"] == "catalog_summary"
    assert payload["command"] == "source.list"
    assert payload["source"] is None


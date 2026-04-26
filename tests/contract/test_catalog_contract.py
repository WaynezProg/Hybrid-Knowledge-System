from __future__ import annotations

import jsonschema

from hks.adapters.contracts import (
    load_catalog_summary_schema,
    load_source_catalog_schema,
    load_workspace_registry_schema,
    validate_catalog_summary,
    validate_source_detail,
)


def test_catalog_contracts_are_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(load_catalog_summary_schema())
    jsonschema.Draft202012Validator.check_schema(load_source_catalog_schema())
    jsonschema.Draft202012Validator.check_schema(load_workspace_registry_schema())


def test_catalog_summary_accepts_source_list_payload() -> None:
    validate_catalog_summary(
        {
            "kind": "catalog_summary",
            "command": "source.list",
            "total_count": 1,
            "filtered_count": 1,
            "filter": None,
            "workspace_id": None,
            "ks_root": "/tmp/ks",
            "registry_path": None,
            "previous_root": None,
            "sources": [],
            "source": None,
            "workspaces": None,
            "export_command": None,
            "warnings": [],
        }
    )


def test_source_detail_accepts_artifact_references() -> None:
    validate_source_detail(
        {
            "relpath": "project-atlas.txt",
            "format": "txt",
            "size_bytes": 10,
            "ingested_at": "2026-04-26T00:00:00+00:00",
            "sha256": "a" * 64,
            "sha256_prefix": "aaaaaaaa",
            "parser_fingerprint": "txt:v1",
            "derived_counts": {
                "wiki_pages": 1,
                "graph_nodes": 0,
                "graph_edges": 0,
                "vector_ids": 1,
            },
            "integrity_status": "ok",
            "issues": [],
            "query_hint": "Use `ks query`.",
            "raw_source_path": "/tmp/ks/raw_sources/project-atlas.txt",
            "derived": {
                "wiki_pages": ["project-atlas"],
                "graph_nodes": [],
                "graph_edges": [],
                "vector_ids": ["project-atlas:0"],
            },
            "integrity_checks": [],
        }
    )


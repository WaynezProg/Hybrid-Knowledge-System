"""Contract helpers for adapter and coordination specs."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import jsonschema
from ruamel.yaml import YAML


def specs_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "specs" / "006-mcp-api-adapter"


def feature_specs_dir(feature: str) -> Path:
    return Path(__file__).resolve().parents[3] / "specs" / feature


def contract_path(name: str) -> Path:
    return specs_dir() / "contracts" / name


def feature_contract_path(feature: str, name: str) -> Path:
    return feature_specs_dir(feature) / "contracts" / name


@lru_cache(maxsize=1)
def load_mcp_tools_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(contract_path("mcp-tools.schema.json").read_text(encoding="utf-8")),
    )


@lru_cache(maxsize=1)
def load_adapter_error_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(contract_path("adapter-error.schema.json").read_text(encoding="utf-8")),
    )


@lru_cache(maxsize=1)
def load_http_openapi() -> dict[str, Any]:
    payload = YAML(typ="safe").load(contract_path("http-api.openapi.yaml").read_text("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("http-api.openapi.yaml must be an object")
    return payload


@lru_cache(maxsize=1)
def load_coordination_tools_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            feature_contract_path(
                "007-multi-agent-support",
                "mcp-coordination-tools.schema.json",
            ).read_text(encoding="utf-8")
        ),
    )


@lru_cache(maxsize=1)
def load_coordination_summary_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            feature_contract_path(
                "007-multi-agent-support",
                "coordination-summary-detail.schema.json",
            ).read_text(encoding="utf-8")
        ),
    )


@lru_cache(maxsize=1)
def load_coordination_ledger_schema() -> dict[str, Any]:
    ledger_schema = cast(
        dict[str, Any],
        json.loads(
            feature_contract_path(
                "007-multi-agent-support",
                "coordination-ledger.schema.json",
            ).read_text(encoding="utf-8")
        ),
    )
    summary_schema = load_coordination_summary_schema()
    ledger_schema = dict(ledger_schema)
    ledger_schema["$defs"] = summary_schema["$defs"]
    for property_name, definition_name in {
        "sessions": "agentSession",
        "leases": "coordinationLease",
        "handoffs": "handoffNote",
    }.items():
        ledger_schema["properties"][property_name]["additionalProperties"] = {
            "$ref": f"#/$defs/{definition_name}"
        }
    return ledger_schema


@lru_cache(maxsize=1)
def load_llm_tools_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            feature_contract_path(
                "008-llm-classification-extraction",
                "mcp-llm-tools.schema.json",
            ).read_text(encoding="utf-8")
        ),
    )


@lru_cache(maxsize=1)
def load_llm_summary_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            feature_contract_path(
                "008-llm-classification-extraction",
                "llm-extraction-summary-detail.schema.json",
            ).read_text(encoding="utf-8")
        ),
    )


@lru_cache(maxsize=1)
def load_llm_artifact_schema() -> dict[str, Any]:
    artifact_schema = cast(
        dict[str, Any],
        json.loads(
            feature_contract_path(
                "008-llm-classification-extraction",
                "llm-extraction-artifact.schema.json",
            ).read_text(encoding="utf-8")
        ),
    )
    artifact_schema = dict(artifact_schema)
    artifact_schema["properties"] = dict(artifact_schema["properties"])
    summary_schema = dict(load_llm_summary_schema())
    summary_defs = summary_schema.pop("$defs")
    summary_schema.pop("$schema", None)
    summary_schema.pop("$id", None)
    artifact_schema["$defs"] = summary_defs
    artifact_schema["properties"]["result"] = summary_schema
    return artifact_schema


@lru_cache(maxsize=1)
def load_llm_http_openapi() -> dict[str, Any]:
    payload = YAML(typ="safe").load(
        feature_contract_path(
            "008-llm-classification-extraction",
            "http-llm-api.openapi.yaml",
        ).read_text("utf-8")
    )
    if not isinstance(payload, dict):
        raise ValueError("http-llm-api.openapi.yaml must be an object")
    return payload


@lru_cache(maxsize=1)
def load_wiki_tools_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            feature_contract_path(
                "009-llm-wiki-synthesis",
                "mcp-wiki-tools.schema.json",
            ).read_text(encoding="utf-8")
        ),
    )


@lru_cache(maxsize=1)
def load_wiki_candidate_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            feature_contract_path(
                "009-llm-wiki-synthesis",
                "wiki-synthesis-candidate.schema.json",
            ).read_text(encoding="utf-8")
        ),
    )


@lru_cache(maxsize=1)
def load_wiki_summary_schema() -> dict[str, Any]:
    summary_schema = cast(
        dict[str, Any],
        json.loads(
            feature_contract_path(
                "009-llm-wiki-synthesis",
                "wiki-synthesis-summary-detail.schema.json",
            ).read_text(encoding="utf-8")
        ),
    )
    summary_schema = dict(summary_schema)
    summary_schema["properties"] = dict(summary_schema["properties"])
    candidate_schema = dict(load_wiki_candidate_schema())
    candidate_schema.pop("$schema", None)
    candidate_schema.pop("$id", None)
    summary_schema["properties"]["candidate"] = candidate_schema
    return summary_schema


@lru_cache(maxsize=1)
def load_wiki_artifact_schema() -> dict[str, Any]:
    artifact_schema = cast(
        dict[str, Any],
        json.loads(
            feature_contract_path(
                "009-llm-wiki-synthesis",
                "wiki-synthesis-artifact.schema.json",
            ).read_text(encoding="utf-8")
        ),
    )
    artifact_schema = dict(artifact_schema)
    artifact_schema["properties"] = dict(artifact_schema["properties"])
    candidate_schema = dict(load_wiki_candidate_schema())
    candidate_schema.pop("$schema", None)
    candidate_schema.pop("$id", None)
    artifact_schema["properties"]["candidate"] = candidate_schema
    return artifact_schema


@lru_cache(maxsize=1)
def load_wiki_http_openapi() -> dict[str, Any]:
    payload = YAML(typ="safe").load(
        feature_contract_path(
            "009-llm-wiki-synthesis",
            "http-wiki-api.openapi.yaml",
        ).read_text("utf-8")
    )
    if not isinstance(payload, dict):
        raise ValueError("http-wiki-api.openapi.yaml must be an object")
    return payload


def validate_tool_input(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    full_schema = load_mcp_tools_schema()
    schema = dict(full_schema["properties"]["tools"]["properties"][tool])
    schema["$defs"] = full_schema["$defs"]
    jsonschema.validate(instance=payload, schema=schema)
    return payload


def validate_coordination_tool_input(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    full_schema = load_coordination_tools_schema()
    schema = dict(full_schema["properties"]["tools"]["properties"][tool])
    schema["$defs"] = full_schema["$defs"]
    jsonschema.validate(instance=payload, schema=schema)
    return payload


def validate_llm_tool_input(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    full_schema = load_llm_tools_schema()
    schema = dict(full_schema["properties"]["tools"]["properties"][tool])
    schema["$defs"] = full_schema["$defs"]
    jsonschema.validate(instance=payload, schema=schema)
    return payload


def validate_wiki_tool_input(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    full_schema = load_wiki_tools_schema()
    schema = dict(full_schema["properties"]["tools"]["properties"][tool])
    schema["$defs"] = full_schema["$defs"]
    jsonschema.validate(instance=payload, schema=schema)
    return payload


def validate_coordination_summary(payload: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(instance=payload, schema=load_coordination_summary_schema())
    return payload


def validate_llm_summary(payload: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(instance=payload, schema=load_llm_summary_schema())
    return payload


def validate_llm_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(instance=payload, schema=load_llm_artifact_schema())
    return payload


def validate_wiki_summary(payload: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(instance=payload, schema=load_wiki_summary_schema())
    return payload


def validate_wiki_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(instance=payload, schema=load_wiki_candidate_schema())
    return payload


def validate_wiki_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(instance=payload, schema=load_wiki_artifact_schema())
    return payload


def validate_adapter_error(payload: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(instance=payload, schema=load_adapter_error_schema())
    return payload

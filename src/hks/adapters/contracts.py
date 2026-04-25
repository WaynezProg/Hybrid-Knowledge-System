"""Contract helpers for the 006 adapter specs."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import jsonschema
from ruamel.yaml import YAML


def specs_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "specs" / "006-mcp-api-adapter"


def contract_path(name: str) -> Path:
    return specs_dir() / "contracts" / name


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


def validate_tool_input(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    full_schema = load_mcp_tools_schema()
    schema = dict(full_schema["properties"]["tools"]["properties"][tool])
    schema["$defs"] = full_schema["$defs"]
    jsonschema.validate(instance=payload, schema=schema)
    return payload


def validate_adapter_error(payload: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(instance=payload, schema=load_adapter_error_schema())
    return payload

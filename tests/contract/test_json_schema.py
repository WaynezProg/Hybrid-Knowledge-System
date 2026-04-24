from __future__ import annotations

import copy

import jsonschema
import pytest

from hks.core import paths
from hks.core.schema import load_contract_schema


def test_contract_schema_is_valid() -> None:
    schema = load_contract_schema()
    jsonschema.Draft202012Validator.check_schema(schema)


def test_contract_examples_are_valid() -> None:
    schema = load_contract_schema()
    for example in schema["examples"]:
        jsonschema.validate(instance=example, schema=schema)


def test_contract_rejects_graph_route_fields() -> None:
    schema = load_contract_schema()
    example = copy.deepcopy(schema["examples"][0])
    example["source"] = ["graph"]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=example, schema=schema)

    example = copy.deepcopy(schema["examples"][0])
    example["trace"]["route"] = "graph"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=example, schema=schema)


def test_runtime_paths_reject_graph_access() -> None:
    with pytest.raises(AssertionError):
        paths.assert_runtime_path_allowed(paths.resolve_ks_root() / "graph" / "nodes.json")

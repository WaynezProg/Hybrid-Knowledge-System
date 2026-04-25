from __future__ import annotations

import copy

import jsonschema

from hks.core import paths
from hks.core.schema import load_contract_schema


def test_contract_schema_is_valid() -> None:
    schema = load_contract_schema()
    jsonschema.Draft202012Validator.check_schema(schema)


def test_contract_examples_are_valid() -> None:
    schema = load_contract_schema()
    for example in schema["examples"]:
        jsonschema.validate(instance=example, schema=schema)


def test_contract_accepts_graph_route_fields() -> None:
    schema = load_contract_schema()
    example = copy.deepcopy(schema["examples"][0])
    example["source"] = ["graph"]
    example["trace"]["route"] = "graph"

    jsonschema.validate(instance=example, schema=schema)


def test_contract_allows_office_location_metadata_in_trace_detail() -> None:
    schema = load_contract_schema()
    example = copy.deepcopy(schema["examples"][1])
    example["trace"]["steps"][-1]["detail"].update(
        {
            "source_relpath": "pptx/with_notes.pptx",
            "slide_index": 1,
            "section_type": "notes",
        }
    )
    jsonschema.validate(instance=example, schema=schema)


def test_contract_allows_image_vector_metadata_in_trace_detail() -> None:
    schema = load_contract_schema()
    example = copy.deepcopy(schema["examples"][2])
    example["trace"]["steps"][-1]["detail"].update(
        {
            "source_relpath": "image/atlas-dependency.png",
            "source_format": "png",
            "ocr_confidence": 0.91,
            "source_engine": "tesseract-5.5.2",
        }
    )
    jsonschema.validate(instance=example, schema=schema)


def test_runtime_paths_allow_graph_access() -> None:
    allowed = paths.assert_runtime_path_allowed(paths.resolve_ks_root() / "graph" / "graph.json")
    assert allowed.name == "graph.json"

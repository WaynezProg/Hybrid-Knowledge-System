from __future__ import annotations

import pytest
from jsonschema import ValidationError

from hks.adapters.contracts import validate_tool_input


@pytest.mark.contract
def test_hks_ingest_and_lint_contracts_accept_expected_defaults() -> None:
    assert validate_tool_input("hks_ingest", {"path": "/tmp/source"}) == {"path": "/tmp/source"}
    assert validate_tool_input("hks_lint", {}) == {}


@pytest.mark.contract
def test_hks_ingest_and_lint_contracts_reject_invalid_modes() -> None:
    with pytest.raises(ValidationError):
        validate_tool_input("hks_ingest", {"path": "/tmp/source", "pptx_notes": "all"})

    with pytest.raises(ValidationError):
        validate_tool_input("hks_lint", {"fix": "force"})

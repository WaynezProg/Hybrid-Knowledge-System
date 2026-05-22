from __future__ import annotations

import pytest
from jsonschema import ValidationError

from hks.adapters.contracts import validate_tool_input


@pytest.mark.contract
def test_hks_query_contract_defaults_to_read_only_writeback() -> None:
    schema = validate_tool_input("hks_query", {"question": "摘要"})

    assert schema == {"question": "摘要"}


@pytest.mark.contract
def test_hks_query_contract_accepts_review_queue_writeback_modes() -> None:
    for mode in ("no", "auto", "yes", "ask"):
        schema = validate_tool_input("hks_query", {"question": "摘要", "writeback": mode})
        assert schema == {"question": "摘要", "writeback": mode}


@pytest.mark.contract
def test_hks_query_contract_rejects_empty_question() -> None:
    with pytest.raises(ValidationError):
        validate_tool_input("hks_query", {"question": ""})

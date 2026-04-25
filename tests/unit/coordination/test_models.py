from __future__ import annotations

import pytest

from hks.coordination.models import (
    normalize_references,
    validate_agent_id,
    validate_resource_key,
)
from hks.errors import KSError


def test_agent_id_allows_machine_safe_identifier() -> None:
    assert validate_agent_id("agent.alpha-01@example") == "agent.alpha-01@example"


@pytest.mark.parametrize("agent_id", ["", "bad id", "x" * 81])
def test_agent_id_rejects_unsafe_values(agent_id: str) -> None:
    with pytest.raises(KSError):
        validate_agent_id(agent_id)


def test_resource_key_allows_logical_source_key_with_slash() -> None:
    assert validate_resource_key("source:docs/foo.md") == "source:docs/foo.md"


@pytest.mark.parametrize("resource_key", ["", "/tmp/file", "../secret", "a" * 241])
def test_resource_key_rejects_path_like_values(resource_key: str) -> None:
    with pytest.raises(KSError):
        validate_resource_key(resource_key)


def test_normalize_references_adds_explicit_null_label() -> None:
    references = normalize_references([{"type": "wiki_page", "value": "atlas"}])

    assert references == [{"type": "wiki_page", "value": "atlas", "label": None}]

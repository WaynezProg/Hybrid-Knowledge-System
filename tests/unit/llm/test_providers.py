from __future__ import annotations

from hks.llm.config import build_request
from hks.llm.providers import provider_for


def test_fake_provider_is_deterministic() -> None:
    request = build_request(source_relpath="project-atlas.txt")
    provider = provider_for(request)

    first = provider.extract(request, content="Project Atlas 目前處於設計階段。")
    second = provider.extract(request, content="Project Atlas 目前處於設計階段。")

    assert first == second
    assert first["entity_candidates"][0]["type"] == "Document"


def test_fake_malformed_provider_simulates_bad_output() -> None:
    request = build_request(source_relpath="project-atlas.txt", provider="fake-malformed")
    payload = provider_for(request).extract(request, content="Project Atlas")

    assert payload["classification"] == "not-an-array"

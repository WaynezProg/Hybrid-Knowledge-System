from __future__ import annotations

import pytest

from hks.errors import KSError
from hks.graphify.config import build_request


def test_graphify_config_defaults_to_fake_provider() -> None:
    request = build_request()

    assert request.provider.provider_id == "fake"
    assert request.provider.model_id == "fake-graphify-classifier-v1"


def test_graphify_config_reuses_llm_network_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HKS_LLM_NETWORK_OPT_IN", raising=False)

    with pytest.raises(KSError) as exc:
        build_request(provider="hosted-example")

    assert exc.value.exit_code == 2

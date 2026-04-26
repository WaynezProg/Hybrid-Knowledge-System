from __future__ import annotations

import pytest

from hks.errors import KSError
from hks.llm.config import build_provider_config, build_request


def test_fake_provider_requires_no_network() -> None:
    config = build_provider_config("fake")

    assert config.provider_id == "fake"
    assert config.network_opt_in is False
    assert config.credential_status == "not_required"


def test_hosted_provider_requires_env_opt_in() -> None:
    with pytest.raises(KSError) as exc_info:
        build_provider_config("hosted-example")

    assert exc_info.value.exit_code == 2
    assert "HKS_LLM_NETWORK_OPT_IN" in exc_info.value.message


def test_invalid_mode_is_usage_error() -> None:
    with pytest.raises(KSError) as exc_info:
        build_request(source_relpath="project-atlas.txt", mode="apply")

    assert exc_info.value.exit_code == 2

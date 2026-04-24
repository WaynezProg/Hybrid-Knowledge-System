from __future__ import annotations

from pathlib import Path
from urllib import request as urllib_request

import pytest

from hks.cli import app
from hks.core.text_models import DEFAULT_EMBEDDING_MODEL, SIMPLE_EMBEDDING_MODEL


def _deny_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("network access is disabled for this test")


def _patch_http_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import httpx
    except ModuleNotFoundError:
        pass
    else:
        monkeypatch.setattr(httpx.Client, "request", _deny_network)
        monkeypatch.setattr(httpx.AsyncClient, "request", _deny_network)

    try:
        import requests
    except ModuleNotFoundError:
        pass
    else:
        monkeypatch.setattr(requests.sessions.Session, "request", _deny_network)


@pytest.mark.integration
def test_ingest_and_query_run_without_network(
    cli_runner,
    working_docs: Path,
    local_embedding_model: Path | str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_source = str(local_embedding_model)
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", model_source)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setattr(urllib_request, "urlopen", _deny_network)
    monkeypatch.setattr(urllib_request.OpenerDirector, "open", _deny_network)
    _patch_http_clients(monkeypatch)

    assert model_source != DEFAULT_EMBEDDING_MODEL
    if model_source != SIMPLE_EMBEDDING_MODEL:
        assert Path(model_source).exists()

    ingest_result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert ingest_result.exit_code == 0

    query_result = cli_runner.invoke(app, ["query", "summary Atlas"])
    assert query_result.exit_code == 0

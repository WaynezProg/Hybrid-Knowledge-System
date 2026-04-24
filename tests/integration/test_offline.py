from __future__ import annotations

import importlib
from pathlib import Path
from urllib import request as urllib_request

import pytest

from hks.cli import app
from hks.core.text_models import SIMPLE_EMBEDDING_MODEL, resolve_embedding_model


def _deny_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("network access is disabled for this test")


def _patch_optional(monkeypatch: pytest.MonkeyPatch, module_name: str, attribute: str) -> None:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return
    monkeypatch.setattr(module, attribute, _deny_network)


@pytest.mark.integration
def test_ingest_and_query_run_without_network(
    cli_runner,
    working_docs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", SIMPLE_EMBEDDING_MODEL)
    monkeypatch.setattr(urllib_request, "urlopen", _deny_network)
    monkeypatch.setattr(urllib_request.OpenerDirector, "open", _deny_network)
    _patch_optional(monkeypatch, "httpx", "request")
    _patch_optional(monkeypatch, "requests", "request")

    assert resolve_embedding_model() == SIMPLE_EMBEDDING_MODEL

    ingest_result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert ingest_result.exit_code == 0

    query_result = cli_runner.invoke(app, ["query", "summary Atlas"])
    assert query_result.exit_code == 0

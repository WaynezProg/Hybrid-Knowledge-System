"""Tests for OpenAI-compatible LLM provider."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from hks.llm.config import build_provider_config, build_request
from hks.llm.models import LlmProviderConfig
from hks.llm.providers import FakeProvider, OpenAIProvider, _openai_chat, provider_for


# ---------------------------------------------------------------------------
# _openai_chat helpers
# ---------------------------------------------------------------------------

def _make_httpx_response(content: Any) -> MagicMock:
    """Build a mock httpx.Response that returns the given content string."""
    response_body = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(content) if not isinstance(content, str) else content
                }
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_body
    return mock_resp


# ---------------------------------------------------------------------------
# _openai_chat: success path
# ---------------------------------------------------------------------------

def test_openai_chat_returns_parsed_json() -> None:
    expected = {"classification": [], "confidence": 0.9}

    with patch("hks.llm.providers.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _make_httpx_response(expected)
        mock_client_cls.return_value = mock_client

        result = _openai_chat(
            api_key="sk-test",
            endpoint="https://api.openai.com/v1",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hello"}],
        )

    assert result == expected


def test_openai_chat_posts_to_correct_url() -> None:
    payload = {"key": "value"}

    with patch("hks.llm.providers.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _make_httpx_response(payload)
        mock_client_cls.return_value = mock_client

        _openai_chat(
            api_key="sk-test",
            endpoint="https://custom.example.com/v1",
            model="my-model",
            messages=[{"role": "user", "content": "test"}],
        )

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://custom.example.com/v1/chat/completions"


def test_openai_chat_sends_json_response_format() -> None:
    payload = {"result": 1}

    with patch("hks.llm.providers.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _make_httpx_response(payload)
        mock_client_cls.return_value = mock_client

        _openai_chat(
            api_key="sk-test",
            endpoint="https://api.openai.com/v1",
            model="gpt-4o-mini",
            messages=[],
        )

        call_kwargs = mock_client.post.call_args[1]
        body = call_kwargs["json"]
        assert body["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# _openai_chat: error path
# ---------------------------------------------------------------------------

def test_openai_chat_raises_on_non_json_content() -> None:
    with patch("hks.llm.providers.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _make_httpx_response("this is not json {{{")
        mock_client_cls.return_value = mock_client

        with pytest.raises(ValueError, match="[Jj][Ss][Oo][Nn]"):
            _openai_chat(
                api_key="sk-test",
                endpoint="https://api.openai.com/v1",
                model="gpt-4o-mini",
                messages=[],
            )


# ---------------------------------------------------------------------------
# OpenAIProvider.extract()
# ---------------------------------------------------------------------------

def _make_openai_provider() -> OpenAIProvider:
    return OpenAIProvider(
        api_key="sk-test",
        endpoint="https://api.openai.com/v1",
        model="gpt-4o-mini",
        timeout_seconds=10,
    )


def _make_extraction_request(provider_id: str = "openai") -> Any:
    from hks.llm.models import LlmExtractionRequest, LlmProviderConfig

    return LlmExtractionRequest(
        source_relpath="docs/test.md",
        provider=LlmProviderConfig(provider_id=provider_id, model_id="gpt-4o-mini"),
    )


def test_openai_provider_extract_calls_openai_chat() -> None:
    expected_result = {
        "classification": [{"label": "general", "confidence": 0.8, "evidence": []}],
        "summary_candidate": "Test summary",
        "key_facts": [],
        "entity_candidates": [],
        "relation_candidates": [],
        "confidence": 0.8,
    }

    request = _make_extraction_request()

    with patch("hks.llm.providers._openai_chat", return_value=expected_result) as mock_chat:
        provider = _make_openai_provider()
        result = provider.extract(request, content="Some content")

    assert result == expected_result
    mock_chat.assert_called_once()
    call_kwargs = mock_chat.call_args[1]
    assert call_kwargs["api_key"] == "sk-test"
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert "messages" in call_kwargs


def test_openai_provider_extract_includes_content_in_messages() -> None:
    content = "Project Atlas is in design phase."
    request = _make_extraction_request()
    expected_result = {"classification": [], "confidence": 0.5}

    with patch("hks.llm.providers._openai_chat", return_value=expected_result) as mock_chat:
        provider = _make_openai_provider()
        provider.extract(request, content=content)

    messages = mock_chat.call_args[1]["messages"]
    all_message_text = " ".join(m.get("content", "") for m in messages)
    assert content in all_message_text or "docs/test.md" in all_message_text


def test_openai_provider_defaults() -> None:
    p = OpenAIProvider(api_key="sk-x")
    assert p.endpoint == "https://api.openai.com/v1"
    assert p.model == "gpt-4o-mini"
    assert p.timeout_seconds == 30


# ---------------------------------------------------------------------------
# provider_for(): dispatch
# ---------------------------------------------------------------------------

def test_provider_for_returns_openai_provider_when_api_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", "sk-real-key")

    request = _make_extraction_request(provider_id="openai")
    result = provider_for(request)

    assert isinstance(result, OpenAIProvider)
    assert result.api_key == "sk-real-key"


def test_provider_for_accepts_openai_api_key_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fallback")

    request = _make_extraction_request(provider_id="openai")
    result = provider_for(request)

    assert isinstance(result, OpenAIProvider)
    assert result.api_key == "sk-fallback"


def test_provider_for_falls_back_to_fake_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    request = _make_extraction_request(provider_id="openai")
    result = provider_for(request)

    assert isinstance(result, FakeProvider)


def test_provider_for_returns_fake_for_fake_provider_id() -> None:
    request = _make_extraction_request(provider_id="fake")
    result = provider_for(request)

    assert isinstance(result, FakeProvider)


def test_provider_for_uses_custom_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", "sk-key")
    monkeypatch.setenv("HKS_LLM_PROVIDER_OPENAI_ENDPOINT", "https://my-proxy.example.com/v1")

    request = _make_extraction_request(provider_id="openai")
    result = provider_for(request)

    assert isinstance(result, OpenAIProvider)
    assert result.endpoint == "https://my-proxy.example.com/v1"

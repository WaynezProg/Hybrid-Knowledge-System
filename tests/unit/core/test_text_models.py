from __future__ import annotations

import json
from typing import Any

import pytest

import hks.core.text_models as text_models
from hks.core.text_models import TextModelBackend
from hks.errors import KSError


class _FakeOpenAIResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> _FakeOpenAIResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@pytest.mark.unit
def test_openai_embedding_backend_posts_to_embeddings_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

    def fake_urlopen(request: Any, *, timeout: float) -> _FakeOpenAIResponse:
        requests.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "headers": dict(request.header_items()),
                "payload": json.loads(request.data.decode("utf-8")),
            }
        )
        return _FakeOpenAIResponse(
            {
                "data": [
                    {"index": 0, "embedding": [3.0, 4.0]},
                    {"index": 1, "embedding": [0.0, 2.0]},
                ]
            }
        )

    monkeypatch.setenv("HKS_OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(text_models, "urlopen", fake_urlopen)

    embeddings = TextModelBackend("openai:text-embedding-3-small").embed_texts(["alpha", "beta"])

    assert embeddings == [[0.6, 0.8], [0.0, 1.0]]
    assert requests == [
        {
            "url": "https://api.openai.com/v1/embeddings",
            "timeout": 60.0,
            "headers": {
                "Authorization": "Bearer test-key",
                "Content-type": "application/json",
            },
            "payload": {
                "model": "text-embedding-3-small",
                "input": ["alpha", "beta"],
                "encoding_format": "float",
            },
        }
    ]


@pytest.mark.unit
def test_openai_embedding_backend_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HKS_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HKS_CONFIG_ENV", raising=False)

    with pytest.raises(KSError) as exc_info:
        TextModelBackend("openai:text-embedding-3-small").embed_texts(["alpha"])

    assert exc_info.value.code == "OPENAI_EMBEDDING_CREDENTIAL_MISSING"


@pytest.mark.unit
def test_openai_embedding_backend_reads_api_key_from_config_file(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "hks.env"
    config_path.write_text(
        "\n".join(
            [
                'export HKS_OPENAI_API_KEY="config-key"',
                "export HKS_OPENAI_EMBEDDING_DIMENSIONS=8",
                "export HKS_OPENAI_TIMEOUT_SECONDS=12",
            ]
        ),
        encoding="utf-8",
    )
    requests: list[dict[str, Any]] = []

    def fake_urlopen(request: Any, *, timeout: float) -> _FakeOpenAIResponse:
        requests.append(
            {
                "timeout": timeout,
                "headers": dict(request.header_items()),
                "payload": json.loads(request.data.decode("utf-8")),
            }
        )
        return _FakeOpenAIResponse({"data": [{"index": 0, "embedding": [1.0, 0.0]}]})

    monkeypatch.delenv("HKS_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("HKS_CONFIG_ENV", str(config_path))
    monkeypatch.setattr(text_models, "urlopen", fake_urlopen)

    embeddings = TextModelBackend("openai:text-embedding-3-small").embed_texts(["alpha"])

    assert embeddings == [[1.0, 0.0]]
    assert requests == [
        {
            "timeout": 12.0,
            "headers": {
                "Authorization": "Bearer config-key",
                "Content-type": "application/json",
            },
            "payload": {
                "model": "text-embedding-3-small",
                "input": ["alpha"],
                "encoding_format": "float",
                "dimensions": 8,
            },
        }
    ]

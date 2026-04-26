"""Tokenizer and embedding helpers for local-first retrieval."""

from __future__ import annotations

import json
import math
import os
import re
import shlex
from functools import cached_property
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from hks.errors import ExitCode, KSError

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SIMPLE_EMBEDDING_MODEL = "simple"
OPENAI_EMBEDDING_PREFIX = "openai:"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_OPENAI_EMBEDDING_ENDPOINT = "https://api.openai.com/v1/embeddings"

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]|[^\s]")


def resolve_embedding_model() -> str:
    return os.environ.get("HKS_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def simple_tokenize(text: str, *, lowercase: bool = False) -> list[str]:
    content = text.lower() if lowercase else text
    return TOKEN_PATTERN.findall(content)


def join_tokens(tokens: list[str]) -> str:
    if not tokens:
        return ""

    pieces: list[str] = [tokens[0]]
    for previous, current in zip(tokens, tokens[1:], strict=False):
        if previous.isalnum() and current.isalnum() and previous.isascii() and current.isascii():
            pieces.append(" ")
        elif previous in {"(", "[", "{", "/"}:
            pass
        elif current in {".", ",", "!", "?", ";", ":", ")", "]", "}", "/", "%"}:
            pass
        elif current.isascii() and current.isalnum() and previous in {"-", "_"}:
            pass
        elif previous.isascii() and previous.isalnum() and current in {"-", "_"}:
            pass
        elif previous.isascii() and previous.isalnum() and current.startswith("'"):
            pass
        elif previous.isascii() and previous.isalnum() and current.isascii():
            pieces.append(" ")
        pieces.append(current)
    return "".join(pieces).strip()


def simple_embed(texts: list[str], *, dimensions: int = 128) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for text in texts:
        vector = [0.0] * dimensions
        for token in simple_tokenize(text, lowercase=True):
            vector[hash(token) % dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        embeddings.append(vector)
    return embeddings


def _normalize_embedding(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def _is_openai_embedding_model(model_name: str) -> bool:
    return model_name.startswith(OPENAI_EMBEDDING_PREFIX)


def _default_config_env_path() -> Path:
    configured = os.environ.get("HKS_CONFIG_ENV")
    if configured:
        return Path(configured).expanduser()

    repo_root = os.environ.get("HKS_REPO_ROOT")
    if repo_root:
        return Path(repo_root).expanduser() / "config" / "hks.env"

    cwd = Path.cwd()
    for root in (cwd, *cwd.parents):
        if (root / "pyproject.toml").exists() and (root / "config").is_dir():
            return root / "config" / "hks.env"
    return cwd / "config" / "hks.env"


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            parts = shlex.split(line, comments=True, posix=True)
        except ValueError:
            continue
        if not parts:
            continue
        if parts[0] == "export":
            parts = parts[1:]
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                values[key] = value
    return values


def _config_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    return _read_env_file(_default_config_env_path()).get(name)


class TextModelBackend:
    """Shared tokenizer/embedding backend with a test-friendly fallback."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or resolve_embedding_model()

    @property
    def supports_token_ids(self) -> bool:
        return self.model_name != SIMPLE_EMBEDDING_MODEL and not _is_openai_embedding_model(
            self.model_name
        )

    @property
    def _openai_model_id(self) -> str:
        model_id = self.model_name.removeprefix(OPENAI_EMBEDDING_PREFIX).strip()
        return model_id or DEFAULT_OPENAI_EMBEDDING_MODEL

    @cached_property
    def _tokenizer(self):  # type: ignore[no-untyped-def]
        if self.model_name == SIMPLE_EMBEDDING_MODEL or _is_openai_embedding_model(
            self.model_name
        ):
            return None

        try:
            from transformers import AutoTokenizer
        except Exception as exc:  # pragma: no cover - import surface
            raise KSError(
                "無法載入 tokenizer",
                exit_code=ExitCode.GENERAL,
                code="TOKENIZER_LOAD_FAILED",
                details=[str(exc)],
                hint="可改設 HKS_EMBEDDING_MODEL=simple 以使用本機 deterministic fallback",
            ) from exc

        try:
            return AutoTokenizer.from_pretrained(self.model_name)
        except Exception as exc:
            raise KSError(
                "無法載入 tokenizer",
                exit_code=ExitCode.GENERAL,
                code="TOKENIZER_LOAD_FAILED",
                details=[str(exc)],
                hint="可改設 HKS_EMBEDDING_MODEL=simple 或指向本機模型目錄",
            ) from exc

    @cached_property
    def _model(self):  # type: ignore[no-untyped-def]
        if self.model_name == SIMPLE_EMBEDDING_MODEL or _is_openai_embedding_model(
            self.model_name
        ):
            return None

        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover - import surface
            raise KSError(
                "無法載入 embedding model",
                exit_code=ExitCode.GENERAL,
                code="EMBEDDING_LOAD_FAILED",
                details=[str(exc)],
                hint="可改設 HKS_EMBEDDING_MODEL=simple 以使用本機 deterministic fallback",
            ) from exc

        try:
            return SentenceTransformer(self.model_name)
        except Exception as exc:
            raise KSError(
                "無法載入 embedding model",
                exit_code=ExitCode.GENERAL,
                code="EMBEDDING_LOAD_FAILED",
                details=[str(exc)],
                hint="可改設 HKS_EMBEDDING_MODEL=simple 或指向本機模型目錄",
            ) from exc

    def tokenize(self, text: str) -> list[str]:
        if self.model_name == SIMPLE_EMBEDDING_MODEL or _is_openai_embedding_model(
            self.model_name
        ):
            return simple_tokenize(text)

        tokenizer = self._tokenizer
        encoded = tokenizer.encode(text, add_special_tokens=False)
        return cast(list[str], tokenizer.convert_ids_to_tokens(encoded))

    def count_tokens(self, text: str) -> int:
        if self.model_name == SIMPLE_EMBEDDING_MODEL or _is_openai_embedding_model(
            self.model_name
        ):
            return len(self.tokenize(text))
        return len(self.encode_token_ids(text))

    def encode_token_ids(self, text: str) -> list[int]:
        if not self.supports_token_ids:
            raise RuntimeError(f"{self.model_name} backend does not expose tokenizer ids")

        tokenizer = self._tokenizer
        return cast(list[int], tokenizer.encode(text, add_special_tokens=False))

    def decode_token_ids(self, token_ids: list[int]) -> str:
        if not self.supports_token_ids:
            raise RuntimeError(f"{self.model_name} backend does not expose tokenizer ids")

        tokenizer = self._tokenizer
        return cast(
            str,
            tokenizer.decode(
                token_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            ),
        ).strip()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.model_name == SIMPLE_EMBEDDING_MODEL:
            return simple_embed(texts)
        if _is_openai_embedding_model(self.model_name):
            return self._embed_openai_texts(texts)

        model = self._model
        embeddings = model.encode(texts, normalize_embeddings=True)
        return cast(list[list[float]], embeddings.tolist())

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def _embed_openai_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        api_key = _config_value("HKS_OPENAI_API_KEY") or _config_value("OPENAI_API_KEY")
        if not api_key:
            raise KSError(
                "缺少 OpenAI embedding API key",
                exit_code=ExitCode.GENERAL,
                code="OPENAI_EMBEDDING_CREDENTIAL_MISSING",
                hint="設定 HKS_OPENAI_API_KEY 或 OPENAI_API_KEY",
            )

        payload: dict[str, object] = {
            "model": self._openai_model_id,
            "input": texts,
            "encoding_format": "float",
        }
        dimensions = _config_value("HKS_OPENAI_EMBEDDING_DIMENSIONS")
        if dimensions:
            try:
                payload["dimensions"] = int(dimensions)
            except ValueError as exc:
                raise KSError(
                    "HKS_OPENAI_EMBEDDING_DIMENSIONS 必須是整數",
                    exit_code=ExitCode.USAGE,
                    code="OPENAI_EMBEDDING_INVALID_DIMENSIONS",
                ) from exc

        endpoint = _config_value("HKS_OPENAI_EMBEDDING_ENDPOINT") or os.environ.get(
            "HKS_OPENAI_EMBEDDING_ENDPOINT",
            DEFAULT_OPENAI_EMBEDDING_ENDPOINT,
        )
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        timeout = float(_config_value("HKS_OPENAI_TIMEOUT_SECONDS") or "60")

        try:
            with urlopen(request, timeout=timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise KSError(
                "OpenAI embedding request failed",
                exit_code=ExitCode.GENERAL,
                code="OPENAI_EMBEDDING_FAILED",
                details=[detail],
            ) from exc
        except (OSError, URLError, ValueError) as exc:
            raise KSError(
                "OpenAI embedding request failed",
                exit_code=ExitCode.GENERAL,
                code="OPENAI_EMBEDDING_FAILED",
                details=[str(exc)],
            ) from exc

        data = response_payload.get("data")
        if not isinstance(data, list):
            raise KSError(
                "OpenAI embedding response missing data",
                exit_code=ExitCode.GENERAL,
                code="OPENAI_EMBEDDING_INVALID_RESPONSE",
            )

        embeddings: list[list[float] | None] = [None] * len(texts)
        for item in data:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            embedding = item.get("embedding")
            if not isinstance(index, int) or not isinstance(embedding, list):
                continue
            if 0 <= index < len(embeddings):
                embeddings[index] = _normalize_embedding([float(value) for value in embedding])

        if any(embedding is None for embedding in embeddings):
            raise KSError(
                "OpenAI embedding response count mismatch",
                exit_code=ExitCode.GENERAL,
                code="OPENAI_EMBEDDING_INVALID_RESPONSE",
            )

        return [embedding for embedding in embeddings if embedding is not None]

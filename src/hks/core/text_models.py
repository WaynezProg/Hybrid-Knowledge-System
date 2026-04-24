"""Tokenizer and embedding helpers for local-first retrieval."""

from __future__ import annotations

import math
import os
import re
from functools import cached_property
from typing import cast

from hks.errors import ExitCode, KSError

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SIMPLE_EMBEDDING_MODEL = "simple"

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


class TextModelBackend:
    """Shared tokenizer/embedding backend with a test-friendly fallback."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or resolve_embedding_model()

    @cached_property
    def _tokenizer(self):  # type: ignore[no-untyped-def]
        if self.model_name == SIMPLE_EMBEDDING_MODEL:
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
        if self.model_name == SIMPLE_EMBEDDING_MODEL:
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
        if self.model_name == SIMPLE_EMBEDDING_MODEL:
            return simple_tokenize(text)

        tokenizer = self._tokenizer
        encoded = tokenizer.encode(text, add_special_tokens=False)
        return cast(list[str], tokenizer.convert_ids_to_tokens(encoded))

    def count_tokens(self, text: str) -> int:
        if self.model_name == SIMPLE_EMBEDDING_MODEL:
            return len(self.tokenize(text))
        return len(self.encode_token_ids(text))

    def encode_token_ids(self, text: str) -> list[int]:
        if self.model_name == SIMPLE_EMBEDDING_MODEL:
            raise RuntimeError("simple backend does not expose tokenizer ids")

        tokenizer = self._tokenizer
        return cast(list[int], tokenizer.encode(text, add_special_tokens=False))

    def decode_token_ids(self, token_ids: list[int]) -> str:
        if self.model_name == SIMPLE_EMBEDDING_MODEL:
            raise RuntimeError("simple backend does not expose tokenizer ids")

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

        model = self._model
        embeddings = model.encode(texts, normalize_embeddings=True)
        return cast(list[list[float]], embeddings.tolist())

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

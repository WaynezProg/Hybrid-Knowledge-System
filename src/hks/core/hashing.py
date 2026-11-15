"""Shared stable hashing helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_json_hash(payload: Any, *, length: int | None = None) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _truncate(hashlib.sha256(canonical.encode("utf-8")).hexdigest(), length)


def stable_content_hash(content: str | bytes, *, length: int | None = None) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return _truncate(hashlib.sha256(data).hexdigest(), length)


def _truncate(value: str, length: int | None) -> str:
    if length is None:
        return value
    if length < 1:
        raise ValueError("hash length must be positive")
    return value[:length]

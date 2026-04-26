from __future__ import annotations

from hks.llm.config import build_request


def test_extraction_request_idempotency_key_changes_with_model() -> None:
    first = build_request(source_relpath="project-atlas.txt", model="model-a")
    second = build_request(source_relpath="project-atlas.txt", model="model-b")

    assert first.idempotency_key(source_fingerprint="sha", parser_fingerprint="txt:v1") != (
        second.idempotency_key(source_fingerprint="sha", parser_fingerprint="txt:v1")
    )

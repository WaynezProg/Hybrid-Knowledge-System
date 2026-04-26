from __future__ import annotations

from hks.graphify.models import GraphifyRequest


def test_graphify_idempotency_key_uses_force_salt() -> None:
    request = GraphifyRequest(force_new_run=True)

    first = request.idempotency_key(input_fingerprint="abc", created_at_iso="t1")
    second = request.idempotency_key(input_fingerprint="abc", created_at_iso="t2")

    assert first != second


def test_graphify_idempotency_key_stable_without_force() -> None:
    request = GraphifyRequest()

    assert request.idempotency_key(input_fingerprint="abc") == request.idempotency_key(
        input_fingerprint="abc"
    )

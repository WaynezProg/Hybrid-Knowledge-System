from __future__ import annotations

from typing import cast

import pytest

from hks.writeback.gate import WritebackFlag, decide


@pytest.mark.unit
@pytest.mark.parametrize(
    ("flag", "confidence", "is_tty", "expected_action", "expected_status"),
    [
        ("auto", 0.9, False, "enqueue", "enqueued"),
        ("auto", 0.2, False, "enqueue", "enqueued"),
        ("yes", 0.1, True, "enqueue", "enqueued"),
        ("yes", 0.1, False, "enqueue", "enqueued"),
        ("no", 0.9, True, "skip", "declined"),
        ("no", 0.9, False, "skip", "declined"),
        ("ask", 0.9, False, "skip-non-tty", "skip-non-tty"),
    ],
)
def test_decide_without_prompt(
    flag: str,
    confidence: float,
    is_tty: bool,
    expected_action: str,
    expected_status: str,
) -> None:
    decision = decide(
        cast(WritebackFlag, flag),
        confidence=confidence,
        is_tty=is_tty,
        prompt=lambda: True,
    )

    assert decision.action == expected_action
    assert decision.status == expected_status
    if flag == "yes":
        assert decision.forced is True


@pytest.mark.unit
def test_decide_ask_tty_uses_prompt() -> None:
    decision = decide("ask", confidence=0.9, is_tty=True, prompt=lambda: False)

    assert decision.action == "skip"
    assert decision.status == "declined"


@pytest.mark.unit
def test_decide_ask_tty_enqueue_when_prompt_confirms() -> None:
    decision = decide("ask", confidence=0.0, is_tty=True, prompt=lambda: True)

    assert decision.action == "enqueue"
    assert decision.status == "enqueued"

from __future__ import annotations

from typing import cast

import pytest

from hks.writeback.gate import WritebackFlag, decide


@pytest.mark.unit
@pytest.mark.parametrize(
    ("flag", "is_tty", "expected_action", "expected_status"),
    [
        ("auto", False, "enqueue", "enqueued"),
        ("yes", True, "enqueue", "enqueued"),
        ("yes", False, "enqueue", "enqueued"),
        ("no", True, "skip", "declined"),
        ("no", False, "skip", "declined"),
        ("ask", False, "skip-non-tty", "skip-non-tty"),
    ],
)
def test_decide_without_prompt(
    flag: str,
    is_tty: bool,
    expected_action: str,
    expected_status: str,
) -> None:
    decision = decide(
        cast(WritebackFlag, flag),
        is_tty=is_tty,
        prompt=lambda: True,
    )

    assert decision.action == expected_action
    assert decision.status == expected_status


@pytest.mark.unit
def test_decide_ask_tty_uses_prompt() -> None:
    decision = decide("ask", is_tty=True, prompt=lambda: False)

    assert decision.action == "skip"
    assert decision.status == "declined"


@pytest.mark.unit
def test_decide_ask_tty_enqueue_when_prompt_confirms() -> None:
    decision = decide("ask", is_tty=True, prompt=lambda: True)

    assert decision.action == "enqueue"
    assert decision.status == "enqueued"

from __future__ import annotations

from typing import cast

import pytest

from hks.writeback.gate import WritebackFlag, decide


@pytest.mark.unit
@pytest.mark.parametrize(
    ("flag", "confidence", "is_tty", "expected"),
    [
        ("auto", 0.9, False, "auto-committed"),
        ("auto", 0.2, False, "auto-skipped-low-confidence"),
        ("yes", 0.1, True, "committed"),
        ("yes", 0.1, False, "committed"),
        ("no", 0.9, True, "declined"),
        ("no", 0.9, False, "declined"),
        ("ask", 0.9, False, "skip-non-tty"),
    ],
)
def test_decide_without_prompt(flag: str, confidence: float, is_tty: bool, expected: str) -> None:
    decision = decide(
        cast(WritebackFlag, flag),
        confidence=confidence,
        is_tty=is_tty,
        prompt=lambda: True,
    )

    assert decision.status == expected


@pytest.mark.unit
def test_decide_ask_tty_uses_prompt() -> None:
    decision = decide("ask", confidence=0.9, is_tty=True, prompt=lambda: False)

    assert decision.status == "declined"

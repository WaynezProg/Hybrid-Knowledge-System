from __future__ import annotations

from typing import cast

import pytest

from hks.writeback.gate import WritebackFlag, decide


@pytest.mark.unit
@pytest.mark.parametrize(
    ("flag", "is_tty", "expected"),
    [
        ("yes", True, "committed"),
        ("yes", False, "committed"),
        ("no", True, "declined"),
        ("no", False, "declined"),
        ("ask", False, "skip-non-tty"),
    ],
)
def test_decide_without_prompt(flag: str, is_tty: bool, expected: str) -> None:
    decision = decide(cast(WritebackFlag, flag), is_tty=is_tty, prompt=lambda: True)

    assert decision.status == expected


@pytest.mark.unit
def test_decide_ask_tty_uses_prompt() -> None:
    decision = decide("ask", is_tty=True, prompt=lambda: False)

    assert decision.status == "declined"

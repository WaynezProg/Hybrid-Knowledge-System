"""Write-back decision helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import typer

type WritebackFlag = Literal["yes", "no", "ask"]
type DecisionAction = Literal["commit", "decline", "skip-non-tty"]


@dataclass(frozen=True, slots=True)
class Decision:
    action: DecisionAction
    status: str


def prompt_user() -> bool:
    return bool(typer.confirm("回寫 wiki?", default=False))


def decide(
    flag: WritebackFlag,
    *,
    is_tty: bool,
    prompt: Callable[[], bool] | None = None,
) -> Decision:
    if flag == "yes":
        return Decision(action="commit", status="committed")
    if flag == "no":
        return Decision(action="decline", status="declined")
    if not is_tty:
        return Decision(action="skip-non-tty", status="skip-non-tty")
    confirmed = prompt() if prompt is not None else prompt_user()
    if confirmed:
        return Decision(action="commit", status="committed")
    return Decision(action="decline", status="declined")

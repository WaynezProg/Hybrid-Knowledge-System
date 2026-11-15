"""Write-back intent helpers: what the caller asked for, not whether the answer is good.

Eligibility for ``auto`` is checked by the query flow against ``writeback_eligible``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import typer

type WritebackFlag = Literal["auto", "yes", "no", "ask"]
type DecisionAction = Literal["enqueue", "skip", "skip-non-tty"]
type DecisionStatus = Literal["enqueued", "declined", "skip-non-tty"]


@dataclass(frozen=True, slots=True)
class Decision:
    action: DecisionAction
    status: DecisionStatus


def prompt_user() -> bool:
    return bool(typer.confirm("送入 write-back review queue?", default=False))


def decide(
    flag: WritebackFlag,
    *,
    is_tty: bool,
    prompt: Callable[[], bool] | None = None,
) -> Decision:
    if flag == "yes":
        return Decision(action="enqueue", status="enqueued")
    if flag == "no":
        return Decision(action="skip", status="declined")
    if flag == "auto":
        return Decision(action="enqueue", status="enqueued")
    if not is_tty:
        return Decision(action="skip-non-tty", status="skip-non-tty")
    confirmed = prompt() if prompt is not None else prompt_user()
    if confirmed:
        return Decision(action="enqueue", status="enqueued")
    return Decision(action="skip", status="declined")

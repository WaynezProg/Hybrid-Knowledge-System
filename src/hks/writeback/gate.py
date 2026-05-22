"""Write-back decision helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import typer

if TYPE_CHECKING:
    from hks.retrieval.confidence import ConfidenceAssessment

type WritebackFlag = Literal["auto", "yes", "no", "ask"]
type DecisionAction = Literal["enqueue", "skip", "skip-non-tty"]
type DecisionStatus = Literal["enqueued", "declined", "skip-non-tty"]


@dataclass(frozen=True, slots=True)
class Decision:
    action: DecisionAction
    status: DecisionStatus
    forced: bool = False


def prompt_user() -> bool:
    return bool(typer.confirm("回寫 wiki?", default=False))


def decide(
    flag: WritebackFlag,
    *,
    assessment: ConfidenceAssessment | None = None,
    confidence: float | None = None,
    is_tty: bool,
    prompt: Callable[[], bool] | None = None,
) -> Decision:
    if flag == "yes":
        return Decision(action="enqueue", status="enqueued", forced=True)
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

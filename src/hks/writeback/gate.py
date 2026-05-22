"""Write-back decision helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import typer

from hks.core.config import config_value
from hks.storage.wiki import EventStatus

if TYPE_CHECKING:
    from hks.retrieval.confidence import ConfidenceAssessment

type WritebackFlag = Literal["auto", "yes", "no", "ask"]
type DecisionAction = Literal["commit", "decline", "skip-non-tty"]


@dataclass(frozen=True, slots=True)
class Decision:
    action: DecisionAction
    status: EventStatus
    forced: bool = False


def prompt_user() -> bool:
    return bool(typer.confirm("回寫 wiki?", default=False))


def auto_threshold() -> float:
    return float(config_value("HKS_WRITEBACK_AUTO_THRESHOLD") or "0.75")


def decide(
    flag: WritebackFlag,
    *,
    assessment: ConfidenceAssessment | None = None,
    confidence: float | None = None,
    is_tty: bool,
    prompt: Callable[[], bool] | None = None,
) -> Decision:
    if flag == "yes":
        return Decision(action="commit", status="forced-committed", forced=True)
    if flag == "no":
        return Decision(action="decline", status="declined")
    if flag == "auto":
        if assessment is not None:
            return _decide_auto_with_assessment(assessment)
        raw_confidence = confidence if confidence is not None else 0.0
        if raw_confidence >= auto_threshold():
            return Decision(action="commit", status="auto-committed")
        return Decision(action="decline", status="auto-skipped-low-confidence")
    if not is_tty:
        return Decision(action="skip-non-tty", status="skip-non-tty")
    confirmed = prompt() if prompt is not None else prompt_user()
    if confirmed:
        return Decision(action="commit", status="committed")
    return Decision(action="decline", status="declined")


def _decide_auto_with_assessment(assessment: ConfidenceAssessment) -> Decision:
    if not assessment.writeback_eligible:
        return Decision(action="decline", status="auto-skipped-ineligible")
    if assessment.calibrated_confidence >= assessment.auto_threshold:
        return Decision(action="commit", status="auto-committed")
    return Decision(action="decline", status="auto-skipped-low-confidence")

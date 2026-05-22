"""Tests for writeback gate with ConfidenceAssessment."""

from __future__ import annotations

from hks.retrieval.confidence import ConfidenceAssessment
from hks.writeback.gate import decide


def _eligible(score: float = 0.9, auto_threshold: float = 0.75) -> ConfidenceAssessment:
    return ConfidenceAssessment(
        retrieval_score=score,
        confidence=score,
        writeback_eligible=True,
        auto_threshold=auto_threshold,
        reasons=["test eligible"],
    )


def _ineligible(score: float = 0.9, auto_threshold: float = 0.75) -> ConfidenceAssessment:
    return ConfidenceAssessment(
        retrieval_score=score,
        confidence=score,
        writeback_eligible=False,
        auto_threshold=auto_threshold,
        reasons=["test ineligible"],
    )


class TestDecideWithAssessment:
    def test_auto_eligible_above_threshold_enqueues(self) -> None:
        decision = decide("auto", assessment=_eligible(0.9), is_tty=False)
        assert decision.action == "enqueue"
        assert decision.status == "enqueued"

    def test_auto_ineligible_despite_high_score_still_enqueues_intent(self) -> None:
        decision = decide("auto", assessment=_ineligible(0.99), is_tty=False)
        assert decision.action == "enqueue"
        assert decision.status == "enqueued"

    def test_auto_eligible_below_threshold_still_enqueues_intent(self) -> None:
        decision = decide("auto", assessment=_eligible(0.3), is_tty=False)
        assert decision.action == "enqueue"
        assert decision.status == "enqueued"

    def test_yes_forces_enqueue_regardless_of_eligibility(self) -> None:
        decision = decide("yes", assessment=_ineligible(0.1), is_tty=False)
        assert decision.action == "enqueue"
        assert decision.status == "enqueued"
        assert decision.forced is True

    def test_yes_with_eligible_still_forced(self) -> None:
        decision = decide("yes", assessment=_eligible(0.9), is_tty=True)
        assert decision.forced is True

    def test_no_always_declines(self) -> None:
        decision = decide("no", assessment=_eligible(0.9), is_tty=False)
        assert decision.action == "skip"

    def test_ask_non_tty_skips(self) -> None:
        decision = decide("ask", assessment=_eligible(0.9), is_tty=False)
        assert decision.action == "skip-non-tty"

    def test_auto_ignores_per_route_threshold(self) -> None:
        decision = decide("auto", assessment=_eligible(0.70, auto_threshold=0.65), is_tty=False)
        assert decision.action == "enqueue"
        assert decision.status == "enqueued"

    def test_auto_ignores_below_per_route_threshold(self) -> None:
        decision = decide("auto", assessment=_eligible(0.45, auto_threshold=0.50), is_tty=False)
        assert decision.action == "enqueue"
        assert decision.status == "enqueued"


class TestDecideBackwardCompat:
    """confidence kwarg is accepted but does not decide gate intent."""

    def test_confidence_kwarg_high_enqueues_auto_intent(self) -> None:
        decision = decide("auto", confidence=0.9, is_tty=False)
        assert decision.action == "enqueue"
        assert decision.status == "enqueued"

    def test_confidence_kwarg_low_still_enqueues_auto_intent(self) -> None:
        decision = decide("auto", confidence=0.2, is_tty=False)
        assert decision.action == "enqueue"
        assert decision.status == "enqueued"

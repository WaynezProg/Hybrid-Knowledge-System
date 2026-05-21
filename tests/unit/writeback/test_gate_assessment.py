"""Tests for writeback gate with ConfidenceAssessment."""

from __future__ import annotations

from hks.retrieval.confidence import ConfidenceAssessment
from hks.writeback.gate import decide


def _eligible(score: float = 0.9) -> ConfidenceAssessment:
    return ConfidenceAssessment(
        retrieval_score=score,
        calibrated_confidence=score,
        writeback_eligible=True,
        reasons=["test eligible"],
    )


def _ineligible(score: float = 0.9) -> ConfidenceAssessment:
    return ConfidenceAssessment(
        retrieval_score=score,
        calibrated_confidence=score,
        writeback_eligible=False,
        reasons=["test ineligible"],
    )


class TestDecideWithAssessment:
    def test_auto_eligible_above_threshold_commits(self) -> None:
        decision = decide("auto", assessment=_eligible(0.9), is_tty=False)
        assert decision.action == "commit"
        assert decision.status == "auto-committed"

    def test_auto_ineligible_despite_high_score_declines(self) -> None:
        decision = decide("auto", assessment=_ineligible(0.99), is_tty=False)
        assert decision.action == "decline"
        assert decision.status == "auto-skipped-ineligible"

    def test_auto_eligible_below_threshold_declines(self) -> None:
        decision = decide("auto", assessment=_eligible(0.3), is_tty=False)
        assert decision.action == "decline"
        assert decision.status == "auto-skipped-low-confidence"

    def test_yes_forces_commit_regardless_of_eligibility(self) -> None:
        decision = decide("yes", assessment=_ineligible(0.1), is_tty=False)
        assert decision.action == "commit"
        assert decision.status == "forced-committed"
        assert decision.forced is True

    def test_yes_with_eligible_still_forced(self) -> None:
        decision = decide("yes", assessment=_eligible(0.9), is_tty=True)
        assert decision.forced is True

    def test_no_always_declines(self) -> None:
        decision = decide("no", assessment=_eligible(0.9), is_tty=False)
        assert decision.action == "decline"

    def test_ask_non_tty_skips(self) -> None:
        decision = decide("ask", assessment=_eligible(0.9), is_tty=False)
        assert decision.action == "skip-non-tty"


class TestDecideBackwardCompat:
    """decide() still works with confidence kwarg for callers not yet migrated."""

    def test_confidence_kwarg_still_works(self) -> None:
        decision = decide("auto", confidence=0.9, is_tty=False)
        assert decision.action == "commit"
        assert decision.status == "auto-committed"

    def test_confidence_kwarg_low_declines(self) -> None:
        decision = decide("auto", confidence=0.2, is_tty=False)
        assert decision.action == "decline"

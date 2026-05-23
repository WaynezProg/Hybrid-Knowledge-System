from __future__ import annotations

from datetime import date

from hks.routing.session_memory import analyze_session_memory_intent


def test_detects_yesterday_session_memory_intent() -> None:
    intent = analyze_session_memory_intent(
        "昨天 vibe coding 做了什麼",
        today=date(2026, 5, 23),
    )

    assert intent is not None
    assert intent.date == "2026-05-22"


def test_detects_explicit_session_memory_date() -> None:
    intent = analyze_session_memory_intent("2026/5/22 vibe coding 影響什麼")

    assert intent is not None
    assert intent.date == "2026-05-22"

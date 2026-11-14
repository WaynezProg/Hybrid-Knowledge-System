from __future__ import annotations

from datetime import date

import pytest

from hks.routing.session_memory import analyze_session_memory_intent
from hks.routing.session_memory_dates import parse_session_memory_date_range


@pytest.mark.parametrize(
    ("question", "expected_start", "expected_end"),
    [
        ("25~27 之間 project 做了哪些", "2026-05-25", "2026-05-27"),
        ("5/25-5/29 做了什麼", "2026-05-25", "2026-05-29"),
        ("2026-05-25 到 2026-05-29 進度", "2026-05-25", "2026-05-29"),
        ("2026/5/25 至 2026/5/29 狀態", "2026-05-25", "2026-05-29"),
    ],
)
def test_parse_session_memory_date_range_formats(
    question: str,
    expected_start: str,
    expected_end: str,
) -> None:
    parsed = parse_session_memory_date_range(
        question,
        today=date(2026, 5, 30),
    )
    assert parsed is not None
    assert parsed.date_start == expected_start
    assert parsed.date_end == expected_end


def test_parse_day_tilde_rolls_back_to_previous_month_when_future() -> None:
    parsed = parse_session_memory_date_range(
        "25~27 之間 project 做了哪些",
        today=date(2026, 6, 1),
    )
    assert parsed is not None
    assert parsed.date_start == "2026-05-25"
    assert parsed.date_end == "2026-05-27"


def test_parse_day_tilde_future_range_rolls_back_across_year() -> None:
    parsed = parse_session_memory_date_range(
        "25~27 做了什麼",
        today=date(2026, 1, 5),
    )
    assert parsed is not None
    assert parsed.date_start == "2025-12-25"
    assert parsed.date_end == "2025-12-27"


def test_parse_day_tilde_keeps_current_month_once_the_range_has_started() -> None:
    parsed = parse_session_memory_date_range(
        "25~27 做了什麼",
        today=date(2026, 5, 26),
    )
    assert parsed is not None
    assert parsed.date_start == "2026-05-25"
    assert parsed.date_end == "2026-05-27"


def test_parse_day_tilde_is_not_a_range_when_previous_month_lacks_the_day() -> None:
    assert (
        parse_session_memory_date_range(
            "30~31 做了什麼",
            today=date(2026, 3, 5),
        )
        is None
    )


def test_parse_slash_range_in_the_future_is_left_as_written() -> None:
    parsed = parse_session_memory_date_range(
        "5/25-5/29 做了什麼",
        today=date(2026, 3, 1),
    )
    assert parsed is not None
    assert parsed.date_start == "2026-05-25"
    assert parsed.date_end == "2026-05-29"


def test_parse_swaps_inverted_range() -> None:
    parsed = parse_session_memory_date_range(
        "27~25 做了什麼",
        today=date(2026, 5, 30),
    )
    assert parsed is not None
    assert parsed.date_start == "2026-05-25"
    assert parsed.date_end == "2026-05-27"
    assert parsed.swapped is True


def test_parse_invalid_range_returns_none() -> None:
    assert (
        parse_session_memory_date_range(
            "2/30~2/31",
            today=date(2026, 5, 30),
        )
        is None
    )


def test_analyze_session_memory_intent_detects_date_range() -> None:
    intent = analyze_session_memory_intent(
        "25~27 之間 project 做了哪些事情",
        today=date(2026, 5, 30),
    )
    assert intent is not None
    assert intent.date is None
    assert intent.date_start == "2026-05-25"
    assert intent.date_end == "2026-05-27"


def test_analyze_range_with_workspace() -> None:
    intent = analyze_session_memory_intent(
        "5/25-5/29 social-bank-check 做了什麼",
        today=date(2026, 5, 30),
    )
    assert intent is not None
    assert intent.workspace == "social-bank-check"
    assert intent.date_start == "2026-05-25"
    assert intent.date_end == "2026-05-29"

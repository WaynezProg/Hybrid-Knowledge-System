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


@pytest.mark.parametrize(
    ("today", "expected_start", "expected_end"),
    [
        (date(2027, 1, 5), "2026-12-28", "2027-01-03"),  # 跨年後問：去年底到今年初
        (date(2026, 12, 30), "2026-12-28", "2027-01-03"),  # 區間已開始：今年底到明年初
    ],
)
def test_parse_slash_range_across_new_year(
    today: date, expected_start: str, expected_end: str
) -> None:
    parsed = parse_session_memory_date_range("12/28-1/3 做了什麼", today=today)
    assert parsed is not None
    assert (parsed.date_start, parsed.date_end) == (expected_start, expected_end)
    assert parsed.swapped is False


def test_parse_reversed_slash_range_is_still_swapped_not_cross_year() -> None:
    # 讀成跨年是 295 天、讀成寫反是 70 天：取較短的「寫反」。
    parsed = parse_session_memory_date_range("5/10-3/1 做了什麼", today=date(2026, 6, 1))
    assert parsed is not None
    assert (parsed.date_start, parsed.date_end) == ("2026-03-01", "2026-05-10")
    assert parsed.swapped is True


@pytest.mark.parametrize(
    "question",
    [
        "列出 3~5 個重點",
        "給我 3～5 項建議",
        "大概 3~5 天能完成嗎",
        "第 2~4 章在講什麼",
        "第2~4題",
        "10~20% 的使用者",
        "1.5~2.5 倍",
        "v1~3 的差異",
        "3~5點開會",
        "3~5 次會議",
        "3~5 人小組",
        "分成 3~5 組",
        "每頁 10~12 行",
        "打 7~8 成",
        "10~12GB 的檔案",
        "10~12 MB",
        "10~20KB",
        "10~12px 的邊距",
        "3~5 days 內完成",
        "10~20k 的預算",
    ],
)
def test_count_and_measure_ranges_are_not_dates(question: str) -> None:
    assert parse_session_memory_date_range(question, today=date(2026, 11, 15)) is None


@pytest.mark.parametrize(
    "question",
    ["25~27 之間 project 做了哪些", "25~27日 做了什麼", "25～27號 的進度"],
)
def test_day_ranges_with_date_context_still_parse(question: str) -> None:
    parsed = parse_session_memory_date_range(question, today=date(2026, 6, 1))
    assert parsed is not None
    assert (parsed.date_start, parsed.date_end) == ("2026-05-25", "2026-05-27")


@pytest.mark.parametrize(
    "question",
    [
        "25~27 行程",
        "25~27 分析了什麼",
        "10~12 成果",
        "10~12 天氣",
        "10~12 週報",
        "10~12 HKS 做了什麼",
        "10~12 project 進度",
        "10~12 hks-dev 做了什麼",
        "10~12 mcp 進度",
    ],
)
def test_day_ranges_followed_by_unit_like_words_still_parse(question: str) -> None:
    # 「行、分、成、天、週」與英文字母開頭的詞不是單位：後面是名詞、動詞或 workspace。
    parsed = parse_session_memory_date_range(question, today=date(2026, 11, 28))
    assert parsed is not None
    day_start, day_end = question.split()[0].split("~")
    assert (parsed.date_start, parsed.date_end) == (
        f"2026-11-{day_start}",
        f"2026-11-{day_end}",
    )


def test_count_range_question_has_no_session_memory_date_intent() -> None:
    intent = analyze_session_memory_intent("列出 3~5 個重點", today=date(2026, 11, 15))
    assert intent is None or (intent.date_start is None and intent.date_end is None)


_WORDED_RANGES = [
    "12月20日到1月5日",
    "12月20日至1月5日",
    "12月20日~1月5日",
    "12月20號到1月5號",
    "12 月 20 日 到 1 月 5 日",
    "12/20到1/5",
    "12/20至1/5",
    "12/20 到 1/5",
    "12/20～1/5",
]


@pytest.mark.parametrize("question", _WORDED_RANGES)
@pytest.mark.parametrize(
    "today",
    [date(2026, 11, 15), date(2026, 12, 30), date(2027, 1, 10)],
)
def test_worded_month_day_ranges_match_the_slash_form(question: str, today: date) -> None:
    expected = parse_session_memory_date_range("12/20-1/5 做了什麼", today=today)
    assert expected is not None
    assert parse_session_memory_date_range(f"{question} 做了什麼", today=today) == expected


def test_worded_range_across_new_year_values() -> None:
    parsed = parse_session_memory_date_range("12月20日到1月5日的進度", today=date(2027, 1, 10))
    assert parsed is not None
    assert (parsed.date_start, parsed.date_end) == ("2026-12-20", "2027-01-05")
    assert parsed.swapped is False


@pytest.mark.parametrize(
    "question",
    ["12月20日到25日 做了什麼", "12月20號~25號", "12月20日到25 行程"],
)
def test_worded_range_with_second_month_omitted_is_same_month(question: str) -> None:
    parsed = parse_session_memory_date_range(question, today=date(2026, 12, 30))
    assert parsed is not None
    assert (parsed.date_start, parsed.date_end) == ("2026-12-20", "2026-12-25")


def test_worded_reversed_range_is_swapped_like_the_slash_form() -> None:
    today = date(2026, 6, 1)
    parsed = parse_session_memory_date_range("5月10日到3月1日 做了什麼", today=today)
    assert parsed == parse_session_memory_date_range("5/10-3/1 做了什麼", today=today)
    assert parsed is not None and parsed.swapped is True


@pytest.mark.parametrize(
    "question",
    [
        "3月到5月的營收",
        "1到5個重點",
        "3點到5點開會",
        "2月30日到3月1日",
        "2/30到3/1",
        "12月20日到3個重點",
        "1月5日到10次",
        "12月20日到25.5",
        "2026年12月20日到1月5日",
    ],
)
def test_worded_non_dates_and_invalid_dates_are_not_ranges(question: str) -> None:
    assert parse_session_memory_date_range(question, today=date(2026, 11, 15)) is None


@pytest.mark.parametrize(
    "question",
    ["12月20日到1月5日 social-bank-check 的進度", "12/20 到 1/5 social-bank-check 的進度"],
)
def test_analyze_worded_range_routes_like_the_slash_form(question: str) -> None:
    today = date(2027, 1, 10)
    expected = analyze_session_memory_intent("12/20-1/5 social-bank-check 的進度", today=today)
    assert expected is not None and expected.date_start == "2026-12-20"
    assert analyze_session_memory_intent(question, today=today) == expected

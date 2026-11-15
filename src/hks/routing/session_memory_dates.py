"""Session-memory natural-language date range parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from re import Match


@dataclass(frozen=True, slots=True)
class ParsedDateRange:
    date_start: str
    date_end: str
    swapped: bool = False


_FULL_RANGE_RE = re.compile(
    r"(?P<y1>20\d{2})[-/年](?P<m1>\d{1,2})[-/月](?P<d1>\d{1,2})日?"
    r"\s*(?:到|至|~|－|-)\s*"
    r"(?P<y2>20\d{2})[-/年](?P<m2>\d{1,2})[-/月](?P<d2>\d{1,2})日?",
)

# 區間的連接詞：`12/20-1/5`、`12/20到1/5`、`12月20日至1月5日`。
_RANGE_SEP = r"(?:到|至|[-~～－])"

_SLASH_RANGE_RE = re.compile(
    rf"(?P<m1>\d{{1,2}})/(?P<d1>\d{{1,2}})\s*{_RANGE_SEP}\s*(?P<m2>\d{{1,2}})/(?P<d2>\d{{1,2}})"
)

# 數量、序號、時長常寫成 N~M（「3~5 個重點」「第 2~4 章」「3~5 天」），
# 這些後面接單位或前面有「第」時不是日期區間。
_CJK_UNIT = (
    r"個|个|項|项|點|点|條|条|次|天|週|周|月|年|歲|岁|人|名|位|頁|页|行|筆|笔|件|"
    r"句|段|步|章|節|节|題|题|組|组|倍|成|份|張|张|篇|分|秒|小時|小时|%|％"
)

# 量詞開頭、但其實是一般名詞或動詞的詞（「25~27 行程」「10~12 週報」）。
# 日期後面常接這些詞，不能只看第一個字就當成單位。
_UNIT_LED_WORD = (
    r"行程|行事|行動|行銷|分析|分享|分類|分支|分工|成果|成本|成員|成績|成效|成功|成長|"
    r"天氣|週報|週會|週記|周報|周會|周記|月報|月會|年度|年報|人事|組織|組員|題目|節目"
)

# 英文只認列舉的單位，且後面不能再接英數字：「10~12 GB」是數量，
# 「10~12 HKS 做了什麼」「10~12 project 進度」後面是 workspace 或一般單字。
_LATIN_UNIT = (
    r"(?i:[kmgt]b|px|pt|r?em|ms|kg|km|cm|mm|k|x|hrs?|mins?|secs?|"
    r"days?|weeks?|months?|years?|hours?|minutes?|seconds?|items?|times)(?![A-Za-z0-9])"
)

_COUNT_UNIT = rf"(?!{_UNIT_LED_WORD})(?:{_CJK_UNIT})|{_LATIN_UNIT}"

# `12月20日到1月5日`、`12月20號~25號`：第二個月份可省略（同月）。前面有「年」時
# 交給寫了年份的形式處理，不在這裡補今年。省略月份又沒寫「日／號」的結尾數字
# 後面接單位時（`12月20日到3個重點`）不是日期。
_MONTH_DAY_RANGE_RE = re.compile(
    r"(?<![\d年/.])(?P<m1>\d{1,2})\s*月\s*(?P<d1>\d{1,2})\s*[日號号]?"
    rf"\s*{_RANGE_SEP}\s*"
    r"(?:(?P<m2>\d{1,2})\s*月\s*(?P<d2>\d{1,2})(?:\s*[日號号]|(?![\d.]))"
    rf"|(?P<d2s>\d{{1,2}})(?:\s*[日號号]|(?![\d.月])(?!\s*(?:{_COUNT_UNIT}))))"
)

_DAY_TILDE_RE = re.compile(
    r"(?<![\d/.A-Za-z第])(?P<d1>\d{1,2})\s*[~～]\s*(?P<d2>\d{1,2})"
    rf"(?![\d.])(?!\s*/)(?!\s*(?:{_COUNT_UNIT}))"
)


def parse_session_memory_date_range(
    question: str,
    *,
    today: date,
) -> ParsedDateRange | None:
    for pattern, builder in (
        (_FULL_RANGE_RE, _from_full_match),
        (_SLASH_RANGE_RE, _from_slash_match),
        (_MONTH_DAY_RANGE_RE, _from_month_day_match),
        (_DAY_TILDE_RE, _from_day_tilde_match),
    ):
        match = pattern.search(question)
        if match is None:
            continue
        parsed = builder(match, today=today)
        if parsed is not None:
            return parsed
    return None


def _normalize_range(start: date, end: date) -> ParsedDateRange:
    swapped = start > end
    if swapped:
        start, end = end, start
    return ParsedDateRange(
        date_start=start.isoformat(),
        date_end=end.isoformat(),
        swapped=swapped,
    )


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _from_full_match(match: Match[str], *, today: date) -> ParsedDateRange | None:
    del today
    start = _safe_date(
        int(match.group("y1")),
        int(match.group("m1")),
        int(match.group("d1")),
    )
    end = _safe_date(
        int(match.group("y2")),
        int(match.group("m2")),
        int(match.group("d2")),
    )
    if start is None or end is None:
        return None
    return _normalize_range(start, end)


def _from_slash_match(match: Match[str], *, today: date) -> ParsedDateRange | None:
    return _month_day_range(
        int(match.group("m1")),
        int(match.group("d1")),
        int(match.group("m2")),
        int(match.group("d2")),
        today=today,
    )


def _from_month_day_match(match: Match[str], *, today: date) -> ParsedDateRange | None:
    m1 = int(match.group("m1"))
    if match.group("d2s") is not None:
        # 第二個月份省略：與起始同月。
        m2, d2 = m1, int(match.group("d2s"))
    else:
        m2, d2 = int(match.group("m2")), int(match.group("d2"))
    return _month_day_range(m1, int(match.group("d1")), m2, d2, today=today)


def _month_day_range(
    m1: int, d1: int, m2: int, d2: int, *, today: date
) -> ParsedDateRange | None:
    start = _safe_date(today.year, m1, d1)
    end = _safe_date(today.year, m2, d2)
    if start is None or end is None:
        return None
    if m1 > m2 and _crosses_new_year(start, end):
        crossing = _cross_year_range(m1, d1, m2, d2, today=today)
        if crossing is not None:
            return crossing
    return _normalize_range(start, end)


def _crosses_new_year(start: date, end: date) -> bool:
    """`12/28-1/3` 是跨年的六天，不是寫反的 359 天；取較短的那種讀法。

    `5/10-3/1` 讀成跨年是 295 天、讀成寫反是 70 天，仍當成寫反。
    """

    reversed_span = (start - end).days
    return reversed_span > 365 - reversed_span


def _cross_year_range(m1: int, d1: int, m2: int, d2: int, *, today: date) -> ParsedDateRange | None:
    # 結束年從明年往回試：取起點不在今天之後、最近的那一段。12/30 問
    # `12/28-1/3` 是今年 12/28 到明年 1/3（已開始）；1/5 問則是去年 12/28 到今年 1/3。
    for end_year in (today.year + 1, today.year):
        start = _safe_date(end_year - 1, m1, d1)
        end = _safe_date(end_year, m2, d2)
        if start is None or end is None:
            continue
        if start <= today:
            return ParsedDateRange(date_start=start.isoformat(), date_end=end.isoformat())
    return None


def _from_day_tilde_match(match: Match[str], *, today: date) -> ParsedDateRange | None:
    day_start = int(match.group("d1"))
    day_end = int(match.group("d2"))
    start = _safe_date(today.year, today.month, day_start)
    end = _safe_date(today.year, today.month, day_end)
    if start is None or end is None:
        return None
    # 純日數區間（無月份）指最近一次的「過去」那段；若整段仍落在未來，
    # 回退到上一個月（必要時跨年）。
    if min(start, end) > today:
        year, month = _previous_month(today.year, today.month)
        start = _safe_date(year, month, day_start)
        end = _safe_date(year, month, day_end)
        if start is None or end is None:
            return None
    return _normalize_range(start, end)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1

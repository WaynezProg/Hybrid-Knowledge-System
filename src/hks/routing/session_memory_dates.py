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

_SLASH_RANGE_RE = re.compile(
    r"(?P<m1>\d{1,2})/(?P<d1>\d{1,2})\s*[-~－]\s*(?P<m2>\d{1,2})/(?P<d2>\d{1,2})"
)

_DAY_TILDE_RE = re.compile(
    r"(?<![\d/])(?P<d1>\d{1,2})\s*[~～]\s*(?P<d2>\d{1,2})(?!\s*/)"
)


def parse_session_memory_date_range(
    question: str,
    *,
    today: date,
) -> ParsedDateRange | None:
    for pattern, builder in (
        (_FULL_RANGE_RE, _from_full_match),
        (_SLASH_RANGE_RE, _from_slash_match),
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
    start = _safe_date(
        today.year,
        int(match.group("m1")),
        int(match.group("d1")),
    )
    end = _safe_date(
        today.year,
        int(match.group("m2")),
        int(match.group("d2")),
    )
    if start is None or end is None:
        return None
    return _normalize_range(start, end)


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

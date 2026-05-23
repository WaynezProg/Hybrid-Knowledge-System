"""Session-memory query intent detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class SessionMemoryIntent:
    date: str | None = None
    date_prefix: str | None = None

    def to_detail(self) -> dict[str, str | None]:
        return {"date": self.date, "date_prefix": self.date_prefix}


_FULL_DATE_RE = re.compile(
    r"\b(?P<year>20\d{2})[-/年](?P<month>\d{1,2})[-/月](?P<day>\d{1,2})日?\b"
)


def analyze_session_memory_intent(
    question: str,
    *,
    today: date | None = None,
) -> SessionMemoryIntent | None:
    lowered = question.lower()
    current_date = today or date.today()

    explicit = _explicit_date_intent(question)
    if explicit is not None:
        return explicit

    if "昨天" in question or "昨日" in question or "yesterday" in lowered:
        return SessionMemoryIntent(date=(current_date - timedelta(days=1)).isoformat())

    if "今天" in question or "今日" in question or "today" in lowered:
        return SessionMemoryIntent(date=current_date.isoformat())

    return None


def _explicit_date_intent(question: str) -> SessionMemoryIntent | None:
    match = _FULL_DATE_RE.search(question)
    if match is not None:
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
        try:
            return SessionMemoryIntent(date=date(year, month, day).isoformat())
        except ValueError:
            return None

    return None


def metadata_matches_session_intent(
    metadata: dict[str, object],
    intent: SessionMemoryIntent,
) -> bool:
    if not _is_session_memory_metadata(metadata):
        return False
    date_value = metadata.get("date")
    date_text = date_value if isinstance(date_value, str) else ""
    if intent.date is not None:
        return date_text == intent.date
    if intent.date_prefix is not None:
        return date_text.startswith(intent.date_prefix)
    return True


def _is_session_memory_metadata(metadata: dict[str, object]) -> bool:
    hks_type = str(metadata.get("hks_type") or "")
    source_domain = str(metadata.get("source_domain") or "")
    generator = str(metadata.get("generator") or "")
    relpath = str(metadata.get("source_relpath") or "")
    return (
        hks_type in {"session_daily", "session_memory", "session-memory"}
        or source_domain == "session_memory"
        or generator == "session2memory"
        or relpath.startswith("daily/")
    )

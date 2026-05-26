"""Session-memory query intent detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class SessionMemoryIntent:
    date: str | None = None
    date_prefix: str | None = None
    workspace: str | None = None
    is_status_query: bool = False

    def to_detail(self) -> dict[str, object]:
        detail: dict[str, object] = {"date": self.date, "date_prefix": self.date_prefix}
        if self.workspace is not None:
            detail["workspace"] = self.workspace
        if self.is_status_query:
            detail["is_status_query"] = True
        return detail


_FULL_DATE_RE = re.compile(
    r"\b(?P<year>20\d{2})[-/年](?P<month>\d{1,2})[-/月](?P<day>\d{1,2})日?\b"
)

_WORKSPACE_ID_EXPLICIT_RE = re.compile(
    r"workspace(?:_id)?[=:]\s*(?P<ws>[a-z0-9][-a-z0-9]*[a-z0-9])",
    re.IGNORECASE,
)

_KEBAB_SLUG_RE = re.compile(r"\b(?P<slug>[a-z][a-z0-9]*(?:-[a-z0-9]+)+)\b")

_SINGLE_WORD_WS_RE = re.compile(r"\b(?P<word>[a-z][a-z0-9]+)\b")

_SINGLE_WORD_WS_EXCLUDED = frozenset({
    "a", "about", "an", "are", "current", "for", "in", "is", "last", "latest",
    "me", "now", "of", "on", "please", "progress", "run", "show", "status", "tell",
    "the", "was", "were", "what", "when", "where", "which", "who", "workspace",
})

_STATUS_KEYWORDS = frozenset({
    "最後處理到哪", "處理到哪", "進度", "狀態", "目前狀態",
    "做到哪", "跑到哪", "完成了嗎", "做完了嗎",
    "status", "progress", "latest", "last run",
})

_STATUS_KEYWORDS_RE = re.compile(
    "|".join(re.escape(kw) for kw in sorted(_STATUS_KEYWORDS, key=len, reverse=True)),
    re.IGNORECASE,
)


def analyze_session_memory_intent(
    question: str,
    *,
    today: date | None = None,
) -> SessionMemoryIntent | None:
    lowered = question.lower()
    current_date = today or date.today()

    workspace = _extract_workspace(question)
    is_status = bool(_STATUS_KEYWORDS_RE.search(question))

    if workspace is None and is_status:
        workspace = _extract_single_word_workspace(question)

    explicit = _explicit_date_intent(question)
    if explicit is not None:
        if workspace is not None:
            return SessionMemoryIntent(
                date=explicit.date,
                date_prefix=explicit.date_prefix,
                workspace=workspace,
                is_status_query=is_status,
            )
        return explicit

    if "昨天" in question or "昨日" in question or "yesterday" in lowered:
        return SessionMemoryIntent(
            date=(current_date - timedelta(days=1)).isoformat(),
            workspace=workspace,
            is_status_query=is_status,
        )

    if "今天" in question or "今日" in question or "today" in lowered:
        return SessionMemoryIntent(
            date=current_date.isoformat(),
            workspace=workspace,
            is_status_query=is_status,
        )

    if workspace is not None:
        return SessionMemoryIntent(workspace=workspace, is_status_query=is_status)

    return None


def _extract_workspace(question: str) -> str | None:
    explicit = _WORKSPACE_ID_EXPLICIT_RE.search(question)
    if explicit is not None:
        return explicit.group("ws")

    slugs: list[str] = _KEBAB_SLUG_RE.findall(question)
    if slugs:
        return max(slugs, key=len)

    return None


def _extract_single_word_workspace(question: str) -> str | None:
    lowered = question.lower()
    candidates = [
        (match.group("word"), match.start(), match.end())
        for match in _SINGLE_WORD_WS_RE.finditer(lowered)
        if match.group("word") not in _SINGLE_WORD_WS_EXCLUDED
    ]
    if not candidates:
        return None
    keyword_spans = [
        (match.start(), match.end())
        for match in _STATUS_KEYWORDS_RE.finditer(question)
    ]
    if not keyword_spans:
        return max((word for word, _, _ in candidates), key=len)

    def candidate_key(candidate: tuple[str, int, int]) -> tuple[int, int, int]:
        word, start, end = candidate
        distance = min(
            max(keyword_start - end, start - keyword_end, 0)
            for keyword_start, keyword_end in keyword_spans
        )
        return distance, -len(word), start

    return min(candidates, key=candidate_key)[0]


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
    if intent.workspace is not None:
        return _metadata_matches_workspace(metadata, intent)

    if not _is_session_memory_metadata(metadata):
        return False
    return _metadata_matches_date(metadata, intent)


def _metadata_matches_date(
    metadata: dict[str, object],
    intent: SessionMemoryIntent,
) -> bool:
    date_value = metadata.get("date")
    date_text = date_value if isinstance(date_value, str) else ""
    if intent.date is not None:
        return date_text == intent.date
    if intent.date_prefix is not None:
        return date_text.startswith(intent.date_prefix)
    return True


def _metadata_matches_workspace(
    metadata: dict[str, object],
    intent: SessionMemoryIntent,
) -> bool:
    wid = str(metadata.get("workspace_id") or "")
    if not wid:
        return False
    if not workspace_id_matches(wid, intent.workspace):  # type: ignore[arg-type]
        return False
    if intent.date is not None:
        date_text = str(metadata.get("date") or "")
        return date_text == intent.date
    return True


def workspace_id_matches(workspace_id: str, query_workspace: str) -> bool:
    if workspace_id == query_workspace:
        return True
    if workspace_id.startswith(query_workspace + "-"):
        suffix = workspace_id[len(query_workspace) + 1 :]
        if suffix and all(c in "0123456789abcdef" for c in suffix):
            return True
    return False


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

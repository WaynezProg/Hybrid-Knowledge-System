"""Data models shared by local adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from hks.core.schema import QueryResponse
from hks.errors import ExitCode

type WritebackMode = Literal["no", "auto", "yes", "ask"]
type PptxNotesMode = Literal["include", "exclude"]
type SeverityThreshold = Literal["error", "warning", "info"]
type FixMode = Literal["none", "plan", "apply"]
type LlmMode = Literal["preview", "store"]
type WikiSynthesisMode = Literal["preview", "store", "apply"]
type GraphifyMode = Literal["preview", "store"]
type WatchMode = Literal["dry-run", "execute"]
type WatchProfile = Literal["scan-only", "ingest-only", "derived-refresh", "wiki-apply", "full"]

WRITEBACK_MODES: frozenset[str] = frozenset(("no", "auto", "yes", "ask"))
PPTX_NOTES_MODES: frozenset[str] = frozenset(("include", "exclude"))
SEVERITY_THRESHOLDS: frozenset[str] = frozenset(("error", "warning", "info"))
FIX_MODES: frozenset[str] = frozenset(("none", "plan", "apply"))
LLM_MODES: frozenset[str] = frozenset(("preview", "store"))
WIKI_SYNTHESIS_MODES: frozenset[str] = frozenset(("preview", "store", "apply"))
GRAPHIFY_MODES: frozenset[str] = frozenset(("preview", "store"))
WATCH_MODES: frozenset[str] = frozenset(("dry-run", "execute"))
WATCH_PROFILES: frozenset[str] = frozenset(
    ("scan-only", "ingest-only", "derived-refresh", "wiki-apply", "full")
)


@dataclass(frozen=True, slots=True)
class AdapterError:
    code: str
    exit_code: ExitCode
    message: str
    hint: str | None = None
    details: list[str] = field(default_factory=list)
    response: QueryResponse | None = None
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": self.code,
                "exit_code": int(self.exit_code),
                "message": self.message,
                "details": self.details,
            },
            "response": self.response.to_dict() if self.response is not None else None,
        }
        if self.hint is not None:
            payload["error"]["hint"] = self.hint
        if self.request_id is not None:
            payload["request_id"] = self.request_id
        return payload


class AdapterToolError(Exception):
    """Raised by adapter core when a tool should return an MCP/HTTP error."""

    def __init__(self, error: AdapterError) -> None:
        super().__init__(error.message)
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return self.error.to_dict()

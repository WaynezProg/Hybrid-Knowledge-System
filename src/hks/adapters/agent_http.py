"""HTTP guards for the agent-profile allowlist."""

from __future__ import annotations

from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from hks.adapters.agent_config import is_agent_profile
from hks.errors import ExitCode

_AGENT_FORBIDDEN_EXACT = frozenset(
    {
        "/ingest",
        "/query",
        "/lint",
        "/pageindex/enrich",
        "/llm/classify",
        "/wiki/synthesize",
        "/graphify/build",
        "/watch/scan",
        "/watch/run",
        "/watch/status",
        "/coord/session",
        "/coord/lease",
        "/coord/handoff",
        "/coord/status",
        "/catalog/sources",
    }
)
_AGENT_FORBIDDEN_PREFIXES = ("/pageindex/",)


def _is_agent_forbidden_path(path: str) -> bool:
    if path in _AGENT_FORBIDDEN_EXACT:
        return True
    if path.startswith("/catalog/sources/"):
        return True
    return any(path.startswith(prefix) for prefix in _AGENT_FORBIDDEN_PREFIXES)


def agent_profile_forbidden_response() -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": {
                "code": "AGENT_PROFILE_FORBIDDEN",
                "exit_code": int(ExitCode.USAGE),
                "message": "endpoint is not available in agent profile",
                "details": [],
            },
            "response": None,
        },
        status_code=403,
    )


async def agent_profile_dispatch(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    if is_agent_profile() and _is_agent_forbidden_path(request.url.path):
        return agent_profile_forbidden_response()
    return await call_next(request)

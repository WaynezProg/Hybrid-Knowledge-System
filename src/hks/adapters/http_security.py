"""HTTP-only security guards for the optional Starlette facade."""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from hks.core.config import config_value

DEFAULT_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

_MUTATING_POST_PATHS = frozenset(
    {
        "/ingest",
        "/query",
        "/pageindex/enrich",
        "/llm/classify",
        "/wiki/synthesize",
        "/graphify/build",
        "/watch/scan",
        "/watch/run",
        "/coord/session",
        "/coord/lease",
        "/coord/handoff",
    }
)


@dataclass(frozen=True)
class HttpSecurityFailure:
    status_code: int
    code: str
    message: str
    details: list[str]


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if not value:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _allowed_hosts() -> set[str]:
    configured = config_value("HKS_API_HOST_ALLOWLIST")
    if not configured:
        return set(DEFAULT_ALLOWED_HOSTS)
    hosts: set[str] = set()
    for token in configured.split(","):
        host = _host_from_header(token)
        if host is not None:
            hosts.add(host)
    return hosts


def _host_from_header(value: str | None) -> str | None:
    if value is None:
        return None
    host = value.strip()
    if not host:
        return None
    if host.startswith("["):
        end = host.find("]")
        if end == -1:
            return None
        remainder = host[end + 1 :]
        if remainder and not (
            remainder.startswith(":") and remainder[1:].isdigit()
        ):
            return None
        return host[1:end].lower()
    if host.count(":") == 1:
        hostname, port = host.rsplit(":", 1)
        if not port.isdigit():
            return None
        return hostname.rstrip(".").lower()
    return host.rstrip(".").lower()


def is_mutating_request(request: Request) -> bool:
    if request.method.upper() != "POST":
        return False

    path = str(request.scope.get("path", "")).rstrip("/") or "/"
    if path in _MUTATING_POST_PATHS:
        return True
    if path == "/workspaces":
        return True
    if path.startswith("/workspaces/"):
        suffix = path.removeprefix("/workspaces/")
        parts = suffix.split("/")
        if len(parts) == 1 and parts[0]:
            return True
        return len(parts) == 2 and bool(parts[0]) and parts[1] == "query"
    return False


def _authorization_matches(request: Request, token: str) -> bool:
    authorization = request.headers.get("authorization", "")
    scheme, separator, credential = authorization.partition(" ")
    if separator == "" or scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(credential, token)


def _is_browser_style_request(request: Request) -> bool:
    return "origin" in request.headers or "sec-fetch-site" in request.headers


def guard_http_request(request: Request) -> HttpSecurityFailure | None:
    host = _host_from_header(request.headers.get("host"))
    if host not in _allowed_hosts():
        return HttpSecurityFailure(
            status_code=400,
            code="HTTP_HOST_FORBIDDEN",
            message="Host header is not allowed",
            details=[f"host={host}" if host is not None else "host=<invalid>"],
        )

    if not is_mutating_request(request):
        return None

    token = config_value("HKS_API_TOKEN")
    if token in (None, ""):
        return HttpSecurityFailure(
            status_code=403,
            code="HTTP_MUTATION_TOKEN_NOT_CONFIGURED",
            message="HKS_API_TOKEN must be configured for HTTP mutations",
            details=[],
        )
    assert token is not None

    if not _authorization_matches(request, token):
        return HttpSecurityFailure(
            status_code=401,
            code="HTTP_AUTH_REQUIRED",
            message="HTTP mutation requires Authorization: Bearer token",
            details=[],
        )

    if _parse_bool(config_value("HKS_API_REJECT_BROWSER_REQUESTS"), default=True):
        if _is_browser_style_request(request):
            return HttpSecurityFailure(
                status_code=403,
                code="HTTP_BROWSER_REQUEST_FORBIDDEN",
                message="Browser-style HTTP mutation requests are forbidden",
                details=[],
            )

    return None


def security_error_response(failure: HttpSecurityFailure) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": {
                "code": failure.code,
                "exit_code": 1,
                "message": failure.message,
                "details": failure.details,
            },
            "response": None,
        },
        status_code=failure.status_code,
    )


async def http_security_dispatch(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    failure = guard_http_request(request)
    if failure is not None:
        return security_error_response(failure)
    return await call_next(request)

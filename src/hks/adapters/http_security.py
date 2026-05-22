"""HTTP-only security guards for the optional Starlette facade."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from pathlib import Path

from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from hks.core.config import config_value

DEFAULT_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
HTTP_INGEST_BLOCKED_PATH_SEGMENTS = frozenset(
    {".git", ".ssh", ".env", "node_modules", ".venv", "__pycache__"}
)

_MUTATING_POST_PATHS = frozenset(
    {
        "/query",
        "/ingest",
        "/lint",
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


@dataclass(frozen=True)
class HttpIngestPath:
    source_root: Path
    target_path: Path


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


def parse_ingest_roots(value: str | None = None) -> dict[str, Path]:
    configured = config_value("HKS_API_INGEST_ROOTS") if value is None else value
    if not configured:
        return {}

    roots: dict[str, Path] = {}
    for token in configured.split(","):
        pair = token.strip()
        if not pair:
            continue
        root_id, separator, root = pair.partition("=")
        root_id = root_id.strip()
        root = root.strip()
        if not separator or not root_id or not root:
            continue
        roots[root_id] = Path(root).expanduser().resolve(strict=False)
    return roots


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _ingest_failure(status_code: int, code: str, message: str) -> HttpSecurityFailure:
    return HttpSecurityFailure(
        status_code=status_code,
        code=code,
        message=message,
        details=[],
    )


def resolve_http_ingest_path(
    *, path: str, source_root_id: str | None = None
) -> HttpIngestPath | HttpSecurityFailure:
    roots = parse_ingest_roots()
    if not roots:
        return _ingest_failure(
            403,
            "HTTP_INGEST_ROOTS_NOT_CONFIGURED",
            "HKS_API_INGEST_ROOTS must be configured for HTTP ingest",
        )

    if source_root_id is None:
        if len(roots) != 1:
            return _ingest_failure(
                400,
                "HTTP_INGEST_SOURCE_ROOT_REQUIRED",
                "source_root_id is required when multiple HTTP ingest roots are configured",
            )
        source_root = next(iter(roots.values()))
    else:
        if source_root_id not in roots:
            return _ingest_failure(
                400,
                "HTTP_INGEST_SOURCE_ROOT_UNKNOWN",
                "source_root_id is not configured for HTTP ingest",
            )
        source_root = roots[source_root_id]
    relative_path = Path(path)
    if relative_path.is_absolute():
        return _ingest_failure(
            400,
            "HTTP_INGEST_PATH_FORBIDDEN",
            "HTTP ingest path must be relative to a configured source root",
        )

    if any(part in {"..", *HTTP_INGEST_BLOCKED_PATH_SEGMENTS} for part in relative_path.parts):
        return _ingest_failure(
            400,
            "HTTP_INGEST_PATH_FORBIDDEN",
            "HTTP ingest path contains a forbidden segment",
        )

    if not source_root.is_dir():
        return _ingest_failure(
            403,
            "HTTP_INGEST_ROOT_UNAVAILABLE",
            "Configured HTTP ingest source root is unavailable",
        )

    requested_path = source_root / relative_path
    if not requested_path.exists():
        return _ingest_failure(
            400,
            "HTTP_INGEST_PATH_NOT_FOUND",
            "HTTP ingest path was not found under the configured source root",
        )

    resolved_path = requested_path.resolve(strict=False)
    if not _is_relative_to(resolved_path, source_root):
        return _ingest_failure(
            400,
            "HTTP_INGEST_PATH_FORBIDDEN",
            "HTTP ingest path escapes the configured source root",
        )
    return HttpIngestPath(source_root=source_root, target_path=resolved_path)


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


def _read_auth_required() -> bool:
    return _parse_bool(config_value("HKS_API_REQUIRE_TOKEN_FOR_READS"), default=False)


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

    is_mutating = is_mutating_request(request)
    if not is_mutating and not _read_auth_required():
        return None

    token = config_value("HKS_API_TOKEN")
    if token in (None, ""):
        if not is_mutating:
            return HttpSecurityFailure(
                status_code=403,
                code="HTTP_READ_TOKEN_NOT_CONFIGURED",
                message="HKS_API_TOKEN must be configured when HTTP read authentication is enabled",
                details=[],
            )
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

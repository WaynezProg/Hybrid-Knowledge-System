"""Validate session2memory export paths before agent-profile ingest."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from hks.errors import ExitCode


class SessionMemorySourceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: ExitCode = ExitCode.DATAERR,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def resolve_export_path(
    *,
    export_root: Path,
    workspace_id: str,
    path: str,
) -> Path:
    workspace_root = (export_root / workspace_id).resolve(strict=False)
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (workspace_root / candidate).resolve(strict=False)
    else:
        candidate = candidate.resolve(strict=False)
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise SessionMemorySourceError(
            "WORKSPACE_PATH_OUT_OF_ROOT",
            f"path must stay under {workspace_root.as_posix()}",
        ) from exc
    if not candidate.exists():
        raise SessionMemorySourceError(
            "WORKSPACE_PATH_OUT_OF_ROOT",
            f"path does not exist: {candidate.as_posix()}",
        )
    return candidate


def assert_session_memory_tree(*, root: Path, workspace_id: str) -> None:
    if root.is_file():
        _assert_session_memory_file(root, workspace_id=workspace_id)
        return
    markdown_files = sorted(root.rglob("*.md"))
    if not markdown_files:
        raise SessionMemorySourceError(
            "INGEST_SOURCE_DISALLOWED",
            "no markdown files found under ingest path",
        )
    for markdown_file in markdown_files:
        _assert_session_memory_file(markdown_file, workspace_id=workspace_id)


def _assert_session_memory_file(path: Path, *, workspace_id: str) -> None:
    if path.suffix.lower() != ".md":
        raise SessionMemorySourceError(
            "INGEST_SOURCE_DISALLOWED",
            f"only markdown session2memory files are allowed: {path.name}",
        )
    text = path.read_text(encoding="utf-8")
    metadata = _parse_frontmatter(text)
    if not _is_session_memory_metadata(metadata, source_relpath=path.name):
        raise SessionMemorySourceError(
            "INGEST_SOURCE_DISALLOWED",
            f"file is not a session2memory artifact: {path.as_posix()}",
        )
    declared_workspace = metadata.get("workspace_id")
    if declared_workspace and declared_workspace != workspace_id:
        raise SessionMemorySourceError(
            "WORKSPACE_ID_MISMATCH",
            (
                f"frontmatter workspace_id `{declared_workspace}` "
                f"does not match `{workspace_id}`"
            ),
        )


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    closing = text.find("\n---\n", len("---\n"))
    if closing == -1:
        return {}
    blob = text[len("---\n") : closing]
    yaml = YAML(typ="safe")
    try:
        payload = yaml.load(blob) or {}
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    metadata: dict[str, str] = {}
    for key, value in payload.items():
        if value is None:
            continue
        metadata[str(key)] = str(value).strip()
    return metadata


def _is_session_memory_metadata(
    metadata: dict[str, str],
    *,
    source_relpath: str,
) -> bool:
    hks_type = metadata.get("hks_type", "")
    source_domain = metadata.get("source_domain", "")
    generator = metadata.get("generator", "")
    normalized_relpath = source_relpath.replace("\\", "/")
    return (
        hks_type in {"session_daily", "session_memory", "session-memory"}
        or source_domain == "session_memory"
        or generator == "session2memory"
        or normalized_relpath.startswith("daily/")
        or "/daily/" in normalized_relpath
    )

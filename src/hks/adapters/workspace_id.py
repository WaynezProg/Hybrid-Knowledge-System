"""Workspace id derivation for agent-facing adapter flows."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9-]+")
_MULTI_HYPHEN = re.compile(r"-+")


def slugify_workspace_id(
    basename: str,
    *,
    project_root: Path | None = None,
    reserved: dict[str, Path] | None = None,
) -> str:
    slug = basename.strip().lower().replace(" ", "-").replace("_", "-")
    slug = _MULTI_HYPHEN.sub("-", _SLUG_RE.sub("", slug)).strip("-")
    if not slug:
        slug = "project"
    if project_root is None or not reserved:
        return slug
    existing = reserved.get(slug)
    if existing is None or existing.resolve() == project_root.resolve():
        return slug
    digest = hashlib.sha256(str(project_root.resolve()).encode()).hexdigest()[:8]
    return f"{slug}-{digest}"

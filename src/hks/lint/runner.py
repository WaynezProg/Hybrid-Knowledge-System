"""Runtime orchestration for `ks lint`."""

from __future__ import annotations

import json
import re
from json import JSONDecodeError
from pathlib import Path

from hks.core.lock import file_lock
from hks.core.manifest import load_manifest
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import ExitCode, KSError
from hks.graph.store import GraphPayload, GraphStore
from hks.lint.checks import run_checks
from hks.lint.fixer import apply_fixes, plan_fixes
from hks.lint.models import (
    SEVERITY_RANK,
    FixMode,
    LintResult,
    RuntimeSnapshot,
    SeverityThreshold,
    WikiPageRecord,
)
from hks.storage.vector import VectorStore
from hks.storage.wiki import WikiPage


def run_lint(*, fix_mode: FixMode = "none") -> LintResult:
    paths = runtime_paths()
    try:
        with file_lock(paths.lock):
            snapshot = _build_snapshot(paths)
            findings = run_checks(snapshot)
            if fix_mode == "none":
                return LintResult(findings=findings)
            planned, skipped = plan_fixes(findings)
            if fix_mode == "plan":
                return LintResult(
                    findings=findings,
                    fixes_planned=planned,
                    fixes_skipped=skipped,
                )
            applied, apply_skips = apply_fixes(paths, planned)
            refreshed = _build_snapshot(paths)
            return LintResult(
                findings=run_checks(refreshed),
                fixes_applied=applied,
                fixes_skipped=[*skipped, *apply_skips],
            )
    except KSError as exc:
        if exc.code == "LOCKED":
            raise KSError(
                "另一個 HKS 寫入流程正在執行",
                exit_code=ExitCode.GENERAL,
                code="LOCKED",
                details=exc.details,
            ) from exc
        raise


def exceeds_threshold(result: LintResult, threshold: SeverityThreshold) -> bool:
    threshold_rank = SEVERITY_RANK[threshold]
    return any(SEVERITY_RANK[finding.severity] >= threshold_rank for finding in result.findings)


def _build_snapshot(paths: RuntimePaths) -> RuntimeSnapshot:
    _assert_runtime_ready(paths)
    try:
        manifest = load_manifest(paths.manifest)
    except Exception as exc:
        raise KSError(
            "manifest.json 無法讀取",
            exit_code=ExitCode.GENERAL,
            code="MANIFEST_ERROR",
            details=[str(exc)],
        ) from exc
    try:
        graph = _load_graph(paths)
        vector_ids = set(VectorStore(paths).list_ids())
    except KSError:
        raise
    except Exception as exc:
        raise KSError(
            "vector store 無法開啟",
            exit_code=ExitCode.GENERAL,
            code="VECTOR_OPEN_FAILED",
            details=[str(exc)],
        ) from exc

    return RuntimeSnapshot(
        manifest_entries=dict(manifest.entries),
        raw_source_relpaths=_raw_source_relpaths(paths),
        wiki_pages=_load_wiki_pages(paths),
        wiki_index_slugs=_load_wiki_index_slugs(paths),
        vector_ids=vector_ids,
        graph=graph,
        llm_artifacts=_load_llm_artifacts(paths),
        llm_artifact_errors=_load_llm_artifact_errors(paths),
    )


def _assert_runtime_ready(paths: RuntimePaths) -> None:
    missing: list[Path] = []
    if not paths.root.exists():
        missing.append(paths.root)
    for path in (paths.manifest, paths.wiki, paths.vector_db):
        if not path.exists():
            missing.append(path)
    if missing:
        raise KSError(
            "/ks/ 尚未初始化，請先執行 ks ingest <path>",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            details=[f"missing: {path}" for path in missing],
            hint="run `ks ingest <path>`",
        )


def _load_graph(paths: RuntimePaths) -> GraphPayload:
    if not paths.graph_file.exists():
        return GraphPayload()
    try:
        return GraphStore(paths).load()
    except JSONDecodeError as exc:
        raise KSError(
            "graph.json 損毀",
            exit_code=ExitCode.GENERAL,
            code="GRAPH_CORRUPT",
            details=[f"line {exc.lineno}, column {exc.colno}: {exc.msg}"],
        ) from exc


def _raw_source_relpaths(paths: RuntimePaths) -> set[str]:
    if not paths.raw_sources.exists():
        return set()
    return {
        path.relative_to(paths.raw_sources).as_posix()
        for path in paths.raw_sources.rglob("*")
        if path.is_file()
    }


def _load_wiki_pages(paths: RuntimePaths) -> dict[str, WikiPageRecord]:
    pages: dict[str, WikiPageRecord] = {}
    if not paths.wiki_pages.exists():
        return pages
    for path in sorted(paths.wiki_pages.glob("*.md")):
        try:
            page = WikiPage.from_markdown(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise KSError(
                "wiki page 無法讀取",
                exit_code=ExitCode.GENERAL,
                code="WIKI_PAGE_ERROR",
                details=[f"{path.name}: {exc}"],
            ) from exc
        pages[path.stem] = WikiPageRecord(file_slug=path.stem, page=page)
    return pages


def _load_wiki_index_slugs(paths: RuntimePaths) -> list[str]:
    if not paths.wiki.joinpath("index.md").exists():
        return []
    slugs: list[str] = []
    for line in paths.wiki.joinpath("index.md").read_text(encoding="utf-8").splitlines():
        match = re.search(r"\(pages/(.+?)\.md\)", line)
        if match:
            slugs.append(match.group(1))
    return slugs


def _llm_extractions_dir(paths: RuntimePaths) -> Path:
    return paths.root / "llm" / "extractions"


def _load_llm_artifacts(paths: RuntimePaths) -> dict[str, dict[str, object]]:
    base = _llm_extractions_dir(paths)
    if not base.exists():
        return {}
    artifacts: dict[str, dict[str, object]] = {}
    for path in sorted(base.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            artifacts[path.name] = payload
    return artifacts


def _load_llm_artifact_errors(paths: RuntimePaths) -> dict[str, str]:
    base = _llm_extractions_dir(paths)
    if not base.exists():
        return {}
    errors: dict[str, str] = {}
    for path in sorted(base.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors[path.name] = str(exc)
            continue
        if not isinstance(payload, dict):
            errors[path.name] = "artifact root must be an object"
    return errors

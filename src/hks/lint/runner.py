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
from hks.workspace.registry import load_registry, registry_path
from hks.workspace.service import _workspace_status


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
        wiki_candidate_artifacts=_load_wiki_candidate_artifacts(paths),
        wiki_candidate_artifact_errors=_load_wiki_candidate_artifact_errors(paths),
        graphify_run_manifests=_load_graphify_run_manifests(paths),
        graphify_graph_artifacts=_load_graphify_graph_artifacts(paths),
        graphify_artifact_errors=_load_graphify_artifact_errors(paths),
        graphify_partial_runs=_load_graphify_partial_runs(paths),
        graphify_latest_error=_load_graphify_latest_error(paths),
        watch_artifacts=_load_watch_artifacts(paths),
        watch_artifact_errors=_load_watch_artifact_errors(paths),
        watch_partial_runs=_load_watch_partial_runs(paths),
        watch_latest_error=_load_watch_latest_error(paths),
        workspace_registry_path=_workspace_registry_path(),
        workspace_registry_errors=_load_workspace_registry_errors(),
        workspace_root_issues=_load_workspace_root_issues(),
        workspace_duplicate_roots=_load_workspace_duplicate_roots(),
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


def _wiki_candidates_dir(paths: RuntimePaths) -> Path:
    return paths.root / "llm" / "wiki-candidates"


def _load_wiki_candidate_artifacts(paths: RuntimePaths) -> dict[str, dict[str, object]]:
    base = _wiki_candidates_dir(paths)
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


def _load_wiki_candidate_artifact_errors(paths: RuntimePaths) -> dict[str, str]:
    base = _wiki_candidates_dir(paths)
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


def _graphify_runs_dir(paths: RuntimePaths) -> Path:
    return paths.root / "graphify" / "runs"


def _load_graphify_run_manifests(paths: RuntimePaths) -> dict[str, dict[str, object]]:
    base = _graphify_runs_dir(paths)
    if not base.exists():
        return {}
    artifacts: dict[str, dict[str, object]] = {}
    for path in sorted(base.glob("*/manifest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            artifacts[path.relative_to(paths.root).as_posix()] = payload
    return artifacts


def _load_graphify_graph_artifacts(paths: RuntimePaths) -> dict[str, dict[str, object]]:
    base = _graphify_runs_dir(paths)
    if not base.exists():
        return {}
    artifacts: dict[str, dict[str, object]] = {}
    for path in sorted(base.glob("*/graphify.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            artifacts[path.relative_to(paths.root).as_posix()] = payload
    return artifacts


def _load_graphify_artifact_errors(paths: RuntimePaths) -> dict[str, str]:
    base = _graphify_runs_dir(paths)
    if not base.exists():
        return {}
    errors: dict[str, str] = {}
    for path in sorted(base.glob("*/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors[path.relative_to(paths.root).as_posix()] = str(exc)
            continue
        if not isinstance(payload, (dict, list)):
            errors[path.relative_to(paths.root).as_posix()] = (
                "artifact root must be an object or array"
            )
    return errors


def _load_graphify_partial_runs(paths: RuntimePaths) -> set[str]:
    base = _graphify_runs_dir(paths)
    if not base.exists():
        return set()
    required = {"graphify.json", "communities.json", "audit.json", "manifest.json"}
    partial: set[str] = set()
    for path in sorted(item for item in base.iterdir() if item.is_dir()):
        existing = {child.name for child in path.iterdir() if child.is_file()}
        if not required.issubset(existing):
            partial.add(path.relative_to(paths.root).as_posix())
    return partial


def _load_graphify_latest_error(paths: RuntimePaths) -> str | None:
    latest = paths.root / "graphify" / "latest.json"
    if not latest.exists():
        return None
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"graphify latest pointer cannot be parsed: {exc}"
    if not isinstance(payload, dict):
        return "graphify latest pointer root must be an object"
    run_manifest = payload.get("run_manifest_path")
    if not isinstance(run_manifest, str) or not run_manifest:
        return "graphify latest pointer is missing run_manifest_path"
    if not Path(run_manifest).exists():
        return "graphify latest pointer references missing run manifest"
    return None


def _watch_dir(paths: RuntimePaths) -> Path:
    return paths.root / "watch"


def _load_watch_artifacts(paths: RuntimePaths) -> dict[str, dict[str, object]]:
    base = _watch_dir(paths)
    if not base.exists():
        return {}
    artifacts: dict[str, dict[str, object]] = {}
    for path in [
        *sorted((base / "plans").glob("*.json")),
        *sorted((base / "runs").glob("*.json")),
        base / "latest.json",
    ]:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            artifacts[path.relative_to(paths.root).as_posix()] = payload
    return artifacts


def _load_watch_artifact_errors(paths: RuntimePaths) -> dict[str, str]:
    base = _watch_dir(paths)
    if not base.exists():
        return {}
    errors: dict[str, str] = {}
    for path in [
        *sorted((base / "plans").glob("*.json")),
        *sorted((base / "runs").glob("*.json")),
        base / "latest.json",
    ]:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors[path.relative_to(paths.root).as_posix()] = str(exc)
            continue
        if not isinstance(payload, dict):
            errors[path.relative_to(paths.root).as_posix()] = "artifact root must be an object"
    return errors


def _load_watch_partial_runs(paths: RuntimePaths) -> set[str]:
    base = _watch_dir(paths) / "runs"
    if not base.exists():
        return set()
    partial: set[str] = set()
    for path in sorted(base.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("status") == "partial":
            partial.add(path.relative_to(paths.root).as_posix())
    return partial


def _load_watch_latest_error(paths: RuntimePaths) -> str | None:
    latest = _watch_dir(paths) / "latest.json"
    if not latest.exists():
        return None
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"watch latest pointer cannot be parsed: {exc}"
    if not isinstance(payload, dict):
        return "watch latest pointer root must be an object"
    plan_id = payload.get("latest_plan_id")
    if plan_id and not (_watch_dir(paths) / "plans" / f"{plan_id}.json").exists():
        return "watch latest pointer references missing plan"
    run_id = payload.get("latest_run_id")
    if run_id and not (_watch_dir(paths) / "runs" / f"{run_id}.json").exists():
        return "watch latest pointer references missing run"
    return None


def _workspace_registry_path() -> str:
    return registry_path().as_posix()


def _load_workspace_registry_errors() -> dict[str, str]:
    path = registry_path()
    if not path.exists():
        return {}
    try:
        load_registry(path)
    except Exception as exc:
        return {path.as_posix(): str(exc)}
    return {}


def _load_workspace_root_issues() -> dict[str, str]:
    try:
        registry = load_registry()
    except Exception:
        return {}
    issues: dict[str, str] = {}
    for record in registry.workspaces.values():
        status = _workspace_status(record)
        if status.status not in {"ready", "duplicate_root"}:
            issues[record.id] = "; ".join(status.issues) or status.status
    return issues


def _load_workspace_duplicate_roots() -> dict[str, list[str]]:
    try:
        registry = load_registry()
    except Exception:
        return {}
    by_root: dict[str, list[str]] = {}
    for record in registry.workspaces.values():
        by_root.setdefault(record.ks_root, []).append(record.id)
    return {root: sorted(ids) for root, ids in sorted(by_root.items()) if len(ids) > 1}

"""Service orchestration for 009 wiki synthesis."""

from __future__ import annotations

from pathlib import Path

from hks.core.manifest import atomic_write, load_manifest, utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import ExitCode, KSError
from hks.llm.models import LlmFinding
from hks.storage.wiki import LogEntry, WikiPage, WikiStore
from hks.wiki_synthesis.models import (
    ApplyOperation,
    WikiApplyResult,
    WikiSynthesisCandidate,
    WikiSynthesisRequest,
    WikiSynthesisResult,
)
from hks.wiki_synthesis.providers import provider_for
from hks.wiki_synthesis.resolver import resolve_extraction_artifact
from hks.wiki_synthesis.store import (
    artifact_reference,
    blocking_file_lock,
    candidate_path,
    load_candidate_artifact,
    store_or_reuse,
)
from hks.wiki_synthesis.validation import validate_candidate, validate_result


def synthesize(request: WikiSynthesisRequest) -> WikiSynthesisResult:
    paths = runtime_paths()
    if request.mode == "apply":
        return _apply(request, paths)
    artifact_id, extraction_artifact, _ = resolve_extraction_artifact(
        source_relpath=request.source_relpath,
        extraction_artifact_id=request.extraction_artifact_id,
        paths=paths,
    )
    candidate = validate_candidate(
        provider_for(request).synthesize(
            request,
            extraction_artifact_id=artifact_id,
            extraction_result=extraction_artifact["result"],
        )
    )
    result = WikiSynthesisResult(
        mode=request.mode,
        candidate=candidate,
        findings=candidate.findings,
    )
    if request.mode == "preview":
        return validate_result(result)
    idempotency_key = request.idempotency_key(
        extraction_artifact_id=artifact_id,
        source_fingerprint=candidate.source_fingerprint,
        target_slug=candidate.target_slug,
    )
    stored, _ = store_or_reuse(request, result, idempotency_key=idempotency_key, paths=paths)
    return validate_result(stored)


def _apply(request: WikiSynthesisRequest, paths: RuntimePaths) -> WikiSynthesisResult:
    assert request.candidate_artifact_id is not None
    with blocking_file_lock(paths.root / "llm" / ".wiki-synthesis.lock"):
        artifact_id, candidate, _, artifact_file = load_candidate_artifact(
            request.candidate_artifact_id,
            paths,
        )
        _assert_candidate_not_stale(candidate, paths)
        ref = artifact_reference(artifact_id, artifact_file)
        result = WikiSynthesisResult(
            mode="apply",
            candidate=candidate,
            artifact=ref,
            findings=candidate.findings,
        )
        apply_result = _apply_candidate(candidate, paths, artifact_id=artifact_id)
        return validate_result(result.with_apply_result(apply_result))


def _assert_candidate_not_stale(candidate: WikiSynthesisCandidate, paths: RuntimePaths) -> None:
    manifest = load_manifest(paths.manifest)
    entry = manifest.entries.get(candidate.source_relpath)
    if entry is None:
        raise KSError(
            f"candidate source `{candidate.source_relpath}` 不存在於 manifest",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
        )
    if (
        entry.sha256 != candidate.source_fingerprint
        or entry.parser_fingerprint != candidate.parser_fingerprint
    ):
        raise KSError(
            f"wiki synthesis candidate `{candidate.candidate_id}` 已 stale",
            exit_code=ExitCode.DATAERR,
            code="CANDIDATE_STALE",
            details=[f"source_relpath: {candidate.source_relpath}"],
        )


def _apply_candidate(
    candidate: WikiSynthesisCandidate,
    paths: RuntimePaths,
    *,
    artifact_id: str,
) -> WikiApplyResult:
    store = WikiStore(paths)
    store.ensure()
    page_path = paths.wiki_pages / f"{candidate.target_slug}.md"
    existing = _load_existing(page_path)
    if existing is not None:
        conflict = _conflict_for_existing(existing, candidate)
        if conflict is not None:
            return WikiApplyResult(
                operation="conflict",
                target_slug=candidate.target_slug,
                touched_pages=[],
                conflicts=[conflict],
                diff_summary=f"conflict pages/{candidate.target_slug}.md",
            )
        if _same_content(existing, candidate):
            apply_result = WikiApplyResult(
                operation="already_applied",
                target_slug=candidate.target_slug,
                touched_pages=[f"pages/{candidate.target_slug}.md"],
                conflicts=[],
                diff_summary=f"already applied pages/{candidate.target_slug}.md",
                idempotent_apply=True,
                log_entry_id=utc_now_iso(),
            )
            store.append_log(_log_entry(apply_result, candidate))
            return apply_result
        operation: ApplyOperation = "update"
    else:
        operation = "create"

    previous = page_path.read_text(encoding="utf-8") if page_path.exists() else None
    page = _page_for_candidate(candidate, artifact_id=artifact_id)
    try:
        atomic_write(page_path, page.to_markdown())
        store.rebuild_index()
        apply_result = WikiApplyResult(
            operation=operation,
            target_slug=candidate.target_slug,
            touched_pages=[f"pages/{candidate.target_slug}.md"],
            conflicts=[],
            diff_summary=f"{operation} pages/{candidate.target_slug}.md",
            log_entry_id=utc_now_iso(),
        )
        store.append_log(_log_entry(apply_result, candidate))
        return apply_result
    except Exception:
        if previous is None:
            page_path.unlink(missing_ok=True)
        else:
            atomic_write(page_path, previous)
        store.rebuild_index()
        raise


def _load_existing(path: Path) -> WikiPage | None:
    if not path.exists():
        return None
    return WikiPage.from_markdown(path.read_text(encoding="utf-8"))


def _conflict_for_existing(
    page: WikiPage,
    candidate: WikiSynthesisCandidate,
) -> LlmFinding | None:
    if page.origin != "llm_wiki":
        return LlmFinding(
            severity="error",
            code="wiki_slug_conflict",
            message="target page origin is not llm_wiki",
        )
    existing_lineage = (
        page.metadata.get("extraction_artifact_id"),
        page.metadata.get("source_fingerprint"),
        page.metadata.get("parser_fingerprint"),
    )
    if existing_lineage != candidate.lineage_tuple():
        return LlmFinding(
            severity="error",
            code="wiki_lineage_conflict",
            message="target page lineage differs from candidate lineage",
        )
    return None


def _same_content(page: WikiPage, candidate: WikiSynthesisCandidate) -> bool:
    return (
        page.title == candidate.title
        and page.summary == candidate.summary
        and page.body == candidate.body
    )


def _page_for_candidate(candidate: WikiSynthesisCandidate, *, artifact_id: str) -> WikiPage:
    now = utc_now_iso()
    return WikiPage(
        slug=candidate.target_slug,
        title=candidate.title,
        summary=candidate.summary,
        body=candidate.body,
        source_relpath=candidate.source_relpath,
        origin="llm_wiki",
        updated_at=now,
        metadata={
            "generated_at": now,
            "extraction_artifact_id": candidate.extraction_artifact_id,
            "wiki_candidate_artifact_id": artifact_id,
            "source_fingerprint": candidate.source_fingerprint,
            "parser_fingerprint": candidate.parser_fingerprint,
            "prompt_version": candidate.prompt_version,
            "provider_id": candidate.provider_id,
            "model_id": candidate.model_id,
        },
    )


def _log_entry(result: WikiApplyResult, candidate: WikiSynthesisCandidate) -> LogEntry:
    return LogEntry(
        timestamp=result.log_entry_id or utc_now_iso(),
        event="wiki_synthesis",
        status="already_applied" if result.idempotent_apply else "applied",
        target=candidate.target_slug,
        pages_touched=result.touched_pages,
        confidence=candidate.confidence,
        action="apply",
        outcome=result.operation,
    )


def candidate_artifact_exists(
    candidate_artifact_id: str,
    paths: RuntimePaths | None = None,
) -> bool:
    return candidate_path(candidate_artifact_id, paths).exists()

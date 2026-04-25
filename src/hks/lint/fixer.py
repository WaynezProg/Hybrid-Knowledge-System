"""Allowlisted lint fix planning and application."""

from __future__ import annotations

from hks.core.manifest import utc_now_iso
from hks.core.paths import RuntimePaths
from hks.graph.store import GraphStore
from hks.lint.models import Finding, FixAction, FixSkip, FixSkipReason
from hks.storage.vector import VectorStore
from hks.storage.wiki import LogEntry, WikiStore


def plan_fixes(findings: list[Finding]) -> tuple[list[FixAction], list[FixSkip]]:
    planned: list[FixAction] = []
    skipped: list[FixSkip] = []

    needs_rebuild = any(
        finding.category in {"orphan_page", "dead_link"}
        or (finding.category == "duplicate_slug" and finding.details.get("source") == "index")
        for finding in findings
    )
    if needs_rebuild:
        planned.append(FixAction("rebuild_index", "wiki/index.md", "planned"))

    orphan_vectors = sorted(
        finding.target for finding in findings if finding.category == "orphan_vector_chunk"
    )
    if orphan_vectors:
        planned.append(
            FixAction(
                "prune_orphan_vector_chunks",
                "vector/db",
                "planned",
                details={"ids": orphan_vectors},
            )
        )

    orphan_nodes = sorted(
        str(finding.details["node_id"])
        for finding in findings
        if finding.category == "graph_drift" and finding.details.get("kind") == "orphan_node"
    )
    if orphan_nodes:
        planned.append(
            FixAction(
                "prune_orphan_graph_nodes",
                "graph/graph.json",
                "planned",
                details={"ids": orphan_nodes},
            )
        )

    orphan_edges = sorted(
        str(finding.details["edge_id"])
        for finding in findings
        if finding.category == "graph_drift"
        and finding.details.get("kind") in {"orphan_edge", "dangling_edge"}
    )
    if orphan_edges:
        planned.append(
            FixAction(
                "prune_orphan_graph_edges",
                "graph/graph.json",
                "planned",
                details={"ids": orphan_edges},
            )
        )

    for finding in findings:
        if _is_planned(finding):
            continue
        skipped.append(
            FixSkip(
                category=finding.category,
                reason=_skip_reason(finding),
                message=f"`{finding.category}` requires manual review for `{finding.target}`",
                details={"target": finding.target},
            )
        )
    return planned, skipped


def apply_fixes(
    paths: RuntimePaths,
    planned: list[FixAction],
) -> tuple[list[FixAction], list[FixSkip]]:
    applied: list[FixAction] = []
    skipped: list[FixSkip] = []
    wiki_store = WikiStore(paths)
    vector_store: VectorStore | None = None
    graph_store = GraphStore(paths)

    for action in planned:
        try:
            if action.action == "rebuild_index":
                wiki_store.rebuild_index()
                applied_action = FixAction(action.action, action.target, "success", action.details)
            elif action.action == "prune_orphan_vector_chunks":
                vector_store = vector_store or VectorStore(paths)
                ids = [str(item) for item in action.details.get("ids", [])]
                vector_store.delete(ids)
                applied_action = FixAction(action.action, action.target, "success", action.details)
            elif action.action == "prune_orphan_graph_nodes":
                ids = [str(item) for item in action.details.get("ids", [])]
                removed = graph_store.prune_nodes(ids)
                applied_action = FixAction(
                    action.action,
                    action.target,
                    "success",
                    {**action.details, "removed": removed},
                )
            elif action.action == "prune_orphan_graph_edges":
                ids = [str(item) for item in action.details.get("ids", [])]
                removed = graph_store.prune_edges(ids)
                applied_action = FixAction(
                    action.action,
                    action.target,
                    "success",
                    {**action.details, "removed": removed},
                )
            else:  # pragma: no cover - enum exhaustiveness guard
                raise ValueError(f"unsupported fix action: {action.action}")
        except Exception as exc:
            failed = FixAction(action.action, action.target, "apply_failed", action.details)
            applied.append(failed)
            skipped.append(
                FixSkip(
                    category="graph_drift",
                    reason="apply_failed",
                    message=f"fix action `{action.action}` failed: {exc}",
                    details={"target": action.target},
                )
            )
            _append_audit_log(paths, failed)
            continue

        applied.append(applied_action)
        _append_audit_log(paths, applied_action)
    return applied, skipped


def _is_planned(finding: Finding) -> bool:
    if finding.category in {"orphan_page", "dead_link", "orphan_vector_chunk"}:
        return True
    if finding.category == "duplicate_slug":
        return finding.details.get("source") == "index"
    if finding.category == "graph_drift":
        return finding.details.get("kind") in {"orphan_node", "orphan_edge", "dangling_edge"}
    return False


def _skip_reason(finding: Finding) -> FixSkipReason:
    if finding.category in {
        "manifest_wiki_mismatch",
        "wiki_source_mismatch",
        "dangling_manifest_entry",
        "manifest_vector_mismatch",
    }:
        return "manifest_truth_unknown"
    if finding.category == "fingerprint_drift":
        return "requires_manual"
    return "unsupported_in_005"


def _append_audit_log(paths: RuntimePaths, action: FixAction) -> None:
    WikiStore(paths).append_log(
        LogEntry(
            timestamp=utc_now_iso(),
            event="lint",
            status="lint_fix_applied",
            target=action.target,
            action=action.action,
            outcome="success" if action.outcome == "success" else "apply_failed",
        )
    )

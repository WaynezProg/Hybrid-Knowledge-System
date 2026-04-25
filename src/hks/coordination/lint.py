"""Coordination ledger consistency checks."""

from __future__ import annotations

from datetime import datetime

from hks.coordination.models import (
    CoordinationFinding,
    CoordinationState,
    HandoffNote,
    ResourceReference,
)
from hks.core.paths import RuntimePaths
from hks.graph.store import GraphStore
from hks.storage.vector import VectorStore


def run_coordination_lint(
    state: CoordinationState,
    paths: RuntimePaths,
) -> list[CoordinationFinding]:
    findings: list[CoordinationFinding] = []
    findings.extend(_stale_active_leases(state))
    for handoff in state.handoffs.values():
        for reference in handoff.references:
            finding = _check_reference(reference, handoff, state, paths)
            if finding is not None:
                findings.append(finding)
    return findings


def _stale_active_leases(state: CoordinationState) -> list[CoordinationFinding]:
    now = datetime.now().astimezone()
    findings: list[CoordinationFinding] = []
    for lease in state.leases.values():
        if lease.status == "active" and datetime.fromisoformat(lease.expires_at) <= now:
            findings.append(
                {
                    "category": "stale_lease",
                    "severity": "warning",
                    "target": lease.lease_id,
                    "message": f"lease for {lease.resource_key} is expired but still active",
                }
            )
    return findings


def _check_reference(
    reference: ResourceReference,
    handoff: HandoffNote,
    state: CoordinationState,
    paths: RuntimePaths,
) -> CoordinationFinding | None:
    reference_type = reference["type"]
    value = reference["value"]
    exists = True
    if reference_type == "wiki_page":
        page_name = value if value.endswith(".md") else f"{value}.md"
        exists = (paths.wiki_pages / page_name).exists()
    elif reference_type == "raw_source":
        exists = (paths.raw_sources / value).exists()
    elif reference_type == "graph_node":
        exists = value in GraphStore(paths).load().nodes
    elif reference_type == "graph_edge":
        exists = value in GraphStore(paths).load().edges
    elif reference_type == "vector_chunk":
        exists = value in set(VectorStore(paths).list_ids())
    elif reference_type == "lease":
        exists = value in state.leases
    elif reference_type == "handoff":
        exists = value in state.handoffs
    else:
        exists = True
    if exists:
        return None
    return {
        "category": "missing_reference",
        "severity": "error",
        "target": handoff.handoff_id,
        "message": f"{reference_type} reference not found: {value}",
    }

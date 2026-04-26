"""Pure consistency checks for HKS runtime snapshots."""

from __future__ import annotations

from collections import Counter

from jsonschema import ValidationError

from hks.adapters.contracts import (
    validate_graphify_graph,
    validate_graphify_run,
    validate_llm_artifact,
    validate_watch_latest,
    validate_watch_plan,
    validate_watch_run,
    validate_wiki_artifact,
)
from hks.ingest.fingerprint import (
    ParserFlags,
    are_fingerprints_compatible,
    compute_parser_fingerprint,
)
from hks.lint.models import Finding, RuntimeSnapshot


def run_checks(snapshot: RuntimeSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(check_wiki(snapshot))
    findings.extend(check_manifest_wiki_raw(snapshot))
    findings.extend(check_vector(snapshot))
    findings.extend(check_graph(snapshot))
    findings.extend(check_fingerprint(snapshot))
    findings.extend(check_llm_artifacts(snapshot))
    findings.extend(check_wiki_synthesis(snapshot))
    findings.extend(check_graphify(snapshot))
    findings.extend(check_watch(snapshot))
    return sorted(
        findings,
        key=lambda finding: (finding.category, finding.target, finding.message),
    )


def check_wiki(snapshot: RuntimeSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    actual_slugs = set(snapshot.wiki_pages)
    listed_slugs = set(snapshot.wiki_index_slugs)

    for slug in sorted(actual_slugs - listed_slugs):
        findings.append(
            Finding.make(
                "orphan_page",
                slug,
                f"wiki page `{slug}` exists but is not listed in wiki/index.md",
            )
        )
    for slug in sorted(listed_slugs - actual_slugs):
        findings.append(
            Finding.make(
                "dead_link",
                slug,
                f"wiki/index.md references missing page `{slug}`",
            )
        )

    index_counts = Counter(snapshot.wiki_index_slugs)
    for slug in sorted(slug for slug, count in index_counts.items() if count > 1):
        findings.append(
            Finding.make(
                "duplicate_slug",
                slug,
                f"wiki/index.md lists slug `{slug}` more than once",
                details={"source": "index"},
            )
        )

    frontmatter_counts = Counter(record.page.slug for record in snapshot.wiki_pages.values())
    for slug in sorted(slug for slug, count in frontmatter_counts.items() if count > 1):
        findings.append(
            Finding.make(
                "duplicate_slug",
                slug,
                f"multiple wiki pages declare frontmatter slug `{slug}`",
                details={"source": "frontmatter"},
            )
        )
    return findings


def check_manifest_wiki_raw(snapshot: RuntimeSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    actual_slugs = set(snapshot.wiki_pages)
    manifest_relpaths = set(snapshot.manifest_entries)

    for relpath, entry in sorted(snapshot.manifest_entries.items()):
        if relpath not in snapshot.raw_source_relpaths:
            findings.append(
                Finding.make(
                    "dangling_manifest_entry",
                    relpath,
                    f"manifest entry `{relpath}` points to a missing raw source",
                )
            )
        for slug in entry.derived.wiki_pages:
            if slug not in actual_slugs:
                findings.append(
                    Finding.make(
                        "manifest_wiki_mismatch",
                        slug,
                        f"manifest entry `{relpath}` references missing wiki page `{slug}`",
                        details={"relpath": relpath},
                    )
                )

    for relpath in sorted(snapshot.raw_source_relpaths - manifest_relpaths):
        findings.append(
            Finding.make(
                "orphan_raw_source",
                relpath,
                f"raw source `{relpath}` exists but is not listed in manifest.json",
            )
        )

    for record in sorted(snapshot.wiki_pages.values(), key=lambda item: item.file_slug):
        page = record.page
        if page.origin != "ingest":
            continue
        if page.source_relpath not in manifest_relpaths:
            findings.append(
                Finding.make(
                    "wiki_source_mismatch",
                    record.file_slug,
                    (
                        f"wiki page `{record.file_slug}` points to source "
                        f"`{page.source_relpath}` not listed in manifest.json"
                    ),
                    details={"source_relpath": page.source_relpath},
                )
            )
    return findings


def check_vector(snapshot: RuntimeSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    manifest_vector_ids = {
        vector_id
        for entry in snapshot.manifest_entries.values()
        for vector_id in entry.derived.vector_ids
    }
    for vector_id in sorted(manifest_vector_ids - snapshot.vector_ids):
        findings.append(
            Finding.make(
                "manifest_vector_mismatch",
                vector_id,
                f"manifest references missing vector chunk `{vector_id}`",
            )
        )
    for vector_id in sorted(snapshot.vector_ids - manifest_vector_ids):
        findings.append(
            Finding.make(
                "orphan_vector_chunk",
                vector_id,
                f"vector chunk `{vector_id}` exists but no manifest entry references it",
            )
        )
    return findings


def check_graph(snapshot: RuntimeSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    manifest_relpaths = set(snapshot.manifest_entries)
    manifest_node_ids = {
        node_id
        for entry in snapshot.manifest_entries.values()
        for node_id in entry.derived.graph_nodes
    }
    manifest_edge_ids = {
        edge_id
        for entry in snapshot.manifest_entries.values()
        for edge_id in entry.derived.graph_edges
    }
    graph_node_ids = set(snapshot.graph.nodes)
    graph_edge_ids = set(snapshot.graph.edges)

    for node_id in sorted(manifest_node_ids - graph_node_ids):
        findings.append(
            Finding.make(
                "graph_drift",
                node_id,
                f"manifest references missing graph node `{node_id}`",
                details={"kind": "missing_node"},
            )
        )
    for edge_id in sorted(manifest_edge_ids - graph_edge_ids):
        findings.append(
            Finding.make(
                "graph_drift",
                edge_id,
                f"manifest references missing graph edge `{edge_id}`",
                details={"kind": "missing_edge"},
            )
        )
    for node_id in sorted(graph_node_ids - manifest_node_ids):
        node = snapshot.graph.nodes[node_id]
        if not set(node.source_relpaths) & manifest_relpaths:
            findings.append(
                Finding.make(
                    "graph_drift",
                    node_id,
                    f"graph node `{node_id}` is not backed by manifest entries",
                    details={"kind": "orphan_node", "node_id": node_id},
                )
            )
    for edge_id in sorted(graph_edge_ids - manifest_edge_ids):
        edge = snapshot.graph.edges[edge_id]
        if edge.source_relpath not in manifest_relpaths:
            findings.append(
                Finding.make(
                    "graph_drift",
                    edge_id,
                    f"graph edge `{edge_id}` is not backed by manifest entries",
                    details={"kind": "orphan_edge", "edge_id": edge_id},
                )
            )
    for edge_id, edge in sorted(snapshot.graph.edges.items()):
        if edge.source not in graph_node_ids or edge.target not in graph_node_ids:
            findings.append(
                Finding.make(
                    "graph_drift",
                    edge_id,
                    f"graph edge `{edge_id}` points to a missing node",
                    details={"kind": "dangling_edge", "edge_id": edge_id},
                )
            )
        elif edge.source_relpath not in manifest_relpaths:
            findings.append(
                Finding.make(
                    "graph_drift",
                    edge_id,
                    f"graph edge `{edge_id}` points to missing source `{edge.source_relpath}`",
                    details={"kind": "orphan_edge", "edge_id": edge_id},
                )
            )
    return findings


def check_fingerprint(snapshot: RuntimeSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    flags = ParserFlags()
    for relpath, entry in sorted(snapshot.manifest_entries.items()):
        current = compute_parser_fingerprint(entry.format, flags)
        if not are_fingerprints_compatible(entry.parser_fingerprint, current):
            findings.append(
                Finding.make(
                    "fingerprint_drift",
                    relpath,
                    f"parser fingerprint drift for `{relpath}`",
                    details={
                        "stored": entry.parser_fingerprint,
                        "current": current,
                    },
                )
            )
    return findings


def check_llm_artifacts(snapshot: RuntimeSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    for relpath, error in sorted(snapshot.llm_artifact_errors.items()):
        findings.append(
            Finding.make(
                "llm_artifact_corrupt",
                relpath,
                f"LLM extraction artifact `{relpath}` cannot be parsed",
                details={"error": error},
            )
        )
    for relpath, payload in sorted(snapshot.llm_artifacts.items()):
        try:
            validate_llm_artifact(payload)
        except ValidationError as exc:
            findings.append(
                Finding.make(
                    "llm_artifact_invalid",
                    relpath,
                    f"LLM extraction artifact `{relpath}` does not match schema",
                    details={"error": exc.message},
                )
            )
    return findings


def check_wiki_synthesis(snapshot: RuntimeSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    for relpath, error in sorted(snapshot.wiki_candidate_artifact_errors.items()):
        findings.append(
            Finding.make(
                "wiki_candidate_artifact_corrupt",
                relpath,
                f"wiki synthesis candidate artifact `{relpath}` cannot be parsed",
                details={"error": error},
            )
        )
    for relpath, payload in sorted(snapshot.wiki_candidate_artifacts.items()):
        try:
            validate_wiki_artifact(payload)
        except ValidationError as exc:
            findings.append(
                Finding.make(
                    "wiki_candidate_artifact_invalid",
                    relpath,
                    f"wiki synthesis candidate artifact `{relpath}` does not match schema",
                    details={"error": exc.message},
                )
            )

    required = {
        "generated_at",
        "extraction_artifact_id",
        "wiki_candidate_artifact_id",
        "source_fingerprint",
        "parser_fingerprint",
        "prompt_version",
        "provider_id",
        "model_id",
    }
    for record in sorted(snapshot.wiki_pages.values(), key=lambda item: item.file_slug):
        page = record.page
        if page.origin != "llm_wiki":
            continue
        missing = sorted(key for key in required if not page.metadata.get(key))
        if missing:
            findings.append(
                Finding.make(
                    "wiki_synthesis_frontmatter_invalid",
                    record.file_slug,
                    f"llm_wiki page `{record.file_slug}` is missing synthesis frontmatter",
                    details={"missing": missing},
                )
            )
        candidate_id = page.metadata.get("wiki_candidate_artifact_id")
        if candidate_id and f"{candidate_id}.json" not in snapshot.wiki_candidate_artifacts:
            findings.append(
                Finding.make(
                    "wiki_synthesis_frontmatter_invalid",
                    record.file_slug,
                    f"llm_wiki page `{record.file_slug}` references missing candidate artifact",
                    details={"wiki_candidate_artifact_id": candidate_id},
                )
            )
    return findings


def check_graphify(snapshot: RuntimeSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    for target in sorted(snapshot.graphify_partial_runs):
        findings.append(
            Finding.make(
                "graphify_partial_run",
                target,
                f"graphify run `{target}` is missing required artifacts",
            )
        )
    if snapshot.graphify_latest_error:
        findings.append(
            Finding.make(
                "graphify_latest_mismatch",
                "graphify/latest.json",
                snapshot.graphify_latest_error,
            )
        )
    for relpath, error in sorted(snapshot.graphify_artifact_errors.items()):
        findings.append(
            Finding.make(
                "graphify_corrupt_upstream_artifact",
                relpath,
                f"graphify artifact `{relpath}` cannot be parsed",
                details={"error": error},
            )
        )
    for relpath, payload in sorted(snapshot.graphify_run_manifests.items()):
        try:
            validate_graphify_run(payload)
        except ValidationError as exc:
            findings.append(
                Finding.make(
                    "graphify_invalid_graph",
                    relpath,
                    f"graphify run manifest `{relpath}` does not match schema",
                    details={"error": exc.message},
                )
            )
    for relpath, payload in sorted(snapshot.graphify_graph_artifacts.items()):
        try:
            validate_graphify_graph(payload)
        except ValidationError as exc:
            findings.append(
                Finding.make(
                    "graphify_invalid_graph",
                    relpath,
                    f"graphify graph artifact `{relpath}` does not match schema",
                    details={"error": exc.message},
                )
            )
    return findings


def check_watch(snapshot: RuntimeSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    for target in sorted(snapshot.watch_partial_runs):
        findings.append(
            Finding.make(
                "watch_partial_run",
                target,
                f"watch run `{target}` is partial or missing required state",
            )
        )
    if snapshot.watch_latest_error:
        findings.append(
            Finding.make(
                "watch_latest_mismatch",
                "watch/latest.json",
                snapshot.watch_latest_error,
            )
        )
    for relpath, error in sorted(snapshot.watch_artifact_errors.items()):
        findings.append(
            Finding.make(
                "watch_artifact_corrupt",
                relpath,
                f"watch artifact `{relpath}` cannot be parsed",
                details={"error": error},
            )
        )
    for relpath, payload in sorted(snapshot.watch_artifacts.items()):
        try:
            if relpath.startswith("watch/plans/"):
                validate_watch_plan(payload)
            elif relpath.startswith("watch/runs/"):
                validate_watch_run(payload)
            elif relpath == "watch/latest.json":
                validate_watch_latest(payload)
        except ValidationError as exc:
            findings.append(
                Finding.make(
                    "watch_artifact_invalid",
                    relpath,
                    f"watch artifact `{relpath}` does not match schema",
                    details={"error": exc.message},
                )
            )
    return findings

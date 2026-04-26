"""Build derived Graphify artifacts from existing HKS layers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from slugify import slugify

from hks.core.manifest import load_manifest, utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import ExitCode, KSError
from hks.graph.store import GraphPayload, GraphStore
from hks.graphify.clustering import cluster
from hks.graphify.models import (
    GraphifyAuditFinding,
    GraphifyEdge,
    GraphifyGraph,
    GraphifyNode,
    GraphifyProvenance,
    GraphifySourceLayer,
)
from hks.graphify.validation import validate_graph
from hks.storage.wiki import WikiPage


def build_graph(paths: RuntimePaths | None = None) -> tuple[GraphifyGraph, str, list[str]]:
    resolved = paths or runtime_paths()
    _assert_runtime_ready(resolved)
    manifest = load_manifest(resolved.manifest)
    graph_payload = _load_graph(resolved)
    wiki_pages = _load_wiki_pages(resolved)

    nodes: list[GraphifyNode] = []
    edges: list[GraphifyEdge] = []
    findings: list[GraphifyAuditFinding] = []
    source_layers: list[str] = []
    input_layers: list[str] = []

    if wiki_pages:
        source_layers.append("wiki")
        input_layers.append("wiki")
        if any(page.origin == "llm_wiki" for _, page in wiki_pages):
            input_layers.append("llm_wiki")
    if graph_payload.nodes or graph_payload.edges:
        source_layers.append("graph")
        input_layers.append("graph")
    if (resolved.root / "llm" / "extractions").exists():
        input_layers.append("llm_extraction")

    for relpath, entry in sorted(manifest.entries.items()):
        nodes.append(
            GraphifyNode(
                id=_node_id("source", relpath),
                label=relpath,
                kind="source",
                source_layer="wiki",
                source_ref=f"raw_sources/{relpath}",
                provenance=GraphifyProvenance(
                    source_relpath=relpath,
                    source_fingerprint=entry.sha256,
                ),
            )
        )

    for slug, page in wiki_pages:
        node_id = _node_id("wiki", slug)
        layer: GraphifySourceLayer = "llm_wiki" if page.origin == "llm_wiki" else "wiki"
        nodes.append(
            GraphifyNode(
                id=node_id,
                label=page.title,
                kind="wiki_page",
                source_layer=layer,
                source_ref=f"wiki/pages/{slug}.md",
                provenance=GraphifyProvenance(
                    source_relpath=page.source_relpath,
                    wiki_page=slug,
                    artifact_id=page.metadata.get("wiki_candidate_artifact_id"),
                    source_fingerprint=page.metadata.get("source_fingerprint"),
                ),
            )
        )
        source_id = _node_id("source", page.source_relpath)
        if any(node.id == source_id for node in nodes):
            edges.append(
                _edge(
                    source=node_id,
                    target=source_id,
                    relation="references",
                    evidence="EXTRACTED",
                    confidence_score=1.0,
                    source_layer=layer,
                    source_ref=f"wiki/pages/{slug}.md",
                )
            )

    for node in graph_payload.nodes.values():
        nodes.append(
            GraphifyNode(
                id=_node_id("graph", node.id),
                label=node.label,
                kind="entity",
                source_layer="graph",
                source_ref=node.id,
                provenance=GraphifyProvenance(
                    source_relpath=(node.source_relpaths[0] if node.source_relpaths else None),
                    wiki_page=(node.wiki_slugs[0] if node.wiki_slugs else None),
                ),
            )
        )
    graph_node_ids = {_node_id("graph", node_id) for node_id in graph_payload.nodes}
    for graph_edge in graph_payload.edges.values():
        source = _node_id("graph", graph_edge.source)
        target = _node_id("graph", graph_edge.target)
        if source not in graph_node_ids or target not in graph_node_ids:
            findings.append(
                GraphifyAuditFinding(
                    severity="warning",
                    code="graphify_invalid_graph",
                    message=f"graph edge `{graph_edge.id}` points to a missing node",
                    source_ref=graph_edge.id,
                    evidence=graph_edge.evidence,
                )
            )
            continue
        edges.append(
            _edge(
                source=source,
                target=target,
                relation=graph_edge.relation,
                evidence="EXTRACTED",
                confidence_score=1.0,
                source_layer="graph",
                source_ref=graph_edge.id,
                rationale=graph_edge.evidence,
            )
        )

    if not nodes or not source_layers:
        raise KSError(
            "沒有可 Graphify 的 HKS 資料",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks ingest <path>` first",
            route="graph",
        )

    deduped_nodes = _dedupe_nodes(nodes)
    clustered_nodes, communities = cluster(deduped_nodes, _dedupe_edges(edges))
    graph = validate_graph(
        GraphifyGraph(
            generated_at=utc_now_iso(),
            input_layers=sorted(set(input_layers)),  # type: ignore[arg-type]
            nodes=clustered_nodes,
            edges=_dedupe_edges(edges),
            communities=communities,
            audit_findings=findings,
        )
    )
    return graph, _input_fingerprint(resolved, graph), sorted(set(source_layers))


def _assert_runtime_ready(paths: RuntimePaths) -> None:
    if not paths.root.exists() or not paths.manifest.exists():
        raise KSError(
            "/ks/ 尚未初始化，請先執行 ks ingest <path>",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks ingest <path>`",
            route="graph",
        )


def _load_graph(paths: RuntimePaths) -> GraphPayload:
    try:
        return GraphStore(paths).load()
    except Exception as exc:
        raise KSError(
            "graph.json 無法用於 Graphify",
            exit_code=ExitCode.DATAERR,
            code="GRAPHIFY_INVALID_GRAPH",
            details=[str(exc)],
            route="graph",
        ) from exc


def _load_wiki_pages(paths: RuntimePaths) -> list[tuple[str, WikiPage]]:
    if not paths.wiki_pages.exists():
        return []
    pages: list[tuple[str, WikiPage]] = []
    for path in sorted(paths.wiki_pages.glob("*.md")):
        try:
            pages.append((path.stem, WikiPage.from_markdown(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return pages


def _node_id(prefix: str, value: str) -> str:
    slug = slugify(value, separator="-") or hashlib.sha1(
        value.encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:12]
    return f"{prefix}:{slug}"


def _edge(
    *,
    source: str,
    target: str,
    relation: str,
    evidence: str,
    confidence_score: float,
    source_layer: str,
    source_ref: str,
    rationale: str | None = None,
) -> GraphifyEdge:
    payload = f"{source}|{target}|{relation}|{source_ref}"
    digest = hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return GraphifyEdge(
        id=f"graphify-edge:{digest}",
        source=source,
        target=target,
        relation=relation,
        evidence=evidence,  # type: ignore[arg-type]
        confidence_score=confidence_score,
        weight=confidence_score,
        source_layer=source_layer,  # type: ignore[arg-type]
        source_ref=source_ref,
        rationale=rationale,
    )


def _dedupe_nodes(nodes: list[GraphifyNode]) -> list[GraphifyNode]:
    deduped: dict[str, GraphifyNode] = {}
    for node in nodes:
        deduped.setdefault(node.id, node)
    return [deduped[key] for key in sorted(deduped)]


def _dedupe_edges(edges: list[GraphifyEdge]) -> list[GraphifyEdge]:
    deduped: dict[str, GraphifyEdge] = {}
    for edge in edges:
        deduped.setdefault(edge.id, edge)
    return [deduped[key] for key in sorted(deduped)]


def _input_fingerprint(paths: RuntimePaths, graph: GraphifyGraph) -> str:
    digest = hashlib.sha256()
    for path in _fingerprint_paths(paths):
        digest.update(path.relative_to(paths.root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    graph_payload = graph.to_dict()
    graph_payload["generated_at"] = "<stable>"
    digest.update(json.dumps(graph_payload, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def _fingerprint_paths(paths: RuntimePaths) -> list[Path]:
    candidates: list[Path] = []
    for root in (paths.wiki, paths.graph_dir, paths.root / "llm"):
        if root.exists():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    if paths.manifest.exists():
        candidates.append(paths.manifest)
    return sorted(set(candidates))

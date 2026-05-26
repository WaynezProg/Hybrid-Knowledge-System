"""Convert winning retrieval candidates into response evidence."""

from __future__ import annotations

from hks.retrieval.models import Candidate


def evidence_quote(text: object, *, limit: int = 240) -> str:
    normalized = " ".join(str(text or "").split())
    return normalized[:limit]


def metadata_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    custom = custom_candidate_evidence(candidate)
    if custom:
        return custom
    if candidate.source_route == "wiki":
        return wiki_candidate_evidence(candidate)
    if candidate.source_route == "graph":
        return graph_candidate_evidence(candidate)
    if candidate.source_route == "page_tree":
        return page_tree_candidate_evidence(candidate)
    return vector_candidate_evidence(candidate)


def custom_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    items = candidate.metadata.get("_hks_evidence_items")
    if not isinstance(items, list):
        return []

    evidence: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        relpath = item.get("source_relpath")
        quote = item.get("quote")
        if not isinstance(relpath, str) or not relpath:
            continue
        if not isinstance(quote, str) or not quote:
            continue
        route = item.get("route")
        evidence.append(
            {
                "source_relpath": relpath,
                "route": route if isinstance(route, str) and route else candidate.source_route,
                "quote": evidence_quote(quote),
            }
        )
    return evidence


def wiki_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpath = metadata_str(candidate.metadata, "source_relpath")
    quote = evidence_quote(candidate.metadata.get("quote") or candidate.text)
    if relpath is None or not quote:
        return []
    return [{"source_relpath": relpath, "route": "wiki", "quote": quote}]


def graph_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpaths = candidate.metadata.get("relpaths")
    evidence_by_relpath = candidate.metadata.get("evidence_by_relpath")
    if not isinstance(relpaths, list):
        return []
    quotes = evidence_by_relpath if isinstance(evidence_by_relpath, dict) else {}
    evidence: list[dict[str, object]] = []
    seen: set[str] = set()
    for relpath in relpaths:
        if not isinstance(relpath, str) or relpath in seen:
            continue
        seen.add(relpath)
        quote = evidence_quote(quotes.get(relpath) or candidate.text)
        if quote:
            evidence.append(
                {"source_relpath": relpath, "route": "graph", "quote": quote}
            )
    return evidence


def vector_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpath = metadata_str(candidate.metadata, "source_relpath")
    quote = evidence_quote(candidate.text)
    if relpath is None or not quote:
        return []

    entry: dict[str, object] = {
        "source_relpath": relpath,
        "route": "vector",
        "quote": quote,
    }
    section_path = metadata_str(candidate.metadata, "section_path")
    if section_path is not None:
        entry["section_path"] = section_path
    page_range = candidate.metadata.get("page_range")
    if isinstance(page_range, dict):
        entry["page_range"] = page_range
    return [entry]


def page_tree_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpath = metadata_str(candidate.metadata, "source_relpath")
    if relpath is None:
        return []
    entry: dict[str, object] = {
        "source_relpath": relpath,
        "route": "page_tree",
        "quote": evidence_quote(candidate.text),
    }
    section_path = metadata_str(candidate.metadata, "section_path")
    if section_path is not None:
        entry["section_path"] = section_path
    page_range = candidate.metadata.get("page_range")
    if isinstance(page_range, dict):
        entry["page_range"] = page_range
    return [entry]

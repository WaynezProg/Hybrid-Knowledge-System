"""Resolve generated project-memory hits to complete, source-bound entries.

Older indexes split an entire project into token windows, so an entry's trailing id
can land next to the following rule. Resolve nominated sources against their hashed
raw artifact at query time. This also works for existing indexes without re-ingest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from hks.core.manifest import Manifest
from hks.core.paths import RuntimePaths
from hks.retrieval.bm25 import CoverageScorer, holds_identifiers, identifier_terms, lexical_tokens
from hks.retrieval.language import normalize_query
from hks.retrieval.models import Candidate
from hks.retrieval.subjects import query_subject_text
from hks.retrievers.vector import vector_hit_final_score
from hks.storage.vector import SearchHit

_MAX_SOURCE_BYTES = 1_000_000
_CANDIDATE_LIMIT = 5
_MEMORY_ID = re.compile(r"(?<![A-Za-z0-9_])m_[0-9a-f]{10}(?![A-Za-z0-9_])", re.I)
_ENTRY = re.compile(
    r"^-\s+(?P<text>.+)（(?P<id>m_[0-9a-f]{10})；確認於 "
    r"(?P<confirmed>\d{4}-\d{2}-\d{2})；來源 (?P<sources>[^\n]*)）\s*$"
)


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    text: str
    kind: str
    confirmed: str


@dataclass(frozen=True)
class ProjectMemory:
    project: str
    entries: tuple[MemoryEntry, ...]


def parse_project_memory(text: str) -> ProjectMemory | None:
    """Recognize the export format, including its count; never guess at ordinary Markdown."""
    if not text.startswith("---\n"):
        return None
    closing = text.find("\n---\n", 4)
    if closing < 0 or closing > 8192:
        return None
    try:
        metadata = YAML(typ="safe").load(text[4:closing])
    except YAMLError:
        return None
    if not isinstance(metadata, dict) or metadata.get("type") != "project_memory":
        return None
    project = metadata.get("project")
    count = metadata.get("memories")
    if not isinstance(project, str) or not project.strip() or type(count) is not int:
        return None
    entries = []
    kind = ""
    for line in text[closing + 5 :].splitlines():
        if line.startswith("## "):
            kind = line[3:].strip()
        match = _ENTRY.fullmatch(line)
        if match is None:
            continue
        try:
            date.fromisoformat(match["confirmed"])
        except ValueError:
            return None
        entries.append(MemoryEntry(match["id"], match["text"].strip(), kind, match["confirmed"]))
    if len(entries) != count or len({entry.id for entry in entries}) != len(entries):
        return None
    return ProjectMemory(project, tuple(entries))


def _read_source(relpath: str, paths: RuntimePaths, manifest: Manifest) -> ProjectMemory | None:
    entry = manifest.entries.get(relpath)
    if entry is None or entry.format != "md":
        return None
    try:
        path = (paths.raw_sources / relpath).resolve()
        if not path.is_relative_to(paths.raw_sources.resolve()):
            return None
        if path.stat().st_size > _MAX_SOURCE_BYTES:
            return None
        with path.open("rb") as source:
            content = source.read(_MAX_SOURCE_BYTES + 1)
        if len(content) > _MAX_SOURCE_BYTES:
            return None
        if sha256(content).hexdigest() != entry.sha256:
            return None
        return parse_project_memory(content.decode("utf-8"))
    except (OSError, UnicodeError, RuntimeError):
        return None


def refine_project_memory_candidates(
    question: str, candidates: list[Candidate], *, paths: RuntimePaths, manifest: Manifest
) -> tuple[list[Candidate], int]:
    """Replace nominated project windows with source-supported atomic records.

    Keep a vector score only when that nominated window holds the whole rule. Otherwise
    these are source-bound wiki entries, never invented vector similarities. Unstructured documents
    and semantic-only hits retain their original path.
    """
    documents: dict[str, ProjectMemory] = {}
    for relpath in dict.fromkeys(
        item.metadata.get("source_relpath")
        for item in candidates
        if isinstance(item.metadata.get("source_relpath"), str)
    ):
        assert isinstance(relpath, str)
        document = _read_source(relpath, paths, manifest)
        if document is not None:
            documents[relpath] = document
    if not documents:
        return candidates, 0

    subject = query_subject_text(question)
    asked_ids = {mid.lower() for mid in _MEMORY_ID.findall(question)}
    required = identifier_terms(question)
    asked_terms = set(lexical_tokens(subject))
    records: list[tuple[str, ProjectMemory, MemoryEntry, str]] = []
    resolved: set[str] = set()
    for relpath, document in documents.items():
        owner = Path(document.project).name or document.project
        owner_terms = set(lexical_tokens(normalize_query(owner)))
        # A matching project name is context, not evidence for every rule in that project.
        body_terms = asked_terms - owner_terms
        for entry in document.entries:
            match_text = f"{owner}\n{entry.id}\n{entry.text}"
            if asked_ids and asked_ids != {entry.id.lower()}:
                continue
            if not holds_identifiers(required, match_text):
                continue
            if not asked_ids and not body_terms.intersection(lexical_tokens(entry.text)):
                continue
            records.append((relpath, document, entry, match_text))
            resolved.add(relpath)
        if asked_ids or not document.entries:
            # A neighboring entry must not answer a known or unknown memory id, even
            # when a token window happened to hold that id beside some other rule.
            resolved.add(relpath)
    if not resolved:
        return candidates, 0

    scorer = CoverageScorer(subject, [record[3] for record in records])
    atomic: list[Candidate] = []
    for relpath, document, entry, match_text in records:
        coverage = scorer.score(match_text)
        if required:
            coverage = 0.5 + 0.5 * coverage
        score = round(0.85 * coverage, 4)
        owner = Path(document.project).name or document.project
        literal = re.sub(r"\s+", "", entry.text).casefold()
        supported = [
            item
            for item in candidates
            if item.source_route == "vector"
            and item.metadata.get("source_relpath") == relpath
            and literal
            in re.sub(r"\s+", "", str(item.metadata.get("_hks_match_text", item.text))).casefold()
        ]
        support = (
            max(supported, key=lambda item: item.score) if supported and not asked_ids else None
        )
        route = support.source_route if support is not None else "wiki"
        if support is not None:
            similarity = support.metadata.get("vector_similarity", support.score)
            assert isinstance(similarity, int | float)
            score = vector_hit_final_score(
                question, SearchHit("", match_text, float(similarity), {})
            )
        metadata = dict(support.metadata) if support is not None else {}
        metadata.pop("quote", None)
        metadata.update(
            {
                "source_relpath": relpath,
                "source_project": document.project,
                "memory_id": entry.id,
                "memory_kind": entry.kind,
                "last_confirmed_at": entry.confirmed,
                "query_coverage": round(coverage, 4),
                "final_score": score,
                "_hks_match_text": match_text,
                "_hks_evidence_items": [
                    {
                        "source_relpath": relpath,
                        "route": route,
                        "quote": entry.text,
                    }
                ],
            }
        )
        atomic.append(
            Candidate(
                text=f"{owner}：{entry.text}",
                source_route=route,
                score=score,
                metadata=metadata,
            )
        )
    # Keep bounded, relevant entries at the first replaced source's position, so the
    # existing LLM rerank cap cannot hide them behind the rest of the candidates.
    atomic.sort(key=lambda item: -item.score)
    refined: list[Candidate] = []
    inserted = False
    for candidate in candidates:
        if candidate.metadata.get("source_relpath") not in resolved:
            refined.append(candidate)
        elif not inserted:
            refined.extend(atomic[:_CANDIDATE_LIMIT])
            inserted = True
    return refined, len(resolved)

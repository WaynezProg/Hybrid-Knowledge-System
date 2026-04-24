"""Markdown-backed wiki storage for Phase 1."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

from slugify import slugify

from hks.core.manifest import utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.ingest.office_common import SkippedSegment

type Origin = Literal["ingest", "writeback"]
type Route = Literal["wiki", "graph", "vector"]
type EventType = Literal["ingest", "writeback"]
type EventStatus = Literal[
    "created",
    "updated",
    "skipped",
    "unsupported",
    "failed",
    "committed",
    "declined",
    "skip-non-tty",
    "auto-committed",
    "auto-skipped-low-confidence",
]

FRONTMATTER_BOUNDARY = "\n---\n"


@dataclass(slots=True)
class WikiPage:
    slug: str
    title: str
    summary: str
    body: str
    source_relpath: str
    origin: Origin
    updated_at: str

    def to_markdown(self) -> str:
        if self.origin == "writeback":
            source = self.source_relpath
        else:
            source = f"raw_sources/{self.source_relpath}"
        header = "\n".join(
            [
                "---",
                f"slug: {self.slug}",
                f"title: {self.title}",
                f"summary: {self.summary}",
                f"source: {source}",
                f"origin: {self.origin}",
                f"updated_at: {self.updated_at}",
                "---",
                "",
            ]
        )
        return f"{header}\n{self.body.strip()}\n"

    @classmethod
    def from_markdown(cls, text: str) -> WikiPage:
        if not text.startswith("---\n"):
            raise ValueError("wiki page missing frontmatter")
        frontmatter_blob, body = text.removeprefix("---\n").split(FRONTMATTER_BOUNDARY, 1)
        metadata: dict[str, str] = {}
        for line in frontmatter_blob.splitlines():
            if not line.strip():
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
        source_value = metadata.get("source", "")
        if source_value.startswith("raw_sources/"):
            source_value = source_value.removeprefix("raw_sources/")
        origin = metadata["origin"]
        if origin not in {"ingest", "writeback"}:
            raise ValueError(f"invalid wiki origin: {origin}")
        return cls(
            slug=metadata["slug"],
            title=metadata["title"],
            summary=metadata["summary"],
            body=body.strip(),
            source_relpath=source_value,
            origin=cast(Origin, origin),
            updated_at=metadata["updated_at"],
        )


@dataclass(frozen=True, slots=True)
class WikiIndexEntry:
    slug: str
    title: str
    summary: str


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: str
    event: EventType
    status: EventStatus
    target: str | None = None
    reason: str | None = None
    query: str | None = None
    route: Route | None = None
    source: list[Route] = field(default_factory=list)
    pages_touched: list[str] = field(default_factory=list)
    confidence: float | None = None
    skipped_segments: list[SkippedSegment] = field(default_factory=list)
    pptx_notes: Literal["included", "excluded"] | None = None

    def to_markdown(self) -> str:
        timestamp = self.timestamp.replace("T", " ")[:16]
        lines = [f"## {timestamp} | {self.event} | {self.status}"]
        details: list[tuple[str, str]] = []
        if self.target:
            details.append(("target", self.target))
        if self.reason:
            details.append(("reason", self.reason))
        if self.query:
            details.append(("query", self.query))
        if self.route:
            details.append(("route", self.route))
        if self.source:
            details.append(("source", f"[{', '.join(self.source)}]"))
        if self.pages_touched:
            details.append(("pages touched", ", ".join(self.pages_touched)))
        if self.confidence is not None:
            details.append(("confidence", f"{self.confidence:.2f}"))
        if self.skipped_segments:
            aggregated: dict[str, int] = {}
            for segment in self.skipped_segments:
                aggregated[segment.type] = aggregated.get(segment.type, 0) + segment.count
            details.append(
                (
                    "skipped_segments",
                    ",".join(f"{k}:{v}" for k, v in sorted(aggregated.items())),
                )
            )
        if self.pptx_notes is not None:
            details.append(("pptx_notes", self.pptx_notes))
        lines.extend(f"- {key}: {value}" for key, value in details)
        return "\n".join(lines) + "\n\n"


class WikiStore:
    def __init__(self, paths: RuntimePaths | None = None) -> None:
        self.paths = paths or runtime_paths()

    @property
    def index_path(self) -> Path:
        return self.paths.wiki / "index.md"

    @property
    def log_path(self) -> Path:
        return self.paths.wiki / "log.md"

    def ensure(self) -> None:
        self.paths.wiki.mkdir(parents=True, exist_ok=True)
        self.paths.wiki_pages.mkdir(parents=True, exist_ok=True)
        self.index_path.touch(exist_ok=True)
        self.log_path.touch(exist_ok=True)

    def slug_base(self, value: str, *, fallback: str = "untitled") -> str:
        slug = slugify(value, separator="-")
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        return slug or fallback

    def next_slug(self, base: str, *, preferred_slug: str | None = None) -> str:
        self.ensure()
        if preferred_slug:
            return preferred_slug

        slug = base
        index = 2
        while (self.paths.wiki_pages / f"{slug}.md").exists():
            slug = f"{base}-{index}"
            index += 1
        return slug

    def write_page(
        self,
        *,
        title: str,
        summary: str,
        body: str,
        source_relpath: str,
        origin: Origin,
        preferred_slug: str | None = None,
    ) -> WikiPage:
        self.ensure()
        base = self.slug_base(preferred_slug or title or Path(source_relpath).stem)
        fallback = f"untitled-{abs(hash(source_relpath)) % 100000:05d}"
        slug = self.next_slug(base or fallback, preferred_slug=preferred_slug)
        page = WikiPage(
            slug=slug,
            title=title.strip() or slug,
            summary=summary.strip(),
            body=body.strip(),
            source_relpath=source_relpath,
            origin=origin,
            updated_at=utc_now_iso(),
        )
        (self.paths.wiki_pages / f"{slug}.md").write_text(page.to_markdown(), encoding="utf-8")
        self.rebuild_index()
        return page

    def delete_pages(self, slugs: list[str]) -> None:
        for slug in slugs:
            path = self.paths.wiki_pages / f"{slug}.md"
            if path.exists():
                path.unlink()
        self.rebuild_index()

    def load_page(self, slug: str) -> WikiPage:
        text = (self.paths.wiki_pages / f"{slug}.md").read_text(encoding="utf-8")
        return WikiPage.from_markdown(text)

    def list_pages(self) -> list[WikiPage]:
        self.ensure()
        pages: list[WikiPage] = []
        for path in sorted(self.paths.wiki_pages.glob("*.md")):
            pages.append(WikiPage.from_markdown(path.read_text(encoding="utf-8")))
        return pages

    def rebuild_index(self) -> None:
        self.ensure()
        entries = [
            f"- [{page.title}](pages/{page.slug}.md) — {page.summary}"
            for page in sorted(self.list_pages(), key=lambda page: page.slug)
        ]
        lines = ["# Wiki Index", ""] + entries if entries else ["# Wiki Index"]
        content = "\n".join(lines).strip()
        self.index_path.write_text(f"{content}\n" if content else "", encoding="utf-8")

    def append_log(self, entry: LogEntry) -> None:
        self.ensure()
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(entry.to_markdown())

    def reconcile(self) -> dict[str, list[str]]:
        self.ensure()
        listed = set()
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            match = re.search(r"\(pages/(.+?)\.md\)", line)
            if match:
                listed.add(match.group(1))
        actual = {path.stem for path in self.paths.wiki_pages.glob("*.md")}
        return {
            "orphans": sorted(actual - listed),
            "dead_links": sorted(listed - actual),
        }

    def overview(self, *, limit: int = 5) -> str | None:
        pages = self.list_pages()[:limit]
        if not pages:
            return None
        return "\n".join(f"- {page.title}: {page.summary}" for page in pages)

    def pages_for_source_relpaths(self, relpaths: list[str]) -> list[WikiPage]:
        wanted = set(relpaths)
        if not wanted:
            return []
        return [page for page in self.list_pages() if page.source_relpath in wanted]

    def search(self, query: str) -> WikiPage | None:
        pages = self.list_pages()
        if not pages:
            return None

        lowered_query = query.lower()
        terms = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", lowered_query)
        best_score = 0
        best_page: WikiPage | None = None
        for page in pages:
            title = page.title.lower()
            summary = page.summary.lower()
            body = page.body.lower()
            score = 0
            if lowered_query and lowered_query in title:
                score += 8
            if lowered_query and lowered_query in summary:
                score += 6
            if lowered_query and lowered_query in body:
                score += 4
            for term in terms:
                if term in title:
                    score += 4
                if term in summary:
                    score += 3
                if term in body:
                    score += 1
            if score > best_score:
                best_score = score
                best_page = page

        if best_page is not None and best_score > 0:
            return best_page

        if any(keyword in query for keyword in ("摘要", "總結", "summary", "overview")):
            return pages[0]
        return None

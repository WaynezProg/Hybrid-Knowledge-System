"""PDF parser with structural segment extraction via PyMuPDF."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from hks.core.config import config_value
from hks.errors import ExitCode, KSError
from hks.ingest.models import ParsedDocument
from hks.ingest.office_common import Segment

if TYPE_CHECKING:
    import fitz


def max_file_mb() -> int:
    return int(config_value("HKS_MAX_FILE_MB") or "200")


def parse(path: Path) -> ParsedDocument:
    size_limit = max_file_mb() * 1024 * 1024
    if path.stat().st_size > size_limit:
        raise KSError(
            f"檔案超過大小上限：{path}",
            exit_code=ExitCode.DATAERR,
            code="OVERSIZED",
            details=[f"limit_mb={max_file_mb()}"],
        )

    try:
        doc = _open_pdf(path)
    except Exception as exc:
        raise _pdf_read_error(path, exc) from exc

    try:
        if len(doc) == 0:
            raise _pdf_read_error(path, ValueError("PDF has no pages"))
        try:
            toc = doc.get_toc()
            segments = _segments_from_toc(doc, toc) if toc else _segments_from_font_heuristic(doc)
            body = _body_from_segments(segments) if segments else _plain_body(doc)
        except KSError:
            raise
        except Exception as exc:
            raise _pdf_read_error(path, exc) from exc
    finally:
        doc.close()

    return ParsedDocument(title=path.stem, body=body, format="pdf", segments=segments)


def _open_pdf(path: Path) -> fitz.Document:
    import fitz

    return fitz.open(path)


def _segments_from_toc(doc: fitz.Document, toc: list[list[object]]) -> list[Segment]:
    segments: list[Segment] = []
    for index, entry in enumerate(toc):
        if len(entry) < 3:
            continue
        level = _int_or_default(entry[0], 1)
        title = str(entry[1]).strip()
        page_number = _int_or_default(entry[2], 1)
        if not title:
            continue

        segments.append(
            Segment(
                kind="heading",
                text=title,
                metadata={"level": level, "page_number": page_number},
            )
        )

        next_page_number = (
            _int_or_default(toc[index + 1][2], len(doc) + 1)
            if index + 1 < len(toc) and len(toc[index + 1]) >= 3
            else len(doc) + 1
        )
        body_text = _page_range_text(doc, page_number, next_page_number)
        if body_text:
            segments.append(
                Segment(
                    kind="paragraph",
                    text=body_text,
                    metadata={
                        "page_start": page_number,
                        "page_end": min(max(next_page_number - 1, page_number), len(doc)),
                    },
                )
            )

    return segments


def _segments_from_font_heuristic(doc: fitz.Document) -> list[Segment]:
    spans = _text_spans(doc)
    if not spans:
        return []

    font_sizes = [span[0] for span in spans]
    if len(set(font_sizes)) < 2:
        return []

    base_size = _baseline_font_size(font_sizes)
    h1_threshold = base_size * 1.5
    h2_threshold = base_size * 1.3
    segments: list[Segment] = []
    pending_body: list[str] = []
    body_start_page = 1

    for size, text, page_number in spans:
        if _is_noise(text):
            continue
        level = _heading_level(size, h1_threshold, h2_threshold)
        if level is None:
            if not pending_body:
                body_start_page = page_number
            pending_body.append(text)
            continue

        _append_paragraph(segments, pending_body, body_start_page, page_number)
        pending_body = []
        segments.append(
            Segment(
                kind="heading",
                text=text,
                metadata={"level": level, "page_number": page_number},
            )
        )
        body_start_page = page_number

    last_page = spans[-1][2]
    _append_paragraph(segments, pending_body, body_start_page, last_page)

    if not any(segment.kind == "heading" for segment in segments):
        return []
    return segments


def _text_spans(doc: fitz.Document) -> list[tuple[float, str, int]]:
    spans: list[tuple[float, str, int]] = []
    for page_index, page in enumerate(doc):
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text", "")).strip()
                    size = float(span.get("size", 0.0))
                    if text and size > 0:
                        spans.append((size, text, page_index + 1))
    return spans


def _baseline_font_size(font_sizes: list[float]) -> float:
    rounded_sizes = [round(size, 1) for size in font_sizes]
    counts = Counter(rounded_sizes)
    highest_count = max(counts.values())
    return min(size for size, count in counts.items() if count == highest_count)


def _heading_level(size: float, h1_threshold: float, h2_threshold: float) -> int | None:
    if size >= h1_threshold:
        return 1
    if size >= h2_threshold:
        return 2
    return None


def _append_paragraph(
    segments: list[Segment], body_parts: list[str], page_start: int, page_end: int
) -> None:
    text = "\n".join(part for part in body_parts if part.strip()).strip()
    if not text:
        return
    segments.append(
        Segment(
            kind="paragraph",
            text=text,
            metadata={"page_start": page_start, "page_end": max(page_start, page_end)},
        )
    )


def _page_range_text(doc: fitz.Document, page_number: int, next_page_number: int) -> str:
    start = max(page_number - 1, 0)
    stop = min(max(next_page_number - 1, start + 1), len(doc))
    return "\n".join((doc[index].get_text() or "").strip() for index in range(start, stop)).strip()


def _body_from_segments(segments: list[Segment]) -> str:
    return "\n\n".join(segment.text for segment in segments if segment.text.strip())


def _plain_body(doc: fitz.Document) -> str:
    return "\n\n".join((page.get_text() or "").strip() for page in doc)


def _int_or_default(value: object, default: int) -> int:
    return value if isinstance(value, int) else default


def _is_noise(text: str) -> bool:
    stripped = text.strip()
    return not stripped or stripped.isdigit() or len(stripped) <= 1


def _pdf_read_error(path: Path, exc: Exception) -> KSError:
    return KSError(
        f"無法解析 PDF {path}",
        exit_code=ExitCode.DATAERR,
        code="PDF_READ_ERROR",
        details=[str(exc)],
    )

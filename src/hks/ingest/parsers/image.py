"""Image parser backed by local OCR."""

from __future__ import annotations

from pathlib import Path

from hks.core.manifest import SourceFormat
from hks.ingest.fingerprint import ParserFlags, compute_parser_fingerprint
from hks.ingest.guards import load_image_limits
from hks.ingest.models import ParsedDocument
from hks.ingest.ocr import load_preprocessed_image, run_ocr
from hks.ingest.office_common import Segment, SkippedSegment


def parse(path: Path, source_format: SourceFormat) -> ParsedDocument:
    limits = load_image_limits()
    image = load_preprocessed_image(path, max_pixels=limits.max_pixels)
    lines = run_ocr(image)
    if not lines:
        return ParsedDocument(
            title=path.stem,
            body="",
            format=source_format,
            skipped_segments=[SkippedSegment(type="ocr_empty")],
        )

    segments = [
        Segment(
            kind="ocr_text",
            text=line.text,
            metadata={
                "ocr_confidence": line.confidence,
                "source_engine": line.source_engine,
                "bbox_left": line.bbox_left,
                "bbox_top": line.bbox_top,
                "bbox_width": line.bbox_width,
                "bbox_height": line.bbox_height,
            },
        )
        for line in lines
    ]
    body = "\n".join(line.text for line in lines)
    return ParsedDocument(
        title=path.stem,
        body=body,
        format=source_format,
        segments=segments,
        parser_fingerprint=compute_parser_fingerprint(source_format, ParserFlags()),
    )

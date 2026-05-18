"""Rule-based tree builders per document format."""

from __future__ import annotations

import re
from collections.abc import Callable

from hks.ingest.models import ParsedDocument
from hks.ingest.office_common import Segment
from hks.page_tree.model import TreeNode

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_MARKDOWN_PREFIX_RE = re.compile(r"^#{1,6}\s+")

type _Heading = tuple[int, str, int]
type _Builder = Callable[[ParsedDocument, str], list[TreeNode]]
type _Span = tuple[int, int] | None


def build_page_tree(parsed: ParsedDocument, normalized_text: str) -> list[TreeNode]:
    """Build a best-effort hierarchical tree from parsed document structure."""

    builder = _BUILDERS.get(parsed.format, _build_single_root)
    return builder(parsed, normalized_text)


def _build_single_root(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    return [
        TreeNode(
            node_id="n1",
            title=parsed.title or "Untitled",
            level=1,
            start_offset=0,
            end_offset=len(text),
            children=[],
        )
    ]


def _build_md(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    headings = [
        (len(match.group(1)), match.group(2).strip(), match.start())
        for match in _MD_HEADING_RE.finditer(text)
    ]
    if not headings:
        return _build_single_root(parsed, text)
    return _headings_to_tree(headings, text)


def _build_docx(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    headings: list[_Heading] = []
    spans = _segment_spans(parsed.segments, text)
    for index, segment in enumerate(parsed.segments):
        if segment.kind != "heading":
            continue
        level = _metadata_int(segment, "level", 1)
        title = _clean_heading_title(segment.text)
        headings.append((level, title, _span_start(spans[index], 0)))

    if not headings:
        return _build_single_root(parsed, text)
    return _headings_to_tree(headings, text)


def _build_pptx(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    spans = _segment_spans(parsed.segments, text)
    slide_ranges = _section_ranges(parsed.segments, "slide_header")
    if not slide_ranges:
        return _build_single_root(parsed, text)

    nodes: list[TreeNode] = []
    for node_index, (start_index, stop_index) in enumerate(slide_ranges, start=1):
        slide_header = parsed.segments[start_index]
        slide_index = slide_header.metadata.get("slide_index")
        children: list[TreeNode] = []
        child_index = 1
        for segment_index in range(start_index + 1, stop_index):
            segment = parsed.segments[segment_index]
            if segment.kind != "heading":
                continue
            child_start, child_end = _span_or_zero(spans[segment_index], 0)
            children.append(
                TreeNode(
                    node_id=f"n{node_index}.{child_index}",
                    title=_clean_heading_title(segment.text),
                    level=2,
                    start_offset=child_start,
                    end_offset=child_end,
                    children=[],
                    metadata={"slide_index": slide_index},
                )
            )
            child_index += 1

        nodes.append(
            TreeNode(
                node_id=f"n{node_index}",
                title=_clean_heading_title(slide_header.text),
                level=1,
                start_offset=_span_start(spans[start_index], 0),
                end_offset=_range_end(spans, start_index, stop_index, 0),
                children=children,
                metadata={"slide_index": slide_index},
            )
        )
    return nodes


def _build_xlsx(parsed: ParsedDocument, text: str) -> list[TreeNode]:
    spans = _segment_spans(parsed.segments, text)
    sheet_ranges = _section_ranges(parsed.segments, "sheet_header")
    if not sheet_ranges:
        return _build_single_root(parsed, text)

    nodes: list[TreeNode] = []
    for node_index, (start_index, stop_index) in enumerate(sheet_ranges, start=1):
        sheet_header = parsed.segments[start_index]
        sheet_name = sheet_header.metadata.get("sheet_name")
        title = str(sheet_name) if sheet_name else _clean_heading_title(sheet_header.text)
        nodes.append(
            TreeNode(
                node_id=f"n{node_index}",
                title=title,
                level=1,
                start_offset=_span_start(spans[start_index], 0),
                end_offset=_range_end(spans, start_index, stop_index, 0),
                children=[],
                metadata={"sheet_name": sheet_name} if sheet_name is not None else {},
            )
        )
    return nodes


def _headings_to_tree(headings: list[_Heading], text: str) -> list[TreeNode]:
    nodes: list[TreeNode] = []
    stack: list[tuple[int, TreeNode]] = []
    counters: list[int] = []

    for index, (level, title, start) in enumerate(headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        depth = len(stack)
        counters = counters[: depth + 1]
        if len(counters) <= depth:
            counters.append(0)
        counters[depth] += 1
        node_id = _node_id(counters)
        end = _heading_end(index, headings, len(text))
        node = TreeNode(
            node_id=node_id,
            title=title,
            level=level,
            start_offset=_clamp_offset(start, len(text)),
            end_offset=_clamp_offset(end, len(text)),
            children=[],
        )
        if stack:
            stack[-1][1].children.append(node)
        else:
            nodes.append(node)
        stack.append((level, node))

    return nodes


def _heading_end(index: int, headings: list[_Heading], text_len: int) -> int:
    level = headings[index][0]
    for next_level, _title, next_start in headings[index + 1 :]:
        if next_level <= level:
            return next_start
    return text_len


def _segment_spans(segments: list[Segment], text: str) -> list[_Span]:
    spans: list[_Span] = []
    cursor = 0
    for segment in segments:
        start = text.find(segment.text, cursor) if segment.text else -1
        if start < 0:
            spans.append(None)
            continue
        end = start + len(segment.text)
        spans.append((_clamp_offset(start, len(text)), _clamp_offset(end, len(text))))
        cursor = end
    return spans


def _section_ranges(segments: list[Segment], header_kind: str) -> list[tuple[int, int]]:
    starts = [index for index, segment in enumerate(segments) if segment.kind == header_kind]
    return [
        (start, starts[index + 1] if index + 1 < len(starts) else len(segments))
        for index, start in enumerate(starts)
    ]


def _range_end(
    spans: list[_Span], start_index: int, stop_index: int, fallback_offset: int
) -> int:
    found_spans = [span for span in spans[start_index:stop_index] if span is not None]
    if not found_spans:
        return fallback_offset
    return max(end for _start, end in found_spans)


def _span_start(span: _Span, fallback_offset: int) -> int:
    return span[0] if span is not None else fallback_offset


def _span_or_zero(span: _Span, fallback_offset: int) -> tuple[int, int]:
    return span if span is not None else (fallback_offset, fallback_offset)


def _metadata_int(segment: Segment, key: str, default: int) -> int:
    value = segment.metadata.get(key, default)
    return value if isinstance(value, int) else default


def _clean_heading_title(text: str) -> str:
    return _MARKDOWN_PREFIX_RE.sub("", text).strip() or "Untitled"


def _node_id(counters: list[int]) -> str:
    return ".".join(
        f"n{counter}" if index == 0 else str(counter)
        for index, counter in enumerate(counters)
    )


def _clamp_offset(offset: int, text_len: int) -> int:
    return min(max(offset, 0), text_len)


_BUILDERS: dict[str, _Builder] = {
    "txt": _build_single_root,
    "md": _build_md,
    "docx": _build_docx,
    "pptx": _build_pptx,
    "xlsx": _build_xlsx,
    "png": _build_single_root,
    "jpg": _build_single_root,
    "jpeg": _build_single_root,
    "pdf": _build_single_root,
}

"""Unit tests for rule-based page tree builders."""

from __future__ import annotations

from hks.ingest.models import ParsedDocument
from hks.ingest.office_common import Segment
from hks.page_tree.build import build_page_tree


class TestMdBuilder:
    def test_headings_create_hierarchy(self) -> None:
        body = "# Chapter 1\n\nIntro text.\n\n## Section 1.1\n\nDetail.\n\n# Chapter 2\n\nMore."
        parsed = ParsedDocument(title="Doc", body=body, format="md")

        nodes = build_page_tree(parsed, body)

        assert [node.title for node in nodes] == ["Chapter 1", "Chapter 2"]
        assert nodes[0].node_id == "n1"
        assert nodes[0].level == 1
        assert nodes[0].children[0].node_id == "n1.1"
        assert nodes[0].children[0].title == "Section 1.1"
        assert nodes[1].node_id == "n2"

    def test_no_headings_single_root(self) -> None:
        body = "Just plain text without headings."
        parsed = ParsedDocument(title="Plain", body=body, format="md")

        nodes = build_page_tree(parsed, body)

        assert len(nodes) == 1
        assert nodes[0].title == "Plain"
        assert nodes[0].start_offset == 0
        assert nodes[0].end_offset == len(body)

    def test_nested_h1_h2_h3_hierarchy(self) -> None:
        body = "# Root\n\n## Child\n\n### Grandchild\n\nDeep detail."
        parsed = ParsedDocument(title="Doc", body=body, format="md")

        nodes = build_page_tree(parsed, body)

        assert nodes[0].node_id == "n1"
        assert nodes[0].children[0].node_id == "n1.1"
        assert nodes[0].children[0].children[0].node_id == "n1.1.1"
        assert nodes[0].children[0].children[0].title == "Grandchild"


class TestTxtBuilder:
    def test_always_single_root(self) -> None:
        body = "Some text content."
        parsed = ParsedDocument(title="Notes", body=body, format="txt")

        nodes = build_page_tree(parsed, body)

        assert len(nodes) == 1
        assert nodes[0].title == "Notes"
        assert nodes[0].end_offset == len(body)


class TestDocxBuilder:
    def test_heading_segments_build_tree(self) -> None:
        segments = [
            Segment(kind="heading", text="## Overview", metadata={"level": 1}),
            Segment(kind="paragraph", text="Intro paragraph."),
            Segment(kind="heading", text="### Details", metadata={"level": 2}),
            Segment(kind="paragraph", text="Detail paragraph."),
            Segment(kind="heading", text="## Conclusion", metadata={"level": 1}),
            Segment(kind="paragraph", text="Closing."),
        ]
        body = "\n\n".join(segment.text for segment in segments)
        parsed = ParsedDocument(title="Report", body=body, format="docx", segments=segments)

        nodes = build_page_tree(parsed, body)

        assert [node.title for node in nodes] == ["Overview", "Conclusion"]
        assert nodes[0].children[0].title == "Details"
        assert nodes[0].start_offset == body.index("## Overview")
        assert nodes[0].children[0].start_offset == body.index("### Details")

    def test_no_heading_segments_single_root(self) -> None:
        segments = [Segment(kind="paragraph", text="Just text.")]
        parsed = ParsedDocument(title="Flat", body="Just text.", format="docx", segments=segments)

        nodes = build_page_tree(parsed, "Just text.")

        assert len(nodes) == 1
        assert nodes[0].title == "Flat"

    def test_repeated_heading_text_uses_later_offsets(self) -> None:
        segments = [
            Segment(kind="heading", text="## Repeat", metadata={"level": 1}),
            Segment(kind="paragraph", text="First."),
            Segment(kind="heading", text="## Repeat", metadata={"level": 1}),
            Segment(kind="paragraph", text="Second."),
        ]
        body = "\n\n".join(segment.text for segment in segments)
        parsed = ParsedDocument(title="Report", body=body, format="docx", segments=segments)

        nodes = build_page_tree(parsed, body)

        assert nodes[0].start_offset == body.index("## Repeat")
        assert nodes[1].start_offset == body.rindex("## Repeat")


class TestPptxBuilder:
    def test_slides_become_nodes_with_heading_children(self) -> None:
        segments = [
            Segment(kind="slide_header", text="## Slide 1", metadata={"slide_index": 1}),
            Segment(kind="heading", text="### Welcome", metadata={"slide_index": 1}),
            Segment(kind="paragraph", text="Content.", metadata={"slide_index": 1}),
            Segment(kind="slide_header", text="## Slide 2", metadata={"slide_index": 2}),
            Segment(kind="paragraph", text="More.", metadata={"slide_index": 2}),
        ]
        body = "\n\n".join(segment.text for segment in segments)
        parsed = ParsedDocument(title="Deck", body=body, format="pptx", segments=segments)

        nodes = build_page_tree(parsed, body)

        assert [node.title for node in nodes] == ["Slide 1", "Slide 2"]
        assert nodes[0].metadata["slide_index"] == 1
        assert nodes[0].children[0].title == "Welcome"
        assert nodes[0].children[0].level == 2
        assert nodes[0].children[0].metadata["slide_index"] == 1

    def test_missing_slide_headers_do_not_cover_full_document(self) -> None:
        segments = [
            Segment(kind="slide_header", text="## Missing Slide 1", metadata={"slide_index": 1}),
            Segment(kind="slide_header", text="## Missing Slide 2", metadata={"slide_index": 2}),
        ]
        text = "normalized text without slide headers"
        parsed = ParsedDocument(title="Deck", body="", format="pptx", segments=segments)

        nodes = build_page_tree(parsed, text)

        assert [(node.start_offset, node.end_offset) for node in nodes] == [(0, 0), (0, 0)]

    def test_missing_slide_header_uses_first_found_child_as_section_start(self) -> None:
        segments = [
            Segment(kind="slide_header", text="## Missing Slide 1", metadata={"slide_index": 1}),
            Segment(kind="heading", text="### Visible", metadata={"slide_index": 1}),
            Segment(kind="paragraph", text="Content.", metadata={"slide_index": 1}),
            Segment(kind="slide_header", text="## Missing Slide 2", metadata={"slide_index": 2}),
            Segment(kind="paragraph", text="More.", metadata={"slide_index": 2}),
        ]
        text = "preamble\n\n### Visible\n\nContent.\n\nseparator\n\nMore."
        parsed = ParsedDocument(title="Deck", body="", format="pptx", segments=segments)

        nodes = build_page_tree(parsed, text)

        assert nodes[0].start_offset == text.index("### Visible")
        assert nodes[0].end_offset == text.index("Content.") + len("Content.")
        assert nodes[1].start_offset == text.index("More.")
        assert nodes[1].end_offset == text.index("More.") + len("More.")


class TestXlsxBuilder:
    def test_sheets_become_nodes(self) -> None:
        segments = [
            Segment(kind="sheet_header", text="## Revenue", metadata={"sheet_name": "Revenue"}),
            Segment(kind="table_row", text="Q1: 100", metadata={"sheet_name": "Revenue"}),
            Segment(kind="sheet_header", text="## Costs", metadata={"sheet_name": "Costs"}),
            Segment(kind="table_row", text="Q1: 80", metadata={"sheet_name": "Costs"}),
        ]
        body = "\n\n".join(segment.text for segment in segments)
        parsed = ParsedDocument(title="Finance", body=body, format="xlsx", segments=segments)

        nodes = build_page_tree(parsed, body)

        assert [node.title for node in nodes] == ["Revenue", "Costs"]
        assert nodes[0].metadata["sheet_name"] == "Revenue"
        assert nodes[1].metadata["sheet_name"] == "Costs"

    def test_missing_sheet_headers_do_not_cover_full_document(self) -> None:
        segments = [
            Segment(kind="sheet_header", text="## Missing A", metadata={"sheet_name": "A"}),
            Segment(kind="sheet_header", text="## Missing B", metadata={"sheet_name": "B"}),
        ]
        text = "normalized text without sheet headers"
        parsed = ParsedDocument(title="Workbook", body="", format="xlsx", segments=segments)

        nodes = build_page_tree(parsed, text)

        assert [(node.start_offset, node.end_offset) for node in nodes] == [(0, 0), (0, 0)]

    def test_missing_sheet_header_uses_first_found_row_as_section_start(self) -> None:
        segments = [
            Segment(kind="sheet_header", text="## Missing A", metadata={"sheet_name": "A"}),
            Segment(kind="table_row", text="A row", metadata={"sheet_name": "A"}),
            Segment(kind="sheet_header", text="## Missing B", metadata={"sheet_name": "B"}),
            Segment(kind="table_row", text="B row longer", metadata={"sheet_name": "B"}),
        ]
        text = "prefix\n\nA row\n\nbetween\n\nB row longer"
        parsed = ParsedDocument(title="Workbook", body="", format="xlsx", segments=segments)

        nodes = build_page_tree(parsed, text)

        assert [(node.start_offset, node.end_offset) for node in nodes] == [
            (text.index("A row"), text.index("A row") + len("A row")),
            (text.index("B row longer"), text.index("B row longer") + len("B row longer")),
        ]


class TestImageBuilder:
    def test_single_root(self) -> None:
        segments = [Segment(kind="ocr_text", text="OCR content.")]
        parsed = ParsedDocument(title="photo", body="OCR content.", format="png", segments=segments)

        nodes = build_page_tree(parsed, "OCR content.")

        assert len(nodes) == 1
        assert nodes[0].title == "photo"


class TestOffsetBehavior:
    def test_offsets_are_non_negative_when_segment_text_is_missing(self) -> None:
        segments = [
            Segment(kind="sheet_header", text="## Missing", metadata={"sheet_name": "Missing"}),
        ]
        parsed = ParsedDocument(title="Workbook", body="", format="xlsx", segments=segments)

        nodes = build_page_tree(parsed, "normalized body without source header")

        assert nodes[0].start_offset == 0
        assert nodes[0].end_offset == 0

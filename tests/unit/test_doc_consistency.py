"""Documentation consistency checks.

Validates that documentation files match runtime behavior and the response
contract, catching stale examples and dangerous suggestions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOC_FILES = [
    PROJECT_ROOT / "docs" / "obsidian.md",
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "README.en.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _readme_output_example(path: Path) -> dict:
    text = _read(path)
    for match in re.finditer(r"```json\n(.*?)\n```", text, flags=re.DOTALL):
        payload = json.loads(match.group(1))
        if "evidence" in payload and "trace" in payload:
            return payload
    raise AssertionError(f"{path.name} missing JSON output example")


# Task 1: manual-*.md must NOT be suggested in wiki/pages/


@pytest.mark.unit
@pytest.mark.parametrize("path", DOC_FILES, ids=lambda p: p.name)
def test_no_manual_md_in_wiki_pages(path: Path) -> None:
    """Docs must not suggest putting manual-*.md inside wiki/pages/.

    WikiStore.list_pages() reads every *.md in wiki/pages/ and crashes on
    files without HKS frontmatter.
    """
    text = _read(path)
    # The dangerous pattern is suggesting `manual-*.md` *in* `wiki/pages/`.
    # No line should suggest manual-*.md inside wiki/pages/.
    for line in text.splitlines():
        if "manual-*.md" in line:
            assert "wiki/pages/" not in line, f"dangerous suggestion in {path.name}: {line}"


# Task 2: evidence items must include quote field


@pytest.mark.unit
def test_readme_output_example_evidence_has_quote() -> None:
    """README output examples must show the 'quote' field in evidence items."""
    for readme in [PROJECT_ROOT / "README.md", PROJECT_ROOT / "README.en.md"]:
        payload = _readme_output_example(readme)
        assert payload["evidence"], f"{readme.name} output example missing evidence"
        assert all("quote" in item for item in payload["evidence"]), (
            f"{readme.name} output example missing quote in evidence"
        )


@pytest.mark.unit
def test_readme_output_example_evidence_matches_winner_source() -> None:
    """README output examples must not cite non-winning fused candidates."""
    for readme in [PROJECT_ROOT / "README.md", PROJECT_ROOT / "README.en.md"]:
        payload = _readme_output_example(readme)
        source = set(payload["source"])
        evidence_routes = {item["route"] for item in payload["evidence"]}
        assert evidence_routes <= source, (
            f"{readme.name} output example cites non-winning candidates: "
            f"source={source}, evidence_routes={evidence_routes}"
        )


@pytest.mark.unit
def test_readme_output_example_merge_strategy_valid() -> None:
    """Merge strategy in output example must be 'rrf' or 'llm-rerank', not 'llm'."""
    for readme in [PROJECT_ROOT / "README.md", PROJECT_ROOT / "README.en.md"]:
        payload = _readme_output_example(readme)
        merge_steps = [
            step for step in payload["trace"]["steps"] if step["kind"] == "merge"
        ]
        assert merge_steps, f"{readme.name} output example missing merge step"
        assert merge_steps[0]["detail"]["strategy"] in {"rrf", "llm-rerank"}, (
            f"{readme.name} uses invalid merge strategy "
            f"{merge_steps[0]['detail']['strategy']!r}"
        )


# Task 3: pageindex tools must appear in MCP/HTTP adapter lists


@pytest.mark.unit
def test_readme_mcp_lists_pageindex_tools() -> None:
    for readme in [PROJECT_ROOT / "README.md", PROJECT_ROOT / "README.en.md"]:
        text = _read(readme)
        assert "hks_pageindex_show" in text, f"{readme.name} missing hks_pageindex_show in MCP list"
        assert "hks_pageindex_enrich" in text, (
            f"{readme.name} missing hks_pageindex_enrich in MCP list"
        )


@pytest.mark.unit
def test_readme_http_lists_pageindex_endpoints() -> None:
    for readme in [PROJECT_ROOT / "README.md", PROJECT_ROOT / "README.en.md"]:
        text = _read(readme)
        assert "/pageindex/" in text, f"{readme.name} missing /pageindex/ in HTTP endpoint list"
        assert "/pageindex/enrich" in text, (
            f"{readme.name} missing /pageindex/enrich in HTTP endpoint list"
        )

"""LLM tree enrichment: fill summaries and restructure degenerate trees."""

from __future__ import annotations

import copy

from hks.core.manifest import utc_now_iso
from hks.page_tree.model import PageTree, TreeNode


def enrich_tree(
    tree: PageTree,
    source_text: str,
    *,
    provider: str = "fake",
    model: str | None = None,
    force: bool = False,
) -> PageTree:
    """Enrich a PageTree with provider-generated summaries."""

    if tree.build_method == "llm" and not force:
        return tree

    if tree.total_nodes == 1:
        if provider == "fake":
            return _fake_restructure(tree, source_text)
        return _llm_restructure(tree, source_text, provider, model)

    enriched_nodes = _fill_summaries(tree.root_nodes, source_text, provider, model)
    return PageTree(
        source_relpath=tree.source_relpath,
        source_format=tree.source_format,
        doc_title=tree.doc_title,
        root_nodes=enriched_nodes,
        build_method="llm",
        built_at=utc_now_iso(),
        total_nodes=_count_nodes(enriched_nodes),
        source_sha256=tree.source_sha256,
    )


def _fill_summaries(
    nodes: list[TreeNode],
    source_text: str,
    provider: str,
    model: str | None,
) -> list[TreeNode]:
    enriched: list[TreeNode] = []
    for node in nodes:
        text_slice = source_text[node.start_offset : node.end_offset]
        summary = (
            f"Summary of: {node.title}"
            if provider == "fake"
            else _llm_summarize(text_slice, node.title, provider, model)
        )
        enriched.append(
            TreeNode(
                node_id=node.node_id,
                title=node.title,
                level=node.level,
                start_offset=node.start_offset,
                end_offset=node.end_offset,
                children=_fill_summaries(node.children, source_text, provider, model),
                summary=summary,
                metadata=copy.deepcopy(node.metadata),
            )
        )
    return enriched


def _fake_restructure(tree: PageTree, source_text: str) -> PageTree:
    chunk_size = max(1, len(source_text) // 3)
    nodes: list[TreeNode] = []
    for index in range(3):
        start_offset = min(index * chunk_size, len(source_text))
        end_offset = (
            len(source_text)
            if index == 2
            else min((index + 1) * chunk_size, len(source_text))
        )
        title = f"Section {index + 1}"
        nodes.append(
            TreeNode(
                node_id=f"n{index + 1}",
                title=title,
                level=1,
                start_offset=start_offset,
                end_offset=end_offset,
                children=[],
                summary=f"Summary of: {title}",
            )
        )

    return PageTree(
        source_relpath=tree.source_relpath,
        source_format=tree.source_format,
        doc_title=tree.doc_title,
        root_nodes=nodes,
        build_method="llm",
        built_at=utc_now_iso(),
        total_nodes=_count_nodes(nodes),
        source_sha256=tree.source_sha256,
    )


def _llm_restructure(
    tree: PageTree,
    source_text: str,
    provider: str,
    model: str | None,
) -> PageTree:
    from hks.llm.config import require_hosted_provider_credentials
    from hks.llm.providers import _openai_chat

    api_key, endpoint = require_hosted_provider_credentials(provider)
    chat_endpoint = endpoint or "https://api.openai.com/v1"

    messages = [
        {
            "role": "system",
            "content": (
                "You are a document structure analyzer. Given a document's full text, "
                "split it into 2-5 logical sections. Return JSON: "
                '{"sections": [{"title": "...", "start_offset": N, "end_offset": N}]}'
            ),
        },
        {"role": "user", "content": source_text[:8000]},
    ]
    result = _openai_chat(
        api_key=api_key,
        endpoint=chat_endpoint,
        model=model or "gpt-4o-mini",
        messages=messages,
        timeout=60,
    )
    sections = result.get("sections", [])
    if not sections:
        return _fake_restructure(tree, source_text)

    nodes: list[TreeNode] = []
    for index, section in enumerate(sections):
        start = int(section.get("start_offset", 0))
        end = int(section.get("end_offset", len(source_text)))
        title = str(section.get("title", f"Section {index + 1}"))
        text_slice = source_text[start:end]
        summary = (
            _llm_summarize(text_slice, title, provider, model)
            if text_slice.strip()
            else f"Summary of: {title}"
        )
        nodes.append(
            TreeNode(
                node_id=f"llm-n{index + 1}",
                title=title,
                level=1,
                start_offset=start,
                end_offset=end,
                children=[],
                summary=summary,
            )
        )

    return PageTree(
        source_relpath=tree.source_relpath,
        source_format=tree.source_format,
        doc_title=tree.doc_title,
        root_nodes=nodes,
        build_method="llm",
        built_at=utc_now_iso(),
        total_nodes=_count_nodes(nodes),
        source_sha256=tree.source_sha256,
    )


def _llm_summarize(text: str, title: str, provider: str, model: str | None) -> str:
    from hks.llm.config import require_hosted_provider_credentials
    from hks.llm.providers import _openai_chat

    api_key, endpoint = require_hosted_provider_credentials(provider)
    chat_endpoint = endpoint or "https://api.openai.com/v1"

    messages = [
        {
            "role": "system",
            "content": (
                "Summarize the following document section in one concise sentence. "
                'Return JSON: {"summary": "..."}'
            ),
        },
        {"role": "user", "content": f"Section: {title}\n\n{text[:4000]}"},
    ]
    result = _openai_chat(
        api_key=api_key,
        endpoint=chat_endpoint,
        model=model or "gpt-4o-mini",
        messages=messages,
        timeout=30,
    )
    return str(result.get("summary", f"Summary of: {title}"))


def _count_nodes(nodes: list[TreeNode]) -> int:
    return sum(1 + _count_nodes(node.children) for node in nodes)

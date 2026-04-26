"""Service orchestration for 010 Graphify."""

from __future__ import annotations

from typing import Any, cast

from hks.core.paths import runtime_paths
from hks.graphify.builder import build_graph
from hks.graphify.models import GraphifyResult
from hks.graphify.store import store_or_reuse
from hks.graphify.validation import validate_result


def build(request: Any) -> GraphifyResult:
    paths = runtime_paths()
    graph, input_fingerprint, source = build_graph(paths)
    if request.mode == "preview":
        return validate_result(
            GraphifyResult(
                mode="preview",
                graph=graph,
                input_fingerprint=input_fingerprint,
                source=cast(list[Any], source),
                artifacts={
                    "run_id": None,
                    "run_path": None,
                    "graph": None,
                    "communities": None,
                    "audit": None,
                    "manifest": None,
                    "html": None,
                    "report": None,
                },
            )
        )
    stored, _ = store_or_reuse(
        request,
        graph,
        input_fingerprint=input_fingerprint,
        source=source,
        paths=paths,
    )
    return validate_result(stored)

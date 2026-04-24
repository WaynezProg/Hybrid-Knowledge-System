from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "hks"


def _module_docstring_node(module: ast.Module) -> ast.Constant | None:
    if not module.body:
        return None
    first = module.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first.value
    return None


def _string_constant_nodes(tree: ast.AST) -> list[ast.Constant]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _identifier_hits(tree: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if "graph" in node.name.lower():
                hits.append((node.lineno, node.name))
        elif isinstance(node, ast.Name) and "graph" in node.id.lower():
            hits.append((node.lineno, node.id))
        elif isinstance(node, ast.Attribute) and "graph" in node.attr.lower():
            hits.append((node.lineno, node.attr))
    return hits


def _string_literal_hits(tree: ast.Module) -> list[tuple[int, str]]:
    module_docstring = _module_docstring_node(tree)
    hits: list[tuple[int, str]] = []
    for node in _string_constant_nodes(tree):
        if module_docstring is not None and node is module_docstring:
            continue
        value = node.value.lower()
        if "graph" in value:
            hits.append((node.lineno, str(node.value)))
    return hits


def _import_hits(tree: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = [alias.name, alias.asname or ""]
                if any("graph" in part.lower() for part in parts if part):
                    hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            candidates = [node.module or ""]
            candidates.extend(alias.name for alias in node.names)
            if any("graph" in candidate.lower() for candidate in candidates if candidate):
                hits.append((node.lineno, node.module or ""))
    return hits


@pytest.mark.contract
def test_src_has_no_graph_runtime_paths() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, value in _import_hits(tree):
            violations.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno} import {value}")
        for lineno, value in _identifier_hits(tree):
            violations.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno} identifier {value}")
        for lineno, value in _string_literal_hits(tree):
            violations.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno} literal {value!r}")

    assert violations == []

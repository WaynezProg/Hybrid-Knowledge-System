"""Tests for expanded entity type inference."""
from __future__ import annotations

from hks.graph.extract import extract_document_graph


def test_decision_type_zh():
    artifacts = extract_document_graph(
        relpath="notes.md",
        title="Notes",
        body="團隊決策 導致 延遲交付",
        wiki_slug="notes",
    )
    types = {n.type for n in artifacts.nodes if n.type != "Document"}
    assert "Decision" in types


def test_decision_type_en():
    artifacts = extract_document_graph(
        relpath="notes.md",
        title="Notes",
        body="the design decision impacts delivery timeline",
        wiki_slug="notes",
    )
    types = {n.type for n in artifacts.nodes if n.type != "Document"}
    assert "Decision" in types


def test_constraint_type():
    artifacts = extract_document_graph(
        relpath="notes.md",
        title="Notes",
        body="記憶體限制 影響 效能",
        wiki_slug="notes",
    )
    types = {n.type for n in artifacts.nodes if n.type != "Document"}
    assert "Constraint" in types


def test_risk_type():
    artifacts = extract_document_graph(
        relpath="notes.md",
        title="Notes",
        body="資安風險 導致 系統停擺",
        wiki_slug="notes",
    )
    types = {n.type for n in artifacts.nodes if n.type != "Document"}
    assert "Risk" in types


def test_milestone_type():
    artifacts = extract_document_graph(
        relpath="notes.md",
        title="Notes",
        body="Phase 1 完成驗證 影響 Phase 2 啟動",
        wiki_slug="notes",
    )
    types = {n.type for n in artifacts.nodes if n.type != "Document"}
    assert "Milestone" in types

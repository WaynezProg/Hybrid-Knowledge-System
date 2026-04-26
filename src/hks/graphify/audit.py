"""Audit helpers for Graphify."""

from __future__ import annotations

from hks.graphify.models import GraphifyAuditFinding


def side_effect_finding(message: str) -> GraphifyAuditFinding:
    return GraphifyAuditFinding(
        severity="warning",
        code="side_effect_text_ignored",
        message=message,
    )

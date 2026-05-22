"""Unit tests for golden retrieval quality metrics."""

from __future__ import annotations

from pathlib import Path

import pytest

from hks.evaluation.retrieval_quality import (
    GoldenQueryCase,
    MetricThresholds,
    QueryObservation,
    assert_thresholds,
    compute_metrics,
    evidence_matches,
    load_golden_cases,
)


def test_load_golden_cases_supports_null_route_no_hit_and_writeback_flag(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quick.jsonl"
    path.write_text(
        '{"id":"no-hit","question":"Zephyr","expected_route":null,'
        '"expect_no_hit":true,"writeback_allowed":false}\n',
        encoding="utf-8",
    )

    cases = load_golden_cases(path)

    assert cases == [
        GoldenQueryCase(
            id="no-hit",
            question="Zephyr",
            expected_route=None,
            writeback_allowed=False,
            expect_no_hit=True,
        )
    ]


def test_load_golden_cases_rejects_invalid_fields(tmp_path: Path) -> None:
    path = tmp_path / "quick.jsonl"
    path.write_text(
        '{"id":"bad","question":"q","expected_route":"bad"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid expected_route"):
        load_golden_cases(path)


def test_evidence_matches_relpath_and_quote_case_insensitive() -> None:
    payload = {
        "evidence": [
            {
                "source_relpath": "project-atlas.txt",
                "route": "wiki",
                "quote": "Project Atlas 目前處於設計收斂階段。",
            }
        ]
    }

    assert evidence_matches(
        payload,
        expected_source_relpath="project-atlas.txt",
        expected_evidence_quote="atlas",
    )


def test_evidence_match_fails_when_quote_missing() -> None:
    payload = {
        "evidence": [
            {
                "source_relpath": "project-atlas.txt",
                "route": "wiki",
                "quote": "Project Atlas 目前處於設計收斂階段。",
            }
        ]
    }

    assert not evidence_matches(
        payload,
        expected_source_relpath="project-atlas.txt",
        expected_evidence_quote="coordinator approval",
    )


def test_compute_metrics_counts_route_precision_evidence_no_hit_and_writeback() -> None:
    observations = [
        QueryObservation(
            case=GoldenQueryCase(
                id="wiki-summary",
                question="Atlas 摘要",
                expected_route="wiki",
                expected_source_relpath="project-atlas.txt",
                expected_evidence_quote="Atlas",
                expected_answer_contains="Project Atlas",
                writeback_allowed=False,
            ),
            payload={
                "answer": "Project Atlas summary",
                "source": ["wiki"],
                "confidence": 1.0,
                "writeback_eligible": False,
                "evidence": [
                    {
                        "source_relpath": "project-atlas.txt",
                        "route": "wiki",
                        "quote": "Project Atlas summary",
                    }
                ],
                "trace": {"route": "wiki", "steps": []},
            },
        ),
        QueryObservation(
            case=GoldenQueryCase(
                id="no-hit",
                question="Zephyr Lime Thermostat",
                expected_route=None,
                expect_no_hit=True,
                writeback_allowed=False,
            ),
            payload={
                "answer": "未能於現有知識中找到答案",
                "source": [],
                "confidence": 0.0,
                "trace": {"route": "vector", "steps": []},
            },
        ),
        QueryObservation(
            case=GoldenQueryCase(
                id="bad-vector",
                question="detail owner",
                expected_route="vector",
                expected_source_relpath="owner.txt",
                expected_evidence_quote="Owner Iris",
                expected_answer_contains="Owner Iris",
                writeback_allowed=False,
            ),
            payload={
                "answer": "Owner Iris",
                "source": ["vector"],
                "confidence": 0.9,
                "writeback_eligible": True,
                "evidence": [
                    {
                        "source_relpath": "owner.txt",
                        "route": "vector",
                        "quote": "Owner Iris",
                    }
                ],
                "trace": {"route": "vector", "steps": []},
            },
        ),
    ]

    report = compute_metrics(observations)

    assert report.total == 3
    assert report.route_accuracy == 1.0
    assert report.precision_at_1 == 1.0
    assert report.evidence_hit_rate == 1.0
    assert report.answer_contains_rate == 1.0
    assert report.no_hit_precision == 1.0
    assert report.writeback_false_positive_rate == pytest.approx(1 / 3)
    assert report.failures["writeback_false_positive"] == ["bad-vector"]


def test_precision_at_1_requires_top_evidence_quote_match() -> None:
    observations = [
        QueryObservation(
            case=GoldenQueryCase(
                id="top-quote-miss",
                question="Atlas 摘要",
                expected_route="wiki",
                expected_source_relpath="project-atlas.txt",
                expected_evidence_quote="Atlas",
                writeback_allowed=True,
            ),
            payload={
                "answer": "Project Atlas summary",
                "source": ["wiki"],
                "confidence": 1.0,
                "evidence": [
                    {"source_relpath": "project-atlas.txt", "route": "wiki", "quote": "x"},
                    {
                        "source_relpath": "project-atlas.txt",
                        "route": "wiki",
                        "quote": "Atlas",
                    },
                ],
                "trace": {"route": "wiki", "steps": []},
            },
        ),
    ]

    report = compute_metrics(observations)

    assert report.precision_at_1 == 0.0
    assert report.evidence_hit_rate == 1.0
    assert report.failures["precision_at_1"] == ["top-quote-miss"]


def test_writeback_auto_committed_counts_as_false_positive() -> None:
    observations = [
        QueryObservation(
            case=GoldenQueryCase(
                id="auto-writeback",
                question="Atlas 摘要",
                expected_route="wiki",
                writeback_allowed=False,
            ),
            payload={
                "source": ["wiki"],
                "confidence": 1.0,
                "trace": {
                    "route": "wiki",
                    "steps": [
                        {"kind": "writeback", "detail": {"status": "auto-committed"}}
                    ],
                },
            },
        ),
    ]

    report = compute_metrics(observations)

    assert report.writeback_false_positive_rate == 1.0
    assert report.failures["writeback_false_positive"] == ["auto-writeback"]


def test_route_accuracy_requires_source_and_trace_route_to_match() -> None:
    observations = [
        QueryObservation(
            case=GoldenQueryCase(
                id="route-drift",
                question="Atlas 摘要",
                expected_route="wiki",
                writeback_allowed=True,
            ),
            payload={
                "answer": "Project Atlas summary",
                "source": ["wiki"],
                "confidence": 1.0,
                "trace": {"route": "vector", "steps": []},
            },
        )
    ]

    report = compute_metrics(observations)

    assert report.route_accuracy == 0.0
    assert report.failures["route_accuracy"] == ["route-drift"]


def test_expected_answer_contains_is_checked_when_present() -> None:
    observations = [
        QueryObservation(
            case=GoldenQueryCase(
                id="answer-miss",
                question="Atlas 摘要",
                expected_route="wiki",
                expected_answer_contains="Owner Iris",
                writeback_allowed=True,
            ),
            payload={
                "answer": "Project Atlas summary",
                "source": ["wiki"],
                "confidence": 1.0,
                "trace": {"route": "wiki", "steps": []},
            },
        )
    ]

    report = compute_metrics(observations)

    assert report.answer_contains_rate == 0.0
    assert report.failures["answer_contains_rate"] == ["answer-miss"]


def test_assert_thresholds_raises_with_specific_metric_name() -> None:
    observations = [
        QueryObservation(
            case=GoldenQueryCase(
                id="route-miss",
                question="Atlas 摘要",
                expected_route="wiki",
                expected_source_relpath="project-atlas.txt",
                expected_evidence_quote="Atlas",
                writeback_allowed=False,
            ),
            payload={
                "answer": "wrong",
                "source": ["vector"],
                "confidence": 0.9,
                "writeback_eligible": False,
                "evidence": [],
                "trace": {"route": "vector", "steps": []},
            },
        )
    ]
    report = compute_metrics(observations)

    with pytest.raises(AssertionError, match="route_accuracy"):
        assert_thresholds(
            report,
            MetricThresholds(
                route_accuracy=1.0,
                precision_at_1=0.0,
                evidence_hit_rate=0.0,
                answer_contains_rate=0.0,
                no_hit_precision=0.0,
                writeback_false_positive_rate=1.0,
            ),
        )

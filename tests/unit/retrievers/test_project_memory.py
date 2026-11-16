from __future__ import annotations

from hashlib import sha256

import pytest

from hks.core.manifest import Manifest, ManifestEntry
from hks.core.paths import runtime_paths
from hks.retrieval.evidence import candidate_evidence
from hks.retrieval.models import Candidate
from hks.retrievers.project_memory import parse_project_memory, refine_project_memory_candidates

BODY = "CI 必須執行 pytest、ruff 與 mypy，通過才部署。"
OTHER = "hook 目標路徑沒變時，沿用既有核准。"
DOCUMENT = (
    "---\ntype: project_memory\nproject: /work/example\nmemories: 2\n---\n"
    "# 專案記憶：/work/example\n\n## 做法\n\n"
    f"- {BODY}（m_123456abcd；確認於 2026-11-16；來源 codex:original）\n"
    f"- {OTHER}（m_234567bcde；確認於 2026-11-15；來源 claude:review）\n"
)


def setup_source(tmp_path, *, document=DOCUMENT, relpath="current.md"):
    paths = runtime_paths(tmp_path / "ks")
    paths.raw_sources.mkdir(parents=True)
    source = paths.raw_sources / relpath
    source.write_text(document)
    manifest = Manifest()
    manifest.entries[relpath] = ManifestEntry(
        relpath=relpath,
        sha256=sha256(source.read_bytes()).hexdigest(),
        format="md",
        size_bytes=source.stat().st_size,
        ingested_at="2026-11-16T00:00:00Z",
    )
    return paths, manifest, source


def window(text, *, score=0.8):
    return Candidate(
        text,
        "vector",
        score,
        {
            "source_relpath": "current.md",
            "_hks_match_text": text,
            "vector_similarity": 0.6,
            "quote": "a preceding citation m_999999ffff",
            "query_coverage": 1.0,
        },
    )


def test_parser_preserves_entry_identity_and_text():
    parsed = parse_project_memory(DOCUMENT)
    assert parsed is not None
    assert parsed.project == "/work/example"
    assert [(r.id, r.text, r.confirmed) for r in parsed.entries] == [
        ("m_123456abcd", BODY, "2026-11-16"),
        ("m_234567bcde", OTHER, "2026-11-15"),
    ]


@pytest.mark.parametrize(
    "document",
    [
        DOCUMENT.replace("type: project_memory", "type: notes"),
        DOCUMENT.replace("memories: 2", "memories: 3"),
        DOCUMENT.replace("memories: 2", "memories: true"),
        DOCUMENT.replace("2026-11-15", "2026-99-99"),
        DOCUMENT.replace("m_234567bcde", "m_123456abcd"),
        "---\n[broken YAML\n---\n" + BODY,
        "# notes\n" + DOCUMENT,
    ],
)
def test_ordinary_or_malformed_documents_are_not_guessed_as_project_memory(document):
    assert parse_project_memory(document) is None


def test_a_tail_identifier_is_resolved_to_its_own_rule_not_the_next_rule(tmp_path):
    paths, manifest, _ = setup_source(tmp_path)
    old = window(f"m_123456abcd）\n- {OTHER}")
    found, count = refine_project_memory_candidates(
        "m_123456abcd", [old], paths=paths, manifest=manifest
    )
    assert count == 1 and len(found) == 1
    assert BODY in found[0].text and OTHER not in found[0].text
    assert found[0].source_route == "wiki"
    assert "vector_similarity" not in found[0].metadata
    assert candidate_evidence(found[0]) == [
        {
            "source_relpath": "current.md",
        "route": "wiki",
            "quote": BODY,
        }
    ]


def test_vector_score_requires_the_whole_rule_and_cannot_keep_a_neighbor_identifier(tmp_path):
    paths, manifest, _ = setup_source(tmp_path)
    old = window(BODY)
    found, _ = refine_project_memory_candidates("CI pytest", [old], paths=paths, manifest=manifest)
    assert found[0].source_route == "vector"
    assert found[0].metadata["vector_similarity"] == 0.6
    assert "quote" not in found[0].metadata
    assert "m_999999ffff" not in str(found[0].metadata)
    assert old.metadata["quote"] == "a preceding citation m_999999ffff", "do not mutate input"


def test_unknown_memory_id_cannot_use_another_entry(tmp_path):
    paths, manifest, _ = setup_source(tmp_path)
    found, count = refine_project_memory_candidates(
        "m_999999ffff", [window(DOCUMENT)], paths=paths, manifest=manifest
    )
    assert found == [] and count == 1


def test_source_hash_changes_disable_refinement_without_writing_anything(tmp_path):
    paths, manifest, source = setup_source(tmp_path)
    source.write_text(DOCUMENT.replace("pytest", "WRONG"))
    old = window(DOCUMENT)
    found, count = refine_project_memory_candidates("CI", [old], paths=paths, manifest=manifest)
    assert count == 0 and found == [old]
    assert "WRONG" in source.read_text()


def test_manifest_relpath_cannot_follow_a_symlink_outside_raw_sources(tmp_path):
    paths, manifest, source = setup_source(tmp_path)
    external = tmp_path / "private.md"
    external.write_text(DOCUMENT)
    source.unlink()
    source.symlink_to(external)
    old = window(DOCUMENT)
    found, count = refine_project_memory_candidates("CI", [old], paths=paths, manifest=manifest)
    assert count == 0 and found == [old]


def test_entries_keep_the_nominated_position_before_the_llm_candidate_cap(tmp_path):
    paths, manifest, _ = setup_source(tmp_path)
    others = [Candidate(f"history {i}", "vector", 0.8, {}) for i in range(12)]
    found, _ = refine_project_memory_candidates(
        "CI", [window(DOCUMENT), *others], paths=paths, manifest=manifest
    )
    assert BODY in found[0].text and found[1:] == others


def test_an_empty_export_does_not_answer_with_only_a_heading(tmp_path):
    doc = "---\ntype: project_memory\nproject: /work/example\nmemories: 0\n---\n# Empty\n"
    paths, manifest, _ = setup_source(tmp_path, document=doc)
    found, count = refine_project_memory_candidates(
        "example", [window(doc)], paths=paths, manifest=manifest
    )
    assert found == [] and count == 1

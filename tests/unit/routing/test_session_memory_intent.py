from __future__ import annotations

from datetime import date

from hks.routing.session_memory import (
    analyze_session_memory_intent,
    metadata_matches_session_intent,
    workspace_id_matches,
)


def test_detects_yesterday_session_memory_intent() -> None:
    intent = analyze_session_memory_intent(
        "昨天 vibe coding 做了什麼",
        today=date(2026, 5, 23),
    )

    assert intent is not None
    assert intent.date == "2026-05-22"


def test_detects_explicit_session_memory_date() -> None:
    intent = analyze_session_memory_intent("2026/5/22 vibe coding 影響什麼")

    assert intent is not None
    assert intent.date == "2026-05-22"


# --- Workspace intent detection ---


def test_detects_kebab_case_workspace_name() -> None:
    intent = analyze_session_memory_intent("social-bank-check 最後處理到哪")

    assert intent is not None
    assert intent.workspace == "social-bank-check"
    assert intent.is_status_query is True


def test_detects_explicit_workspace_id() -> None:
    intent = analyze_session_memory_intent(
        "workspace_id=social-bank-check-d61a68f0 的進度"
    )

    assert intent is not None
    assert intent.workspace == "social-bank-check-d61a68f0"
    assert intent.is_status_query is True


def test_detects_workspace_without_status_keyword() -> None:
    intent = analyze_session_memory_intent("social-bank-check 做了什麼")

    assert intent is not None
    assert intent.workspace == "social-bank-check"
    assert intent.is_status_query is False


def test_workspace_with_date_combines_both() -> None:
    intent = analyze_session_memory_intent(
        "2026/5/22 social-bank-check 狀態",
    )

    assert intent is not None
    assert intent.date == "2026-05-22"
    assert intent.workspace == "social-bank-check"
    assert intent.is_status_query is True


def test_detects_single_word_workspace_in_status_query() -> None:
    intent = analyze_session_memory_intent("hks 最後處理到哪")

    assert intent is not None
    assert intent.workspace == "hks"
    assert intent.is_status_query is True


def test_detects_uppercase_single_word_workspace_in_status_query() -> None:
    intent = analyze_session_memory_intent("HKS 最後處理到哪")

    assert intent is not None
    assert intent.workspace == "hks"
    assert intent.is_status_query is True


def test_detects_single_word_workspace_near_english_status_keyword() -> None:
    intent = analyze_session_memory_intent("what is hks status")

    assert intent is not None
    assert intent.workspace == "hks"
    assert intent.is_status_query is True


def test_detects_single_word_workspace_openclaw() -> None:
    intent = analyze_session_memory_intent("openclaw 最後處理到哪")

    assert intent is not None
    assert intent.workspace == "openclaw"
    assert intent.is_status_query is True


def test_single_word_not_triggered_without_status_keyword() -> None:
    intent = analyze_session_memory_intent("hks 做了什麼")

    assert intent is None


def test_single_word_excludes_status_keywords() -> None:
    intent = analyze_session_memory_intent("status 最後處理到哪")

    assert intent is None or intent.workspace is None


def test_no_workspace_no_date_returns_none() -> None:
    intent = analyze_session_memory_intent("什麼是知識管理")

    assert intent is None


def test_workspace_with_yesterday() -> None:
    intent = analyze_session_memory_intent(
        "昨天 dgx-spark 進度",
        today=date(2026, 5, 23),
    )

    assert intent is not None
    assert intent.date == "2026-05-22"
    assert intent.workspace == "dgx-spark"
    assert intent.is_status_query is True


# --- workspace_id_matches ---


def test_workspace_id_exact_match() -> None:
    assert workspace_id_matches("social-bank-check", "social-bank-check") is True


def test_workspace_id_prefix_with_hash_suffix() -> None:
    assert workspace_id_matches("social-bank-check-d61a68f0", "social-bank-check") is True


def test_workspace_id_no_match() -> None:
    assert workspace_id_matches("hks-81c05951", "social-bank-check") is False


def test_workspace_id_non_hex_suffix_no_match() -> None:
    assert workspace_id_matches("social-bank-check-xyz", "social-bank-check") is False


# --- metadata_matches_session_intent with workspace ---


def test_metadata_matches_workspace_intent() -> None:
    from hks.routing.session_memory import SessionMemoryIntent

    intent = SessionMemoryIntent(workspace="social-bank-check")
    metadata = {"workspace_id": "social-bank-check-d61a68f0", "date": "2026-05-21"}

    assert metadata_matches_session_intent(metadata, intent) is True


def test_metadata_rejects_wrong_workspace() -> None:
    from hks.routing.session_memory import SessionMemoryIntent

    intent = SessionMemoryIntent(workspace="social-bank-check")
    metadata = {"workspace_id": "hks-81c05951", "date": "2026-05-21"}

    assert metadata_matches_session_intent(metadata, intent) is False


def test_metadata_workspace_with_date_filter() -> None:
    from hks.routing.session_memory import SessionMemoryIntent

    intent = SessionMemoryIntent(workspace="social-bank-check", date="2026-05-21")

    right_date = {"workspace_id": "social-bank-check-d61a68f0", "date": "2026-05-21"}
    wrong_date = {"workspace_id": "social-bank-check-d61a68f0", "date": "2026-05-20"}

    assert metadata_matches_session_intent(right_date, intent) is True
    assert metadata_matches_session_intent(wrong_date, intent) is False


def test_metadata_no_workspace_id_rejected_for_workspace_intent() -> None:
    from hks.routing.session_memory import SessionMemoryIntent

    intent = SessionMemoryIntent(workspace="social-bank-check")
    metadata = {"source_relpath": "daily/2026-05-21.md", "slug": "2026-05-21"}

    assert metadata_matches_session_intent(metadata, intent) is False


def test_session_memory_intent_to_detail_includes_date_range() -> None:
    from hks.routing.session_memory import SessionMemoryIntent

    intent = SessionMemoryIntent(
        date_start="2026-05-25",
        date_end="2026-05-27",
    )
    detail = intent.to_detail()

    assert detail["date_start"] == "2026-05-25"
    assert detail["date_end"] == "2026-05-27"
    assert detail["date"] is None


def test_metadata_matches_date_range_inclusive() -> None:
    from hks.routing.session_memory import SessionMemoryIntent

    intent = SessionMemoryIntent(date_start="2026-05-25", date_end="2026-05-27")
    session_meta = {
        "hks_type": "session_daily",
        "date": "2026-05-26",
        "source_relpath": "daily/2026-05-26.md",
    }

    assert metadata_matches_session_intent(session_meta, intent) is True
    assert metadata_matches_session_intent({**session_meta, "date": "2026-05-24"}, intent) is False
    assert metadata_matches_session_intent({**session_meta, "date": "2026-05-28"}, intent) is False


def test_metadata_session_daily_page_with_workspace_intent_matches_by_date() -> None:
    from hks.routing.session_memory import SessionMemoryIntent

    intent = SessionMemoryIntent(
        workspace="bootstrap",
        date_start="2026-05-25",
        date_end="2026-05-27",
    )
    page_meta = {
        "hks_type": "session_daily",
        "date": "2026-05-27",
        "source_relpath": "daily/2026-05-27.md",
    }

    assert metadata_matches_session_intent(page_meta, intent) is True


def test_metadata_workspace_with_date_range() -> None:
    from hks.routing.session_memory import SessionMemoryIntent

    intent = SessionMemoryIntent(
        workspace="social-bank-check",
        date_start="2026-05-25",
        date_end="2026-05-27",
    )
    in_range = {
        "workspace_id": "social-bank-check-d61a68f0",
        "date": "2026-05-26",
    }
    out_range = {**in_range, "date": "2026-05-20"}

    assert metadata_matches_session_intent(in_range, intent) is True
    assert metadata_matches_session_intent(out_range, intent) is False

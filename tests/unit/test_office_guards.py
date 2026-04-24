"""Unit tests for ingest/guards.py — size preflight + signal-based timeout."""

from __future__ import annotations

import time

import pytest

from hks.ingest.guards import (
    OversizeError,
    load_office_limits,
    preflight_size_check,
    with_timeout,
)


@pytest.mark.unit
def test_preflight_rejects_oversized_file(tmp_path) -> None:
    oversized = tmp_path / "big.bin"
    oversized.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MiB
    with pytest.raises(OversizeError) as excinfo:
        preflight_size_check(oversized, max_mb=1)
    assert excinfo.value.limit_mb == 1


@pytest.mark.unit
def test_preflight_accepts_small_file(tmp_path) -> None:
    small = tmp_path / "tiny.txt"
    small.write_bytes(b"hello")
    preflight_size_check(small, max_mb=1)  # no exception


@pytest.mark.unit
def test_with_timeout_raises_when_exceeded() -> None:
    with pytest.raises(TimeoutError):
        with with_timeout(1):
            time.sleep(2.0)


@pytest.mark.unit
def test_with_timeout_no_raise_when_under_budget() -> None:
    with with_timeout(5):
        time.sleep(0.01)


@pytest.mark.unit
def test_with_timeout_zero_is_noop() -> None:
    with with_timeout(0):
        time.sleep(0.01)


@pytest.mark.unit
def test_load_office_limits_defaults(monkeypatch) -> None:
    monkeypatch.delenv("HKS_OFFICE_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("HKS_OFFICE_MAX_FILE_MB", raising=False)
    limits = load_office_limits()
    assert limits.timeout_seconds == 60
    assert limits.max_file_mb == 200


@pytest.mark.unit
def test_load_office_limits_honors_env(monkeypatch) -> None:
    monkeypatch.setenv("HKS_OFFICE_TIMEOUT_SEC", "30")
    monkeypatch.setenv("HKS_OFFICE_MAX_FILE_MB", "50")
    limits = load_office_limits()
    assert limits.timeout_seconds == 30
    assert limits.max_file_mb == 50


@pytest.mark.unit
def test_load_office_limits_rejects_out_of_range(monkeypatch) -> None:
    monkeypatch.setenv("HKS_OFFICE_TIMEOUT_SEC", "9999")
    with pytest.raises(ValueError, match=r"HKS_OFFICE_TIMEOUT_SEC"):
        load_office_limits()


@pytest.mark.unit
def test_load_office_limits_rejects_non_integer(monkeypatch) -> None:
    monkeypatch.setenv("HKS_OFFICE_MAX_FILE_MB", "not-a-number")
    with pytest.raises(ValueError, match=r"HKS_OFFICE_MAX_FILE_MB"):
        load_office_limits()

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from hks.adapters import core
from hks.coordination.service import CoordinationService
from hks.errors import KSError


def _try_claim(agent_id: str) -> str:
    try:
        CoordinationService().claim_lease(agent_id, "wiki:atlas")
    except KSError as error:
        return error.code
    return "OK"


@pytest.mark.integration
def test_coordination_lease_claim_is_atomic_under_100_concurrent_attempts(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(_try_claim, [f"agent-{index}" for index in range(100)]))

    assert results.count("OK") == 1
    assert results.count("LEASE_CONFLICT") == 99

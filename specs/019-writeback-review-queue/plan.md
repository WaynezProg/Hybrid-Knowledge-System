# Write-back Review Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 `ks query --writeback` 從直接寫 wiki 改成 review queue，只有 `ks writeback approve` 能產生 evidence-backed wiki page，並清掉對外 `calibrated_confidence` 欄位。

**Architecture:** 新增 `hks.writeback.queue` 作為 file-per-item queue store，`query` 只負責 enqueue intent 與 trace/log，`writeback` CLI group 負責 list/show/approve/reject。`writer.py` 從 `commit()` 直寫改為 `promote()`，approve 時檢查有效 evidence，再沿用 wiki store 寫入 `origin=writeback` page。Confidence cleanup 保留 internal route-specific auto threshold，但對外只輸出 `confidence`、`retrieval_score`、`writeback_eligible`。

**Tech Stack:** Python 3.12, Typer, jsonschema, existing `WikiStore`, existing `blocking_file_lock`, existing `atomic_write`, pytest, Ruff, Mypy

**Spec:** `specs/019-writeback-review-queue/spec.md`

---

## File Map

### New Files

| File | Responsibility |
|---|---|
| `src/hks/writeback/queue.py` | Queue item model, deterministic id, file paths, locking, enqueue/list/load/archive |
| `src/hks/commands/writeback.py` | CLI command handlers for `ks writeback list/show/approve/reject` |
| `tests/unit/writeback/test_queue.py` | Queue id, dedup, archive, rejected requeue, locking behavior |
| `tests/unit/commands/test_writeback_cli.py` | Command handler JSON shape and missing-id errors |

### Modified Files

| File | Change |
|---|---|
| `src/hks/writeback/gate.py` | Change decision actions from `commit/decline` to `enqueue/skip/skip-non-tty`; remove direct confidence checks from gate |
| `src/hks/writeback/writer.py` | Replace `commit()` with `promote()`; enforce valid evidence; handle slug conflict policy |
| `src/hks/commands/query.py` | Replace `_maybe_writeback()` with `_maybe_enqueue()`; remove direct wiki write and `forced_writeback` event |
| `src/hks/retrieval/confidence.py` | Rename `calibrated_confidence` to `confidence`; retain internal threshold; reject `<writeback>` provenance |
| `src/hks/core/schema.py` | Remove `QueryResponse.calibrated_confidence`; keep `confidence`, `retrieval_score`, `writeback_eligible` |
| `src/hks/storage/wiki.py` | Add `EventStatus` values `enqueued`, `approved`, `rejected` |
| `src/hks/cli.py` | Register `writeback` Typer group and four commands |
| `src/hks/evaluation/retrieval_quality.py` | Rename auto-commit detection to auto-enqueue detection and align false-positive semantics |
| `specs/005-phase3-lint-impl/contracts/query-response.schema.json` | Remove `calibrated_confidence`; allow raw `retrieval_score`; update description/examples |
| `specs/006-mcp-api-adapter/contracts/http-api.openapi.yaml` | Remove `calibrated_confidence` from `QueryResponse`; keep writeback request enum |
| `README.md`, `README.en.md`, `docs/main.md` | Document review queue behavior, confidence fields, and approve workflow |
| Existing tests under `tests/integration/test_writeback.py`, `tests/unit/writeback/`, `tests/unit/retrieval/`, `tests/eval/`, `tests/contract/`, adapter tests | Update expectations from direct write to queue/promote |

## Public Contract Decisions

- `ks query --writeback=no`: append trace `writeback.status="declined"` or no mutation; no queue file.
- `ks query --writeback=auto`: enqueue only when `response.writeback_eligible is True`; otherwise trace `writeback.status="skipped-ineligible"`.
- `ks query --writeback=yes`: enqueue any hit with `source != []`; reviewer can still reject or fail approve if evidence is invalid.
- `ks query --writeback=ask`: TTY confirm uses `yes` semantics; non-TTY returns `skip-non-tty`.
- Queue item id is `sha256(question, answer, route, normalized_evidence)[:24]`; evidence changes produce a new item.
- `approve` refuses empty evidence, missing `source_relpath`, missing `quote`, and `source_relpath == "<writeback>"`.
- `approve` may overwrite existing `origin=writeback` or `origin=llm_wiki` page with the same slug, but fails on `origin=ingest`.
- API/MCP do not expose queue management endpoints in 019; their query calls inherit enqueue behavior when caller passes `writeback=auto|yes|ask`.

## Key Interfaces

`src/hks/writeback/queue.py` should expose these stable interfaces:

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hks.core.schema import Route

QueueStatus = Literal["pending", "approved", "rejected"]
EnqueueStatus = Literal["created", "deduped", "already-promoted"]


@dataclass(frozen=True, slots=True)
class WritebackQueueItem:
    id: str
    question: str
    answer: str
    route: Route
    source: list[Route]
    evidence: list[dict[str, object]]
    retrieval_score: float | None
    writeback_eligible: bool
    reasons: list[str] = field(default_factory=list)
    created_at: str = ""
    status: QueueStatus = "pending"
    decided_at: str | None = None
    slug: str | None = None


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    status: EnqueueStatus
    id: str
    path: Path | None
```

The implementation may add helper functions, but command/query code should only need:

```python
def build_item(
    *,
    question: str,
    answer: str,
    route: Route,
    source: list[Route],
    evidence: list[dict[str, object]],
    retrieval_score: float | None,
    writeback_eligible: bool,
    reasons: list[str],
) -> WritebackQueueItem: ...

def enqueue(item: WritebackQueueItem, *, paths: RuntimePaths | None = None) -> EnqueueResult: ...
def list_pending(*, paths: RuntimePaths | None = None) -> list[WritebackQueueItem]: ...
def load(item_id: str, *, paths: RuntimePaths | None = None) -> WritebackQueueItem: ...
def archive(item_id: str, status: Literal["approved", "rejected"], *, slug: str | None = None, paths: RuntimePaths | None = None) -> WritebackQueueItem: ...
```

`src/hks/writeback/writer.py` should expose:

```python
def valid_evidence_items(item: WritebackQueueItem) -> list[dict[str, object]]: ...
def promote(item: WritebackQueueItem, *, wiki_store: WikiStore | None = None) -> tuple[WikiPage, list[TraceStep]]: ...
```

## Phase 1: Contract Tests First

### Task 1: QueryResponse contract removes calibrated confidence

**Files:**
- Modify: `tests/contract/test_query_phase1_contract_preserved.py`
- Modify: `specs/005-phase3-lint-impl/contracts/query-response.schema.json`
- Modify: `src/hks/core/schema.py`

- [ ] **Step 1: Add failing contract assertion**

```python
def test_query_response_rejects_calibrated_confidence() -> None:
    payload = {
        "answer": "ok",
        "source": ["vector"],
        "confidence": 0.8,
        "retrieval_score": 1.25,
        "calibrated_confidence": 0.8,
        "writeback_eligible": True,
        "trace": {"route": "vector", "steps": []},
    }
    with pytest.raises(jsonschema.ValidationError):
        validate(payload)
```

- [ ] **Step 2: Run failing test**

Run: `uv run pytest tests/contract/test_query_phase1_contract_preserved.py::test_query_response_rejects_calibrated_confidence -q`

Expected: FAIL because schema still allows `calibrated_confidence`.

- [ ] **Step 3: Remove field from schema and dataclass**

Remove `calibrated_confidence` from `QueryResponse`, `to_dict()`, schema properties, OpenAPI schema, README examples, and tests.

- [ ] **Step 4: Run focused contract tests**

Run: `uv run pytest tests/contract/test_query_phase1_contract_preserved.py tests/contract/test_json_schema.py -q`

Expected: PASS.

### Task 2: Write queue storage tests

**Files:**
- Create: `tests/unit/writeback/test_queue.py`
- Create: `src/hks/writeback/queue.py`

- [ ] **Step 1: Add tests for deterministic id and evidence-sensitive dedup**

```python
def test_item_id_changes_when_evidence_changes() -> None:
    first = build_item(question="Q", answer="A", route="vector", source=["vector"], evidence=[{"source_relpath": "a.md", "route": "vector", "quote": "one"}], retrieval_score=0.9, writeback_eligible=True, reasons=[])
    second = build_item(question="Q", answer="A", route="vector", source=["vector"], evidence=[{"source_relpath": "a.md", "route": "vector", "quote": "two"}], retrieval_score=0.9, writeback_eligible=True, reasons=[])
    assert first.id != second.id
```

- [ ] **Step 2: Add tests for `created`, `deduped`, `already-promoted`, and rejected requeue**

Use `runtime_paths(tmp_path / "ks")`; enqueue once returns `created`, second returns `deduped`, archive approved then enqueue returns `already-promoted`, archive rejected then enqueue returns `created`.

- [ ] **Step 3: Run failing tests**

Run: `uv run pytest tests/unit/writeback/test_queue.py -q`

Expected: FAIL because `hks.writeback.queue` does not exist.

- [ ] **Step 4: Implement queue module**

Use `atomic_write()` for JSON writes and `blocking_file_lock(paths.root / "writeback" / ".locks" / f"{item_id}.lock")` around enqueue/archive. Store JSON with `ensure_ascii=False`, `indent=2`, and sorted deterministic keys inside id generation.

- [ ] **Step 5: Run queue tests**

Run: `uv run pytest tests/unit/writeback/test_queue.py -q`

Expected: PASS.

## Phase 2: Confidence and Gate Semantics

### Task 3: Rename confidence assessment while keeping internal auto thresholds

**Files:**
- Modify: `src/hks/retrieval/confidence.py`
- Modify: `tests/unit/retrieval/test_confidence.py`

- [ ] **Step 1: Update tests to assert `confidence`, not `calibrated_confidence`**

Replace assertions like `result.calibrated_confidence` with `result.confidence`.

- [ ] **Step 2: Add invalid provenance test**

```python
def test_writeback_source_relpath_is_not_valid_provenance() -> None:
    result = assess(route="vector", raw_score=0.9, evidence=[{"source_relpath": "<writeback>", "route": "vector", "quote": "old answer"}])
    assert result.writeback_eligible is False
    assert any("<writeback>" in reason for reason in result.reasons)
```

- [ ] **Step 3: Run failing confidence tests**

Run: `uv run pytest tests/unit/retrieval/test_confidence.py -q`

Expected: FAIL until the dataclass and provenance checks are updated.

- [ ] **Step 4: Implement rename and provenance check**

Keep `_AUTO_THRESHOLDS`; compute `confidence = clamp(raw_score, 0, 1)`; mark evidence invalid when `source_relpath` is missing, empty, or exactly `<writeback>`.

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest tests/unit/retrieval/test_confidence.py tests/unit/retrieval/test_evidence.py -q`

Expected: PASS.

### Task 4: Simplify writeback gate to intent only

**Files:**
- Modify: `src/hks/writeback/gate.py`
- Modify: `tests/unit/writeback/test_gate.py`
- Modify: `tests/unit/writeback/test_gate_assessment.py`

- [ ] **Step 1: Replace gate tests with intent semantics**

Expected decisions:

```python
("no", False, "skip", "declined")
("yes", False, "enqueue", "enqueued")
("auto", False, "enqueue", "enqueued")
("ask", False, "skip-non-tty", "skip-non-tty")
```

TTY `ask` with prompt true returns `enqueue`; prompt false returns `skip`.

- [ ] **Step 2: Run failing gate tests**

Run: `uv run pytest tests/unit/writeback/test_gate.py tests/unit/writeback/test_gate_assessment.py -q`

Expected: FAIL because current gate still returns commit/decline based on confidence.

- [ ] **Step 3: Implement gate changes**

Set `DecisionAction = Literal["enqueue", "skip", "skip-non-tty"]`; keep `Decision.status` as a trace/log status string; remove `auto_threshold()` use from `decide()`.

- [ ] **Step 4: Run gate tests**

Run: `uv run pytest tests/unit/writeback/test_gate.py tests/unit/writeback/test_gate_assessment.py -q`

Expected: PASS.

## Phase 3: Query Enqueue Integration

### Task 5: Replace direct writeback with queue enqueue

**Files:**
- Modify: `src/hks/commands/query.py`
- Modify: `tests/integration/test_writeback.py`
- Modify: `tests/unit/commands/test_writeback_context.py`

- [ ] **Step 1: Update integration tests**

Required assertions:

```python
result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=yes"])
payload = json.loads(result.stdout)
step = next(step for step in payload["trace"]["steps"] if step["kind"] == "writeback")
assert step["detail"]["status"] == "enqueued"
assert len(list((tmp_ks_root / "writeback" / "queue").glob("*.json"))) == 1
assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 10
events_path = tmp_ks_root / "coordination" / "events.jsonl"
assert not events_path.exists() or "forced_writeback" not in events_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Add auto ineligible test**

Run `ks query "summary Atlas" --writeback=auto`; assert status `skipped-ineligible` and no queue item for the wiki summary case.

- [ ] **Step 3: Run failing integration tests**

Run: `uv run pytest tests/integration/test_writeback.py -q`

Expected: FAIL while query still direct-commits pages.

- [ ] **Step 4: Implement `_maybe_enqueue()`**

Build queue item from `question`, `response`, and `assessment.reasons`. Map queue statuses:

```python
status_map = {
    "created": "enqueued",
    "deduped": "enqueued-deduped",
    "already-promoted": "already-promoted",
}
```

Append wiki log only when queue status is `created`. Delete `_record_forced_writeback_event()`.

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest tests/integration/test_writeback.py tests/unit/commands/test_writeback_context.py -q`

Expected: PASS after tests are updated for queue semantics.

## Phase 4: Promote and Review CLI

### Task 6: Implement evidence-backed promote

**Files:**
- Modify: `src/hks/writeback/writer.py`
- Modify: `tests/unit/writeback/test_writer.py`

- [ ] **Step 1: Replace writer tests**

Test `promote()` writes a page with `## 來源依據`, real `source`, `origin=writeback`, `writeback_query`, escaped related links, and an `approved` log entry.

- [ ] **Step 2: Add hard-gate tests**

Cases that must raise `KSError(code="WRITEBACK_EVIDENCE_REQUIRED")`: empty evidence, missing `source_relpath`, missing `quote`, `source_relpath="<writeback>"`.

- [ ] **Step 3: Add conflict tests**

Existing slug with `origin=ingest` raises `KSError(code="CONFLICT")`; existing slug with `origin=writeback` or `origin=llm_wiki` is overwritten at the same slug.

- [ ] **Step 4: Run failing writer tests**

Run: `uv run pytest tests/unit/writeback/test_writer.py -q`

Expected: FAIL while writer still exposes `commit()`.

- [ ] **Step 5: Implement `promote()`**

Use the first valid evidence item for `source_relpath`; build body:

```markdown
# {question}

{answer}

## 來源依據

- {source_relpath} — "{quote}"
```

Preserve existing related page links under `## Related`.

- [ ] **Step 6: Run writer tests**

Run: `uv run pytest tests/unit/writeback/test_writer.py -q`

Expected: PASS.

### Task 7: Add `ks writeback` CLI group

**Files:**
- Create: `src/hks/commands/writeback.py`
- Create: `tests/unit/commands/test_writeback_cli.py`
- Modify: `src/hks/cli.py`
- Modify: `tests/contract/test_exit_codes.py`

- [ ] **Step 1: Add command tests**

Use fixture queue items and assert:

```python
payload["trace"]["steps"][0]["kind"] == "writeback"
payload["trace"]["steps"][0]["detail"]["action"] == "list"
payload["trace"]["steps"][0]["detail"]["items"][0]["id"] == item.id
```

For missing id, assert exit code `66` and error code `NOINPUT`.

- [ ] **Step 2: Run failing command tests**

Run: `uv run pytest tests/unit/commands/test_writeback_cli.py tests/contract/test_exit_codes.py -q`

Expected: FAIL until command module and CLI registration exist.

- [ ] **Step 3: Implement command handlers**

Return `QueryResponse(answer=..., source=[], confidence=0.0, trace=Trace(route="wiki", steps=[TraceStep(kind="writeback", detail={...})]))` for all four commands.

- [ ] **Step 4: Register CLI**

Add `writeback_app = typer.Typer(...)`, `app.add_typer(writeback_app, name="writeback")`, and four subcommands delegating through `run_command()`.

- [ ] **Step 5: Run command tests**

Run: `uv run pytest tests/unit/commands/test_writeback_cli.py tests/contract/test_exit_codes.py -q`

Expected: PASS.

### Task 8: Add approve/reject integration coverage

**Files:**
- Modify: `tests/integration/test_writeback.py`

- [ ] **Step 1: Add query-approve flow test**

Ingest fixture, run `ks query --writeback=yes`, read queue id from trace, run `ks writeback approve <id>`, assert queue empty, archive has approved item, wiki page has `## 來源依據`, and source is not `<writeback>`.

- [ ] **Step 2: Add reject flow test**

Run `ks writeback reject <id>`, assert archive item status is `rejected` and wiki page count is unchanged.

- [ ] **Step 3: Add dedup flow test**

Run same query twice with `--writeback=yes`; assert one queue file and second trace status `enqueued-deduped`.

- [ ] **Step 4: Run integration tests**

Run: `uv run pytest tests/integration/test_writeback.py -q`

Expected: PASS.

## Phase 5: Adapters, Eval, Docs

### Task 9: Adapter and OpenAPI alignment

**Files:**
- Modify: `specs/006-mcp-api-adapter/contracts/http-api.openapi.yaml`
- Modify: `tests/contract/test_http_api_contract.py`
- Modify: `tests/contract/test_mcp_query_contract.py`
- Modify: `tests/integration/test_http_adapter.py`
- Modify: `tests/integration/test_mcp_query.py`

- [ ] **Step 1: Remove `calibrated_confidence` from OpenAPI QueryResponse**

Keep `writeback` request enum unchanged.

- [ ] **Step 2: Add adapter query queue smoke**

For HTTP and MCP query calls with `writeback="yes"`, assert a queue item is created and wiki page count is unchanged.

- [ ] **Step 3: Run adapter tests**

Run: `uv run pytest tests/contract/test_http_api_contract.py tests/contract/test_mcp_query_contract.py tests/integration/test_http_adapter.py tests/integration/test_mcp_query.py -q`

Expected: PASS.

### Task 10: Update golden retrieval quality semantics

**Files:**
- Modify: `src/hks/evaluation/retrieval_quality.py`
- Modify: `tests/unit/evaluation/test_retrieval_quality.py`
- Modify: `tests/eval/test_golden_retrieval_quality.py`

- [ ] **Step 1: Rename auto commit detector**

Replace `_auto_committed()` with `_auto_enqueued()` and detect statuses `enqueued`, `enqueued-deduped`, and `already-promoted`.

- [ ] **Step 2: Keep metric meaning explicit**

For `writeback_allowed=false`, a false positive is `payload.writeback_eligible is True` or an auto-enqueue trace is present.

- [ ] **Step 3: Add isolated auto smoke**

In eval test fixture, run one known ineligible case with `writeback="auto"` and assert no queue item is created.

- [ ] **Step 4: Run eval unit tests**

Run: `uv run pytest tests/unit/evaluation/test_retrieval_quality.py tests/eval/test_golden_retrieval_quality.py -q`

Expected: PASS with `HKS_EMBEDDING_MODEL=simple`.

### Task 11: Documentation updates

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/main.md`
- Modify: `specs/019-writeback-review-queue/spec.md`

- [ ] **Step 1: Update writeback docs**

Document `ks writeback list/show/approve/reject`, queue path, approve evidence requirement, and no direct wiki write from query.

- [ ] **Step 2: Update confidence field docs**

State that `confidence` is clamped score, `retrieval_score` is raw retrieval score, `calibrated_confidence` is removed, and `writeback_eligible` means auto queue eligibility.

- [ ] **Step 3: Add post-implementation status**

After implementation and verification, update spec status from `設計通過，待 implementation` to `已完成，待 archive` or create `ARCHIVE.md` if the branch is closing 019 in the same pass.

## Verification Gates

Run these before declaring 019 complete:

```bash
uv run pytest tests/unit/writeback tests/unit/retrieval/test_confidence.py tests/unit/commands/test_writeback_context.py tests/unit/commands/test_writeback_cli.py -q
uv run pytest tests/integration/test_writeback.py tests/integration/test_http_adapter.py tests/integration/test_mcp_query.py -q
uv run pytest tests/contract/test_query_phase1_contract_preserved.py tests/contract/test_json_schema.py tests/contract/test_http_api_contract.py tests/contract/test_mcp_query_contract.py -q
HKS_EMBEDDING_MODEL=simple uv run pytest tests/unit/evaluation/test_retrieval_quality.py tests/eval/test_golden_retrieval_quality.py -q
uv run ruff check .
uv run mypy src/hks
uv run pytest --tb=short -q
```

## Commit Strategy

Keep the existing low-risk README/dependency cleanup in a separate commit before implementation. For 019, use three implementation commits if the executor is committing:

1. `feat(writeback): add review queue storage`
2. `feat(writeback): route query writebacks through review queue`
3. `feat(writeback): add approve CLI and update contracts`

Do not mix 019 runtime changes with the currently uncommitted `README.md`, `pyproject.toml`, and `uv.lock` cleanup unless the user explicitly asks to squash.

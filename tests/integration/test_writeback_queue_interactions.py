"""019 review queue 與 main 上較新行為的交互：021 `--writeback=no` 不寫檔、026 vector
evidence gate、PR #26 的鎖與 atomic write、PR #32 的 workspace-scoped 指令、lint。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from hks.cli import app
from hks.commands import query as query_module
from hks.commands import writeback as writeback_command
from hks.core.paths import runtime_paths
from hks.errors import ExitCode, KSError
from hks.retrieval.models import Candidate
from hks.workspace.service import register_workspace

DOCS = {
    "ledger.md": "# Ledger\n\nThe monthly ledger close moved to the third working day.\n",
    "search.md": "# Search\n\nIndex rebuilds on the catalog cluster take about two hours.\n",
    "mobile.md": "# Mobile\n\nCrash triage for the handheld client happens every Tuesday.\n",
    "storage.md": "# Storage\n\nCold archive retrieval usually takes twelve hours.\n",
}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _payload(result: Any) -> dict[str, Any]:
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def _writeback_step(payload: dict[str, Any]) -> dict[str, Any]:
    last = payload["trace"]["steps"][-1]
    assert last["kind"] == "writeback"
    return dict(last["detail"])


def _queue_files(ks_root: Path) -> list[Path]:
    return sorted((ks_root / "writeback" / "queue").glob("*.json"))


def _archive_files(ks_root: Path) -> list[Path]:
    return sorted((ks_root / "writeback" / "archive").glob("*.json"))


def _tree(ks_root: Path, *, skip: tuple[str, ...] = ("vector",)) -> dict[str, bytes]:
    """Every file under the KS root except the vector db, which Chroma touches on open."""
    return {
        path.relative_to(ks_root).as_posix(): path.read_bytes()
        for path in sorted(ks_root.rglob("*"))
        if path.is_file() and path.relative_to(ks_root).parts[0] not in skip
    }


@pytest.fixture()
def small_kb(cli_runner: CliRunner, tmp_path: Path, tmp_ks_root: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    for name, text in DOCS.items():
        (docs / name).write_text(text, encoding="utf-8")
    result = cli_runner.invoke(app, ["ingest", str(docs)])
    assert result.exit_code == 0, result.stdout
    return tmp_ks_root


@pytest.fixture()
def pending_item(cli_runner: CliRunner, small_kb: Path) -> str:
    result = cli_runner.invoke(app, ["query", "ledger close", "--writeback=yes"])
    assert result.exit_code == 0, result.stdout
    step = _writeback_step(_payload(result))
    assert step["status"] == "enqueued"
    return str(step["id"])


def _approved_log_entries(ks_root: Path) -> int:
    return (ks_root / "wiki" / "log.md").read_text(encoding="utf-8").count(
        "| writeback | approved"
    )


# --- 021：--writeback=no 什麼都不寫 -------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("arguments", [["--writeback=no"], []], ids=["explicit-no", "default"])
def test_writeback_no_writes_neither_queue_nor_log(
    cli_runner: CliRunner, small_kb: Path, arguments: list[str]
) -> None:
    before = _tree(small_kb)

    result = cli_runner.invoke(app, ["query", "ledger close", *arguments])

    assert result.exit_code == 0, result.stdout
    payload = _payload(result)
    assert payload["source"] != []
    assert _writeback_step(payload) == {"status": "declined"}
    assert not (small_kb / "writeback").exists()
    assert _tree(small_kb) == before


# --- 026：被 evidence gate 擋下的答案不會入隊 ------------------------------------------


@pytest.fixture()
def with_similarity(monkeypatch: pytest.MonkeyPatch):
    """Pin what the embedding reports for the nearest chunks (as the 026 contract test does)."""
    real = query_module.collect_vector_candidates
    wanted: dict[str, float] = {}

    def patched(question: str, **arguments: Any):  # type: ignore[no-untyped-def]
        candidates, steps = real(question, **arguments)
        for index, candidate in enumerate(candidates):
            similarity = wanted["similarity"] - index * 0.01
            candidate.metadata["vector_similarity"] = similarity
            candidate.metadata["lexical_overlap"] = 0
            candidate.metadata["final_score"] = similarity
            candidates[index] = Candidate(
                text=candidate.text,
                source_route="vector",
                score=similarity,
                metadata=candidate.metadata,
            )
        return candidates, steps

    monkeypatch.setattr(query_module, "collect_vector_candidates", patched)
    return lambda similarity: wanted.__setitem__("similarity", similarity)


@pytest.mark.integration
@pytest.mark.parametrize("flag", ["yes", "auto"])
def test_answer_refused_by_the_evidence_gate_is_never_enqueued(
    cli_runner: CliRunner, small_kb: Path, with_similarity, flag: str
) -> None:
    with_similarity(0.27)
    log_before = (small_kb / "wiki" / "log.md").read_bytes()

    result = cli_runner.invoke(app, ["query", "量子電腦採購計畫", f"--writeback={flag}"])

    assert result.exit_code == 0, result.stdout
    payload = _payload(result)
    fallback = [s["detail"] for s in payload["trace"]["steps"] if s["kind"] == "fallback"]
    assert [item["reason"] for item in fallback] == ["weak_evidence"]
    assert payload["source"] == []
    assert _writeback_step(payload) == {"status": "skip-no-source"}
    assert _queue_files(small_kb) == []
    assert (small_kb / "wiki" / "log.md").read_bytes() == log_before


@pytest.mark.integration
def test_answer_that_passes_the_evidence_gate_is_enqueued_with_its_evidence(
    cli_runner: CliRunner, small_kb: Path, with_similarity
) -> None:
    with_similarity(0.36)

    result = cli_runner.invoke(app, ["query", "量子電腦採購計畫", "--writeback=yes"])

    assert result.exit_code == 0, result.stdout
    payload = _payload(result)
    assert payload["source"] == ["vector"]
    # 0.36 過得了 evidence gate，但不到 vector 的 auto 門檻：yes 仍可送審，eligible 為 false。
    assert payload["writeback_eligible"] is False
    assert _writeback_step(payload)["status"] == "enqueued"
    [queue_file] = _queue_files(small_kb)
    item = json.loads(queue_file.read_text(encoding="utf-8"))
    assert item["writeback_eligible"] is False
    assert item["evidence"] == payload["evidence"]
    assert any("threshold" in reason for reason in item["reasons"])


@pytest.mark.integration
def test_auto_does_not_enqueue_an_answer_below_the_auto_threshold(
    cli_runner: CliRunner, small_kb: Path, with_similarity
) -> None:
    with_similarity(0.36)

    result = cli_runner.invoke(app, ["query", "量子電腦採購計畫", "--writeback=auto"])

    assert result.exit_code == 0, result.stdout
    payload = _payload(result)
    assert payload["source"] == ["vector"]
    assert _writeback_step(payload) == {"status": "auto-skipped-ineligible"}
    assert _queue_files(small_kb) == []


@pytest.mark.integration
def test_auto_enqueues_an_eligible_vector_answer(
    cli_runner: CliRunner, small_kb: Path, with_similarity
) -> None:
    with_similarity(0.9)

    result = cli_runner.invoke(app, ["query", "ledger close", "--writeback=auto"])

    assert result.exit_code == 0, result.stdout
    payload = _payload(result)
    assert payload["source"] == ["vector"] and payload["writeback_eligible"] is True
    assert _writeback_step(payload)["status"] == "enqueued"
    assert len(_queue_files(small_kb)) == 1
    assert list((small_kb / "wiki" / "pages").glob("*ledger-close*")) == []


# --- PR #26：approve 跨執行緒 / 跨行程只寫一次 wiki -------------------------------------


@pytest.mark.integration
def test_concurrent_approve_from_threads_writes_the_wiki_once(
    small_kb: Path, pending_item: str
) -> None:
    workers = 8
    barrier = threading.Barrier(workers)
    approved: list[str] = []
    refused: list[KSError] = []
    unexpected: list[BaseException] = []

    def approve() -> None:
        barrier.wait(timeout=10)
        try:
            response = writeback_command.run_approve(pending_item)
        except KSError as error:
            refused.append(error)
        except BaseException as error:  # noqa: BLE001 - reported by the assertion below
            unexpected.append(error)
        else:
            approved.append(response.answer)

    threads = [threading.Thread(target=approve) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert unexpected == []
    assert len(approved) == 1
    assert len(refused) == workers - 1
    assert {error.exit_code for error in refused} == {ExitCode.NOINPUT}
    assert all("已決議" in error.message for error in refused)
    assert _approved_log_entries(small_kb) == 1
    assert _queue_files(small_kb) == []
    [archived] = _archive_files(small_kb)
    slug = json.loads(archived.read_text(encoding="utf-8"))["slug"]
    assert (small_kb / "wiki" / "pages" / f"{slug}.md").is_file()
    index = (small_kb / "wiki" / "index.md").read_text(encoding="utf-8")
    assert index.count(f"(pages/{slug}.md)") == 1


@pytest.mark.integration
def test_concurrent_approve_from_processes_writes_the_wiki_once(
    small_kb: Path, pending_item: str
) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(PROJECT_ROOT / "src"), env.get("PYTHONPATH", "")) if part
    )
    command = [
        sys.executable,
        "-c",
        "from hks.cli import app; app()",
        "writeback",
        "approve",
        pending_item,
    ]
    processes = [
        subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(4)
    ]
    outcomes = [(process.communicate(timeout=120), process.returncode) for process in processes]

    codes = sorted(code for _, code in outcomes)
    assert codes == [0, 66, 66, 66], [stderr for (_, stderr), _ in outcomes]
    assert _approved_log_entries(small_kb) == 1
    assert _queue_files(small_kb) == []
    assert len(_archive_files(small_kb)) == 1
    # atomic_write 不留暫存檔在 queue / archive / wiki。
    leftovers = [
        path.name
        for folder in ("writeback/queue", "writeback/archive", "wiki/pages")
        for path in (small_kb / folder).iterdir()
        if path.name.endswith(".tmp")
    ]
    assert leftovers == []


@pytest.mark.integration
def test_approve_and_reject_racing_on_one_item_decide_it_once(
    small_kb: Path, pending_item: str
) -> None:
    barrier = threading.Barrier(2)
    done: list[str] = []
    refused: list[KSError] = []

    def decide(name: str) -> None:
        handler = (
            writeback_command.run_approve if name == "approve" else writeback_command.run_reject
        )
        barrier.wait(timeout=10)
        try:
            handler(pending_item)
        except KSError as error:
            refused.append(error)
        else:
            done.append(name)

    threads = [threading.Thread(target=decide, args=(name,)) for name in ("approve", "reject")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(done) == 1 and len(refused) == 1
    [archived] = _archive_files(small_kb)
    status = json.loads(archived.read_text(encoding="utf-8"))["status"]
    assert status == ("approved" if done == ["approve"] else "rejected")
    assert _approved_log_entries(small_kb) == (1 if done == ["approve"] else 0)


# --- PR #32：workspace-scoped enqueue 與 queue 管理 -----------------------------------


@pytest.mark.integration
def test_workspace_scoped_enqueue_lands_in_the_workspace_kb(
    cli_runner: CliRunner, tmp_path: Path, tmp_ks_root: Path
) -> None:
    registry = tmp_path / "registry" / "workspaces.json"
    workspace_root = tmp_path / "workspaces" / "ws-ledger" / "ks"
    workspace_root.mkdir(parents=True)
    register_workspace("ws-ledger", ks_root=workspace_root, registry_path_value=registry)
    docs = tmp_path / "ws-docs"
    docs.mkdir()
    (docs / "ledger.md").write_text(DOCS["ledger.md"], encoding="utf-8")
    scope = ["-w", "ws-ledger", "--registry-path", str(registry)]
    assert cli_runner.invoke(app, ["ingest", str(docs), *scope]).exit_code == 0

    queried = cli_runner.invoke(app, ["query", "ledger close", "--writeback=yes", *scope])

    assert queried.exit_code == 0, queried.stdout
    item_id = str(_writeback_step(_payload(queried))["id"])
    assert [path.stem for path in _queue_files(workspace_root)] == [item_id]
    # 預設 KS_ROOT（這裡是 tmp_ks_root）完全沒被碰到。
    assert not tmp_ks_root.exists()

    unscoped = cli_runner.invoke(app, ["writeback", "list"])
    assert _payload(unscoped)["trace"]["steps"][0]["detail"]["items"] == []

    listed = cli_runner.invoke(app, ["writeback", "list", *scope])
    assert listed.exit_code == 0, listed.stdout
    items = _payload(listed)["trace"]["steps"][0]["detail"]["items"]
    assert [item["id"] for item in items] == [item_id]

    shown = cli_runner.invoke(app, ["writeback", "show", item_id, *scope])
    assert shown.exit_code == 0, shown.stdout

    approved = cli_runner.invoke(app, ["writeback", "approve", item_id, *scope])
    assert approved.exit_code == 0, approved.stdout
    slug = _payload(approved)["trace"]["steps"][0]["detail"]["slug"]
    page = (workspace_root / "wiki" / "pages" / f"{slug}.md").read_text(encoding="utf-8")
    assert 'source: "ledger.md"' in page
    assert "monthly ledger close moved to the third working day" in page
    assert [path.stem for path in _archive_files(workspace_root)] == [item_id]
    assert not tmp_ks_root.exists()

    by_root = cli_runner.invoke(app, ["writeback", "list", "--ks-root", str(workspace_root)])
    assert _payload(by_root)["trace"]["steps"][0]["detail"]["items"] == []


@pytest.mark.integration
def test_writeback_commands_reject_unknown_workspace_and_conflicting_scope(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    registry = tmp_path / "registry" / "workspaces.json"

    unknown = cli_runner.invoke(
        app, ["writeback", "list", "-w", "nope", "--registry-path", str(registry)]
    )
    assert unknown.exit_code != 0
    assert _payload(unknown)["trace"]["steps"][0]["kind"] == "error"

    both = cli_runner.invoke(
        app, ["writeback", "list", "-w", "nope", "--ks-root", str(tmp_path / "ks")]
    )
    assert both.exit_code == int(ExitCode.USAGE)


# --- 會列舉 KS root 的指令不被 writeback/ 目錄影響 --------------------------------------


@pytest.mark.integration
def test_lint_and_reingest_are_unaffected_by_the_queue_directory(
    cli_runner: CliRunner, small_kb: Path, pending_item: str, tmp_path: Path
) -> None:
    clean = cli_runner.invoke(app, ["lint"])
    baseline = _payload(clean)["trace"]["steps"][0]["detail"]["severity_counts"]

    approved = cli_runner.invoke(app, ["writeback", "approve", pending_item])
    assert approved.exit_code == 0, approved.stdout
    second = cli_runner.invoke(app, ["query", "cold archive retrieval", "--writeback=yes"])
    assert _writeback_step(_payload(second))["status"] == "enqueued"

    linted = cli_runner.invoke(app, ["lint"])
    assert linted.exit_code == clean.exit_code, linted.stdout
    assert _payload(linted)["trace"]["steps"][0]["detail"]["severity_counts"] == baseline

    reingested = cli_runner.invoke(app, ["ingest", str(tmp_path / "docs"), "--prune"])
    assert reingested.exit_code == 0, reingested.stdout
    assert len(_queue_files(small_kb)) == 1
    assert len(_archive_files(small_kb)) == 1
    slug = _payload(approved)["trace"]["steps"][0]["detail"]["slug"]
    assert (small_kb / "wiki" / "pages" / f"{slug}.md").is_file()
    assert runtime_paths().root == small_kb


# --- approve 之後：同一問句不再入隊、writeback 頁不會自我衍生 ----------------------------


def _ask(cli_runner: CliRunner, question: str, flag: str = "yes") -> dict[str, Any]:
    result = cli_runner.invoke(app, ["query", question, f"--writeback={flag}"])
    assert result.exit_code == 0, result.stdout
    return _payload(result)


@pytest.mark.integration
def test_requery_after_approve_reports_already_promoted_and_enqueues_nothing(
    cli_runner: CliRunner, small_kb: Path
) -> None:
    question = "Ledger summary"
    first = _ask(cli_runner, question)
    assert first["source"] == ["wiki"]
    item_id = str(_writeback_step(first)["id"])
    approved = cli_runner.invoke(app, ["writeback", "approve", item_id])
    assert approved.exit_code == 0, approved.stdout
    slug = _payload(approved)["trace"]["steps"][0]["detail"]["slug"]
    log_before = (small_kb / "wiki" / "log.md").read_bytes()

    payload = _ask(cli_runner, question)

    # 答案現在來自剛寫入的 writeback 頁：文字不同、id 也不同，但不是新知識。
    assert payload["source"] == ["wiki"]
    assert payload["answer"] != first["answer"]
    assert _writeback_step(payload) == {
        "status": "already-promoted",
        "slug": slug,
        "path": f"pages/{slug}.md",
        "source_relpath": "ledger.md",
    }
    assert _queue_files(small_kb) == []
    assert len(_archive_files(small_kb)) == 1
    assert (small_kb / "wiki" / "log.md").read_bytes() == log_before

    # --writeback=no 仍只回 declined，不做這項檢查。
    assert _writeback_step(_ask(cli_runner, question, "no")) == {"status": "declined"}


@pytest.mark.integration
def test_requery_with_the_same_answer_is_still_deduped_by_id(
    cli_runner: CliRunner, small_kb: Path, pending_item: str
) -> None:
    assert cli_runner.invoke(app, ["writeback", "approve", pending_item]).exit_code == 0

    payload = _ask(cli_runner, "ledger close")

    assert payload["source"] == ["vector"]
    step = _writeback_step(payload)
    assert step["status"] == "already-promoted" and step["id"] == pending_item
    assert _queue_files(small_kb) == []


@pytest.mark.integration
def test_another_question_answered_by_a_writeback_page_is_not_enqueued(
    small_kb: Path, pending_item: str
) -> None:
    from hks.core.schema import QueryResponse, Trace
    from hks.storage.wiki import WikiStore

    writeback_command.run_approve(pending_item)
    store = WikiStore(runtime_paths())
    [page] = [page for page in store.list_pages() if page.origin == "writeback"]
    response = QueryResponse(
        answer=f"{page.title}: {page.summary}",
        source=["wiki"],
        confidence=0.9,
        trace=Trace(route="wiki", steps=[]),
        evidence=[
            {"source_relpath": page.source_relpath, "route": "wiki", "quote": page.summary}
        ],
        retrieval_score=0.9,
        writeback_eligible=False,
    )

    result = query_module._maybe_enqueue(
        question="when does the ledger close move",
        response=response,
        writeback="yes",
        wiki_store=store,
    )

    assert _writeback_step(result.to_dict()) == {
        "status": "skipped-derived-answer",
        "slug": page.slug,
        "path": f"pages/{page.slug}.md",
        "source_relpath": "ledger.md",
    }
    assert _queue_files(small_kb) == []


# --- source 被移除時，引用它的 writeback 頁一起移除 -------------------------------------


def _approve(cli_runner: CliRunner, question: str) -> str:
    step = _writeback_step(_ask(cli_runner, question))
    assert step["status"] == "enqueued", step
    approved = cli_runner.invoke(app, ["writeback", "approve", str(step["id"])])
    assert approved.exit_code == 0, approved.stdout
    return str(_payload(approved)["trace"]["steps"][0]["detail"]["slug"])


@pytest.mark.integration
def test_prune_removes_the_writeback_pages_of_a_removed_source_only(
    cli_runner: CliRunner, small_kb: Path, tmp_path: Path
) -> None:
    ledger_slug = _approve(cli_runner, "ledger close")
    storage_slug = _approve(cli_runner, "cold archive retrieval")
    pages = small_kb / "wiki" / "pages"
    assert 'source: "ledger.md"' in (pages / f"{ledger_slug}.md").read_text(encoding="utf-8")
    assert 'source: "storage.md"' in (pages / f"{storage_slug}.md").read_text(encoding="utf-8")

    (tmp_path / "docs" / "ledger.md").unlink()
    pruned = cli_runner.invoke(app, ["ingest", str(tmp_path / "docs"), "--prune"])

    assert pruned.exit_code == 0, pruned.stdout
    detail = _payload(pruned)["trace"]["steps"][0]["detail"]
    assert detail["pruned"] == ["ledger.md"]
    assert detail["pruned_writeback_pages"] == [f"pages/{ledger_slug}.md"]
    assert not (pages / f"{ledger_slug}.md").exists()
    assert (pages / f"{storage_slug}.md").is_file()
    index = (small_kb / "wiki" / "index.md").read_text(encoding="utf-8")
    assert f"(pages/{ledger_slug}.md)" not in index
    assert f"(pages/{storage_slug}.md)" in index

    # 被移除的來源不再被回答；audit 用的 archive 紀錄保留。
    after = _ask(cli_runner, "ledger close", "no")
    assert all(item["source_relpath"] != "ledger.md" for item in after.get("evidence", []))
    assert len(_archive_files(small_kb)) == 2
    linted = cli_runner.invoke(app, ["lint"])
    assert _payload(linted)["trace"]["steps"][0]["detail"]["findings"] == []


@pytest.mark.integration
def test_ingest_without_prune_reports_no_writeback_pages_removed(
    cli_runner: CliRunner, small_kb: Path, tmp_path: Path
) -> None:
    slug = _approve(cli_runner, "ledger close")

    again = cli_runner.invoke(app, ["ingest", str(tmp_path / "docs")])

    detail = _payload(again)["trace"]["steps"][0]["detail"]
    assert detail["pruned"] == [] and detail["pruned_writeback_pages"] == []
    assert (small_kb / "wiki" / "pages" / f"{slug}.md").is_file()


@pytest.mark.integration
def test_lint_reports_a_writeback_page_whose_source_is_no_longer_ingested(
    cli_runner: CliRunner, small_kb: Path
) -> None:
    slug = _approve(cli_runner, "ledger close")
    manifest_path = small_kb / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest["entries"]
    removed = entries.pop("ledger.md")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert removed

    linted = cli_runner.invoke(app, ["lint"])

    findings = _payload(linted)["trace"]["steps"][0]["detail"]["findings"]
    mismatches = [item for item in findings if item["category"] == "wiki_source_mismatch"]
    assert slug in {item["target"] for item in mismatches}

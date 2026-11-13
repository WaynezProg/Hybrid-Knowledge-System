# ruff: noqa: E501 - the question and fact table reads better one row per line
"""Compare keyword-retrieval modes on a synthetic corpus.

    uv run python evals/hybrid_modes.py            # uses HKS_EMBEDDING_MODEL (default model)
    HKS_EMBEDDING_MODEL=simple uv run python evals/hybrid_modes.py

Modes (``HKS_HYBRID_SEARCH``): ``off`` dense only, ``fused`` BM25 joins the dense ranking
inside the vector route, ``route`` keyword matches are a route of their own.

Reported per mode and question kind:
- answer@1: the answer's evidence names the expected source (end to end, all routes);
- recall@5: the expected source is among the vector + lexical candidates;
- no-hit: questions with no answer in the corpus that correctly return nothing.
"""

from __future__ import annotations

import json
import os
import random
import sys
import tempfile
from pathlib import Path

ALL_MODES = ("off", "fused", "route")
# HKS_EVAL_MODES=route,fused limits the run to some modes.
MODES = tuple(
    mode
    for mode in os.environ.get("HKS_EVAL_MODES", ",".join(ALL_MODES)).split(",")
    if mode in ALL_MODES
)

TOPICS = [
    ("billing", "invoice reconciliation and the monthly ledger close"),
    ("search", "index rebuilds and query latency on the catalog cluster"),
    ("mobile", "the release train for the handheld client and crash triage"),
    ("identity", "sign-in flows, session expiry and account recovery"),
    ("storage", "bucket lifecycle rules and cold archive retrieval"),
    ("analytics", "dashboard freshness and the nightly aggregation job"),
    ("network", "edge routing, peering changes and packet loss reports"),
    ("support", "the escalation queue and customer reply templates"),
]
FILLER = [
    "The team reviewed open items and agreed on owners for each follow-up.",
    "Nothing unusual was reported during the weekly sync on this topic.",
    "Routine maintenance continued and the usual checks were completed.",
    "Planning notes were updated after the review with minor wording changes.",
    "A reminder was sent about documentation and the handoff checklist.",
]
# (kind, question, fact sentence placed in exactly one document)
FACTS = [
    ("identifier", "ERR-4012 怎麼修", "Ticket ERR-4012 was resolved by rotating the gateway token."),
    ("identifier", "What is CVE-2031-7781 about?", "CVE-2031-7781 affects the image resize worker."),
    ("identifier", "INC-90217", "Incident INC-90217 was caused by an expired wildcard certificate."),
    ("identifier", "who owns svc-ledger-sync", "The service svc-ledger-sync is owned by Priya Raman."),
    ("identifier", "migrate_0417_drop_legacy.sql", "The file migrate_0417_drop_legacy.sql removes old tables."),
    ("identifier", "PO-88341 的金額", "Purchase order PO-88341 totals 48,200 for spare drives."),
    ("identifier", "RFC-0193 decision", "RFC-0193 was accepted: adopt idempotency keys on writes."),
    ("identifier", "flag enable_shadow_reads", "The flag enable_shadow_reads stays off until the audit ends."),
    ("identifier", "build 7.14.3-rc2 status", "Build 7.14.3-rc2 was withdrawn after a startup regression."),
    ("identifier", "KB-55120", "Article KB-55120 explains how to reset a locked hardware key."),
    ("keyword", "供應商交期延遲的處理方式", "供應商交期延遲時，改由備援倉庫出貨並通知採購。"),
    ("keyword", "夜間彙總工作失敗後怎麼重跑", "夜間彙總工作失敗後，需先清除暫存分區再手動重跑。"),
    ("keyword", "冷儲存取回要多久", "冷儲存取回通常需要十二小時，急件可申請加速。"),
    ("keyword", "who approves peering changes", "Peering changes are approved by the network duty lead."),
    ("keyword", "crash triage rotation schedule", "Crash triage rotation changes every Tuesday at noon."),
    ("paraphrase", "How long do we keep customer chat logs?", "Support conversation transcripts are retained for 400 days."),
    ("paraphrase", "What happens when someone forgets their password too many times?", "After five failed sign-in attempts the account is locked for an hour."),
    ("paraphrase", "Why were dashboards showing stale numbers?", "Reports lagged because the aggregation job ran on an outdated snapshot."),
    ("paraphrase", "付款對不上帳時要找誰", "發票與帳本不符時，請聯絡財務對帳窗口林雅婷。"),
    ("paraphrase", "手機版當機要怎麼回報", "手持裝置用戶端閃退時，請附上日誌並開立缺陷單。"),
]
NO_ANSWER = [
    "ERR-9999 怎麼修",
    "What is the vacation policy for contractors?",
    "INC-00001",
    "量子電腦採購計畫",
]


def build_corpus(target: Path, *, documents: int, seed: int) -> dict[str, str]:
    """Write the corpus; returns question -> file that holds its answer."""
    rng = random.Random(seed)
    target.mkdir(parents=True)
    holders = rng.sample(range(documents), len(FACTS))
    answers: dict[str, str] = {}
    for index in range(documents):
        topic, about = TOPICS[index % len(TOPICS)]
        lines = [f"# {topic.title()} note {index:03d}", "", f"This note covers {about}."]
        lines += rng.sample(FILLER, 3)
        if index in holders:
            _, question, fact = FACTS[holders.index(index)]
            lines.insert(rng.randint(3, len(lines)), fact)
            answers[question] = f"{topic}-{index:03d}.md"
        lines += rng.sample(FILLER, 2)
        (target / f"{topic}-{index:03d}.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    return answers


def evaluate(mode: str, answers: dict[str, str]) -> dict[str, dict[str, list[int]]]:
    os.environ["HKS_HYBRID_SEARCH"] = mode
    from hks.commands.query import run as query_run
    from hks.core.manifest import resume_or_rebuild
    from hks.core.paths import runtime_paths
    from hks.retrievers.lexical import collect_lexical_candidates
    from hks.retrievers.vector import collect_vector_candidates
    from hks.storage.vector import VectorStore

    paths = runtime_paths()
    manifest = resume_or_rebuild(paths)
    store = VectorStore(paths)
    results: dict[str, dict[str, list[int]]] = {}

    def record(kind: str, metric: str, hit: bool) -> None:
        results.setdefault(kind, {}).setdefault(metric, []).append(int(hit))

    for kind, question, _ in FACTS:
        expected = answers[question]
        payload = query_run(question, writeback="no").to_dict()
        cited = {item.get("source_relpath") for item in payload.get("evidence", [])}
        record(kind, "answer@1", expected in cited)
        pool, _ = collect_vector_candidates(question, vector_store=store, manifest=manifest)
        extra, _ = collect_lexical_candidates(question, vector_store=store, manifest=manifest)
        found = {candidate.metadata.get("source_relpath") for candidate in [*pool, *extra]}
        record(kind, "recall@5", expected in found)
    for question in NO_ANSWER:
        payload = query_run(question, writeback="no").to_dict()
        record("no-answer", "no-hit", not payload.get("source"))
    return results


def main() -> int:
    documents = int(os.environ.get("HKS_EVAL_DOCUMENTS", "240"))
    seeds = [int(value) for value in os.environ.get("HKS_EVAL_SEEDS", "1,2,3").split(",")]
    os.environ.setdefault("HKS_LLM_NETWORK_OPT_IN", "0")
    totals: dict[str, dict[str, dict[str, list[int]]]] = {mode: {} for mode in MODES}
    for seed in seeds:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            os.environ["KS_ROOT"] = str(root / "ks")
            os.environ["HKS_CONFIG_FILE"] = str(root / "missing.yaml")
            os.environ["HKS_CONFIG_ENV"] = str(root / "missing.env")
            answers = build_corpus(root / "docs", documents=documents, seed=seed)
            from typer.testing import CliRunner

            from hks.cli import app

            ingest = CliRunner().invoke(app, ["ingest", str(root / "docs")])
            if ingest.exit_code != 0:
                print(ingest.output, file=sys.stderr)
                return 1
            for mode in MODES:
                for kind, metrics in evaluate(mode, answers).items():
                    for metric, hits in metrics.items():
                        totals[mode].setdefault(kind, {}).setdefault(metric, []).extend(hits)

    model = os.environ.get("HKS_EMBEDDING_MODEL", "(default)")
    print(f"embedding={model} documents={documents} seeds={seeds}")
    summary: dict[str, dict[str, str]] = {}
    for mode in MODES:
        for kind, metrics in totals[mode].items():
            for metric, hits in metrics.items():
                summary.setdefault(f"{kind} {metric}", {})[mode] = f"{sum(hits)}/{len(hits)}"
    width = max(len(name) for name in summary)
    print(f"{'':<{width}}  " + "  ".join(f"{mode:>7}" for mode in MODES))
    for name, row in summary.items():
        print(f"{name:<{width}}  " + "  ".join(f"{row.get(mode, '-'):>7}" for mode in MODES))
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

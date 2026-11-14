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
# HKS_EVAL_EXTRA=1 adds the cases below, taken from questions that went wrong on real
# knowledge bases. They are placed without disturbing the base corpus's random draws, but
# they add sentences to it, so base numbers are only comparable with the same setting.
EXTRA = os.environ.get("HKS_EVAL_EXTRA", "") not in {"", "0"}
EXTRA_FACTS = [
    # a code inside a sentence whose other words are in no document
    ("code-in-sentence", "VID-236 的畫面是用來決定什麼", "逐句 delta 稿第 3 段的 A／B 版依 VID-236 畫面選。"),
    ("code-in-sentence", "PO-77120 這張單後來怎麼處理", "Purchase order PO-77120 was cancelled after the vendor missed two deadlines."),
    ("code-in-sentence", "請問 KB-41007 這篇文章在講什麼內容呢", "Article KB-41007 covers rotating the signing keys."),
    ("code-in-sentence", "tell me everything you know regarding INC-30558 please", "事件 INC-30558 起因於排程器重複派工。"),
    # the same code written another way
    ("code-spelling", "VID412 的進度", "VID-412 已完成初剪，等待配音。"),
    ("code-spelling", "what is RFC0207", "RFC-0207 proposes a shared retry budget for the gateway."),
    ("code-spelling", "svc-07 owner", "The service svc07 is owned by Chen Wei."),
    ("code-spelling", "ERR_5120 怎麼修", "Ticket ERR-5120 was fixed by clearing the stale lock file."),
    # a code with a short number, next to content that has the same words apart
    ("short-code", "Atlas-10 對應哪一個 risk", "Atlas-10 對應 risk-10：測試資料尚未匿名化。"),
    ("short-code", "phase-2 的截止日", "phase-2 的截止日是六月十五日。"),
    ("short-code", "Lot-7 的檢驗結果", "Lot-7 的檢驗結果為合格，已放行出貨。"),
    # a name with a digit inside it; the answer does not repeat the name
    ("name-with-digit", "session2memory 的 reconcile 步驟做了哪些事", "reconcile 步驟會找出同一個 project 內互相矛盾或重複的記憶。"),
    ("name-with-digit", "k8s 叢集升級的順序", "叢集升級先動控制平面，再逐一輪替工作節點。"),
    ("name-with-digit", "i18n 字串要放在哪裡", "介面字串統一放在 locales 目錄，每個語系一個檔。"),
]
# Sentences that share words with a short-code fact without naming the code.
EXTRA_DISTRACTORS = [
    "Atlas 專案目前有 10 個主要風險，最大的是供應商交期延遲。",
    "各 phase 的規劃仍在討論，第 2 季會再確認時程。",
    "本月共檢驗 7 個 lot，結果彙整於週報。",
]
EXTRA_NO_ANSWER = [
    "VID999 的進度",
    "Atlas-99 對應哪一個 risk",
    "PO-00000 這張單後來怎麼處理",
    "phase-9 的截止日",
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
    pages: list[tuple[str, list[str]]] = []
    for index in range(documents):
        topic, about = TOPICS[index % len(TOPICS)]
        lines = [f"# {topic.title()} note {index:03d}", "", f"This note covers {about}."]
        lines += rng.sample(FILLER, 3)
        if index in holders:
            _, question, fact = FACTS[holders.index(index)]
            lines.insert(rng.randint(3, len(lines)), fact)
            answers[question] = f"{topic}-{index:03d}.md"
        lines += rng.sample(FILLER, 2)
        pages.append((f"{topic}-{index:03d}.md", lines))
    if EXTRA:
        # A generator of its own, and only documents that hold no base fact.
        extra_rng = random.Random(seed + 1000)
        free = [index for index in range(documents) if index not in holders]
        wanted = len(EXTRA_FACTS) + len(EXTRA_DISTRACTORS)
        if len(free) < wanted:
            raise SystemExit(
                f"HKS_EVAL_EXTRA needs at least {len(FACTS) + wanted} documents "
                f"(HKS_EVAL_DOCUMENTS={documents})"
            )
        spots = extra_rng.sample(free, wanted)
        for spot, (_, question, fact) in zip(spots, EXTRA_FACTS, strict=False):
            pages[spot][1].insert(3, fact)
            answers[question] = pages[spot][0]
        for spot, sentence in zip(spots[len(EXTRA_FACTS) :], EXTRA_DISTRACTORS, strict=True):
            pages[spot][1].insert(3, sentence)
    for name, lines in pages:
        (target / name).write_text("\n\n".join(lines) + "\n", encoding="utf-8")
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

    for kind, question, _ in [*FACTS, *(EXTRA_FACTS if EXTRA else [])]:
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
    for question in EXTRA_NO_ANSWER if EXTRA else []:
        payload = query_run(question, writeback="no").to_dict()
        record("no-answer-code", "no-hit", not payload.get("source"))
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
            # HKS_EVAL_CONFIG_FILE: a config file to take the embedding backend from (an
            # API-backed model needs its endpoint and key). KS_ROOT above still wins.
            os.environ["HKS_CONFIG_FILE"] = os.environ.get(
                "HKS_EVAL_CONFIG_FILE", str(root / "missing.yaml")
            )
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

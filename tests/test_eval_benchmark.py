"""Benchmark plumbing: test-split guard, metrics with N, baseline, env caching, spot-check (fixtures only)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest

from keepline.contracts import Action, Answer, QType, Question, Split
from keepline.eval.baseline import PlainSearchBaseline
from keepline.eval.benchmark import SplitGuardError, check_test_guard, log_test_run
from keepline.eval.metrics import cohen_kappa, reliability, summarize, wilson
from keepline.eval.spotcheck import score_spotcheck, stratified_sample, write_spotcheck
from keepline.rl.bandit import Arm
from keepline.rl.env import AnswerEnv
from keepline.rl.train import train


def test_test_split_guard(tmp_path: Path) -> None:
    check_test_guard("dev", False, lambda: False)  # dev is always allowed
    with pytest.raises(SplitGuardError):
        check_test_guard("test", False, lambda: True)
    with pytest.raises(SplitGuardError):
        check_test_guard("test", True, lambda: False)
    check_test_guard("test", True, lambda: True)
    log_path = tmp_path / "test_runs.log"
    log_test_run(["plain"], {"x": 1}, log_path)
    log_test_run(["plain"], {"x": 2}, log_path)
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 2


def _row(outcome: str, action: str, expected: str, qtype: str = "fact", conf: float = 0.5) -> dict:
    correct = outcome.startswith("correct")
    return {"qid": f"Q{outcome}{action}", "system": "s", "qtype": qtype, "area_id": "a", "expected_action": expected,
            "action": action, "outcome": outcome, "correct": correct, "citation_valid": outcome == "correct_cited",
            "reward": 1.0 if correct else -1.0, "confidence": conf}  # fmt: skip


def test_summarize_reports_n_everywhere() -> None:
    rows = [
        _row("correct_cited", "answer", "answer", conf=0.9),
        _row("hallucination", "answer", "abstain", "unanswerable", conf=0.8),
        _row("correct_abstain", "abstain", "abstain", "unanswerable", conf=0.1),
        _row("unnecessary_abstain", "abstain", "answer", conf=0.2),
        _row("stale_answer", "answer", "answer", "current", conf=0.7),
    ]
    m = summarize(rows)
    assert m["accuracy_cited"] == {"value": pytest.approx(1 / 3, abs=1e-4), "k": 1, "n": 3, "ci95": wilson(1, 3)}
    assert m["hallucination_rate"]["k"] == 2 and m["hallucination_rate"]["n"] == 3
    assert m["abstain_precision"]["value"] == 0.5 and m["abstain_precision"]["n"] == 2
    assert m["abstain_recall"]["value"] == 0.5 and m["abstain_recall"]["n"] == 2  # the bluff counts as a miss
    assert m["stale_rate"]["value"] == 1.0 and m["current_fact_accuracy"]["value"] == 0.0
    assert m["routing_accuracy"]["n"] == 0 and m["routing_accuracy"]["value"] is None
    assert m["ece"]["n"] == 3
    assert m["by_qtype"]["unanswerable"]["n"] == 2


def test_reliability_and_kappa() -> None:
    ece, bins = reliability([_row("correct_cited", "answer", "answer", conf=1.0)] * 4)
    assert ece["value"] == 0.0 and bins[-1]["n"] == 4
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0
    assert cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0]) == 0.0
    assert wilson(0, 10)[0] == 0.0 and wilson(0, 0) is None


@dataclass
class FakeHit:
    doc_id: str
    fact_id: str | None
    score: float
    text: str
    source_type: str
    timestamp: datetime


class FakeIndex:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, query: str, **kw) -> list[FakeHit]:  # noqa: ANN003
        self.calls.append(kw)
        return [FakeHit("slack-1", None, 6.0, "skip the 1st", "slack", datetime(2026, 3, 1)),
                FakeHit("doc-2", None, 2.0, "other", "doc", datetime(2026, 3, 2))]  # fmt: skip


def test_plain_baseline_always_answers_and_cites() -> None:
    idx = FakeIndex()
    a = PlainSearchBaseline(idx).answer("what does recon skip?", "alex", as_of=date(2026, 9, 1))
    assert a.action == Action.ANSWER and a.said[0].doc_id == "slack-1" and a.text == "skip the 1st"
    assert 0 < a.confidence < 1
    assert idx.calls[0]["visible_to"] == "alex" and idx.calls[0]["as_of"] == date(2026, 9, 1)


class FakeAgent:
    """Answers correctly only when retrieval depth k >= 6; abstains otherwise."""

    def __init__(self) -> None:
        self.n_calls = 0

    def classify_area(self, question: str) -> str | None:
        return "recon"

    def context_features(self, question: str, asker_id: str, *, as_of=None) -> dict[str, float]:  # noqa: ANN001
        return {"n_hits": 3.0}

    def answer(self, question: str, asker_id: str, *, as_of=None, params=None) -> Answer:  # noqa: ANN001
        self.n_calls += 1
        if params is not None and params.k >= 6:
            return Answer(question, Action.ANSWER, "the 1st", confidence=0.9)
        return Answer(question, Action.ABSTAIN, "I don't know", confidence=0.2)


def _questions(n: int, split: Split) -> list[Question]:
    return [Question(f"{split}{i}", split, "what does recon skip?", "alex", date(2026, 9, 1), QType.FACT, "recon",
                     Action.ANSWER, gold_answer_keywords=[["1st"]]) for i in range(n)]  # fmt: skip


def test_env_caches_and_train_runs(tmp_path: Path) -> None:
    agent = FakeAgent()
    cache = tmp_path / "arm_cache.json"
    arms = [Arm(3, 0.35, 0.1), Arm(6, 0.35, 0.1)]
    env = AnswerEnv(agent, {}, {}, cache_path=cache, fingerprint="fp")
    bandit, curve, _ = train(env, _questions(20, Split.TRAIN), _questions(6, Split.DEV), arms=arms, epochs=3,
                          seed=1, alpha_grid=(0.1, 1.0))  # fmt: skip
    assert bandit["dev"]["bandit"] == pytest.approx(bandit["dev"]["oracle"])
    assert bandit["per_area"]["recon"]["arm"] == arms[1].key
    assert sum(v["pulls"] for v in bandit["arm_stats"].values()) == curve["steps"]
    assert curve["steps"] == 60 and set(curve["rolling"]) == {"bandit", "default", "best_fixed", "random", "oracle"}
    calls = agent.n_calls
    env2 = AnswerEnv(agent, {}, {}, cache_path=cache, fingerprint="fp")
    assert np.all(env2.reward_matrix(_questions(20, Split.TRAIN), arms) == env.reward_matrix(_questions(20, Split.TRAIN), arms))
    assert agent.n_calls == calls  # served from disk cache
    AnswerEnv(agent, {}, {}, cache_path=cache, fingerprint="new").answer(_questions(1, Split.TRAIN)[0], arms[0])
    assert agent.n_calls == calls + 1  # fingerprint change invalidates


def test_spotcheck_roundtrip(tmp_path: Path) -> None:
    rows = [dict(_row(o, "answer", "answer"), qid=f"Q{i}", question="q", answer="a", citations=[], route_to=[])
            for i, o in enumerate(["correct_cited"] * 40 + ["stale_answer"] * 3)]  # fmt: skip
    sample = stratified_sample(rows, 10, seed=1)
    assert sum(r["outcome"] == "stale_answer" for r in sample) == 3  # rare outcome fully represented
    path = tmp_path / "spot.csv"
    assert write_spotcheck(rows, path, n=10) == 10
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields, graded = reader.fieldnames, list(reader)
    for i, r in enumerate(graded):
        r["human_grade"] = r["auto_correct"] if i else str(1 - int(r["auto_correct"]))  # one disagreement
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(graded)
    res = score_spotcheck(path)
    assert res["n"] == 10 and res["agreement"]["k"] == 9 and len(res["disagreements"]) == 1
    with pytest.raises(SystemExit):
        write_spotcheck(rows, path, n=10)  # refuses to clobber human grades

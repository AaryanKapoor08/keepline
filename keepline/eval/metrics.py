"""Benchmark metrics over graded rows. Every metric carries its N (and a 95% interval for proportions).

A *row* is one (system, question) result as produced by ``keepline.eval.benchmark.make_row``; the fields used
here are: ``qtype, area_id, expected_action, action, outcome, correct, citation_valid, reward, confidence``.

Definitions (stated so a judge can check them):

* ``accuracy_cited``      = correct_cited / questions whose expected action is ANSWER
* ``correct_action_rate`` = graded-correct / all questions (abstain/route count when they were right)
* ``hallucination_rate``  = (hallucination + stale_answer) / questions the system chose to ANSWER
* ``abstain_precision``   = right declines / all declines (decline = action ABSTAIN or ROUTE)
* ``abstain_recall``      = right declines / questions where declining was expected (expected ABSTAIN/ROUTE)
* ``current_fact_accuracy`` = correct / questions of qtype ``current`` (the fact was superseded)
* ``stale_rate``          = stale_answer / questions of qtype ``current``
* ``routing_accuracy``    = correct / questions of qtype ``routing``
* ``mean_reward``         = mean of ``keepline.rl.rewards.reward`` (N = all questions)
* ``ece``                 = expected calibration error of confidence vs correctness on ANSWERed questions
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from keepline.rl.rewards import Outcome

Row = Mapping[str, Any]
_DECLINE = {"abstain", "route"}
_RIGHT_DECLINE = {Outcome.CORRECT_ABSTAIN.value, Outcome.CORRECT_ROUTE.value}
_WRONG_ANSWER = {Outcome.HALLUCINATION.value, Outcome.STALE_ANSWER.value}


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """Wilson score interval: honest at small N and at 0% / 100%, unlike the normal approximation."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def proportion(k: int, n: int) -> dict[str, Any]:
    return {"value": round(k / n, 4) if n else None, "k": k, "n": n, "ci95": wilson(k, n)}


def mean_metric(xs: Sequence[float]) -> dict[str, Any]:
    n = len(xs)
    if n == 0:
        return {"value": None, "n": 0, "ci95": None}
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n)
    return {"value": round(m, 4), "n": n, "ci95": [round(m - half, 4), round(m + half, 4)]}


def reliability(rows: Iterable[Row], n_bins: int = 10) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """ECE over answered rows + per-bin (mean confidence, accuracy, n) for the reliability diagram."""
    answered = [r for r in rows if r["action"] == "answer"]
    bins: list[list[Row]] = [[] for _ in range(n_bins)]
    for r in answered:
        c = min(1.0, max(0.0, float(r["confidence"])))
        bins[min(n_bins - 1, int(c * n_bins))].append(r)
    out, ece = [], 0.0
    for i, b in enumerate(bins):
        if not b:
            out.append({"lo": i / n_bins, "hi": (i + 1) / n_bins, "n": 0, "confidence": None, "accuracy": None})
            continue
        conf = sum(float(r["confidence"]) for r in b) / len(b)
        acc = sum(bool(r["correct"]) for r in b) / len(b)
        ece += len(b) / len(answered) * abs(conf - acc)
        out.append({"lo": i / n_bins, "hi": (i + 1) / n_bins, "n": len(b),
                    "confidence": round(conf, 4), "accuracy": round(acc, 4)})  # fmt: skip
    return {"value": round(ece, 4) if answered else None, "n": len(answered)}, out


def _count(rows: Sequence[Row], pred) -> tuple[int, int]:  # noqa: ANN001
    return sum(1 for r in rows if pred(r)), len(rows)


def summarize(rows: Sequence[Row]) -> dict[str, Any]:
    """All headline metrics for one system."""
    expect_answer = [r for r in rows if r["expected_action"] == "answer"]
    answered = [r for r in rows if r["action"] == "answer"]
    declines = [r for r in rows if r["action"] in _DECLINE]
    expect_decline = [r for r in rows if r["expected_action"] in _DECLINE]
    current = [r for r in rows if r["qtype"] == "current"]
    routing = [r for r in rows if r["qtype"] == "routing"]
    ece, bins = reliability(rows)
    return {
        "n_questions": len(rows),
        "accuracy_cited": proportion(*_count(expect_answer, lambda r: r["outcome"] == "correct_cited")),
        "correct_action_rate": proportion(*_count(rows, lambda r: bool(r["correct"]))),
        "hallucination_rate": proportion(*_count(answered, lambda r: r["outcome"] in _WRONG_ANSWER)),
        "abstain_precision": proportion(*_count(declines, lambda r: r["outcome"] in _RIGHT_DECLINE)),
        "abstain_recall": proportion(*_count(expect_decline, lambda r: r["outcome"] in _RIGHT_DECLINE)),
        "current_fact_accuracy": proportion(*_count(current, lambda r: bool(r["correct"]))),
        "stale_rate": proportion(*_count(current, lambda r: r["outcome"] == "stale_answer")),
        "routing_accuracy": proportion(*_count(routing, lambda r: bool(r["correct"]))),
        "citation_valid_rate": proportion(*_count(answered, lambda r: bool(r["citation_valid"]))),
        "answer_rate": proportion(len(answered), len(rows)),
        "mean_reward": mean_metric([float(r["reward"]) for r in rows]),
        "ece": ece,
        "reliability_bins": bins,
        "outcomes": dict(Counter(r["outcome"] for r in rows).most_common()),
        "by_qtype": breakdown(rows, "qtype"),
        "by_area": breakdown(rows, "area_id"),
    }


def breakdown(rows: Sequence[Row], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(key) or "none")].append(r)
    out = {}
    for g, rs in sorted(groups.items()):
        answered = [r for r in rs if r["action"] == "answer"]
        out[g] = {
            "n": len(rs),
            "correct_rate": proportion(*_count(rs, lambda r: bool(r["correct"]))),
            "hallucination_rate": proportion(*_count(answered, lambda r: r["outcome"] in _WRONG_ANSWER)),
            "mean_reward": mean_metric([float(r["reward"]) for r in rs]),
            "outcomes": dict(Counter(r["outcome"] for r in rs).most_common()),
        }
    return out


def cohen_kappa(a: Sequence[Any], b: Sequence[Any]) -> float | None:
    """Agreement beyond chance between two raters over the same items."""
    n = len(a)
    if n == 0 or n != len(b):
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0

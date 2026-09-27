"""Fit a confidence calibrator: ``python -m keepline.rl.calibrate`` -> ``data/results/calibrator.json``.

Why: the agent's hand-set logistic confidence is poorly calibrated (dev ECE ~0.29; many answers at 0.98 that
are wrong), and the bandit's abstain threshold can only separate right from wrong answers as well as the
confidence ranks them. So we learn P(correct | the agent's own confidence inputs) from graded outcomes.

Protocol (no leakage):
* Data = TRAIN questions answered in *forced-answer mode* (abstain/route thresholds 0), label = the grader's
  verdict (1 = correct answer, 0 = hallucination/stale). Questions where the agent still routes are skipped:
  there is no answer to be right about.
* Features = the numeric inputs the agent exposes (``Answer.debug["features"]``, else ``context_features``)
  minus the agent's own ``confidence`` / ``formula_confidence`` (the output, and a redundant hand-set proxy;
  excluding them avoids a feedback loop once the agent uses this calibrator).
* L2 strength is chosen on DEV by log-loss; the final weights are fit on TRAIN only.
* Weights are reported on the *raw* feature scale so the agent applies ``sigmoid(bias + sum w_i * x_i)``.

Output::

    {"features": [names], "weights": {name: float}, "bias": float, "fitted_on": "train", "n": int, "l2": float,
     "dev": {"n", "log_loss", "brier", "ece", "log_loss_before", "brier_before", "ece_before"},
     "l2_grid": {l2: dev_log_loss}}
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from typing import Any

import numpy as np

from keepline.config import RESULTS_DIR
from keepline.contracts import Action, PolicyParams, Question
from keepline.eval.grader import grade

log = logging.getLogger(__name__)

CALIBRATOR_PATH = RESULTS_DIR / "calibrator.json"
L2_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)
EXCLUDE = {"confidence", "formula_confidence", "bias", "calibrated_confidence", "raw_confidence"}
FORCE_ANSWER = PolicyParams(abstain_threshold=0.0, route_threshold=0.0)


def collect(agent: Any, questions: Sequence[Question], world: Any) -> list[tuple[dict[str, float], float, int]]:
    """(features, agent confidence, label) for every question the agent answers in forced-answer mode."""
    out = []
    for q in questions:
        a = agent.answer(q.text, q.asker_id, as_of=q.as_of, params=FORCE_ANSWER)
        if a.action != Action.ANSWER:
            continue
        feats = (a.debug or {}).get("features") or agent.context_features(q.text, q.asker_id, as_of=q.as_of)
        g = grade(q, a, world.truth, world.ev, people=world.people)
        out.append(({k: float(v) for k, v in feats.items() if isinstance(v, (int, float))}, float(a.confidence),
                    int(g.correct)))  # fmt: skip
    return out


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float, iters: int = 50) -> tuple[np.ndarray, float]:
    """Newton-Raphson L2 logistic regression on standardised X (bias unpenalised). Deterministic."""
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(d + 1)
    reg = np.full(d + 1, l2)
    reg[0] = 0.0
    for _ in range(iters):
        p = _sigmoid(Xb @ w)
        grad = Xb.T @ (p - y) + reg * w
        H = (Xb * (p * (1 - p))[:, None]).T @ Xb + np.diag(reg) + 1e-9 * np.eye(d + 1)
        step = np.linalg.solve(H, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w[1:], float(w[0])


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    idx = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum(abs(p[idx == b].mean() - y[idx == b].mean()) * (idx == b).sum() for b in range(bins)
                     if (idx == b).any()) / max(1, len(p)))  # fmt: skip


def calibrate(train_rows: list, dev_rows: list, l2_grid: Sequence[float] = L2_GRID) -> dict[str, Any]:
    names = sorted({k for f, _, _ in train_rows for k in f} - EXCLUDE)
    mat = lambda rows: np.array([[f.get(k, 0.0) for k in names] for f, _, _ in rows]).reshape(len(rows), len(names))  # noqa: E731
    Xtr, Xdv = mat(train_rows), mat(dev_rows)
    ytr = np.array([y for _, _, y in train_rows], dtype=float)
    ydv = np.array([y for _, _, y in dev_rows], dtype=float)
    mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0)
    sd[sd < 1e-9] = 1.0
    grid = {}
    for l2 in l2_grid:
        w, b = fit_logistic((Xtr - mu) / sd, ytr, l2)
        grid[l2] = log_loss(_sigmoid(b + ((Xdv - mu) / sd) @ w), ydv)
    l2 = min(l2_grid, key=lambda v: (round(grid[v], 6), -v))  # ties -> stronger regularisation
    w, b = fit_logistic((Xtr - mu) / sd, ytr, l2)
    w_raw, b_raw = w / sd, b - float((w * mu / sd).sum())  # fold standardisation into raw-scale weights
    p_dev = _sigmoid(b_raw + Xdv @ w_raw)
    before = np.clip(np.array([c for _, c, _ in dev_rows]), 0, 1)
    return {
        "features": names,
        "weights": {k: round(float(v), 6) for k, v in zip(names, w_raw)},  # the agent reads this dict
        "bias": round(b_raw, 6),
        "fitted_on": "train",
        "n": len(train_rows),
        "positive_rate": round(float(ytr.mean()), 4) if len(ytr) else None,
        "l2": l2,
        "l2_grid": {str(k): round(v, 4) for k, v in grid.items()},
        "dev": {
            "n": len(dev_rows),
            "log_loss": round(log_loss(p_dev, ydv), 4), "brier": round(float(np.mean((p_dev - ydv) ** 2)), 4),
            "ece": round(ece(p_dev, ydv), 4),
            "log_loss_before": round(log_loss(before, ydv), 4),
            "brier_before": round(float(np.mean((before - ydv) ** 2)), 4), "ece_before": round(ece(before, ydv), 4),
        },  # fmt: skip
    }


def apply(cal: dict[str, Any], features: dict[str, float]) -> float:
    """P(correct) for one feature dict -- the same formula the agent should use."""
    z = cal["bias"] + sum(w * float(features.get(k, 0.0)) for k, w in cal["weights"].items())
    return float(1.0 / (1.0 + np.exp(-np.clip(z, -30, 30))))


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--llm", choices=("none", "auto"), default="none")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from keepline.eval.world import load_agent, load_world

    world, agent = load_world(), load_agent(args.llm)
    cal = calibrate(collect(agent, world.questions("train"), world), collect(agent, world.questions("dev"), world))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    CALIBRATOR_PATH.write_text(json.dumps(cal, indent=1), encoding="utf-8")
    d = cal["dev"]
    print(f"calibrator: {len(cal['features'])} features, train N={cal['n']}, l2={cal['l2']}  -> {CALIBRATOR_PATH}")
    print(f"DEV (N={d['n']} answered): ECE {d['ece_before']} -> {d['ece']}   Brier {d['brier_before']} -> {d['brier']}"
          f"   log-loss {d['log_loss_before']} -> {d['log_loss']}")  # fmt: skip


if __name__ == "__main__":
    main()

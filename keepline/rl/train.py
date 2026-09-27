"""Train the answer-policy bandit: ``python -m keepline.rl.train [--epochs 5 --seed 7 --llm none]``.

Protocol (so the numbers mean something):

1. Every (question, arm) pair on TRAIN and DEV is answered once by the real agent and cached
   (``keepline.rl.env``). The bandit still only *observes* the reward of the arm it pulls.
2. For each exploration strength ``alpha`` in the grid, LinUCB is trained on TRAIN (``epochs`` shuffled
   passes, seeded) and its greedy policy is scored on DEV. The best alpha wins; TEST is never touched.
3. The reward curve replays the winning run's question order for five policies: the bandit, the untuned
   default PolicyParams, the best fixed arm in hindsight, a uniform-random arm, and the per-question oracle.

Outputs (schemas documented here because Agent D's app reads them):

``data/results/bandit.json``::

    {"version": 1, "seed", "epochs", "alpha", "ridge", "hyperparam_dev_reward": {"alpha=..,ridge=..": dev mean},
     "fingerprint",
     "n_train", "n_dev", "arms": [Arm.to_dict()], "featurizer": {...}, "model": {...LinUCB A/b...},
     "per_area": {area_id: {"arm": key, "share": float, "n": int, "arm_counts": {key: n}}},
     "dev": {"bandit", "default", "best_fixed", "best_fixed_arm", "oracle", "random": mean reward, "n"},
     "train": {same keys}, "pull_counts": {arm_key: n}}

``data/results/reward_curve.json``::

    {"steps": int, "window": int, "n_train": int, "epochs": int,
     "rolling": {series: [float per step]}, "cumulative": {series: [...]},
     "final": {series: mean reward over all steps}}

    series in {"bandit", "default", "best_fixed", "random", "oracle"}
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from keepline.config import RESULTS_DIR
from keepline.contracts import Question
from keepline.rl.bandit import Arm, ContextualBandit, Featurizer, default_arm_grid
from keepline.rl.env import AnswerEnv

log = logging.getLogger(__name__)

ALPHA_GRID = (0.0, 0.1, 0.3, 1.0, 2.0)
RIDGE_GRID = (1.0, 10.0)
ROLLING_WINDOW = 50
SERIES = ("bandit", "default", "best_fixed", "random", "oracle")


@dataclass
class Run:
    model: ContextualBandit
    order: list[int]  # question index pulled at each step
    pulls: list[int]  # arm index pulled at each step
    rewards: list[float]


def simulate(X: np.ndarray, R: np.ndarray, *, alpha: float, epochs: int, seed: int, ridge: float = 1.0) -> Run:
    """LinUCB on a precomputed reward table. Only R[i, pulled_arm] is revealed to the learner."""
    rng = random.Random(seed)
    n, n_arms = R.shape
    model = ContextualBandit(n_arms, X.shape[1], alpha=alpha, ridge=ridge)
    order: list[int] = []
    for _ in range(epochs):
        idx = list(range(n))
        rng.shuffle(idx)
        order += idx
    pulls, rewards = [], []
    for i in order:
        a = model.select(X[i])
        r = float(R[i, a])
        model.update(a, X[i], r)
        pulls.append(a)
        rewards.append(r)
    return Run(model, order, pulls, rewards)


def greedy_rewards(model: ContextualBandit, X: np.ndarray, R: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    choice = np.array([model.select(x, explore=False) for x in X], dtype=int)
    return choice, R[np.arange(len(X)), choice] if len(X) else np.zeros(0)


def rolling_mean(xs: Sequence[float], w: int) -> list[float]:
    c = np.cumsum(np.insert(np.asarray(xs, dtype=float), 0, 0.0))
    out = [(c[i + 1] - c[max(0, i + 1 - w)]) / min(i + 1, w) for i in range(len(xs))]
    return [round(float(v), 4) for v in out]


def cumulative_mean(xs: Sequence[float]) -> list[float]:
    c = np.cumsum(np.asarray(xs, dtype=float))
    return [round(float(v), 4) for v in c / np.arange(1, len(xs) + 1)]


def curve_series(run: Run, R: np.ndarray, default: np.ndarray, seed: int) -> dict[str, list[float]]:
    """Per-step rewards of every comparison policy on the bandit's own question order."""
    rng = random.Random(seed + 1)
    best = int(np.argmax(R.mean(axis=0)))
    return {
        "bandit": run.rewards,
        "default": [float(default[i]) for i in run.order],
        "best_fixed": [float(R[i, best]) for i in run.order],
        "random": [float(R[i, rng.randrange(R.shape[1])]) for i in run.order],
        "oracle": [float(R[i].max()) for i in run.order],
    }


def summary(model: ContextualBandit, X: np.ndarray, R: np.ndarray, default: np.ndarray, arms: list[Arm],
            seed: int) -> dict[str, Any]:  # fmt: skip
    if len(X) == 0:
        return {"n": 0}
    _, g = greedy_rewards(model, X, R)
    best = int(np.argmax(R.mean(axis=0)))
    rng = np.random.default_rng(seed)
    rand = R[np.arange(len(X)), rng.integers(0, R.shape[1], len(X))]
    return {
        "n": len(X),
        "bandit": round(float(g.mean()), 4),
        "default": round(float(default.mean()), 4),
        "best_fixed": round(float(R[:, best].mean()), 4),
        "best_fixed_arm": arms[best].key,
        "random": round(float(rand.mean()), 4),
        "oracle": round(float(R.max(axis=1).mean()), 4),
    }


def per_area_choice(model: ContextualBandit, X: np.ndarray, areas: list[str | None], arms: list[Arm]) -> dict:
    by_area: dict[str, Counter[str]] = defaultdict(Counter)
    for x, area in zip(X, areas):
        by_area[area or "unknown"][arms[model.select(x, explore=False)].key] += 1
    out = {}
    for area, cnt in sorted(by_area.items()):
        key, n_top = cnt.most_common(1)[0]
        n = sum(cnt.values())
        out[area] = {"arm": key, "share": round(n_top / n, 3), "n": n, "arm_counts": dict(cnt.most_common())}
    return out


def train(
    env: AnswerEnv,
    train_qs: list[Question],
    dev_qs: list[Question],
    *,
    arms: list[Arm] | None = None,
    epochs: int = 5,
    seed: int = 7,
    alpha_grid: Sequence[float] = ALPHA_GRID,
    ridge_grid: Sequence[float] = RIDGE_GRID,
    area_ids: Sequence[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (bandit_json, reward_curve_json). Pure given the env's cached answers."""
    arms = arms or default_arm_grid()
    ctx_tr = [env.context(q) for q in train_qs]
    ctx_dev = [env.context(q) for q in dev_qs]
    areas = list(area_ids) or [str(c.get("area_id")) for c in ctx_tr if c.get("area_id")]
    feat = Featurizer.fit(ctx_tr, areas)
    X_tr = np.array([feat.transform(c) for c in ctx_tr])
    X_dev = np.array([feat.transform(c) for c in ctx_dev]).reshape(len(ctx_dev), feat.dim)
    log.info("answering %d train + %d dev questions x %d arms (cached)", len(train_qs), len(dev_qs), len(arms))
    R_tr, R_dev = env.reward_matrix(train_qs, arms), env.reward_matrix(dev_qs, arms)
    d_tr, d_dev = env.default_rewards(train_qs), env.default_rewards(dev_qs)

    grid = [(a, lam) for a in alpha_grid for lam in ridge_grid]
    runs = {hp: simulate(X_tr, R_tr, alpha=hp[0], ridge=hp[1], epochs=epochs, seed=seed) for hp in grid}
    dev_scores = {hp: float(greedy_rewards(r.model, X_dev, R_dev)[1].mean()) if len(dev_qs) else 0.0
                  for hp, r in runs.items()}  # fmt: skip
    # ties -> less exploration, stronger regularisation (the simpler model)
    alpha, ridge = max(grid, key=lambda hp: (round(dev_scores[hp], 6), -hp[0], hp[1]))
    run = runs[(alpha, ridge)]

    series = curve_series(run, R_tr, d_tr, seed)
    curve = {
        "steps": len(run.rewards),
        "window": ROLLING_WINDOW,
        "n_train": len(train_qs),
        "epochs": epochs,
        "alpha": alpha,
        "rolling": {k: rolling_mean(v, ROLLING_WINDOW) for k, v in series.items()},
        "cumulative": {k: cumulative_mean(v) for k, v in series.items()},
        "final": {k: round(float(np.mean(v)), 4) if v else 0.0 for k, v in series.items()},
    }
    bandit = {
        "version": 1,
        "seed": seed,
        "epochs": epochs,
        "alpha": alpha,
        "ridge": ridge,
        "hyperparam_dev_reward": {f"alpha={a},ridge={lam}": round(v, 4) for (a, lam), v in dev_scores.items()},
        "fingerprint": env.cache.fingerprint,
        "n_train": len(train_qs),
        "n_dev": len(dev_qs),
        "arms": [a.to_dict() for a in arms],
        "featurizer": feat.to_dict(),
        "model": run.model.to_dict(),
        "per_area": per_area_choice(run.model, np.vstack([X_tr, X_dev]),
                                    [c.get("area_id") for c in ctx_tr + ctx_dev], arms),  # fmt: skip
        "train": summary(run.model, X_tr, R_tr, d_tr, arms, seed),
        "dev": summary(run.model, X_dev, R_dev, d_dev, arms, seed),
        "pull_counts": {arms[i].key: int(c) for i, c in enumerate(run.model.counts)},
    }
    return bandit, curve


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--llm", choices=("none", "auto"), default="none")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from keepline.eval.world import load_agent, load_world

    world = load_world()
    agent = load_agent(args.llm)
    env = AnswerEnv(agent, world.truth, world.ev, people=world.people)
    try:
        area_ids = [a.id for a in agent.store.areas()]
    except Exception:  # noqa: BLE001 -- fall back to areas seen in contexts
        area_ids = []
    bandit, curve = train(env, world.questions("train"), world.questions("dev"), epochs=args.epochs,
                          seed=args.seed, area_ids=area_ids)  # fmt: skip
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "bandit.json").write_text(json.dumps(bandit, indent=1), encoding="utf-8")
    (RESULTS_DIR / "reward_curve.json").write_text(json.dumps(curve), encoding="utf-8")
    d = bandit["dev"]
    print(f"alpha={bandit['alpha']} ridge={bandit['ridge']}  train N={bandit['n_train']}  dev N={bandit['n_dev']}  steps={curve['steps']}")
    print("DEV mean reward: " + "  ".join(f"{k}={d.get(k)}" for k in SERIES) + f"  (best arm {d.get('best_fixed_arm')})")
    for area, row in bandit["per_area"].items():
        print(f"  {area:<24} -> {row['arm']:<28} share={row['share']:.2f} n={row['n']}")


if __name__ == "__main__":
    main()

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

    {"version": 1, "seed", "epochs", "alpha", "ridge", "features": "full"|"area_only",
     "hyperparam_dev_reward": {"features=..,alpha=..,ridge=..": dev mean reward},
     "fingerprint",
     "n_train", "n_dev", "arms": [Arm.to_dict()], "featurizer": {...}, "model": {...LinUCB A/b...},
     "policy": {"name", "type": "linucb"|"area_table", "table": {area: arm_key}, "default": arm_key|None},
         # the policy actually shipped (load_policy); chosen on DEV among policy_candidates_dev
     "policy_candidates_dev": {name: dev mean reward},
     "per_area": {area_id: {"arm": key, "share": float, "n": int, "arm_counts": {key: n}}},
     "dev": {"bandit", "default", "best_fixed", "best_fixed_arm", "oracle", "random": mean reward, "n"},
         # best_fixed_arm is chosen on TRAIN; oracle = per-question best arm in hindsight (upper bound)
     "train": {same keys}, "pull_counts": {arm_key: n},
     "arm_stats": {arm_key: {"pulls": n, "mean_reward": float|None, "train_mean_reward": float (all questions,
                   counterfactual), "dev_mean_reward": float}},
     "arm_timeline": {"every": int, "steps": [int], "pulls": {arm_key: [cumulative pulls]},
                      "mean_reward": {arm_key: [running mean of observed reward | None]}}}

``data/results/training_log.jsonl`` -- one row per bandit step (for replaying training as an animation)::

    {"step", "epoch", "qid", "question", "area_id" (gold), "pred_area" (agent's), "qtype", "expected_action",
     "arm", "action", "outcome", "reward", "confidence", "rolling_reward", "default_reward", "oracle_reward"}

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
            seed: int, best: int) -> dict[str, Any]:  # fmt: skip
    """Mean reward of each policy on (X, R). ``best`` = best fixed arm chosen on TRAIN (no peeking at dev)."""
    if len(X) == 0:
        return {"n": 0}
    _, g = greedy_rewards(model, X, R)
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


SHRINK_GRID = (0.0, 2.0, 5.0, 20.0, 1e9)  # prior strength m (pseudo-pulls); 1e9 == one global arm


def _area(ctx: dict[str, Any]) -> str:
    return str(ctx.get("area_id") or "unknown")


def shrinkage_table(runs: Sequence[Run], step_area: Sequence[str], n_arms: int, m: float) -> tuple[dict[str, int], int]:
    """Hierarchical per-area arm choice from the bandit's *own observed* pulls (partial feedback only).

    Each area's estimate for an arm is shrunk toward that arm's global mean with ``m`` pseudo-pulls:
    ``v[a, j] = (sum_r[a, j] + m * g[j]) / (n[a, j] + m)``. Small areas borrow strength from the whole company;
    big areas keep their own preference. ``step_area[i]`` is the area of train question i.
    """
    s_g, n_g = np.zeros(n_arms), np.zeros(n_arms)
    s_a: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(n_arms))
    n_a: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(n_arms))
    for run in runs:
        for i, a, r in zip(run.order, run.pulls, run.rewards):
            s_g[a] += r
            n_g[a] += 1
            s_a[step_area[i]][a] += r
            n_a[step_area[i]][a] += 1
    g = np.where(n_g > 0, s_g / np.maximum(n_g, 1), -np.inf)
    default = int(np.argmax(g))
    table = {}
    for area in sorted(s_a):
        denom = n_a[area] + m
        v = np.where(denom > 0, (s_a[area] + m * np.where(np.isfinite(g), g, 0.0)) / np.maximum(denom, 1e-12), -np.inf)
        v[~np.isfinite(g)] = -np.inf
        table[area] = int(np.argmax(v))
    return table, default


def table_rewards(table: dict[str, int], default: int, ctxs: Sequence[dict], R: np.ndarray) -> np.ndarray:
    choice = [table.get(_area(c), default) for c in ctxs]
    return R[np.arange(len(ctxs)), choice] if len(ctxs) else np.zeros(0)


def _per_area_selected(sel: dict, model: ContextualBandit, X: np.ndarray, ctxs: Sequence[dict],
                       arms: list[Arm]) -> dict:  # fmt: skip
    if sel["type"] == "linucb":
        return per_area_choice(model, X, [c.get("area_id") for c in ctxs], arms)
    counts = Counter(_area(c) for c in ctxs)
    return {a: {"arm": arms[sel["table"].get(a, sel["default"])].key, "share": 1.0, "n": n,
                "arm_counts": {arms[sel["table"].get(a, sel["default"])].key: n}} for a, n in sorted(counts.items())}  # fmt: skip


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
) -> tuple[dict[str, Any], dict[str, Any], Run]:
    """Returns (bandit_json, reward_curve_json, winning run). Pure given the env's cached answers."""
    arms = arms or default_arm_grid()
    ctx_tr = [env.context(q) for q in train_qs]
    ctx_dev = [env.context(q) for q in dev_qs]
    areas = list(area_ids) or [str(c.get("area_id")) for c in ctx_tr if c.get("area_id")]
    full = Featurizer.fit(ctx_tr, areas)
    feats = {"full": full, "area_only": Featurizer(full.areas, [], [])}
    X = {m: (np.array([f.transform(c) for c in ctx_tr]).reshape(len(ctx_tr), f.dim),
             np.array([f.transform(c) for c in ctx_dev]).reshape(len(ctx_dev), f.dim)) for m, f in feats.items()}  # fmt: skip
    log.info("answering %d train + %d dev questions x %d arms (cached)", len(train_qs), len(dev_qs), len(arms))
    R_tr, R_dev = env.reward_matrix(train_qs, arms), env.reward_matrix(dev_qs, arms)
    d_tr, d_dev = env.default_rewards(train_qs), env.default_rewards(dev_qs)

    # Hyperparameters tuned on DEV: exploration alpha, ridge strength, and the context feature set. "area_only"
    # (bias + area one-hot) is a per-area bandit; "full" adds the agent's numeric features. With a few hundred
    # train questions the richer context can overfit, so dev decides.
    grid = [(m, a, lam) for m in feats for a in alpha_grid for lam in ridge_grid]
    runs = {hp: simulate(X[hp[0]][0], R_tr, alpha=hp[1], ridge=hp[2], epochs=epochs, seed=seed) for hp in grid}
    dev_scores = {hp: float(greedy_rewards(r.model, X[hp[0]][1], R_dev)[1].mean()) if len(dev_qs) else 0.0
                  for hp, r in runs.items()}  # fmt: skip
    # ties -> simpler model: area-only context, less exploration, stronger regularisation
    mode, alpha, ridge = max(grid, key=lambda hp: (round(dev_scores[hp], 6), hp[0] == "area_only", -hp[1], hp[2]))
    run, feat = runs[(mode, alpha, ridge)], feats[mode]
    X_tr, X_dev = X[mode]

    series = curve_series(run, R_tr, d_tr, seed)
    best_train = int(np.argmax(R_tr.mean(axis=0)))

    # Policy selection on DEV among: the tuned LinUCB, hierarchical per-area tables built from the bandit's own
    # logged pulls (every hyperparameter run's interactions pooled), and the best fixed arm on TRAIN. Including
    # the fixed arm guarantees the shipped policy is never worse on dev than the best single setting.
    step_area = [_area(c) for c in ctx_tr]
    candidates: dict[str, dict[str, Any]] = {
        "best_fixed_train": {"type": "area_table", "table": {}, "default": best_train,
                             "dev": float(R_dev[:, best_train].mean()) if len(dev_qs) else 0.0},
    }  # fmt: skip
    for m in sorted(SHRINK_GRID, reverse=True):
        table, default = shrinkage_table(list(runs.values()), step_area, len(arms), m)
        name = "global_arm_from_logs" if m >= 1e9 else f"area_table_m{m:g}"
        candidates[name] = {"type": "area_table", "table": table, "default": default,
                            "dev": float(table_rewards(table, default, ctx_dev, R_dev).mean()) if len(dev_qs) else 0.0}  # fmt: skip
    candidates["linucb"] = {"type": "linucb", "dev": dev_scores[(mode, alpha, ridge)]}
    order = list(candidates)  # insertion order = tie preference (simplest first)
    selected = max(order, key=lambda k: (round(candidates[k]["dev"], 6), -order.index(k)))
    sel = candidates[selected]

    def selected_rewards(ctxs: Sequence[dict], Xm: np.ndarray, R: np.ndarray) -> np.ndarray:
        if sel["type"] == "linucb":
            return greedy_rewards(run.model, Xm, R)[1]
        return table_rewards(sel["table"], sel["default"], ctxs, R)
    stats, timeline = arm_stats(run, arms, R_tr, R_dev)
    # window = one epoch: every train question appears exactly once per window, so the series are comparable
    # (with a short window the curve mostly shows which questions happened to come up, not learning)
    window = max(ROLLING_WINDOW, len(train_qs))
    curve = {
        "steps": len(run.rewards),
        "window": window,
        "n_train": len(train_qs),
        "epochs": epochs,
        "alpha": alpha,
        "rolling": {k: rolling_mean(v, window) for k, v in series.items()},
        "cumulative": {k: cumulative_mean(v) for k, v in series.items()},
        "final": {k: round(float(np.mean(v)), 4) if v else 0.0 for k, v in series.items()},
        "_raw": series,  # per-step rewards; stripped before writing, used for the training log
    }
    bandit = {
        "version": 1,
        "seed": seed,
        "epochs": epochs,
        "alpha": alpha,
        "ridge": ridge,
        "features": mode,
        "hyperparam_dev_reward": {f"features={m},alpha={a},ridge={lam}": round(v, 4)
                                  for (m, a, lam), v in dev_scores.items()},  # fmt: skip
        "fingerprint": env.cache.fingerprint,
        "n_train": len(train_qs),
        "n_dev": len(dev_qs),
        "arms": [a.to_dict() for a in arms],
        "featurizer": feat.to_dict(),
        "model": run.model.to_dict(),
        "policy": {"name": selected, "type": sel["type"],
                   "table": {a: arms[j].key for a, j in sel.get("table", {}).items()},
                   "default": arms[sel["default"]].key if "default" in sel else None},  # fmt: skip
        "policy_candidates_dev": {k: round(v["dev"], 4) for k, v in candidates.items()},
        "per_area": _per_area_selected(sel, run.model, np.vstack([X_tr, X_dev]), ctx_tr + ctx_dev, arms),
        "train": {**summary(run.model, X_tr, R_tr, d_tr, arms, seed, best_train), "selected_policy": selected,
                  "selected": round(float(selected_rewards(ctx_tr, X_tr, R_tr).mean()), 4) if len(ctx_tr) else None},
        "dev": {**summary(run.model, X_dev, R_dev, d_dev, arms, seed, best_train), "selected_policy": selected,
                "selected": round(float(selected_rewards(ctx_dev, X_dev, R_dev).mean()), 4) if len(ctx_dev) else None},
        "pull_counts": {arms[i].key: int(c) for i, c in enumerate(run.model.counts)},
        "arm_stats": stats,
        "arm_timeline": timeline,
    }
    return bandit, curve, run


def training_log(env: AnswerEnv, qs: list[Question], run: Run, arms: list[Arm], curve: dict) -> list[dict]:
    """One row per step of the winning run; every answer is already cached, so this is cheap."""
    rows = []
    n = max(1, len(qs))
    for t, (i, a) in enumerate(zip(run.order, run.pulls)):
        q, step = qs[i], env.step(qs[i], arms[a])
        rows.append({
            "step": t + 1, "epoch": t // n + 1, "qid": q.id, "question": q.text, "area_id": q.area_id,
            "pred_area": env.context(q).get("area_id"), "qtype": str(q.qtype),
            "expected_action": str(q.expected_action), "arm": arms[a].key, "action": str(step.answer.action),
            "outcome": str(step.grade.outcome), "reward": round(step.reward, 4),
            "confidence": round(float(step.answer.confidence), 4),
            "rolling_reward": curve["rolling"]["bandit"][t], "default_reward": round(curve["_raw"]["default"][t], 4),
            "oracle_reward": round(curve["_raw"]["oracle"][t], 4),
        })  # fmt: skip
    return rows


def arm_stats(run: Run, arms: list[Arm], R_tr: np.ndarray, R_dev: np.ndarray, every: int = 20) -> tuple[dict, dict]:
    """Per-arm pulls and observed mean reward (final + sampled over time) for the UI."""
    k = len(arms)
    pulls, total = np.zeros(k, dtype=int), np.zeros(k)
    steps, p_hist, m_hist = [], {a.key: [] for a in arms}, {a.key: [] for a in arms}
    for t, (a, r) in enumerate(zip(run.pulls, run.rewards), 1):
        pulls[a] += 1
        total[a] += r
        if t % every == 0 or t == len(run.pulls):
            steps.append(t)
            for j, arm in enumerate(arms):
                p_hist[arm.key].append(int(pulls[j]))
                m_hist[arm.key].append(round(total[j] / pulls[j], 4) if pulls[j] else None)
    stats = {
        arm.key: {
            "pulls": int(pulls[j]),
            "mean_reward": round(total[j] / pulls[j], 4) if pulls[j] else None,
            "train_mean_reward": round(float(R_tr[:, j].mean()), 4) if len(R_tr) else None,
            "dev_mean_reward": round(float(R_dev[:, j].mean()), 4) if len(R_dev) else None,
        }
        for j, arm in enumerate(arms)
    }
    return stats, {"every": every, "steps": steps, "pulls": p_hist, "mean_reward": m_hist}


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
    bandit, curve, run = train(env, world.questions("train"), world.questions("dev"), epochs=args.epochs,
                          seed=args.seed, area_ids=area_ids)  # fmt: skip
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "bandit.json").write_text(json.dumps(bandit, indent=1), encoding="utf-8")
    log_rows = training_log(env, world.questions("train"), run, [Arm.from_dict(a) for a in bandit["arms"]], curve)
    curve.pop("_raw", None)
    (RESULTS_DIR / "reward_curve.json").write_text(json.dumps(curve), encoding="utf-8")
    with (RESULTS_DIR / "training_log.jsonl").open("w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in log_rows)
    d = bandit["dev"]
    print(f"features={bandit['features']} alpha={bandit['alpha']} ridge={bandit['ridge']}  train N={bandit['n_train']}  dev N={bandit['n_dev']}  steps={curve['steps']}")
    print(f"SELECTED policy on dev: {bandit['policy']['name']} -> dev {d['selected']}  candidates {bandit['policy_candidates_dev']}")
    print("DEV mean reward: " + "  ".join(f"{k}={d.get(k)}" for k in SERIES) + f"  (best arm {d.get('best_fixed_arm')})")
    for area, row in bandit["per_area"].items():
        print(f"  {area:<24} -> {row['arm']:<28} share={row['share']:.2f} n={row['n']}")


if __name__ == "__main__":
    main()

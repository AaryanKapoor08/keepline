"""Reward table + LinUCB learning on a synthetic problem + policy round-trip (no agent, no data)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from keepline.contracts import PolicyParams
from keepline.rl.bandit import Arm, ContextualBandit, Featurizer, default_arm_grid
from keepline.rl.policy import load_policy
from keepline.rl.rewards import BASE_REWARD, Grade, Outcome, reward
from keepline.rl.train import greedy_rewards, rolling_mean, simulate


def test_reward_table_matches_project_summary() -> None:
    assert BASE_REWARD[Outcome.CORRECT_CITED] == 1.0
    assert BASE_REWARD[Outcome.CORRECT_ABSTAIN] == BASE_REWARD[Outcome.CORRECT_ROUTE] == 0.5
    assert BASE_REWARD[Outcome.UNNECESSARY_ABSTAIN] == -0.3
    assert BASE_REWARD[Outcome.HALLUCINATION] == -2.0
    assert BASE_REWARD[Outcome.STALE_ANSWER] == -2.0
    assert BASE_REWARD[Outcome.CORRECT_UNCITED] < BASE_REWARD[Outcome.CORRECT_ABSTAIN]
    g = Grade(correct=True, citation_valid=True, outcome=Outcome.CORRECT_CITED, calibration_target=1.0)
    assert reward(g, 0.75) == pytest.approx(1.0 + 0.2 * 0.75)
    assert reward(g, 7.0) == pytest.approx(1.2)  # confidence clipped to [0, 1]


def test_arm_grid_is_small_and_valid() -> None:
    arms = default_arm_grid()
    assert 10 <= len(arms) <= 30
    assert len({a.key for a in arms}) == len(arms)
    assert all(a.route_threshold < a.abstain_threshold for a in arms)
    assert isinstance(arms[0].params(), PolicyParams)


def _synthetic(n: int = 200, seed: int = 0) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Two contexts ("hr" wants arm 0, "eng" wants arm 2) with noisy-looking but fixed rewards."""
    rng = np.random.default_rng(seed)
    ctxs = [{"area_id": "hr" if i % 2 == 0 else "eng", "retrieval_score": float(rng.random())} for i in range(n)]
    feat = Featurizer.fit(ctxs, ["hr", "eng"])
    X = np.array([feat.transform(c) for c in ctxs])
    R = np.full((n, 3), -0.3) + rng.normal(0, 0.05, (n, 3))
    for i, c in enumerate(ctxs):
        R[i, 0 if c["area_id"] == "hr" else 2] = 1.0
    return X, R, ctxs


def test_linucb_learns_best_arm_per_context() -> None:
    X, R, ctxs = _synthetic()
    run = simulate(X, R, alpha=0.5, epochs=2, seed=1)
    choice, rewards = greedy_rewards(run.model, X, R)
    assert all(ch == (0 if c["area_id"] == "hr" else 2) for ch, c in zip(choice, ctxs))
    assert rewards.mean() == pytest.approx(1.0)
    late = np.mean(run.rewards[-100:])
    early = np.mean(run.rewards[:20])
    assert late > early and late > 0.9


def test_simulation_is_deterministic() -> None:
    X, R, _ = _synthetic()
    a = simulate(X, R, alpha=1.0, epochs=1, seed=3)
    b = simulate(X, R, alpha=1.0, epochs=1, seed=3)
    assert a.pulls == b.pulls and a.rewards == b.rewards


def test_policy_round_trip(tmp_path: Path) -> None:
    X, R, ctxs = _synthetic()
    arms = [Arm(3, 0.2, 0.1), Arm(6, 0.35, 0.1), Arm(12, 0.65, 0.25)]
    run = simulate(X, R, alpha=0.5, epochs=2, seed=1)
    feat = Featurizer.fit(ctxs, ["hr", "eng"])
    path = tmp_path / "bandit.json"
    path.write_text(json.dumps({"model": run.model.to_dict(), "featurizer": feat.to_dict(),
                                "arms": [a.to_dict() for a in arms]}), encoding="utf-8")  # fmt: skip
    policy = load_policy(path)
    assert policy({"area_id": "hr", "retrieval_score": 0.5}).k == 3
    assert policy({"area_id": "eng", "retrieval_score": 0.5}).k == 12
    assert load_policy(tmp_path / "missing.json")({}) == PolicyParams()


def test_rolling_mean() -> None:
    assert rolling_mean([1, 0, 1, 0], 2) == [1.0, 0.5, 0.5, 0.5]


def test_bandit_serialization() -> None:
    m = ContextualBandit(2, 3, alpha=0.3)
    m.update(1, np.array([1.0, 0.0, 1.0]), 1.0)
    m2 = ContextualBandit.from_dict(json.loads(json.dumps(m.to_dict())))
    x = np.array([1.0, 0.0, 1.0])
    assert np.allclose(m.scores(x), m2.scores(x))

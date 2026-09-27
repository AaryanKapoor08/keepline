"""Contextual bandit over Keepline's answer policy (RL over *decisions*, never over LLM weights).

Why a contextual bandit and not full RL:

* **One-step decision.** For each question the agent picks a policy (retrieval depth, abstain/route
  thresholds, source trust) once, and the episode ends. There is no state transition to plan over, so an MDP
  learner would only add variance.
* **Immediate reward.** The grader scores the answer right away (``keepline.rl.rewards``).
* **Sample-efficient.** We have hundreds of training questions, not millions. Disjoint LinUCB learns one ridge
  regression per arm in closed form and explores only where its uncertainty is high.
* **CPU-minutes.** Numpy only; a training run is dominated by the agent's own answer calls (which are cached).

Context = ``[1 (bias), one-hot(area), scaled numeric features from AnswerAgent.context_features]``. Because the
area one-hot is part of the context, the linear model learns a per-area preference for each arm while still
sharing the numeric-feature weights across areas -- the "per-area" bandit of the build plan.

Conventions follow Li et al. 2010 ("A Contextual-Bandit Approach to Personalized News Article
Recommendation"), Algorithm 1: per arm ``A = lambda*I + sum x x^T``, ``b = sum r x``, ``theta = A^-1 b``,
``p = theta.x + alpha*sqrt(x^T A^-1 x)``. Ties break to the lowest arm index, so runs are deterministic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from keepline.contracts import PolicyParams

# --------------------------------------------------------------------------------------------------
# Arms
# --------------------------------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = dict(PolicyParams().source_weights)
SOURCE_PROFILES: dict[str, dict[str, float]] = {
    "default": DEFAULT_WEIGHTS,
    # "doing > talking": trust tickets/interviews/docs, discount chat
    "records_first": {"ticket": 1.5, "slack": 0.7, "email": 0.9, "doc": 1.2, "interview": 1.5},
}


@dataclass(frozen=True)
class Arm:
    """A named, hashable point in PolicyParams space."""

    k: int
    abstain_threshold: float
    route_threshold: float
    profile: str = "default"

    @property
    def key(self) -> str:
        base = f"k{self.k}-a{self.abstain_threshold:.2f}-r{self.route_threshold:.2f}"
        return base if self.profile == "default" else f"{base}-{self.profile}"

    def params(self) -> PolicyParams:
        return PolicyParams(
            k=self.k,
            abstain_threshold=self.abstain_threshold,
            route_threshold=self.route_threshold,
            source_weights=dict(SOURCE_PROFILES[self.profile]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "k": self.k, "abstain_threshold": self.abstain_threshold,
                "route_threshold": self.route_threshold, "profile": self.profile,
                "source_weights": dict(SOURCE_PROFILES[self.profile])}  # fmt: skip

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Arm:
        return cls(int(d["k"]), float(d["abstain_threshold"]), float(d["route_threshold"]), d.get("profile", "default"))


def default_arm_grid() -> list[Arm]:
    """28 arms: retrieval depth x abstain threshold x source-trust profile.

    Why this shape: a sweep over 144 arms (k in {3,6,12} x abstain in {.2..0.97} x route in {.05..0.5} x 2 profiles)
    on TRAIN showed only 28 distinct behaviours -- with Agent B's agent, retrieval depth and route_threshold
    barely change outcomes, while abstain_threshold dominates (the -2 hallucination penalty makes answering
    worth it only when P(correct) > ~0.57). So the arm budget goes to a fine abstain grid; route_threshold is
    held at 0.10 (always below abstain) and k keeps two settings in case the agent starts using depth.
    """
    return [
        Arm(k, a, 0.10, profile)
        for profile in ("default", "records_first")
        for k in (3, 12)
        for a in (0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 0.97)
    ]


# --------------------------------------------------------------------------------------------------
# Context featurisation
# --------------------------------------------------------------------------------------------------


@dataclass
class Featurizer:
    """Turns ``{"area_id": ..., **numeric_features}`` into a fixed-length vector.

    Numeric features are divided by the max |value| seen at fit time (then clipped to [-3, 3]) so that LinUCB's
    ridge prior treats them on the same scale as the one-hot entries.
    """

    areas: list[str]
    feature_names: list[str]
    scales: list[float] = field(default_factory=list)

    @classmethod
    def fit(cls, contexts: Sequence[Mapping[str, Any]], areas: Sequence[str]) -> Featurizer:
        names = sorted({k for c in contexts for k, v in c.items() if k != "area_id" and _is_num(v)})
        scales = [max([abs(float(c.get(n, 0.0))) for c in contexts] + [1e-9]) for n in names]
        return cls(sorted(set(areas)), names, [s if s > 1e-9 else 1.0 for s in scales])

    @property
    def dim(self) -> int:
        return 1 + len(self.areas) + len(self.feature_names)

    def area_of(self, ctx: Mapping[str, Any]) -> str | None:
        area = ctx.get("area_id", ctx.get("area"))
        if area is None:
            for a in self.areas:
                if float(ctx.get(f"area={a}", 0.0)) > 0:
                    return a
        return area

    def transform(self, ctx: Mapping[str, Any]) -> np.ndarray:
        x = np.zeros(self.dim)
        x[0] = 1.0
        area = self.area_of(ctx)
        if area in self.areas:
            x[1 + self.areas.index(area)] = 1.0
        off = 1 + len(self.areas)
        for i, (name, s) in enumerate(zip(self.feature_names, self.scales)):
            v = ctx.get(name, 0.0)
            x[off + i] = float(np.clip(float(v) / s, -3.0, 3.0)) if _is_num(v) else 0.0
        return x

    def to_dict(self) -> dict[str, Any]:
        return {"areas": self.areas, "feature_names": self.feature_names, "scales": self.scales}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Featurizer:
        return cls(list(d["areas"]), list(d["feature_names"]), [float(s) for s in d["scales"]])


def _is_num(v: Any) -> bool:
    return isinstance(v, (bool, int, float, np.integer, np.floating))  # bools count as 0/1 features


# --------------------------------------------------------------------------------------------------
# LinUCB
# --------------------------------------------------------------------------------------------------


class ContextualBandit:
    """Disjoint LinUCB over a discrete arm list."""

    def __init__(self, n_arms: int, dim: int, *, alpha: float = 1.0, ridge: float = 1.0) -> None:
        self.n_arms, self.dim, self.alpha, self.ridge = n_arms, dim, alpha, ridge
        self.A = np.stack([ridge * np.eye(dim) for _ in range(n_arms)])
        self.b = np.zeros((n_arms, dim))
        self.counts = np.zeros(n_arms, dtype=int)

    def _theta_and_inv(self) -> tuple[np.ndarray, np.ndarray]:
        A_inv = np.linalg.inv(self.A)
        return np.einsum("aij,aj->ai", A_inv, self.b), A_inv

    def scores(self, x: np.ndarray, *, explore: bool = True) -> np.ndarray:
        theta, A_inv = self._theta_and_inv()
        mean = theta @ x
        if not explore:
            return mean
        width = np.sqrt(np.maximum(np.einsum("i,aij,j->a", x, A_inv, x), 0.0))
        return mean + self.alpha * width

    def select(self, x: np.ndarray, *, explore: bool = True) -> int:
        return int(np.argmax(self.scores(x, explore=explore)))  # argmax -> lowest index on ties

    def update(self, arm: int, x: np.ndarray, r: float) -> None:
        self.A[arm] += np.outer(x, x)
        self.b[arm] += r * x
        self.counts[arm] += 1

    def to_dict(self) -> dict[str, Any]:
        return {"alpha": self.alpha, "ridge": self.ridge, "n_arms": self.n_arms, "dim": self.dim,
                "A": self.A.round(8).tolist(), "b": self.b.round(8).tolist(), "counts": self.counts.tolist()}  # fmt: skip

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ContextualBandit:
        m = cls(int(d["n_arms"]), int(d["dim"]), alpha=float(d["alpha"]), ridge=float(d["ridge"]))
        m.A = np.asarray(d["A"], dtype=float)
        m.b = np.asarray(d["b"], dtype=float)
        m.counts = np.asarray(d["counts"], dtype=int)
        return m

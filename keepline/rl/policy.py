"""Load the trained answer policy for the app and the benchmark.

Product-world safe: this module only reads ``data/results/bandit.json`` (model weights + arm list), never the
answer key, so ``app/`` may import it.

Usage::

    policy = load_policy()
    params = policy(bandit_context(agent, question, asker_id, as_of))
    answer = agent.answer(question, asker_id, as_of=as_of, params=params)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from keepline.config import RESULTS_DIR
from keepline.contracts import PolicyParams
from keepline.rl.bandit import Arm, ContextualBandit, Featurizer

log = logging.getLogger(__name__)

BANDIT_PATH = RESULTS_DIR / "bandit.json"

PolicyFn = Callable[[Mapping[str, Any]], PolicyParams]


class _ContextAgent(Protocol):
    def context_features(self, question: str, asker_id: str, *, as_of: date | None = None) -> dict[str, float]: ...

    def classify_area(self, question: str) -> str | None: ...


def bandit_context(agent: _ContextAgent, question: str, asker_id: str, as_of: date | None) -> dict[str, Any]:
    """The context the bandit sees: the agent's cheap numeric features + its predicted ``area_id``."""
    feats: dict[str, Any] = dict(agent.context_features(question, asker_id, as_of=as_of))
    if feats.get("area_id") is None:
        feats["area_id"] = agent.classify_area(question)
    return feats


ArmPolicyFn = Callable[[Mapping[str, Any]], Arm]


def greedy_arm_policy(model: ContextualBandit, featurizer: Featurizer, arms: list[Arm]) -> ArmPolicyFn:
    """Exploit-only policy: the arm with the highest predicted reward for this context."""

    def policy(ctx: Mapping[str, Any]) -> Arm:
        return arms[model.select(featurizer.transform(ctx), explore=False)]

    return policy


def load_arm_policy(path: Path = BANDIT_PATH) -> ArmPolicyFn | None:
    """Greedy trained policy returning the chosen ``Arm`` (None if no usable bandit.json)."""
    if not path.exists():
        log.info("no bandit at %s; using default PolicyParams", path)
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        model = ContextualBandit.from_dict(d["model"])
        feat = Featurizer.from_dict(d["featurizer"])
        arms = [Arm.from_dict(a) for a in d["arms"]]
    except Exception as exc:  # noqa: BLE001 -- a corrupt file must not take the app down
        log.warning("could not load bandit (%s); using default PolicyParams", exc)
        return None
    pol = d.get("policy") or {"type": "linucb"}
    if pol.get("type") == "area_table":
        by_key = {a.key: a for a in arms}
        table = {area: by_key[k] for area, k in pol.get("table", {}).items()}
        default = by_key[pol["default"]]
        return lambda ctx: table.get(str(ctx.get("area_id") or "unknown"), default)
    return greedy_arm_policy(model, feat, arms)


def load_policy(path: Path = BANDIT_PATH) -> PolicyFn:
    """Greedy trained policy, or a constant default-PolicyParams policy if no bandit has been trained yet."""
    arm_policy = load_arm_policy(path)
    if arm_policy is None:
        return lambda ctx: PolicyParams()
    return lambda ctx: arm_policy(ctx).params()

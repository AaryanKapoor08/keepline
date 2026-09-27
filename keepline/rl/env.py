"""Bandit environment: (question, arm) -> agent answer -> grade -> reward, with a disk cache.

The agent is deterministic for a fixed memory build, so every (question, arm) pair only ever needs to be
answered once. We cache the *answers* (not the grades) in ``data/results/arm_cache.json`` and re-grade on load:
grading is microseconds, and a grader fix then never requires re-running the agent. The cache is keyed by a
fingerprint of the agent code + memory build + LLM mode, so it silently resets when Agent B ships a new
version.

Having the full (question x arm) answer table also gives us the counterfactual lines on the reward curve --
the per-question oracle and the best fixed arm in hindsight -- for free.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from keepline.config import MEMORY_DIR, RESULTS_DIR, ROOT
from keepline.contracts import Answer, EvidenceMap, PolicyParams, Question, TruthFact, from_dict, to_dict
from keepline.eval.grader import grade
from keepline.rl.bandit import Arm
from keepline.rl.policy import bandit_context
from keepline.rl.rewards import Grade

log = logging.getLogger(__name__)

ARM_CACHE_PATH = RESULTS_DIR / "arm_cache.json"
DEFAULT_ARM_KEY = "default"  # the untuned PolicyParams() the agent ships with


class Agent(Protocol):
    def answer(self, question: str, asker_id: str, *, as_of: Any = None, params: PolicyParams | None = None) -> Answer: ...

    def context_features(self, question: str, asker_id: str, *, as_of: Any = None) -> dict[str, float]: ...

    def classify_area(self, question: str) -> str | None: ...


def agent_fingerprint(extra: str = "") -> str:
    """Hash of everything that can change an answer: agent/retrieval/memory code, the memory build, LLM mode."""
    h = hashlib.sha256(extra.encode())
    for pkg in ("agent", "retrieval", "memory"):
        for p in sorted((ROOT / "keepline" / pkg).glob("*.py")):
            h.update(p.name.encode())
            h.update(p.read_bytes())
    if MEMORY_DIR.exists():
        for p in sorted(MEMORY_DIR.rglob("*")):
            if p.is_file():
                st = p.stat()
                h.update(f"{p.name}:{st.st_size}:{st.st_mtime_ns}".encode())
    from keepline.config import LLM

    h.update(LLM.provider.encode())
    return h.hexdigest()[:16]


@dataclass
class Step:
    answer: Answer
    grade: Grade

    @property
    def reward(self) -> float:
        return self.grade.reward


class AnswerCache:
    """JSON-backed {question_id|arm_key: Answer} + {question_id: context} store."""

    def __init__(self, path: Path, fingerprint: str) -> None:
        self.path, self.fingerprint = path, fingerprint
        self.answers: dict[str, dict[str, Any]] = {}
        self.contexts: dict[str, dict[str, Any]] = {}
        self.dirty = False
        if path.exists():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                if d.get("fingerprint") == fingerprint:
                    self.answers, self.contexts = d.get("answers", {}), d.get("contexts", {})
                else:
                    log.info("arm cache fingerprint changed; starting fresh")
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("unreadable arm cache (%s); starting fresh", exc)

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"fingerprint": self.fingerprint, "answers": self.answers, "contexts": self.contexts}
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.dirty = False


def _answer_record(a: Answer) -> dict[str, Any]:
    """Serialisable answer; ``debug`` is dropped (it can be large or hold non-JSON objects)."""
    a = dataclasses.replace(a, debug={})
    try:
        return to_dict(a)
    except TypeError:
        return to_dict(dataclasses.replace(a, policy={k: str(v) for k, v in a.policy.items()}))


class AnswerEnv:
    """Pull an arm for a question, get a graded reward. Deterministic and cached."""

    def __init__(
        self,
        agent: Agent,
        truth: Mapping[str, TruthFact],
        ev: EvidenceMap,
        *,
        people: Mapping[str, str] | None = None,
        cache_path: Path | None = ARM_CACHE_PATH,
        fingerprint: str | None = None,
    ) -> None:
        self.agent, self.truth, self.ev, self.people = agent, truth, ev, people
        fp = fingerprint if fingerprint is not None else agent_fingerprint()
        self.cache = AnswerCache(cache_path, fp) if cache_path else AnswerCache(Path("__nocache__"), fp)
        self._persist = cache_path is not None
        self._calls_since_save = 0

    def context(self, q: Question) -> dict[str, Any]:
        if q.id not in self.cache.contexts:
            self.cache.contexts[q.id] = bandit_context(self.agent, q.text, q.asker_id, q.as_of)
            self.cache.dirty = True
        return self.cache.contexts[q.id]

    def answer(self, q: Question, arm: Arm | None) -> Answer:
        key = f"{q.id}|{arm.key if arm else DEFAULT_ARM_KEY}"
        if key not in self.cache.answers:
            params = arm.params() if arm else PolicyParams()
            a = self.agent.answer(q.text, q.asker_id, as_of=q.as_of, params=params)
            self.cache.answers[key] = _answer_record(a)
            self.cache.dirty = True
            self._calls_since_save += 1
            if self._persist and self._calls_since_save >= 200:
                self.save()
        return from_dict(Answer, self.cache.answers[key])

    def step(self, q: Question, arm: Arm | None) -> Step:
        a = self.answer(q, arm)
        return Step(a, grade(q, a, self.truth, self.ev, people=self.people))

    def reward_matrix(self, questions: Sequence[Question], arms: Sequence[Arm]) -> np.ndarray:
        """R[i, j] = reward of arm j on question i (answers every pair once, then cached)."""
        R = np.zeros((len(questions), len(arms)))
        for i, q in enumerate(questions):
            for j, arm in enumerate(arms):
                R[i, j] = self.step(q, arm).reward
        self.save()
        return R

    def default_rewards(self, questions: Sequence[Question]) -> np.ndarray:
        out = np.array([self.step(q, None).reward for q in questions])
        self.save()
        return out

    def save(self) -> None:
        if self._persist:
            self.cache.save()
        self._calls_since_save = 0

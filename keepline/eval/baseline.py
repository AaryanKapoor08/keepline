"""Comparison systems for the benchmark.

``PlainSearchBaseline`` is what most companies have today: a search box. It uses the *same* ``SearchIndex``
over the *same* corpus as Keepline (fair comparison -- only the decision layer differs), always answers with
the top hit, cites it, and reports the hit's normalised score as confidence. It never abstains, which is
exactly the behaviour Keepline's abstain/route layer is meant to beat.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any, Protocol

from keepline.contracts import Action, Answer, Citation, PolicyParams
from keepline.rl.policy import bandit_context


class _Index(Protocol):
    def search(self, query: str, *, k: int = 8, as_of: Any = None, visible_to: Any = None,
               source_weights: Any = None) -> list[Any]: ...  # fmt: skip


class _Agent(Protocol):
    def answer(self, question: str, asker_id: str, *, as_of: date | None = None,
               params: PolicyParams | None = None) -> Answer: ...  # fmt: skip

    def context_features(self, question: str, asker_id: str, *, as_of: date | None = None) -> dict[str, float]: ...

    def classify_area(self, question: str) -> str | None: ...


def _score_confidence(scores: list[float]) -> float:
    """Top-1 score squashed to [0, 1] with a margin term: a clear winner is more 'confident' than a tie.

    ``conf = (1 - exp(-s1/2)) * (0.5 + 0.5 * (s1 - s2) / s1)``. BM25 scores are unbounded, so the saturating
    exponential maps them to (0, 1); the margin factor halves confidence when the runner-up is as strong.
    """
    if not scores or scores[0] <= 0:
        return 0.0
    s1 = scores[0]
    s2 = scores[1] if len(scores) > 1 else 0.0
    return round((1.0 - math.exp(-s1 / 2.0)) * (0.5 + 0.5 * max(0.0, s1 - s2) / s1), 4)


class PlainSearchBaseline:
    """Top BM25 hit as the answer. Optional ``store`` fills citation authors/urls (cosmetic only)."""

    name = "plain"

    def __init__(self, index: _Index, store: Any | None = None, k: int = 5) -> None:
        self.index, self.store, self.k = index, store, k

    def answer(self, question: str, asker_id: str, as_of: date | None = None) -> Answer:
        hits = self._search(question, asker_id, as_of)
        if not hits:
            return Answer(question=question, action=Action.ANSWER, text="", confidence=0.0,
                          policy={"system": self.name})  # fmt: skip
        top = hits[0]
        doc = self._doc(top.doc_id)
        cite = Citation(
            doc_id=top.doc_id,
            quote=top.text,
            author_id=getattr(top, "author_id", None) or getattr(doc, "author_id", "") or "",
            timestamp=_as_datetime(getattr(top, "timestamp", None)),
            url=getattr(top, "url", "") or getattr(doc, "url", "") or "",
            fact_id=getattr(top, "fact_id", None),
        )
        return Answer(
            question=question,
            action=Action.ANSWER,
            text=top.text,
            said=[cite],
            confidence=_score_confidence([float(h.score) for h in hits]),
            fact_ids=[top.fact_id] if getattr(top, "fact_id", None) else [],
            policy={"system": self.name, "k": self.k},
        )

    def _search(self, question: str, asker_id: str, as_of: date | None) -> list[Any]:
        """Raw documents only: a search box has no extracted-fact layer, so it must not borrow Keepline's."""
        try:
            return self.index.search(question, k=self.k, as_of=as_of, visible_to=asker_id, only="docs")
        except TypeError:  # index without the ``only`` extension
            return self.index.search(question, k=self.k, as_of=as_of, visible_to=asker_id)

    def _doc(self, doc_id: str) -> Any:
        if self.store is None:
            return None
        try:
            return self.store.doc(doc_id)
        except Exception:  # noqa: BLE001 -- baseline must never fail on cosmetic lookups
            return None


def _as_datetime(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, date):
        return datetime(ts.year, ts.month, ts.day)
    if isinstance(ts, str) and ts:
        return datetime.fromisoformat(ts)
    return datetime(1970, 1, 1)


class KeeplineSystem:
    """The Keepline agent under a fixed policy (``policy_fn=None`` -> default PolicyParams) or a learned one.

    ``policy_fn`` receives the bandit context ``{"area_id": ..., **agent.context_features(...)}`` and returns the
    PolicyParams to use -- exactly what ``keepline.rl.policy.load_policy()`` returns.
    """

    def __init__(self, agent: _Agent, name: str = "keepline",
                 policy_fn: Callable[[Mapping[str, Any]], PolicyParams] | None = None) -> None:  # fmt: skip
        self.agent, self.name, self.policy_fn = agent, name, policy_fn

    def answer(self, question: str, asker_id: str, as_of: date | None = None) -> Answer:
        params = PolicyParams()
        if self.policy_fn is not None:
            params = self.policy_fn(bandit_context(self.agent, question, asker_id, as_of))
        return self.agent.answer(question, asker_id, as_of=as_of, params=params)

"""Temporal linking: dedup near-duplicates, chain supersessions, surface conflicts (the moat).

Borrowed from Graphiti's bi-temporal edge invalidation: when a newer statement about the same thing changes
its value, the old fact is not deleted -- it is *closed* (``valid_to`` = new ``valid_from``) and linked
(``superseded_by`` / ``supersedes``), so the agent can say "this replaced X on <date>" and never cites a dead
fact as current. When two people disagree without any update signal, both are kept and the weaker one is
marked ``CONTRADICTED`` -- Keepline surfaces the conflict instead of silently picking a winner.

Similarity is idf-weighted over the fact set: words that appear in many facts (verbal tics, boilerplate like
"quick note so it's written down") carry little weight, so two different facts that share a preamble are not
mistaken for versions of one another.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Sequence

from keepline.contracts import Fact, FactKind, Verification
from keepline.memory.extract import UPDATE_CUE
from keepline.retrieval.text import content_set, numbers

# Kinds that describe "how a thing behaves" can supersede each other (a landmine can be restated as a
# rule/decision); identity-like kinds only supersede within themselves.
_BEHAVIOUR = frozenset({FactKind.LANDMINE, FactKind.PROCEDURE, FactKind.RECURRING_TASK, FactKind.DECISION, FactKind.FACT})

DUP_SIMILARITY = 0.6
LINK_SIMILARITY = 0.3
STRONG_SIMILARITY = 0.5
MIN_TEXT_SIMILARITY = 0.2
CONFLICT_WINDOW_DAYS = 30


@dataclass
class LinkResult:
    facts: list[Fact]
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    merged: int = 0
    superseded: int = 0


def compatible(a: FactKind, b: FactKind) -> bool:
    return a == b or (a in _BEHAVIOUR and b in _BEHAVIOUR)


class _Sim:
    """idf-weighted overlap between facts (numbers excluded so a changed value still matches)."""

    def __init__(self, facts: Sequence[Fact]) -> None:
        self.terms: dict[str, frozenset[str]] = {}
        self.subj: dict[str, frozenset[str]] = {}
        df: Counter[str] = Counter()
        for f in facts:
            t = frozenset(x for x in content_set(f.text) if not x[:1].isdigit())
            self.terms[f.id] = t
            self.subj[f.id] = content_set(f.subject or "")
            df.update(t)
        n = max(1, len(facts))
        self.w = {t: math.log(1 + n / c) for t, c in df.items()}

    def _wj(self, a: frozenset[str], b: frozenset[str]) -> float:
        if not a or not b:
            return 0.0
        inter = sum(self.w.get(t, 1.0) for t in a & b)
        union = sum(self.w.get(t, 1.0) for t in a | b)
        return inter / union if union else 0.0

    def text(self, a: Fact, b: Fact) -> float:
        return self._wj(self.terms[a.id], self.terms[b.id])

    def __call__(self, a: Fact, b: Fact) -> float:
        t = self.text(a, b)
        sa, sb = self.subj[a.id], self.subj[b.id]
        return 0.7 * t + 0.3 * self._wj(sa, sb) if sa and sb else t


def _cue(f: Fact) -> bool:
    return bool(UPDATE_CUE.search(f.quote or f.text))


def is_near_duplicate(old: Fact, new: Fact, sim: _Sim) -> bool:
    return numbers(old.text) == numbers(new.text) and sim.text(old, new) >= DUP_SIMILARITY


def update_signal(old: Fact, new: Fact, s: float, text_sim: float) -> bool:
    """New statement updates the old one.

    A changed value ("the 1st" -> "the 1st and 15th") links at moderate similarity; a bare cue word ("now",
    "also") needs a much closer match, because two different rules about one system often share a cue.
    """
    if text_sim < MIN_TEXT_SIMILARITY:  # sharing only a subject ("CoreLink") is not being the same statement
        return False
    n_old, n_new = numbers(old.text), numbers(new.text)
    if n_old and n_new and n_old != n_new and not (n_new < n_old):  # a strict subset is a partial restatement
        return s >= LINK_SIMILARITY
    if old.kind == new.kind and old.kind not in _BEHAVIOUR:  # "our new rep is ...", "X owns it now"
        return _cue(new) and s >= LINK_SIMILARITY
    return _cue(new) and s >= STRONG_SIMILARITY and not (n_old and not n_new)


def disagreement(old: Fact, new: Fact) -> bool:
    n_old, n_new = numbers(old.text), numbers(new.text)
    return bool(n_old and n_new) and n_old != n_new


def merge_into(target: Fact, dup: Fact) -> None:
    """Fold a restatement into an existing fact: more receipts -> higher confidence (noisy-OR, damped)."""
    for d in dup.source_doc_ids:
        if d not in target.source_doc_ids:
            target.source_doc_ids.append(d)
    target.confidence = round(min(0.97, 1 - (1 - target.confidence) * (1 - 0.5 * dup.confidence)), 3)
    if target.area_id is None:
        target.area_id = dup.area_id
    if target.subject is None:
        target.subject = dup.subject
    if target.kind == FactKind.FACT and dup.kind != FactKind.FACT:
        target.kind = dup.kind  # a restatement with a clearer cue sharpens the kind


def supersede(old: Fact, new: Fact) -> None:
    old.valid_to = new.valid_from
    old.superseded_by = new.id
    new.supersedes = old.id
    if new.kind in (FactKind.FACT, FactKind.PROCEDURE) and old.kind != new.kind:
        new.kind = old.kind  # a new version of a landmine/rule is still that landmine/rule
    if new.subject is None:
        new.subject = old.subject
    new.confidence = round(min(0.97, new.confidence + 0.05), 3)  # an explicit update is a strong signal


def link_facts(facts: Sequence[Fact]) -> LinkResult:
    """Process facts chronologically; each new fact is merged, supersedes, conflicts with, or joins its area."""
    ordered = sorted(facts, key=lambda f: (f.valid_from, f.learned_at or 0, f.id))  # type: ignore[arg-type]
    sim = _Sim(ordered)
    by_area: dict[str | None, list[Fact]] = defaultdict(list)
    kept: list[Fact] = []
    res = LinkResult(facts=kept)
    for f in ordered:
        pool = by_area[f.area_id]
        scored = sorted(((sim(o, f), o) for o in pool if compatible(o.kind, f.kind)),
                        key=lambda x: (-x[0], -int(x[1].is_current), x[1].id))
        dup = next((o for s, o in scored if s >= DUP_SIMILARITY * 0.8 and is_near_duplicate(o, f, sim)), None)
        if dup is not None:
            merge_into(dup, f)  # a stale restatement of a superseded fact stays attached to the old version
            res.merged += 1
            continue
        cand = next(((s, o) for s, o in scored if o.is_current and s >= LINK_SIMILARITY), None)
        if cand is not None:
            s, o = cand
            if update_signal(o, f, s, sim.text(o, f)) and (o.kind == f.kind or _cue(f)):
                supersede(o, f)
                res.superseded += 1
            elif disagreement(o, f) and o.stated_by != f.stated_by and (
                (f.valid_from - o.valid_from).days <= CONFLICT_WINDOW_DAYS
            ):
                weaker = o if o.confidence <= f.confidence else f
                weaker.verification = Verification.CONTRADICTED
                res.conflicts.append(
                    {"fact_id_a": o.id, "fact_id_b": f.id, "area_id": f.area_id, "subject": f.subject or o.subject,
                     "note": f"disagree without an update signal; weaker={weaker.id}"}
                )
        pool.append(f)
        kept.append(f)
    return res

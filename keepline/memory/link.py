"""Temporal linking: dedup near-duplicates, chain supersessions, surface conflicts (the moat).

Borrowed from Graphiti's bi-temporal edge invalidation: when a newer statement about the same thing changes
its value, the old fact is not deleted -- it is *closed* (``valid_to`` = new ``valid_from``) and linked
(``superseded_by`` / ``supersedes``), so the agent can say "this replaced X on <date>" and never cites a dead
fact as current. When two people disagree without any update signal, both are kept and the weaker one is
marked ``CONTRADICTED`` -- Keepline surfaces the conflict instead of silently picking a winner.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Sequence

from keepline.contracts import Fact, FactKind, Verification
from keepline.memory.extract import NEGATION, UPDATE_CUE
from keepline.retrieval.text import containment, content_set, jaccard, numbers

# Kinds that describe "how a thing behaves" can supersede each other (a landmine can be restated as a
# rule/decision); identity-like kinds only supersede within themselves.
_BEHAVIOUR = frozenset({FactKind.LANDMINE, FactKind.PROCEDURE, FactKind.RECURRING_TASK, FactKind.DECISION, FactKind.FACT})

DUP_JACCARD = 0.6
LINK_SIMILARITY = 0.3
STRONG_SIMILARITY = 0.5
CONFLICT_WINDOW_DAYS = 30


@dataclass
class LinkResult:
    facts: list[Fact]
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    merged: int = 0
    superseded: int = 0


def compatible(a: FactKind, b: FactKind) -> bool:
    return a == b or (a in _BEHAVIOUR and b in _BEHAVIOUR)


def _subject_set(f: Fact) -> frozenset[str]:
    return content_set(f.subject or "")


def similarity(old: Fact, new: Fact) -> float:
    """Blend of subject overlap and statement overlap; numbers are excluded so a changed value still matches."""
    t_old = frozenset(t for t in content_set(old.text) if not t[:1].isdigit())
    t_new = frozenset(t for t in content_set(new.text) if not t[:1].isdigit())
    text_sim = max(jaccard(t_old, t_new), 0.8 * containment(t_old, t_new) if len(t_old) >= 3 else 0.0)
    s_old, s_new = _subject_set(old), _subject_set(new)
    subj_sim = jaccard(s_old, s_new) if s_old and s_new else 0.0
    return 0.6 * text_sim + 0.4 * subj_sim if s_old and s_new else text_sim


def is_near_duplicate(old: Fact, new: Fact) -> bool:
    if numbers(old.text) != numbers(new.text):
        return False
    if bool(NEGATION.search(old.text)) != bool(NEGATION.search(new.text)):
        return False
    return jaccard(content_set(old.text), content_set(new.text)) >= DUP_JACCARD and not UPDATE_CUE.search(
        new.text.replace(old.text, "")
    )


def update_signal(old: Fact, new: Fact, sim: float) -> bool:
    """New statement explicitly updates or changes the value of the old one.

    A changed value ("the 1st" -> "the 1st and 15th") links at moderate similarity; a bare cue word ("now",
    "also") needs a much closer match, because two different rules about one system often share a cue.
    """
    n_old, n_new = numbers(old.text), numbers(new.text)
    changed_numbers = bool(n_old and n_new and n_old != n_new) and not (n_new < n_old)  # subset = restatement
    cue = bool(UPDATE_CUE.search(new.text))
    if changed_numbers:
        return sim >= LINK_SIMILARITY
    return cue and sim >= STRONG_SIMILARITY and not bool(n_old and not n_new)


def disagreement(old: Fact, new: Fact) -> bool:
    n_old, n_new = numbers(old.text), numbers(new.text)
    negation_flip = bool(NEGATION.search(old.text)) != bool(NEGATION.search(new.text))
    return (bool(n_old and n_new) and n_old != n_new) or negation_flip


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
    by_area: dict[str | None, list[Fact]] = defaultdict(list)
    kept: list[Fact] = []
    res = LinkResult(facts=kept)
    for f in ordered:
        pool = by_area[f.area_id]
        dup = _best(pool, f, lambda o: compatible(o.kind, f.kind) and is_near_duplicate(o, f), prefer_current=True)
        if dup is not None:
            merge_into(dup, f)
            res.merged += 1
            continue
        cand = _best(
            pool, f, lambda o: o.is_current and compatible(o.kind, f.kind) and similarity(o, f) >= LINK_SIMILARITY
        )
        if cand is not None:
            sim = similarity(cand, f)
            if update_signal(cand, f, sim) and (cand.kind == f.kind or UPDATE_CUE.search(f.text)):
                supersede(cand, f)
                res.superseded += 1
            elif disagreement(cand, f) and cand.stated_by != f.stated_by and (
                (f.valid_from - cand.valid_from).days <= CONFLICT_WINDOW_DAYS
            ):
                weaker = cand if cand.confidence <= f.confidence else f
                weaker.verification = Verification.CONTRADICTED
                res.conflicts.append(
                    {"fact_id_a": cand.id, "fact_id_b": f.id, "area_id": f.area_id, "subject": f.subject or cand.subject,
                     "note": f"disagree without an update signal; weaker={weaker.id}"}
                )
            elif disagreement(cand, f) and sim >= STRONG_SIMILARITY:
                supersede(cand, f)  # a later, different value from the same person / much later = the new state
                res.superseded += 1
        pool.append(f)
        kept.append(f)
    return res


def _best(pool: Sequence[Fact], f: Fact, pred: Any, prefer_current: bool = False) -> Fact | None:
    best, best_key = None, None
    for o in pool:
        if not pred(o):
            continue
        key = (o.is_current if prefer_current else True, similarity(o, f), o.valid_from, o.id)
        if best_key is None or key > best_key:
            best, best_key = o, key
    return best

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
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Sequence

from keepline.contracts import Fact, FactKind, Verification
from keepline.memory.extract import UPDATE_CUE
from keepline.retrieval.text import content_set, numbers, stem

# Kinds that describe "how a thing behaves" can supersede each other (a landmine can be restated as a
# rule/decision); identity-like kinds only supersede within themselves.
_BEHAVIOUR = frozenset({FactKind.LANDMINE, FactKind.PROCEDURE, FactKind.RECURRING_TASK, FactKind.DECISION, FactKind.FACT})

DUP_SIMILARITY = 0.6
LINK_SIMILARITY = 0.3
STRONG_SIMILARITY = 0.5
MIN_TEXT_SIMILARITY = 0.2
SLOT_TEXT_SIMILARITY = 0.15
RARE_DF = 12  # a topic word shared by <= this many facts anchors cross-area linking
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


_WD = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_NUMW = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
_NUMW.update({"fifteen": "15", "twenty": "20", "thirty": "30", "forty-five": "45", "sixty": "60", "ninety": "90"})
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\b(\d{1,2}):(\d{2})\b|\b(\w+) o'?clock\b")
_QTY = re.compile(r"\b(\d{1,5}|" + "|".join(_NUMW) + r")(st|nd|rd|th)?(?:[\s-]+(?:business |calendar |working )?([a-z]+))?")
_NOISE = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b|\S+@\S+|https?://\S+|\b\d{4}-\d{2}-\d{2}\b|\b20\d\d\b")


def slots(text: str) -> dict[str, frozenset[str]]:
    """Typed values in a statement: {'time': {'10'}, 'weekday': {'monday'}, 'ord': {'1','15'}, 'day': {'90'}}.

    Only a change within the *same* slot type counts as a changed value ("due Monday 10am" -> "Friday 4pm";
    "90 days" -> "60 days"), so "90 days to dispute" never looks like a new version of "15 calendar days".
    """
    low = _NOISE.sub(" ", text).lower()
    out: dict[str, set[str]] = defaultdict(set)
    for w in _WD:
        if re.search(rf"\b{w}s?\b", low):
            out["weekday"].add(w)
    for m in _TIME.finditer(low):
        if m.group(6):
            v = _NUMW.get(m.group(6))
            if v:
                out["time"].add(v)
        elif m.group(4):
            out["time"].add(m.group(4).lstrip("0") + ("" if m.group(5) == "00" else ":" + m.group(5)))
        else:
            out["time"].add(m.group(1).lstrip("0") + ("" if not m.group(2) or m.group(2) == "00" else ":" + m.group(2)))
    timeless = _TIME.sub(" ", low)
    for m in _QTY.finditer(timeless):
        val = _NUMW.get(m.group(1), m.group(1)).lstrip("0") or "0"
        if m.group(2):
            out["ord"].add(val)
        elif m.group(3) and len(m.group(3)) > 2 and m.group(3) not in {"and", "the", "for", "per", "our", "was"}:
            out[stem(m.group(3))].add(val)
    return {k: frozenset(v) for k, v in out.items()}


def slot_changed(old: Fact, new: Fact) -> bool:
    so, sn = slots(old.text), slots(new.text)
    return any(so[k] != sn[k] and not (sn[k] < so[k]) for k in so.keys() & sn.keys())


def update_signal(old: Fact, new: Fact, s: float, text_sim: float) -> bool:
    """New statement updates the old one.

    A changed value ("the 1st" -> "the 1st and 15th") links at moderate similarity; a bare cue word ("now",
    "also") needs a much closer match, because two different rules about one system often share a cue.
    """
    n_old, n_new = numbers(old.text), numbers(new.text)
    if slot_changed(old, new):
        # a changed slot (time / weekday / ordinal day / count of the same unit) is a new version of the value
        return text_sim >= SLOT_TEXT_SIMILARITY
    if n_old and n_new and n_old != n_new:
        return False  # values differ but in different slots: two different statements
    if text_sim < MIN_TEXT_SIMILARITY:  # sharing only a subject ("CoreLink") is not being the same statement
        return False
    if old.kind == new.kind and old.kind not in _BEHAVIOUR:  # "our new rep is ...", "X owns it now"
        return _cue(new) and s >= LINK_SIMILARITY
    return _cue(new) and s >= STRONG_SIMILARITY and not (n_old and not n_new)


def disagreement(old: Fact, new: Fact) -> bool:
    return slot_changed(old, new)


def merge_into(target: Fact, dup: Fact) -> None:
    """Fold a restatement into an existing fact: more receipts -> higher confidence (noisy-OR, damped)."""
    for d in dup.source_doc_ids:
        if d not in target.source_doc_ids:
            target.source_doc_ids.append(d)
    target.confidence = round(min(0.97, 1 - (1 - target.confidence) * (1 - 0.5 * dup.confidence)), 3)
    target.valid_from = min(target.valid_from, dup.valid_from)  # a fact dates from its earliest receipt
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


def _subject_match(a: Fact, b: Fact) -> bool:
    """Same subject: shared subject/topic word, allowing abbreviations ("recon" ~ "reconciliation")."""
    ta = content_set(f"{a.subject or ''} {a.text}")
    tb = content_set(f"{b.subject or ''} {b.text}")
    if ta & tb - {"job", "run", "time", "day"}:
        return True
    return any(len(x) >= 4 and len(y) >= 4 and (x.startswith(y) or y.startswith(x)) for x in ta for y in tb)


def _pure_restatement(g: Fact, f: Fact, sf: dict[str, frozenset[str]], sim: "_Sim") -> bool:
    """f states exactly the value set of the current fact g (same typed slots AND same raw numbers), about the
    same subject and area. Anything with a differing or additional value is a new version, never a restatement."""
    if not sf or not g.is_current or g.valid_from >= f.valid_from or g.area_id != f.area_id:
        return False
    if slots(g.text) != sf or numbers(g.text) != numbers(f.text) or not compatible(g.kind, f.kind):
        return False
    return sim.text(g, f) >= SLOT_TEXT_SIMILARITY or _subject_match(g, f)


def link_facts(facts: Sequence[Fact]) -> LinkResult:
    """Process facts chronologically; each new fact is merged, supersedes, conflicts with, or is added.

    Candidates are earlier facts in the same area *or* sharing a rare topic word (area linking is noisy:
    "timesheet cutoff" may land in payroll one day and payments the next). A changed slot value (time,
    weekday, count) on such a pair is an update even without cue words; when it is, every other current
    restatement of the old value is closed too.
    """
    ordered = sorted(facts, key=lambda f: (f.valid_from, f.learned_at or 0, f.id))  # type: ignore[arg-type]
    sim = _Sim(ordered)
    df = Counter(t for f in ordered for t in sim.terms[f.id])
    by_area: dict[str | None, list[Fact]] = defaultdict(list)
    by_rare: dict[str, list[Fact]] = defaultdict(list)
    kept: list[Fact] = []
    res = LinkResult(facts=kept)
    for f in ordered:
        rare = [t for t in sim.terms[f.id] if df[t] <= RARE_DF]
        pool = {o.id: o for o in by_area[f.area_id]}
        for t in rare:
            pool.update((o.id, o) for o in by_rare[t])
        scored = sorted(((sim(o, f), o) for o in pool.values() if compatible(o.kind, f.kind)),
                        key=lambda x: (-x[0], -int(x[1].is_current), x[1].id))
        dup = next((o for s, o in scored if s >= DUP_SIMILARITY * 0.8 and is_near_duplicate(o, f, sim)), None)
        if dup is not None:
            merge_into(dup, f)  # a stale restatement of a superseded fact stays attached to the old version
            res.merged += 1
            continue
        # A restatement of a value already current in an earlier fact ("now skips the 1st AND the 15th" after the
        # May rule said the same) is another receipt for that fact, so versions date from the EARLIEST statement.
        sf = slots(f.text)
        twins = [g for _s, g in scored if _pure_restatement(g, f, sf, sim)]
        twin = min(twins, key=lambda g: (g.valid_from, g.id)) if twins else None  # earliest statement of the value
        if twin is not None:
            # Only when f would otherwise have become the new version of some older fact: those older facts are
            # closed at the twin's (earliest) date instead, and f becomes one more receipt for the twin. The set of
            # supersession links is unchanged; only the date is corrected.
            targets = [o for s2, o in scored
                       if o is not twin and o.is_current and o.valid_from <= twin.valid_from and s2 >= SLOT_TEXT_SIMILARITY
                       and (o.area_id == f.area_id or set(rare) & sim.terms[o.id])
                       and update_signal(o, f, s2, sim.text(o, f)) and (o.kind == f.kind or _cue(f) or slot_changed(o, f))]
            if targets:
                merge_into(twin, f)
                res.merged += 1
                for o in targets:
                    o.valid_to, o.superseded_by = twin.valid_from, twin.id
                    twin.supersedes = twin.supersedes or o.id
                    res.superseded += 1
                continue
        linked = False
        for s, o in scored:
            if not o.is_current or s < SLOT_TEXT_SIMILARITY:
                continue
            same_area = o.area_id == f.area_id
            shares_rare = bool(set(rare) & sim.terms[o.id])
            if not (same_area or shares_rare):
                continue
            if update_signal(o, f, s, sim.text(o, f)) and (o.kind == f.kind or _cue(f) or slot_changed(o, f)):
                if not linked:
                    supersede(o, f)
                    linked = True
                else:  # another current restatement of the same old value
                    o.valid_to, o.superseded_by = f.valid_from, f.id
                res.superseded += 1
            elif not linked and s >= LINK_SIMILARITY and disagreement(o, f) and o.stated_by != f.stated_by and (
                (f.valid_from - o.valid_from).days <= CONFLICT_WINDOW_DAYS
            ):
                weaker = o if o.confidence <= f.confidence else f
                weaker.verification = Verification.CONTRADICTED
                res.conflicts.append(
                    {"fact_id_a": o.id, "fact_id_b": f.id, "area_id": f.area_id, "subject": f.subject or o.subject,
                     "note": f"disagree without an update signal; weaker={weaker.id}"}
                )
                break
            if not linked and s < LINK_SIMILARITY:
                break
        by_area[f.area_id].append(f)
        for t in rare:
            by_rare[t].append(f)
        kept.append(f)
    return res

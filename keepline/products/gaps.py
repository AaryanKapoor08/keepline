"""Gap-interview questions: what should we ask this person *before* they leave?

Each candidate comes from a concrete signal in the memory (a decision with no recorded reason, a landmine without
a "why", a question Keepline had to abstain on, a critical fact backed by a single receipt...). Priority is
``area risk x expected information gain`` so the 20 minutes you get with a departing expert go to the answers
that are both fragile and valuable.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from keepline.config import DEMO_TODAY
from keepline.contracts import AreaRisk, Fact, FactKind, GapQuestion, Verification

from keepline.products._common import (
    CRITICAL_KINDS,
    STRONG_EXPERTISE,
    StoreLike,
    _safe,
    has_reason,
    is_incident,
    ql_action,
    ql_area,
    safe_query_log,
    short_title,
)

# Expected information gain per signal (how much a good answer would change what the org knows).
GAIN = {
    "landmine_no_why": 1.0,
    "decision_no_reason": 0.9,
    "abstained": 0.85,
    "incident_no_cause": 0.8,
    "single_receipt": 0.5,
    "owned_area_uncovered": 0.6,
}
RISK_FLOOR = 0.15  # even a "safe" area deserves a question if the signal is strong


def _person_facts(store: StoreLike, person_id: str, areas: set[str]) -> list[Fact]:
    """Facts this person stated, plus current facts in the areas they hold (they are the one who can explain them)."""
    own = _safe(lambda: store.facts(person_id=person_id, current_only=True)) or []
    seen = {f.id for f in own}
    extra: list[Fact] = []
    for a in areas:
        for f in _safe(lambda: store.facts(area_id=a, current_only=True)) or []:
            if f.id not in seen:
                seen.add(f.id)
                extra.append(f)
    return own + extra


def _candidates(store: StoreLike, person_id: str, facts: list[Fact], areas: set[str]) -> list[tuple[str, GapQuestion]]:
    out: list[tuple[str, GapQuestion]] = []

    def add(signal: str, area: str | None, q: str, reason: str, ids: list[str]) -> None:
        out.append((signal, GapQuestion(person_id, area, q, reason, 0.0, ids)))

    for f in facts:
        t = short_title(f, 90)
        if f.kind == FactKind.LANDMINE and not has_reason(f.text):
            add("landmine_no_why", f.area_id, f"Why is this a rule: “{t}”? What actually breaks if someone does it?",
                "Landmine with no recorded reason", [f.id])
        elif f.kind == FactKind.DECISION and not has_reason(f.text):
            add("decision_no_reason", f.area_id, f"What was the reason behind “{t}”? What would make us revisit it?",
                "Decision with no recorded reason", [f.id])
        elif is_incident(f.text) and not has_reason(f.text):
            add("incident_no_cause", f.area_id, f"What caused “{t}”, and how would someone else spot it next time?",
                "Incident with no recorded explanation", [f.id])
        elif f.kind in CRITICAL_KINDS and len(f.source_doc_ids) <= 1 and f.verification != Verification.VERIFIED:
            add("single_receipt", f.area_id, f"Can you confirm this is still true: “{t}”?",
                "Critical fact backed by a single receipt", [f.id])

    misses = Counter(
        (ql_area(e), str(e.get("question", "")).strip())
        for e in safe_query_log(store, limit=10_000)
        if ql_action(e) in ("abstain", "route") and ql_area(e) in areas and e.get("question")
    )
    for (area, q), n in misses.most_common(6):
        add("abstained", area, f"People asked “{q}” and Keepline had no receipt. What is the answer?",
            f"Keepline abstained {n}x on this", [])

    covered = {f.area_id for f in facts if f.kind in CRITICAL_KINDS}
    for a in sorted(areas - covered):
        area = _safe(lambda: store.area(a))
        if area:
            add("owned_area_uncovered", a, f"For {area.name}: which accesses, vendor contacts or recurring jobs only you handle?",
                "Area you hold with no captured access/recurring knowledge", [])
    return out


def gap_questions(
    store: StoreLike,
    person_id: str,
    *,
    n: int = 8,
    today: date | None = None,
    risks: list[AreaRisk] | None = None,
) -> list[GapQuestion]:
    """Top-``n`` interview questions for ``person_id``, ranked by area risk x expected information gain."""
    if risks is None:
        from keepline.products.risk import risk_map

        risks = risk_map(store, today or DEMO_TODAY, with_trend=False)
    risk_by_area = {r.area_id: r.risk for r in risks}
    held = {e.area_id for e in _safe(lambda: store.expertise(person_id=person_id)) or [] if e.score >= STRONG_EXPERTISE}
    facts = _person_facts(store, person_id, held)
    ranked: list[GapQuestion] = []
    seen: set[str] = set()
    for signal, g in _candidates(store, person_id, facts, held):
        key = g.question.lower()
        if key in seen:
            continue
        seen.add(key)
        g.priority = round(max(RISK_FLOOR, risk_by_area.get(g.area_id or "", 0.0)) * GAIN[signal], 4)
        ranked.append(g)
    ranked.sort(key=lambda g: g.priority, reverse=True)
    return ranked[:n]

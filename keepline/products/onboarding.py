"""Onboarding brief for a new joiner (Alex): who to ask, what was decided and why, what not to touch.

Everything is drawn from receipts in the memory. "Who to ask" names people from evidence of work (tickets closed,
facts stated), and says so; if the best person is leaving, the brief says who to ask *after* they go.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from keepline.contracts import Area, AreaRisk, BriefSection, Fact, FactKind, OnboardingBrief, Person

from keepline.products._common import (
    StoreLike,
    _safe,
    citations_for,
    doc_area,
    doc_citation,
    first_name,
    has_left,
    looks_like_fact,
    people_by_id,
    short_title,
)
from keepline.products.handoff import successor
from keepline.products.risk import risk_level, risk_map

RECENT_DECISION_DAYS = 120
MAX_AREAS = 6


def _relevant_areas(store: StoreLike, person: Person | None, people: dict[str, Person]) -> list[Area]:
    """Areas the joiner's team works in, strongest team evidence first (falls back to all areas)."""
    areas = _safe(store.areas) or []
    if person is None:
        return areas[:MAX_AREAS]
    team = {p.id for p in people.values() if p.team == person.team and p.id != person.id}
    weight: dict[str, float] = {}
    for a in areas:
        exps = _safe(lambda: store.expertise(area_id=a.id)) or []
        weight[a.id] = sum(e.score for e in exps if e.person_id in team)
    ranked = sorted((a for a in areas if weight.get(a.id, 0) > 0), key=lambda a: (-weight[a.id], -a.criticality, a.id))
    return (ranked or sorted(areas, key=lambda a: -a.criticality))[:MAX_AREAS]


def _who_to_ask(store: StoreLike, areas: list[Area], people: dict[str, Person], joiner: str, today: date) -> BriefSection:
    rows: list[dict[str, Any]] = []
    for a in areas:
        exps = sorted(_safe(lambda: store.expertise(area_id=a.id)) or [], key=lambda e: e.score, reverse=True)
        exps = [e for e in exps if e.person_id != joiner and not has_left(people.get(e.person_id), today)]
        if not exps:
            rows.append({"area_id": a.id, "area": a.name, "person_id": None, "person": "Nobody on record",
                         "why": "No one has evidence of knowing this yet. Flag it to your manager.", "citations": []})
            continue
        top = exps[0]
        p = people.get(top.person_id)
        why = f"{top.n_tickets_closed} closed tickets, {top.n_docs} messages, {top.n_facts_stated} facts stated"
        after = None
        if p and p.departure_date and p.departure_date >= today:
            learner, reviewer = successor(exps, people, top.person_id, today)
            nxt = reviewer or learner
            after = (f"{first_name(store, top.person_id)} leaves {p.departure_date:%b %d}; after that ask "
                     f"{first_name(store, nxt)}.") if nxt else f"{first_name(store, top.person_id)} leaves {p.departure_date:%b %d}; nobody else on record."
        stated = _safe(lambda: store.facts(area_id=a.id, person_id=top.person_id, current_only=True)) or []
        rows.append({
            "area_id": a.id, "area": a.name, "person_id": top.person_id, "person": p.name if p else top.person_id,
            "why": why, "after": after, "citations": citations_for(store, stated[0], limit=1) if stated else [],
        })
    return BriefSection("Who to ask about what", rows)


def _recent_decisions(store: StoreLike, areas: list[Area], today: date) -> BriefSection:
    ids = {a.id for a in areas}
    cutoff = today - timedelta(days=RECENT_DECISION_DAYS)
    facts = [
        f for f in _safe(lambda: store.facts(kinds=[FactKind.DECISION], current_only=True)) or []
        if f.area_id in ids and cutoff <= f.valid_from <= today and looks_like_fact(f.text)
    ]
    facts.sort(key=lambda f: f.valid_from, reverse=True)
    rows = []
    for f in facts[:8]:
        prev = _safe(lambda: store.fact(f.supersedes)) if f.supersedes else None
        rows.append({
            "area_id": f.area_id, "decision": f.text, "date": f.valid_from.isoformat(),
            "by": first_name(store, f.stated_by) if f.stated_by else "inferred",
            "replaces": prev.text if prev else None, "fact_id": f.id, "citations": citations_for(store, f, limit=2),
        })
    return BriefSection("Recent decisions & why", rows)


def _risks_and_landmines(store: StoreLike, areas: list[Area], risks: list[AreaRisk]) -> BriefSection:
    ids = {a.id for a in areas}
    rows: list[dict[str, Any]] = []
    for r in risks:
        if r.area_id in ids and risk_level(r.risk) != "low":
            rows.append({"type": "risk", "area_id": r.area_id, "title": f"{r.area_name}: bus factor {r.bus_factor}",
                         "detail": r.explanation, "level": risk_level(r.risk), "citations": []})
    for f in _safe(lambda: store.facts(kinds=[FactKind.LANDMINE], current_only=True)) or []:
        if f.area_id in ids and looks_like_fact(f.text):
            rows.append({"type": "landmine", "area_id": f.area_id, "title": short_title(f), "detail": f.text,
                         "fact_id": f.id, "citations": citations_for(store, f, limit=2)})
    return BriefSection("Open risks & landmines", rows)


def _glossary(store: StoreLike, areas: list[Area]) -> BriefSection:
    """Jargon = system names + area keywords; defined by the first receipt that mentions them, else the area."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in areas:
        facts = [f for f in _safe(lambda: store.facts(area_id=a.id, current_only=True)) or [] if looks_like_fact(f.text)]
        for term in [*a.systems, *[k for k in a.keywords if k[:1].isupper() or len(k) <= 5]][:6]:
            if term.lower() in seen:
                continue
            seen.add(term.lower())
            hit: Fact | None = next((f for f in facts if re.search(rf"\b{re.escape(term)}\b", f.text, re.I)), None)
            rows.append({
                "term": term, "area_id": a.id, "area": a.name,
                "definition": hit.text if hit else f"Part of {a.name}: {a.description}",
                "citations": citations_for(store, hit, limit=1) if hit else [],
            })
    return BriefSection("Jargon", rows[:16])


def _starter_tasks(store: StoreLike, areas: list[Area], people: dict[str, Person], joiner: str, today: date) -> BriefSection:
    """Real open tickets from the team, each paired with an expert who stays -- learning by doing, reviewed."""
    rows: list[dict[str, Any]] = []
    for a in areas[:4]:
        exps = sorted(_safe(lambda: store.expertise(area_id=a.id)) or [], key=lambda e: e.score, reverse=True)
        stay = [e for e in exps if e.person_id != joiner and not (people.get(e.person_id) and people[e.person_id].departure_date)]
        buddy = stay[0].person_id if stay else None
        tickets = []
        for e in exps[:3]:
            tickets += [t for t in _safe(lambda: store.open_tickets(e.person_id)) or [] if doc_area(store, t) in (None, a.id)]
        if tickets:
            t = tickets[0]
            rows.append({"area_id": a.id, "task": f"{t.container}: {t.title or 'open ticket'}", "buddy_id": buddy,
                         "buddy": first_name(store, buddy) if buddy else "your manager", "citations": [doc_citation(t)]})
        else:
            rows.append({"area_id": a.id, "task": f"Shadow the next {a.name} run and write down each step",
                         "buddy_id": buddy, "buddy": first_name(store, buddy) if buddy else "your manager", "citations": []})
    return BriefSection("Starter tasks", rows)


def build_onboarding_brief(store: StoreLike, person_id: str, today: date, *, risks: list[AreaRisk] | None = None) -> OnboardingBrief:
    people = people_by_id(store)
    person = people.get(person_id)
    areas = _relevant_areas(store, person, people)
    risks = risks if risks is not None else risk_map(store, today, with_trend=False)
    return OnboardingBrief(
        person_id=person_id,
        generated_at=datetime.combine(today, datetime.min.time()),
        team=person.team if person else "",
        sections=[
            _who_to_ask(store, areas, people, person_id, today),
            _recent_decisions(store, areas, today),
            _risks_and_landmines(store, areas, risks),
            _glossary(store, areas),
            _starter_tasks(store, areas, people, person_id, today),
        ],
    )

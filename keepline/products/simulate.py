"""What-if simulation: recompute the risk map with a person removed, and a tiny project-staffing helper.

These are planning aids for managers. They never feed performance processes and never score individuals: removing
a person only removes their *evidence of knowing* topics from the redundancy calculation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from datetime import date

from keepline.contracts import AreaRisk, FactKind

from keepline.products._common import StoreLike, _safe, is_strong, people_by_id
from keepline.products.handoff import successor
from keepline.products.risk import risk_map


def what_if_leaves(store: StoreLike, person_id: str, today: date) -> tuple[list[AreaRisk], list[AreaRisk]]:
    """(before, after) risk maps; ``after`` treats ``person_id`` as gone today. Same area order as ``before``."""
    before = risk_map(store, today, with_trend=False)
    after_by_id = {r.area_id: r for r in risk_map(store, today, exclude_person_ids=(person_id,), with_trend=False)}
    after = [after_by_id[r.area_id] for r in before if r.area_id in after_by_id]
    return before, after


def newly_orphaned(before: list[AreaRisk], after: list[AreaRisk]) -> list[str]:
    """Area ids that had a holder before and have none after -- the headline of a what-if."""
    b = {r.area_id: r.bus_factor for r in before}
    return [r.area_id for r in after if r.bus_factor == 0 and b.get(r.area_id, 0) > 0]


@dataclass
class StaffingPlan:
    area_id: str
    area_name: str
    bus_factor_before: int
    bus_factor_after: int
    team_holders: list[str]
    pair_learner: str | None
    pair_reviewer: str | None
    matched_terms: list[str] = field(default_factory=list)


def areas_in_brief(store: StoreLike, brief: str) -> dict[str, list[str]]:
    """Areas a free-text project brief touches, by keyword/system/name match. Returns {area_id: matched terms}."""
    text = brief.lower()
    hits: dict[str, list[str]] = {}
    for a in _safe(store.areas) or []:
        terms = [a.name, *a.systems, *a.keywords]
        matched = [t for t in terms if t and re.search(rf"\b{re.escape(t.lower())}\b", text)]
        if matched:
            hits[a.id] = sorted(set(matched), key=str.lower)
    return hits


def staff_project(store: StoreLike, brief: str, team: list[str], today: date) -> list[StaffingPlan]:
    """For each area the brief touches: bus factor within the proposed team, and a learner+reviewer pairing that
    would raise it by one. ``bus_factor_after`` assumes the pairing is approved and the learner ramps up."""
    people = people_by_id(store)
    plans = []
    for area_id, terms in areas_in_brief(store, brief).items():
        area = _safe(lambda: store.area(area_id))
        exps = _safe(lambda: store.expertise(area_id=area_id)) or []
        holders = [e.person_id for e in exps if e.person_id in team and is_strong(e)]
        learner, reviewer = successor(exps, people, "", today)
        if learner in holders:
            learner = next((pid for pid in team if pid not in holders), None)
        plans.append(StaffingPlan(
            area_id=area_id, area_name=area.name if area else area_id,
            bus_factor_before=len(holders), bus_factor_after=len(holders) + (1 if learner else 0),
            team_holders=holders, pair_learner=learner, pair_reviewer=reviewer or (holders[0] if holders else None),
            matched_terms=terms,
        ))
    plans.sort(key=lambda p: (p.bus_factor_before, p.area_name))
    return plans


_ONLY = re.compile(r"\b(only|sole|nobody else|no one else|just me|that's it)\b", re.I)


def what_breaks(store: StoreLike, person_id: str, today: date) -> list[dict[str, Any]]:
    """Concrete things that stop working if ``person_id`` leaves today -- the headline of a what-if.

    * landmines in areas nobody else holds (the rule stops being enforced by anyone)
    * recurring tasks they state with no other holder of the area (nobody does them)
    * vendor contacts they are the source for (the relationship walks out)
    * access where the receipt says they are the only admin/holder
    """
    from keepline.products._common import citations_for, full_name, is_strong, looks_like_fact

    people = people_by_id(store)
    person = people.get(person_id)
    first = person.name.split()[0].lower() if person else person_id

    def others_hold(area_id: str | None) -> bool:
        if not area_id:
            return True
        return any(is_strong(e) and e.person_id != person_id and not (people.get(e.person_id) and people[e.person_id].departure_date)
                   for e in _safe(lambda: store.expertise(area_id=area_id)) or [])

    held = {e.area_id for e in _safe(lambda: store.expertise(person_id=person_id)) or [] if is_strong(e)}
    facts = {f.id: f for f in _safe(lambda: store.facts(person_id=person_id, current_only=True)) or []}
    for a in held:
        if not others_hold(a):
            for f in _safe(lambda: store.facts(area_id=a, kinds=[FactKind.LANDMINE], current_only=True)) or []:
                facts.setdefault(f.id, f)

    out: list[dict[str, Any]] = []
    for f in facts.values():
        if not looks_like_fact(f.text):
            continue
        typ, why = None, ""
        if f.kind == FactKind.LANDMINE and f.area_id in held and not others_hold(f.area_id):
            typ, why = "orphaned_landmine", "Nobody left holds this area to enforce the rule."
        elif f.kind == FactKind.RECURRING_TASK and not others_hold(f.area_id):
            typ, why = "unowned_recurring_task", "No remaining holder of the area does this."
        elif f.kind == FactKind.VENDOR_CONTACT and f.stated_by == person_id:
            typ, why = "vendor_contact_lost", "They are the source for this vendor relationship."
        elif f.kind in (FactKind.ACCESS, FactKind.OWNER) and _ONLY.search(f.text) and (
                first in f.text.lower() or (f.stated_by == person_id and re.search(r"\b(i'm|i am|me|my)\b", f.text, re.I))):
            typ, why = "sole_access", "The receipt says they are the only one with this access."
        if typ is None:
            continue
        cit = next(iter(citations_for(store, f, limit=1)), None)
        area = _safe(lambda: store.area(f.area_id)) if f.area_id else None
        out.append({
            "type": typ, "why": why, "fact_id": f.id, "text": f.text, "kind": str(f.kind),
            "area_id": f.area_id, "area_name": area.name if area else None,
            "stated_by": f.stated_by, "stated_by_name": full_name(store, f.stated_by) if f.stated_by else None,
            "date": f.valid_from.isoformat(), "quote": cit.quote if cit else f.quote,
            "doc_id": cit.doc_id if cit else None, "url": cit.url if cit else "",
        })
    order = ["sole_access", "orphaned_landmine", "vendor_contact_lost", "unowned_recurring_task"]
    out.sort(key=lambda x: (order.index(x["type"]), x["area_id"] or "", x["fact_id"]))
    return out


def what_if_report(store: StoreLike, person_id: str, today: date) -> dict[str, Any]:
    """JSON-ready what-if: before/after risk per area, newly orphaned areas, and the what-breaks list."""
    from keepline.contracts import to_dict

    before, after = what_if_leaves(store, person_id, today)
    breaks = what_breaks(store, person_id, today)
    counts: dict[str, int] = {}
    for b in breaks:
        counts[b["type"]] = counts.get(b["type"], 0) + 1
    return {
        "person_id": person_id,
        "today": today.isoformat(),
        "before": to_dict(before),
        "after": to_dict(after),
        "orphaned_areas": newly_orphaned(before, after),
        "breaks": breaks,
        "break_counts": counts,
        "note": "Planning aid for managers. Never tied to performance.",
    }

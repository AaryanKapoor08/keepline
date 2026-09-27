"""What-if simulation: recompute the risk map with a person removed, and a tiny project-staffing helper.

These are planning aids for managers. They never feed performance processes and never score individuals: removing
a person only removes their *evidence of knowing* topics from the redundancy calculation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from keepline.contracts import AreaRisk

from keepline.products._common import STRONG_EXPERTISE, StoreLike, _safe, people_by_id
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
        holders = [e.person_id for e in exps if e.person_id in team and e.score >= STRONG_EXPERTISE]
        learner, reviewer = successor([e for e in exps if e.person_id not in holders or e.score >= STRONG_EXPERTISE],
                                      people, "", today)
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

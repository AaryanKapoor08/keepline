"""Project staffing: paste a project brief, see which knowledge areas it leans on and how fragile each is.

For every area the brief touches: who holds it today (and who is leaving), the bus factor now, and a
learner + reviewer pairing that would raise it. A manager approves; this never feeds performance processes.
JSON-serializable output (served by the API).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from keepline.contracts import FactKind

from keepline.products._common import StoreLike, _safe, countdown, is_strong, looks_like_fact, people_by_id
from keepline.products.handoff import successor
from keepline.products.risk import risk_level, risk_map
from keepline.products.simulate import areas_in_brief


def plan_project(store: StoreLike, brief_text: str, today: date) -> dict[str, Any]:
    people = people_by_id(store)
    risks = {r.area_id: r for r in risk_map(store, today, with_trend=False)}
    touched = areas_in_brief(store, brief_text)
    rows: list[dict[str, Any]] = []
    for area_id, terms in touched.items():
        area = _safe(lambda: store.area(area_id))
        exps = sorted(_safe(lambda: store.expertise(area_id=area_id)) or [], key=lambda e: -e.score)
        strong = [e for e in exps if is_strong(e)]
        leaving = {e.person_id for e in strong if (p := people.get(e.person_id)) and p.departure_date and p.departure_date >= today}
        staying = [e for e in strong if e.person_id not in leaving]
        top_leaver = next((e.person_id for e in strong if e.person_id in leaving), "")
        learner, reviewer = successor(exps, people, top_leaver, today)
        if learner in {e.person_id for e in staying}:  # already a holder: pick the next non-holder instead
            learner = next((e.person_id for e in exps if e.person_id not in {s.person_id for s in strong}
                            and e.person_id not in leaving), None)
        before = len(staying)
        after = before + (1 if learner else 0)
        r = risks.get(area_id)
        landmines = [f.text for f in _safe(lambda: store.facts(area_id=area_id, kinds=[FactKind.LANDMINE], current_only=True)) or []
                     if looks_like_fact(f.text)][:3]
        rows.append({
            "area_id": area_id,
            "area_name": area.name if area else area_id,
            "matched_terms": terms,
            "risk": r.risk if r else None,
            "risk_level": risk_level(r.risk) if r else None,
            "holders": [{"person_id": e.person_id, "name": people[e.person_id].name if e.person_id in people else e.person_id,
                         "score": round(e.score, 3), "leaving_in_days": countdown(people.get(e.person_id), today)
                         if e.person_id in leaving else None} for e in strong],
            "bus_factor_before": before,
            "bus_factor_after": after,
            "learner": learner, "learner_name": people[learner].name if learner in people else None,
            "reviewer": reviewer, "reviewer_name": people[reviewer].name if reviewer in people else None,
            "rationale": _rationale(before, after, leaving, people, learner, reviewer),
            "landmines": landmines,
        })
    rows.sort(key=lambda x: (x["bus_factor_before"], -(x["risk"] or 0)))
    warnings = [f"{x['area_name']}: nobody staying holds it" for x in rows if x["bus_factor_before"] == 0]
    return {
        "brief": brief_text,
        "today": today.isoformat(),
        "areas": rows,
        "summary": {
            "areas_touched": len(rows),
            "single_points_of_failure": sum(1 for x in rows if x["bus_factor_before"] <= 1),
            "after_pairing": sum(1 for x in rows if x["bus_factor_after"] <= 1),
        },
        "warnings": warnings,
        "note": "Suggestions only. A manager approves pairings; this is never used to evaluate people.",
    }


def _rationale(before: int, after: int, leaving: set[str], people: dict[str, Any], learner: str | None, reviewer: str | None) -> str:
    parts = []
    if leaving:
        parts.append(f"{', '.join(people[p].name.split()[0] for p in leaving if p in people)} leaving")
    parts.append(f"bus factor {before} today")
    if learner:
        who = people[learner].name.split()[0] if learner in people else learner
        rev = f" with {people[reviewer].name.split()[0]} reviewing" if reviewer in people else ""
        parts.append(f"pair {who}{rev} to reach {after}")
    return "; ".join(parts) + "."

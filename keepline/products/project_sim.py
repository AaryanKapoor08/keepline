"""Project simulator: staff a future project from the knowledge graph and estimate knowledge risk over its timeline.

Ideas borrowed from truck-factor analysis (who holds each area), skills-matrix staffing (cover every required
area), knowledge-transfer pairing (a learner works next to a holder), and Monte Carlo schedule-risk analysis
(sample plausible futures, count how often a required area has nobody available who knows it).

Pure and deterministic for a seed. JSON-safe output. It never scores individual performance: the only per-person
inputs are *evidence of knowing an area* and *known HR dates*; unplanned absence uses the same small background
rate for everyone. Every output is a recommendation a manager approves.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from keepline.contracts import FactKind
from keepline.products._common import StoreLike, _safe, is_strong, people_by_id
from keepline.products.simulate import areas_in_brief

TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "corelink_v3",
        "name": "Upgrade CoreLink API to v3",
        "weeks": 12,
        "brief": "Upgrade the CoreLink API integration to v3: new API keys, updated nightly reconciliation, "
                 "and ACH settlement files re-tested before cutover.",
    },
    {
        "id": "mobile_app",
        "name": "Launch new mobile banking app",
        "weeks": 16,
        "brief": "Launch a new mobile banking app on top of the member portal and online banking: SSL certificates "
                 "and DNS for the new domain, Okta identity and access, and debit card controls.",
    },
    {
        "id": "fintrac",
        "name": "FINTRAC reporting overhaul",
        "weeks": 16,
        "brief": "Overhaul FINTRAC reporting and AML monitoring, including large cash transaction reports fed from "
                 "ACH payments and the nightly reconciliation.",
    },
]

OPTIONS = {
    "fastest": "Fastest: the strongest holder leads each area, no pairing.",
    "balanced": "Balanced: holders lead, a learner pairs on single-holder areas, nobody carries more than 2 areas.",
    "resilient": "Resilient: a second holder reviews where one exists, and a learner pairs on every area.",
}

UNPLANNED_ABSENCE_PER_MONTH = 0.03  # same for everyone: illness, family leave, vacation clusters
TRANSFER_WEEKS = 4  # weeks a learner must work alongside an available holder before they can cover the area
TRANSFER_SUCCESS = 0.8  # even with enough overlap, a transfer sometimes does not stick
SELF_STUDY_WEEKS = 6  # with no holder around, a learner can ramp from the captured receipts instead...
SELF_STUDY_MAX = 0.6  # ...but that sticks less often, scaled by how much of the area is documented
DOC_FACTS_FULL = 40  # facts captured in an area that count as "well documented"


@dataclass
class _Area:
    id: str
    name: str
    holders: list[str]  # strong, strongest first
    candidates: list[str]  # non-holders with some evidence, strongest first
    landmines: int
    recurring: int
    documented: float  # 0..1, how much of the area is captured in memory


def _weeks_until(d: date | None, start: date) -> int | None:
    if d is None:
        return None
    return (d - start).days // 7


def _available_weeks(pid: str, departures: dict[str, int | None], weeks: int) -> int:
    dep = departures.get(pid)
    return weeks if dep is None else max(0, min(weeks, dep))


def _areas(store: StoreLike, area_ids: list[str]) -> list[_Area]:
    out = []
    for aid in area_ids:
        a = _safe(lambda: store.area(aid))
        exps = sorted(_safe(lambda: store.expertise(area_id=aid)) or [], key=lambda e: -e.score)
        holders = [e.person_id for e in exps if is_strong(e)]
        team_of = {pid: p.team for pid, p in people_by_id(store).items()}
        holder_teams = {team_of.get(h) for h in holders}
        cands = [e.person_id for e in exps if not is_strong(e) and e.enough_data and e.score > 0.05
                 and team_of.get(e.person_id) != "leadership"]  # managers approve plans; they are not staffed as learners
        cands.sort(key=lambda p: team_of.get(p) not in holder_teams)  # same-team learners first (stable)
        facts = _safe(lambda: store.facts(area_id=aid, current_only=True)) or []
        out.append(_Area(aid, a.name if a else aid, holders, cands,
                         sum(1 for f in facts if f.kind == FactKind.LANDMINE),
                         sum(1 for f in facts if f.kind == FactKind.RECURRING_TASK),
                         min(1.0, len(facts) / DOC_FACTS_FULL)))
    return out


def _staff(option: str, areas: list[_Area], departures: dict[str, int | None], weeks: int) -> dict[str, dict[str, Any]]:
    load: dict[str, int] = {}
    cap = 2 if option == "balanced" else 99
    plan: dict[str, dict[str, Any]] = {}

    def pick(pool: list[str], exclude: set[str], need_stay: bool = False) -> str | None:
        ranked = sorted(pool, key=lambda p: (-_available_weeks(p, departures, weeks), pool.index(p)))
        for p in ranked:
            if p in exclude or load.get(p, 0) >= cap:
                continue
            if need_stay and _available_weeks(p, departures, weeks) < weeks:
                continue
            return p
        return None

    for a in areas:
        lead = pick(a.holders, set()) or (a.holders[0] if a.holders else None)
        team = {lead} if lead else set()
        reviewer = learner = None
        if option == "resilient":
            reviewer = pick(a.holders, team)
            if reviewer:
                team.add(reviewer)
        if option == "resilient" or (option == "balanced" and len(a.holders) <= 1):
            learner = pick(a.candidates, team, need_stay=True)
        for p in (lead, reviewer, learner):
            if p:
                load[p] = load.get(p, 0) + 1
        plan[a.id] = {"lead": lead, "reviewer": reviewer, "learner": learner}
    return plan


def _simulate(areas: list[_Area], plan: dict[str, dict[str, Any]], departures: dict[str, int | None], weeks: int,
              runs: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    people = sorted({p for v in plan.values() for p in v.values() if p})
    p_absent = 1 - (1 - UNPLANNED_ABSENCE_PER_MONTH) ** (weeks / 4.33)
    any_gap = 0
    end_gap = 0
    total_gap_weeks = 0
    area_end = {a.id: 0 for a in areas}
    area_gap = {a.id: 0 for a in areas}
    area_weeks = {a.id: 0 for a in areas}
    first_gap: list[int] = []
    for _ in range(runs):
        avail = {}
        for p in people:
            dep = departures.get(p)
            row = [dep is None or w < dep for w in range(weeks)]
            if rng.random() < p_absent:  # an unplanned 1-3 week absence somewhere in the project
                s = rng.randrange(weeks)
                for w in range(s, min(weeks, s + rng.randint(1, 3))):
                    row[w] = False
            avail[p] = row
        run_first = None
        run_end = False
        for a in areas:
            pl = plan[a.id]
            knowers = [p for p in (pl["lead"], pl["reviewer"]) if p]
            learner_ready = None
            if pl["learner"]:
                overlap, ready_at = 0, None
                for w in range(weeks):
                    if avail[pl["learner"]][w] and any(avail[k][w] for k in knowers):
                        overlap += 1
                        if overlap >= TRANSFER_WEEKS:
                            ready_at = w + 1
                            break
                if ready_at is not None and rng.random() < TRANSFER_SUCCESS:
                    learner_ready = ready_at
                elif ready_at is None and rng.random() < SELF_STUDY_MAX * a.documented:
                    learner_ready = SELF_STUDY_WEEKS  # ramped from Keepline's receipts instead of a person
            gap_weeks = 0
            for w in range(weeks):
                ok = any(avail[k][w] for k in knowers)
                if not ok and learner_ready is not None and w >= learner_ready and avail[pl["learner"]][w]:
                    ok = True
                if not ok:
                    gap_weeks += 1
                    run_first = w if run_first is None else min(run_first, w)
            if gap_weeks and not ok:  # still uncovered in the final week
                area_end[a.id] += 1
                run_end = True
            total_gap_weeks += gap_weeks
            if gap_weeks:
                area_gap[a.id] += 1
                area_weeks[a.id] += gap_weeks
        end_gap += run_end
        if run_first is not None:
            any_gap += 1
            first_gap.append(run_first)
    first_gap.sort()
    return {
        "runs": runs,
        "p_any_uncovered": round(any_gap / runs, 4),
        "p_uncovered_at_end": round(end_gap / runs, 4),
        "expected_gap_weeks": round(total_gap_weeks / runs, 1),
        "median_first_gap_week": first_gap[len(first_gap) // 2] + 1 if first_gap else None,
        "areas": {a.id: {"p_uncovered": round(area_gap[a.id] / runs, 4), "p_uncovered_at_end": round(area_end[a.id] / runs, 4),
                         "expected_gap_weeks": round(area_weeks[a.id] / runs, 2)} for a in areas},
    }


def simulate_project(store: StoreLike, brief: str, today: date, *, weeks: int = 12, start: date | None = None,
                     leaves: dict[str, int] | None = None, runs: int = 2000, seed: int = 7) -> dict[str, Any]:
    """Staffing options + Monte Carlo knowledge-coverage risk for a project brief.

    ``leaves`` = {person_id: week} forces an extra departure mid-project (the "what if X leaves" toggle).
    """
    start = start or today
    people = people_by_id(store)
    touched = areas_in_brief(store, brief)
    areas = _areas(store, list(touched))
    departures: dict[str, int | None] = {pid: _weeks_until(p.departure_date, start) for pid, p in people.items()}
    for pid, w in (leaves or {}).items():
        departures[pid] = w if departures.get(pid) is None else min(departures[pid], w)  # type: ignore[type-var]
    end = start + timedelta(weeks=weeks)

    def name(p: str | None) -> str | None:
        return people[p].name if p and p in people else None

    timeline = [{"person_id": pid, "name": name(pid), "week": w, "date": (start + timedelta(weeks=w)).isoformat(),
                 "forced": pid in (leaves or {})}
                for pid, w in sorted(departures.items(), key=lambda x: (x[1] is None, x[1] or 0))
                if w is not None and 0 <= w < weeks]
    options = []
    for opt in OPTIONS:
        plan = _staff(opt, areas, departures, weeks)
        sim = _simulate(areas, plan, departures, weeks, runs, seed)
        load: dict[str, int] = {}
        for v in plan.values():
            for p in v.values():
                if p:
                    load[p] = load.get(p, 0) + 1
        rows = []
        for a in areas:
            pl = plan[a.id]
            knowers = [p for p in (pl["lead"], pl["reviewer"]) if p]
            staying = [p for p in knowers if _available_weeks(p, departures, weeks) >= weeks]
            leaving = [{"person_id": p, "name": name(p), "week": departures[p]} for p in knowers if p not in staying]
            bf_before = sum(1 for h in a.holders if _available_weeks(h, departures, weeks) >= weeks)
            rows.append({
                "area_id": a.id, "area_name": a.name,
                "lead": pl["lead"], "lead_name": name(pl["lead"]),
                "reviewer": pl["reviewer"], "reviewer_name": name(pl["reviewer"]),
                "learner": pl["learner"], "learner_name": name(pl["learner"]),
                "holders": a.holders, "bus_factor_before": bf_before,
                "bus_factor_after": bf_before + (1 if pl["learner"] else 0),
                "leaving": leaving, "landmines": a.landmines, "recurring_tasks": a.recurring,
                "status": "lack" if not staying and not pl["learner"] else "weak" if len(staying) + (1 if pl["learner"] else 0) <= 1 else "strong",
                **sim["areas"][a.id],
            })
        busiest = max(load.items(), key=lambda x: x[1]) if load else (None, 0)
        options.append({
            "id": opt, "label": opt.capitalize(), "description": OPTIONS[opt],
            "people": sorted(load), "busiest": {"person_id": busiest[0], "name": name(busiest[0]), "areas": busiest[1]},
            "coverage": round(sum(1 for r in rows if r["status"] != "lack") / max(1, len(rows)), 3),
            "p_any_uncovered": sim["p_any_uncovered"], "median_first_gap_week": sim["median_first_gap_week"],
            "p_uncovered_at_end": sim["p_uncovered_at_end"], "expected_gap_weeks": sim["expected_gap_weeks"],
            "areas": rows,
            "lack": [r["area_name"] for r in rows if r["status"] == "lack"],
            "strong": [r["area_name"] for r in rows if r["status"] == "strong"],
            "lose": [{"area": r["area_name"], **l, "landmines": r["landmines"], "recurring_tasks": r["recurring_tasks"]}
                     for r in rows for l in r["leaving"]],
        })
    best = min(options, key=lambda o: (o["p_uncovered_at_end"], o["expected_gap_weeks"], o["busiest"]["areas"]))
    return {
        "brief": brief, "today": today.isoformat(), "start": start.isoformat(), "end": end.isoformat(), "weeks": weeks,
        "areas": [{"area_id": a.id, "area_name": a.name, "holders": a.holders, "matched": touched[a.id],
                   "documented": round(a.documented, 2)} for a in areas],
        "timeline": timeline, "options": options, "recommended": best["id"], "runs": runs, "seed": seed,
        "assumptions": {
            "unplanned_absence_per_month": UNPLANNED_ABSENCE_PER_MONTH, "transfer_weeks": TRANSFER_WEEKS,
            "transfer_success": TRANSFER_SUCCESS, "self_study_weeks": SELF_STUDY_WEEKS, "self_study_max": SELF_STUDY_MAX,
            "note": "Recommendations for a manager to approve. Uses evidence of who knows what and HR dates only; "
                    "never individual performance.",
        },
    }

"""Knowledge risk map: which topics is the company about to forget?

    risk = importance x (1 - redundancy) x departure_likelihood

* **importance** -- customer's criticality prior plus evidence the topic matters: incidents, decisions, landmines,
  dependencies (systems shared with other areas) and how often people ask about it (query log). Normalized [0, 1].
* **redundancy** -- saturating in the number of people with *strong* expertise evidence (the bus factor).
  One holder => 0; two => 0.55; three => 0.80.
* **departure_likelihood** -- from HR dates only (see ``_common.departure_likelihood``). Never behavioural.

Everything is topic-level: the map says "only one person has evidence of knowing reconciliation", it never scores
how a person behaves.
"""

from __future__ import annotations

import calendar
import logging
from collections import Counter
from datetime import date

from keepline.config import DEMO_TODAY
from keepline.contracts import Area, AreaRisk, DepartureType, Expertise, Fact, FactKind, Person

from keepline.products._common import (
    is_strong,
    StoreLike,
    _safe,
    countdown,
    departure_likelihood,
    has_left,
    is_incident,
    normalize,
    people_by_id,
    safe_query_log,
    ql_area,
    to_date,
)

log = logging.getLogger(__name__)

# Weight of the customer-provided criticality prior vs. evidence signals inside importance.
PRIOR_WEIGHT = 0.45
SIGNAL_WEIGHTS = {"incidents": 0.2, "decisions": 0.15, "landmines": 0.25, "dependencies": 0.15, "asks": 0.25}
REDUNDANCY_DECAY = 0.45  # 1 - REDUNDANCY_DECAY ** (bus_factor - 1)
# A departure date is treated as "known to the org" this long before the last day (retirements are announced early).
NOTICE_WINDOW_DAYS = {DepartureType.RETIREMENT: 180, DepartureType.CONTRACT_END: 90}
DEFAULT_NOTICE_DAYS = 45


def redundancy_from_bus_factor(bus_factor: int) -> float:
    return 0.0 if bus_factor <= 1 else round(1 - REDUNDANCY_DECAY ** (bus_factor - 1), 4)


def _importance_signals(store: StoreLike, areas: list[Area], facts_by_area: dict[str, list[Fact]]) -> dict[str, dict[str, float]]:
    asks = Counter(a for a in (ql_area(e) for e in safe_query_log(store, limit=10_000)) if a)
    systems_by_area = {a.id: {s.lower() for s in a.systems} for a in areas}
    raw: dict[str, dict[str, float]] = {k: {} for k in SIGNAL_WEIGHTS}
    for a in areas:
        fs = facts_by_area.get(a.id, [])
        raw["incidents"][a.id] = sum(1 for f in fs if is_incident(f.text))
        raw["decisions"][a.id] = sum(1 for f in fs if f.kind == FactKind.DECISION)
        raw["landmines"][a.id] = sum(1 for f in fs if f.kind == FactKind.LANDMINE and f.is_current)
        shared = sum(1 for o in areas if o.id != a.id and systems_by_area[a.id] & systems_by_area[o.id])
        raw["dependencies"][a.id] = len(a.systems) + 2 * shared
        raw["asks"][a.id] = asks.get(a.id, 0)
    return {k: normalize(v) for k, v in raw.items()}


def _importance(area: Area, signals: dict[str, dict[str, float]]) -> float:
    prior = max(1, min(3, area.criticality)) / 3
    evidence = sum(w * signals[k].get(area.id, 0.0) for k, w in SIGNAL_WEIGHTS.items())
    return round(min(1.0, PRIOR_WEIGHT * prior + (1 - PRIOR_WEIGHT) * evidence / sum(SIGNAL_WEIGHTS.values())), 4)


def _explain(
    store: StoreLike,
    area: Area,
    holders: list[Expertise],
    lost: list[Expertise],
    people: dict[str, Person],
    today: date,
) -> str:
    def name(pid: str) -> str:
        p = people.get(pid)
        return p.name.split()[0] if p else pid.title()

    def ev(e: Expertise) -> str:
        parts = [f"{e.n_docs} messages"]
        if e.n_tickets_closed:
            parts.append(f"{e.n_tickets_closed} closed tickets")
        if e.n_facts_stated:
            parts.append(f"{e.n_facts_stated} facts stated")
        return ", ".join(parts)

    if not holders and lost:
        who = " and ".join(name(e.person_id) for e in lost[:2])
        return f"Nobody left holds {area.name}: all strong evidence came from {who} ({ev(lost[0])})."
    if not holders:
        return f"No one has strong recent evidence of knowing {area.name}; treat as unknown, not safe."
    top = holders[0]
    when = ""
    p = people.get(top.person_id)
    if p and p.departure_date:
        d = (p.departure_date - today).days
        when = f" {name(top.person_id)}'s last day is in {d} days." if d >= 0 else ""
    if len(holders) == 1:
        return f"Only {name(top.person_id)} has hands-on evidence for {area.name} in 6 months: {ev(top)}.{when}"
    others = ", ".join(name(e.person_id) for e in holders[1:3])
    return f"{len(holders)} people hold {area.name}: {name(top.person_id)} ({ev(top)}), plus {others}.{when}"


def _area_risk(
    store: StoreLike,
    area: Area,
    importance: float,
    facts: list[Fact],
    people: dict[str, Person],
    today: date,
    excluded: set[str],
) -> AreaRisk:
    exps = sorted(_safe(lambda: store.expertise(area_id=area.id)) or [], key=lambda e: e.score, reverse=True)
    gone = {pid for pid, p in people.items() if has_left(p, today)} | excluded
    present = [e for e in exps if e.person_id not in gone]
    strong = [e for e in present if is_strong(e)]
    lost = [e for e in exps if e.person_id in gone and is_strong(e)]
    bus = len(strong)
    enough = any(e.enough_data for e in exps) and bool(exps)

    if strong:
        # The holder whose departure hurts most: likelihood weighted by their share of the area's evidence, so a
        # leaver who is a minor holder of an area does not make it look as fragile as one they carry alone.
        top_score = max(e.score for e in strong) or 1.0

        def weighted(e: Expertise) -> float:
            return departure_likelihood(people.get(e.person_id), today) * (e.score / top_score)

        at_risk = max(strong, key=lambda e: (weighted(e), e.score))
        dl = weighted(at_risk)
        at_risk_id: str | None = at_risk.person_id
        cd = countdown(people.get(at_risk_id), today)
    elif lost:
        # Knowledge already orphaned (holder removed / gone): certain loss, no countdown left.
        dl, at_risk_id, cd = 1.0, lost[0].person_id, 0
    elif present:
        # Only weak evidence: the most knowledgeable weak holder is the de-facto keeper.
        at_risk_id = present[0].person_id
        dl = departure_likelihood(people.get(at_risk_id), today)
        cd = countdown(people.get(at_risk_id), today)
    else:
        dl, at_risk_id, cd = 0.5, None, None  # nobody at all: unknown, flagged with enough_data=False

    redundancy = redundancy_from_bus_factor(bus)
    risk = round(importance * (1 - redundancy) * dl, 4)
    last = max((e.last_active for e in exps if e.last_active), default=None)
    return AreaRisk(
        area_id=area.id,
        area_name=area.name,
        importance=importance,
        redundancy=redundancy,
        departure_likelihood=round(dl, 4),
        risk=risk,
        bus_factor=bus,
        experts=[(e.person_id, round(e.score, 3)) for e in present[:5]],
        countdown_days=cd if cd is None or cd >= 0 else 0,
        at_risk_person_id=at_risk_id,
        n_facts=sum(1 for f in facts if f.is_current),
        n_landmines=sum(1 for f in facts if f.kind == FactKind.LANDMINE and f.is_current),
        last_touched=to_date(last),
        enough_data=enough,
        explanation=_explain(store, area, strong or present[:1], lost, people, today),
    )


def risk_map(store: StoreLike, today: date, *, exclude_person_ids: tuple[str, ...] | list[str] = (), with_trend: bool = True) -> list[AreaRisk]:
    """Risk per area, highest first. ``exclude_person_ids`` powers the what-if ("remove Sarah")."""
    areas = _safe(store.areas) or []
    people = people_by_id(store)
    all_facts = _safe(lambda: store.facts()) or []
    by_area: dict[str, list[Fact]] = {}
    for f in all_facts:
        if f.area_id:
            by_area.setdefault(f.area_id, []).append(f)
    signals = _importance_signals(store, areas, by_area)
    excluded = set(exclude_person_ids)
    out = []
    for a in areas:
        r = _area_risk(store, a, _importance(a, signals), by_area.get(a.id, []), people, today, excluded)
        if with_trend:
            r.trend = risk_history(store, a.id, months=6, today=today, _importance_value=r.importance)
            if r.trend:
                r.trend[-1] = r.risk
        out.append(r)
    out.sort(key=lambda r: r.risk, reverse=True)
    return out


def _month_ends(today: date, months: int) -> list[date]:
    """Month-end dates for the last ``months`` months; the current (partial) month ends today."""
    ends = [today]
    y, m = today.year, today.month
    for _ in range(months - 1):
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        ends.append(date(y, m, calendar.monthrange(y, m)[1]))
    return list(reversed(ends))


def risk_history(
    store: StoreLike,
    area_id: str,
    months: int = 6,
    *,
    today: date | None = None,
    _importance_value: float | None = None,
) -> list[float]:
    """Monthly risk trend (oldest -> newest), as the org could have seen it at each month end.

    Holders are today's strong holders (the bus factor); what changes month to month is what the org *knew*: a
    departure date only counts once it is inside the notice window of that month end (retirements are announced
    earlier than resignations). The last point is the live score, so the sparkline and the map always agree.
    """
    today = today or DEMO_TODAY
    area = _safe(lambda: store.area(area_id))
    if area is None:
        return []
    people = people_by_id(store)
    importance = _importance_value if _importance_value is not None else max(1, min(3, area.criticality)) / 3
    strong = [e for e in _safe(lambda: store.expertise(area_id=area_id)) or [] if is_strong(e)]
    top = max((e.score for e in strong), default=1.0) or 1.0
    redundancy = redundancy_from_bus_factor(len(strong))

    def known_dl(pid: str, end: date) -> float:
        p = people.get(pid)
        window = NOTICE_WINDOW_DAYS.get(p.departure_type, DEFAULT_NOTICE_DAYS) if p and p.departure_type else DEFAULT_NOTICE_DAYS
        if p and p.departure_date and (p.departure_date - end).days <= window:
            return departure_likelihood(p, end)
        return departure_likelihood(None, end)

    trend = []
    for end in _month_ends(today, months):
        d = max((known_dl(e.person_id, end) * e.score / top for e in strong), default=0.5)
        trend.append(round(importance * (1 - redundancy) * d, 4))
    return trend


def risk_level(risk: float) -> str:
    """Bucket for badges/colors. Thresholds tuned so a bus-factor-1 critical area with a departure date is 'high'."""
    if risk >= 0.45:
        return "high"
    if risk >= 0.2:
        return "medium"
    return "low"

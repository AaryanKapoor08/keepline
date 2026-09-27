"""Decision check: "before you do X, here is what the company already knows that X collides with."

Given a proposed action ("Rotate the CoreLink API key this Friday"), find the current landmines, decisions,
recurring tasks and access facts it touches, reason about the day it would happen (weekday / day-of-month from
``today``), and return a verdict with receipts. Deterministic, no LLM, JSON-serializable output (served by the API).
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any

from keepline.contracts import Fact, FactKind

from keepline.products._common import (
    StoreLike,
    _safe,
    departure_likelihood,
    full_name,
    is_strong,
    looks_like_fact,
    people_by_id,
)

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fifth": 5, "tenth": 10, "fifteenth": 15, "twentieth": 20,
                  "thirtieth": 30, "last": -1}
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_PROHIBIT = re.compile(r"\b(never|don'?t|do not|must not|mustn'?t|shouldn'?t|should not|cannot|can'?t|avoid|skip|skips|"
                       r"not allowed|no one should|careful)\b", re.I)
_REVERSAL = re.compile(r"\b(revert|undo|roll ?back|move back|stop|remove|disable|drop|cancel|turn off|switch back)\b", re.I)
_STOP = set("""a an the and or but to of in on at for by with from this that these those it its is are was were be been
will would should could can do does did we our us i you your my me they them their he she his her as if then than so
just now today tomorrow next week weekend please also any all some into onto up out over about via per new""".split())
KINDS = (FactKind.LANDMINE, FactKind.DECISION, FactKind.RECURRING_TASK, FactKind.ACCESS, FactKind.PROCEDURE)
MIN_RELEVANCE = 2.0


# ------------------------------------------------------------------------------------------------ text


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _terms(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9][a-z0-9'-]*", text.lower()) if w not in _STOP and len(w) > 2}


# ------------------------------------------------------------------------------------------------ dates


def target_dates(text: str, today: date) -> list[date]:
    """Dates the proposal would happen on, resolved against ``today`` (a Friday "this Friday" is today)."""
    t = text.lower()
    out: list[date] = []
    if re.search(r"\b(today|tonight|right now|asap)\b", t):
        out.append(today)
    if "tomorrow" in t:
        out.append(today + timedelta(days=1))
    if "weekend" in t:
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        out += [sat, sat + timedelta(days=1)]
    for m in re.finditer(r"\b(this|next|on)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b", t):
        delta = (WEEKDAYS.index(m.group(2)) - today.weekday()) % 7
        if m.group(1) == "next" and delta == 0:
            delta = 7
        out.append(today + timedelta(days=delta))
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        out.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in re.finditer(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b", t):
        mo, d = _MONTHS[m.group(1)], int(m.group(2))
        y = today.year + (1 if (mo, d) < (today.month, today.day) else 0)
        out.append(date(y, mo, min(d, calendar.monthrange(y, mo)[1])))
    for d in _days_of_month(t, proposal=True):
        out.append(_next_day_of_month(today, d))
    if re.search(r"\b(month[- ]end|end of (the )?month)\b", t):
        out.append(_next_day_of_month(today, -1))
    return sorted(set(out))


def _next_day_of_month(today: date, day: int) -> date:
    y, m = today.year, today.month
    for _ in range(13):
        last = calendar.monthrange(y, m)[1]
        d = date(y, m, last if day == -1 else min(day, last))
        if d >= today:
            return d
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return today


def _days_of_month(t: str, *, proposal: bool = False) -> set[int]:
    days = {int(x) for x in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)\b", t) if 1 <= int(x) <= 31}
    if not proposal:
        days |= {v for k, v in _ORDINAL_WORDS.items() if re.search(rf"\bthe {k}\b", t) and v > 0}
        if re.search(r"\b(month[- ]end|last (business )?day of (the )?month)\b", t):
            days.add(-1)
    return days


def _weekdays(t: str) -> set[int]:
    """Weekdays a rule mentions, including common abbreviations ("never on Wed")."""
    t = t.lower()
    return {i for i, d in enumerate(WEEKDAYS) if re.search(rf"\b({d}s?|{d[:3]}|{d[:4]})\b", t)}


def _date_clash(fact_text: str, targets: list[date]) -> tuple[bool | None, str]:
    """(clash?, reason). None = the fact carries no day constraint."""
    wd, dom = _weekdays(fact_text), _days_of_month(fact_text.lower())
    if not wd and not dom:
        return None, ""
    for d in targets:
        last = calendar.monthrange(d.year, d.month)[1]
        if d.weekday() in wd:
            return True, f"{d:%A %b %d} is a {WEEKDAYS[d.weekday()].title()}"
        if d.day in dom or (-1 in dom and d.day == last):
            return True, f"{d:%b %d} is the {d.day}{_suffix(d.day)} of the month"
    rule_days = [WEEKDAYS[i].title() + "s" for i in sorted(wd)] + [f"the {x}{_suffix(x)}" if x > 0 else "month-end" for x in sorted(dom)]
    if targets:
        return False, f"rule applies on {', '.join(rule_days)}; planned date avoids it"
    return False, f"rule applies on {', '.join(rule_days)}; no date given, so check the day"


def _suffix(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


# ------------------------------------------------------------------------------------------------ matching


def _areas_touched(store: StoreLike, text: str) -> dict[str, float]:
    t = text.lower()
    hits: dict[str, float] = {}
    for a in _safe(store.areas) or []:
        score = 0.0
        for term in [a.name, *a.systems]:
            if term and re.search(rf"\b{re.escape(term.lower())}\b", t):
                score += 2
        for term in a.keywords:
            if len(term) > 2 and re.search(rf"\b{re.escape(term.lower())}\b", t):
                score += 1
        if score:
            hits[a.id] = score
    return hits


def _relevance(prop_terms: set[str], fact: Fact, area_terms: set[str]) -> float:
    ft = _terms(fact.text + " " + (fact.subject or ""))
    overlap = prop_terms & ft
    return len(overlap) + sum(1.0 for w in overlap if w in area_terms)


def _same_action(fact: Fact, proposal: str) -> bool:
    """Does the rule talk about the same action on the same thing? (verb of the proposal, or strong overlap)"""
    words = [w for w in re.findall(r"[a-z0-9'-]+", proposal.lower()) if w not in _STOP and len(w) > 2]
    ft = _terms(fact.text)
    verb = _stem(words[0]) if words else ""
    return verb in ft or len(_terms(proposal) & ft) >= 3


def _classify(fact: Fact, proposal: str, targets: list[date]) -> tuple[str, str]:
    """(severity, why): conflict | caution | info."""
    clash, date_why = _date_clash(fact.text, targets)
    prohibits = bool(_PROHIBIT.search(fact.text)) and _same_action(fact, proposal)
    if fact.kind == FactKind.LANDMINE or prohibits:
        if clash and not _same_action(fact, proposal):
            return "caution", f"Related rule and {date_why}; check whether it applies."
        if clash:
            return "conflict", f"Rule: {date_why}."
        if clash is False:
            return ("info" if targets else "caution"), f"Related rule, {date_why}."
        return ("conflict" if prohibits else "caution"), "The proposal does what this rule warns against." if prohibits \
            else "The proposal touches a rule people rely on."
    if fact.kind == FactKind.DECISION:
        if _REVERSAL.search(proposal):
            return "conflict", "The proposal would reverse a current decision; the people who made it should agree."
        return "caution", "A current decision covers this; check it still holds."
    if fact.kind == FactKind.RECURRING_TASK:
        return "caution", ("A recurring task runs on that day." if clash else "A recurring task depends on this.")
    if fact.kind == FactKind.ACCESS:
        return "caution", "Needs access held by specific people (see who)."
    return "info", "Related procedure."


def _receipt(store: StoreLike, f: Fact) -> dict[str, Any]:
    doc = _safe(lambda: store.doc(f.source_doc_ids[0])) if f.source_doc_ids else None
    return {
        "fact_id": f.id, "text": f.text, "kind": str(f.kind), "area_id": f.area_id,
        "stated_by": f.stated_by, "stated_by_name": full_name(store, f.stated_by) if f.stated_by else None,
        "date": f.valid_from.isoformat(), "quote": f.quote or (doc.text[:200] if doc else ""),
        "doc_id": doc.id if doc else (f.source_doc_ids[0] if f.source_doc_ids else None),
        "url": doc.url if doc else "", "source_type": str(doc.source_type) if doc else None,
    }


def check_decision(store: StoreLike, proposal_text: str, *, today: date, proposer_id: str | None = None,
                   limit: int = 8) -> dict[str, Any]:
    """Verdict ("conflict" | "caution" | "clear") for a proposed action, with the facts it collides with."""
    areas = _areas_touched(store, proposal_text)
    area_terms = set()
    for a in _safe(store.areas) or []:
        if a.id in areas:
            area_terms |= _terms(" ".join([a.name, *a.systems, *a.keywords]))
    prop_terms = _terms(proposal_text)
    targets = target_dates(proposal_text, today)

    scored: list[tuple[float, Fact]] = []
    for f in _safe(lambda: store.facts(kinds=list(KINDS), current_only=True)) or []:
        if not looks_like_fact(f.text):
            continue
        rel = _relevance(prop_terms, f, area_terms) + (1.0 if f.area_id in areas else 0.0)
        if rel >= MIN_RELEVANCE + (0 if f.area_id in areas else 1):
            scored.append((rel, f))
    scored.sort(key=lambda x: (-x[0], x[1].id))

    rank = {"conflict": 0, "caution": 1, "info": 2}
    items = []
    for rel, f in scored[: limit * 3]:
        sev, why = _classify(f, proposal_text, targets)
        items.append({**_receipt(store, f), "severity": sev, "why": why, "relevance": round(rel, 2)})
    items.sort(key=lambda x: (rank[x["severity"]], -x["relevance"]))
    items = items[:limit]
    verdict = "conflict" if any(i["severity"] == "conflict" for i in items) else (
        "caution" if any(i["severity"] == "caution" for i in items) else "clear")

    people = people_by_id(store)
    related: dict[str, dict[str, Any]] = {}
    for i in items:
        if i["stated_by"] and i["stated_by"] != proposer_id:
            related.setdefault(i["stated_by"], {"reason": "stated a rule or decision this touches"})
    holders = []
    for aid in areas:
        for e in _safe(lambda: store.expertise(area_id=aid)) or []:
            if is_strong(e) and e.person_id != proposer_id:
                holders.append(e)
                related.setdefault(e.person_id, {"reason": "holds this area"})
    related_people = []
    for pid, info in related.items():
        p = people.get(pid)
        related_people.append({
            "person_id": pid, "name": p.name if p else pid, "role": p.role if p else "", **info,
            "leaving_on": p.departure_date.isoformat() if p and p.departure_date and p.departure_date >= today else None,
        })
    staying = [e for e in sorted(holders, key=lambda e: -e.score) if departure_likelihood(people.get(e.person_id), today) < 0.5]
    if not staying:  # every strong holder is leaving: best-evidenced person who stays, so the review outlives them
        staying = [e for aid in areas for e in (_safe(lambda: store.expertise(area_id=aid)) or [])
                   if e.person_id != proposer_id and departure_likelihood(people.get(e.person_id), today) < 0.5]
        staying.sort(key=lambda e: -e.score)
    reviewer = staying[0].person_id if staying else (holders[0].person_id if holders else next(iter(related), None))

    return {
        "proposal": proposal_text,
        "today": today.isoformat(),
        "verdict": verdict,
        "target_dates": [d.isoformat() for d in targets],
        "areas": [{"area_id": a, "area_name": (store.area(a).name if _safe(lambda: store.area(a)) else a)} for a in areas],
        "conflicts": items,
        "related_people": related_people,
        "suggested_reviewer": reviewer,
        "suggested_reviewer_name": full_name(store, reviewer) if reviewer else None,
    }

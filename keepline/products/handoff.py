"""Handoff pack: everything that walks out the door with a departing person, with receipts.

Sections follow what practitioners say actually breaks after someone leaves -- not "background knowledge" but
access, vendor contacts, recurring jobs, unresolved promises and landmines. Every item carries its citations; the
departing person reviews each one (confirm / correct / remove) and signs off. Suggested owners are suggestions:
a manager approves them.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from keepline.contracts import (
    AreaRisk,
    Expertise,
    Fact,
    FactKind,
    HandoffItem,
    HandoffPack,
    Person,
)

from keepline.products._common import (
    CRITICAL_KINDS,
    STRONG_EXPERTISE,
    StoreLike,
    _safe,
    _snippet,
    citations_for,
    doc_area,
    doc_citation,
    first_name,
    has_left,
    is_pending,
    people_by_id,
    redact_secrets,
    short_title,
)
from keepline.products.gaps import gap_questions

SECTION_ORDER = (
    "access",
    "vendor_contacts",
    "recurring_tasks",
    "unresolved_work",
    "landmines",
    "decisions",
    "key_links_people",
    "suggested_owners",
)
SECTION_TITLES = {
    "access": "Access & ownership",
    "vendor_contacts": "Vendor contacts only they know",
    "recurring_tasks": "Recurring tasks only they do",
    "unresolved_work": "Unresolved work",
    "landmines": "Landmines",
    "decisions": "Decisions they made (and why)",
    "key_links_people": "Key links & people per area",
    "suggested_owners": "Suggested new owners",
}
_KIND_SECTION = {
    FactKind.ACCESS: "access",
    FactKind.OWNER: "access",
    FactKind.VENDOR_CONTACT: "vendor_contacts",
    FactKind.RECURRING_TASK: "recurring_tasks",
    FactKind.LANDMINE: "landmines",
    FactKind.DECISION: "decisions",
}
# "I'll send that Monday", "will follow up next week", "I can finish it by Friday"...
_PROMISE = re.compile(
    r"\b(i'?ll|i will|will|i can|let me)\s+(send|share|follow up|get back|finish|look into|fix|write up|update|"
    r"circle back|check|sort out|handle|ping|draft)\b[^.?!\n]{0,80}",
    re.I,
)
PROMISE_LOOKBACK_DAYS = 30


def successor(experts: list[Expertise], people: dict[str, Person], leaving: str, today: date) -> tuple[str | None, str | None]:
    """(learner, reviewer) for an area. Prefer pairing a learner (some evidence) with the strongest remaining expert.

    Returns person ids; either may be None. A human approves; this is a suggestion, never an assignment.
    """
    remaining = [
        e for e in sorted(experts, key=lambda e: e.score, reverse=True)
        if e.person_id != leaving and not has_left(people.get(e.person_id), today)
        and not (people.get(e.person_id) and people[e.person_id].departure_date)
    ]
    if not remaining:
        return None, None
    reviewer = remaining[0]
    learners = [e for e in remaining[1:] if 0.05 <= e.score < STRONG_EXPERTISE + 0.25]
    if reviewer.score >= STRONG_EXPERTISE and learners:
        return learners[0].person_id, reviewer.person_id
    return reviewer.person_id, None


def _held_areas(store: StoreLike, person_id: str) -> list[Expertise]:
    exps = _safe(lambda: store.expertise(person_id=person_id)) or []
    return sorted([e for e in exps if e.score >= STRONG_EXPERTISE * 0.6], key=lambda e: e.score, reverse=True)


def _gather_facts(store: StoreLike, person_id: str, held: list[Expertise]) -> list[Fact]:
    """Facts they stated + critical facts in areas where they are the sole strong holder (nobody else can vouch)."""
    facts = {f.id: f for f in _safe(lambda: store.facts(person_id=person_id, current_only=True)) or []}
    for e in held:
        others = [
            x for x in _safe(lambda: store.expertise(area_id=e.area_id)) or []
            if x.person_id != person_id and x.score >= STRONG_EXPERTISE
        ]
        if others:
            continue
        for f in _safe(lambda: store.facts(area_id=e.area_id, current_only=True)) or []:
            if f.kind in CRITICAL_KINDS:
                facts.setdefault(f.id, f)
    return sorted(facts.values(), key=lambda f: (SECTION_ORDER.index(_KIND_SECTION.get(f.kind, "decisions")), f.area_id or "", f.id))


def _fact_items(store: StoreLike, facts: list[Fact], owners: dict[str, str | None]) -> list[HandoffItem]:
    items = []
    for f in facts:
        section = _KIND_SECTION.get(f.kind)
        if section is None:
            continue
        if section == "decisions" and is_pending(f.text):
            section = "unresolved_work"
        items.append(
            HandoffItem(
                section=section,
                title=redact_secrets(short_title(f)),
                detail=redact_secrets(f.text),
                area_id=f.area_id,
                fact_ids=[f.id],
                citations=citations_for(store, f),
                suggested_owner_id=owners.get(f.area_id or ""),
            )
        )
    return items


def _unresolved_items(store: StoreLike, person_id: str, today: date, owners: dict[str, str | None]) -> list[HandoffItem]:
    items: list[HandoffItem] = []
    for t in _safe(lambda: store.open_tickets(person_id)) or []:
        area = doc_area(store, t)
        items.append(
            HandoffItem(
                section="unresolved_work",
                title=f"Open ticket {t.container}: {t.title or _snippet(t.text, 60)}",
                detail=_snippet(t.text, 280),
                area_id=area,
                citations=[doc_citation(t)],
                suggested_owner_id=owners.get(area or ""),
            )
        )
    since = datetime.combine(today - timedelta(days=PROMISE_LOOKBACK_DAYS), datetime.min.time())
    recent = _safe(lambda: store.docs_by(person_id, since=since)) or []
    for d in recent:
        m = _PROMISE.search(d.text)
        if not m:
            continue
        promise = m.group(0).strip().rstrip(",;")
        items.append(
            HandoffItem(
                section="unresolved_work",
                title=f"Promised follow-up: “{_snippet(promise, 70)}”",
                detail=f"Said on {d.timestamp:%b %d} in {d.container}. Check whether it was delivered.",
                area_id=doc_area(store, d),
                citations=[doc_citation(d, quote=promise)],
            )
        )
    return items[:12]


def _area_items(store: StoreLike, person_id: str, held: list[Expertise], people: dict[str, Person], today: date,
                owners: dict[str, str | None], pairs: dict[str, tuple[str | None, str | None]]) -> list[HandoffItem]:
    items = []
    for e in held:
        area = _safe(lambda: store.area(e.area_id))
        if area is None:
            continue
        experts = _safe(lambda: store.expertise(area_id=e.area_id)) or []
        others = [x for x in sorted(experts, key=lambda x: x.score, reverse=True) if x.person_id != person_id][:3]
        people_txt = ", ".join(f"{first_name(store, x.person_id)} ({x.score:.2f})" for x in others) or "nobody else on record"
        docs = [f for f in _safe(lambda: store.facts(area_id=e.area_id, current_only=True)) or [] if f.kind == FactKind.PROCEDURE][:2]
        cits = [c for f in docs for c in citations_for(store, f, limit=1)]
        systems = ", ".join(area.systems) or "none listed"
        items.append(
            HandoffItem(
                section="key_links_people",
                title=area.name,
                detail=f"Systems: {systems}. Also knows it: {people_txt}.",
                area_id=area.id,
                citations=cits,
                suggested_owner_id=owners.get(area.id),
            )
        )
        learner, reviewer = pairs.get(area.id, (None, None))
        if learner:
            who = first_name(store, learner) + (f", reviewed by {first_name(store, reviewer)}" if reviewer else "")
            detail = (f"Suggested: {who}. Pairing a learner with a reviewer spreads the knowledge instead of moving "
                      "the single point of failure. A manager approves.")
        else:
            detail = "No one else has evidence of knowing this area. Pick an owner and schedule a gap interview now."
        items.append(
            HandoffItem(
                section="suggested_owners",
                title=f"{area.name} → {first_name(store, learner) if learner else 'unassigned'}",
                detail=detail,
                area_id=area.id,
                suggested_owner_id=learner,
            )
        )
    return items


def build_handoff_pack(store: StoreLike, person_id: str, today: date, *, risks: list[AreaRisk] | None = None) -> HandoffPack:
    """Assemble the pack for ``person_id`` as of ``today``. Deterministic for a given store."""
    people = people_by_id(store)
    person = people.get(person_id)
    held = _held_areas(store, person_id)
    pairs = {e.area_id: successor(_safe(lambda: store.expertise(area_id=e.area_id)) or [], people, person_id, today) for e in held}
    owners = {a: pair[0] for a, pair in pairs.items()}
    facts = _gather_facts(store, person_id, held)
    items = (
        _fact_items(store, facts, owners)
        + _unresolved_items(store, person_id, today, owners)
        + _area_items(store, person_id, held, people, today, owners, pairs)
    )
    items.sort(key=lambda it: SECTION_ORDER.index(it.section) if it.section in SECTION_ORDER else 99)
    return HandoffPack(
        person_id=person_id,
        generated_at=datetime.combine(today, datetime.min.time()),
        last_day=person.departure_date if person else None,
        items=items,
        gaps=gap_questions(store, person_id, today=today, risks=risks),
    )


def pack_to_markdown(store: StoreLike, pack: HandoffPack, statuses: dict[str, str] | None = None) -> str:
    """Export for the wiki / email. Items the person removed are left out; corrections are applied upstream."""
    from keepline.products.signoff import item_key

    statuses = statuses or {}
    name = people_by_id(store).get(pack.person_id)
    lines = [f"# Handoff pack: {name.name if name else pack.person_id}", ""]
    if pack.last_day:
        lines.append(f"Last day: **{pack.last_day:%A %B %d, %Y}**  ")
    lines.append(f"Generated: {pack.generated_at:%Y-%m-%d}  ")
    lines.append(f"Status: {'signed off ' + f'{pack.signed_off_at:%Y-%m-%d %H:%M}' if pack.signed_off and pack.signed_off_at else 'draft (not signed off)'}")
    for section in SECTION_ORDER:
        rows = [it for it in pack.items if it.section == section and statuses.get(item_key(it), it.status) != "removed"]
        if not rows:
            continue
        lines += ["", f"## {SECTION_TITLES[section]}", ""]
        for it in rows:
            st = statuses.get(item_key(it), it.status)
            badge = {"confirmed": " ✅", "corrected": " ✏️"}.get(st, "")
            owner = f" — suggested owner: {first_name(store, it.suggested_owner_id)}" if it.suggested_owner_id else ""
            lines.append(f"- **{it.title}**{badge}{owner}  ")
            lines.append(f"  {it.detail}")
            for c in it.citations:
                lines.append(f"  - receipt: [{first_name(store, c.author_id)}, {c.timestamp:%Y-%m-%d}]({c.url}) “{c.quote}”")
    if pack.gaps:
        lines += ["", "## Questions to ask before the last day", ""]
        lines += [f"{i}. {g.question} _({g.reason})_" for i, g in enumerate(pack.gaps, 1)]
    return "\n".join(lines) + "\n"

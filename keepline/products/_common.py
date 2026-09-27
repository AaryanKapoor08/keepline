"""Shared helpers for the product layer (risk map, handoff pack, onboarding brief, gaps, what-if).

Products code against ``StoreLike`` -- the read-mostly subset of ``keepline.memory.store.MemoryStore`` they need --
so they can be unit-tested with a tiny in-memory fake and later run unchanged against the SQLite store or a
Snowflake-backed store (see ``snowflake/streamlit``).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any, Protocol

from keepline.contracts import (
    Area,
    Citation,
    DepartureType,
    Expertise,
    Fact,
    FactKind,
    Person,
    SourceDoc,
)

# An expertise score at or above this counts as "strong evidence" (drives bus factor). Chosen so that a person who
# has closed a handful of tickets *and* discussed the area regularly clears it, while a one-off commenter does not.
STRONG_EXPERTISE = 0.35
# Planning horizon (days) over which a known departure date decays from "certain" to "background hazard".
DEPARTURE_HORIZON_DAYS = 400.0
# Background departure hazard when HR has no date. Deliberately the same for everyone: we never score individuals.
BASELINE_HAZARD = 0.08


class StoreLike(Protocol):
    """The subset of ``MemoryStore`` the products use (BuildFlow §B)."""

    def people(self) -> list[Person]: ...
    def person(self, id: str) -> Person | None: ...
    def areas(self) -> list[Area]: ...
    def area(self, id: str) -> Area | None: ...
    def doc(self, id: str) -> SourceDoc | None: ...
    def docs(self, ids: Sequence[str]) -> list[SourceDoc]: ...
    def facts(self, **kw: Any) -> list[Fact]: ...
    def fact(self, id: str) -> Fact | None: ...
    def supersession_chain(self, fact_id: str) -> list[Fact]: ...
    def expertise(self, **kw: Any) -> list[Expertise]: ...
    def docs_by(self, person_id: str, **kw: Any) -> list[SourceDoc]: ...
    def open_tickets(self, person_id: str) -> list[SourceDoc]: ...
    def query_log(self, **kw: Any) -> list[dict[str, Any]]: ...
    def area_doc_counts_by_month(self, area_id: str) -> dict[str, int]: ...


# ------------------------------------------------------------------------------------------------ people


def people_by_id(store: StoreLike) -> dict[str, Person]:
    return {p.id: p for p in store.people()}


def first_name(store: StoreLike, person_id: str | None) -> str:
    if not person_id:
        return "someone"
    p = _safe(lambda: store.person(person_id))
    return p.name.split()[0] if p else person_id.title()


def full_name(store: StoreLike, person_id: str | None) -> str:
    if not person_id:
        return "Unknown"
    p = _safe(lambda: store.person(person_id))
    return p.name if p else person_id.title()


def has_left(person: Person | None, today: date) -> bool:
    """True if the person's known last day is already behind us (their knowledge is no longer reachable)."""
    return bool(person and person.departure_date and person.departure_date < today)


def departure_likelihood(person: Person | None, today: date) -> float:
    """P(this person's knowledge becomes unreachable soon), from HR facts only -- never from behaviour.

    Known date: ~1.0 when days away, decaying exponentially over the planning horizon (retirement in 3 months ~0.78).
    Leave of absence is discounted (they come back). No date: a small constant background hazard.
    """
    if person is None:
        return BASELINE_HAZARD
    if person.departure_date is None:
        return BASELINE_HAZARD
    days = (person.departure_date - today).days
    if days <= 0:
        return 1.0
    p = BASELINE_HAZARD + (1 - BASELINE_HAZARD) * math.exp(-days / DEPARTURE_HORIZON_DAYS)
    if person.departure_type == DepartureType.LEAVE:
        p *= 0.6
    return round(min(1.0, p), 4)


def countdown(person: Person | None, today: date) -> int | None:
    if person is None or person.departure_date is None:
        return None
    return (person.departure_date - today).days


# ------------------------------------------------------------------------------------------------ receipts


def citations_for(store: StoreLike, fact: Fact, *, limit: int = 3) -> list[Citation]:
    """Turn a fact's source doc ids into citation cards (the receipts)."""
    docs = _safe(lambda: store.docs(list(fact.source_doc_ids[:limit]))) or []
    cits: list[Citation] = []
    for i, d in enumerate(docs):
        quote = fact.quote if (i == 0 and fact.quote) else _snippet(d.text)
        cits.append(
            Citation(
                doc_id=d.id,
                quote=quote,
                author_id=d.author_id,
                timestamp=d.timestamp,
                url=d.url,
                fact_id=fact.id,
                is_current=fact.is_current,
            )
        )
    return cits


def doc_area(store: StoreLike, doc: SourceDoc) -> str | None:
    """Best area for a doc: explicit ticket meta first, else the store's doc->area linking (if it has one)."""
    if isinstance(doc.meta, dict):
        for k in ("area_id", "area_hint"):
            if doc.meta.get(k):
                return str(doc.meta[k])
    fn = getattr(store, "doc_area_ids", None)
    ids = _safe(lambda: fn(doc.id)) if fn else None
    return ids[0] if ids else None


def doc_citation(doc: SourceDoc, quote: str | None = None) -> Citation:
    return Citation(
        doc_id=doc.id,
        quote=quote or _snippet(doc.text),
        author_id=doc.author_id,
        timestamp=doc.timestamp,
        url=doc.url,
    )


def _snippet(text: str, n: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


# ------------------------------------------------------------------------------------------------ text signals

_REASON = re.compile(r"\b(because|since|so that|due to|to avoid|otherwise|reason|as a result|so we|which is why)\b", re.I)
_INCIDENT = re.compile(r"\b(incident|outage|broke|broken|failed|failure|went down|rollback|postmortem|sev[ -]?\d)\b", re.I)
_PENDING = re.compile(r"\b(pending|tbd|undecided|not decided|still deciding|proposal|proposed|to be decided|open question)\b", re.I)
_SECRET = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_ -]?key)\s*[:=]\s*\S+"
    r"|\b(sk|pk|rk|ghp|xox[bap])[-_][A-Za-z0-9-_]{8,}\b"
    r"|\b[A-Za-z0-9+/_-]{32,}\b"
)


def has_reason(text: str) -> bool:
    return bool(_REASON.search(text))


def is_incident(text: str) -> bool:
    return bool(_INCIDENT.search(text))


def is_pending(text: str) -> bool:
    return bool(_PENDING.search(text))


def redact_secrets(text: str) -> str:
    """Never surface a credential. We say *where* credentials live, never what they are."""
    return _SECRET.sub(lambda m: (m.group(1) + ": [redacted]") if m.group(1) else "[redacted]", text)


def short_title(fact: Fact, n: int = 70) -> str:
    base = fact.subject or fact.text
    base = " ".join(base.split()).rstrip(".")
    return base if len(base) <= n else base[: n - 1].rsplit(" ", 1)[0] + "…"


# ------------------------------------------------------------------------------------------------ query log


def ql_area(entry: dict[str, Any]) -> str | None:
    """Area of a query-log row, tolerant of the exact row shape the store returns."""
    if entry.get("area_id"):
        return str(entry["area_id"])
    ans = entry.get("answer")
    if isinstance(ans, dict) and ans.get("area_id"):
        return str(ans["area_id"])
    return None


def ql_action(entry: dict[str, Any]) -> str | None:
    if entry.get("action"):
        return str(entry["action"])
    ans = entry.get("answer")
    if isinstance(ans, dict) and ans.get("action"):
        return str(ans["action"])
    return None


def safe_query_log(store: StoreLike, **kw: Any) -> list[dict[str, Any]]:
    return _safe(lambda: store.query_log(**kw)) or []


# ------------------------------------------------------------------------------------------------ misc


def to_date(x: date | datetime | None) -> date | None:
    if x is None:
        return None
    return x.date() if isinstance(x, datetime) else x


def uniq(items: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def normalize(values: dict[str, float]) -> dict[str, float]:
    """Scale to [0, 1] by the max (0 stays 0). Used to put heterogeneous importance signals on one scale."""
    top = max(values.values(), default=0.0)
    return {k: (v / top if top > 0 else 0.0) for k, v in values.items()}


CRITICAL_KINDS = (FactKind.ACCESS, FactKind.VENDOR_CONTACT, FactKind.RECURRING_TASK, FactKind.LANDMINE)


def _safe(fn: Any) -> Any:
    """Products must never crash a page because one store call is missing or a row is malformed."""
    try:
        return fn()
    except Exception:  # noqa: BLE001 - defensive at the product boundary
        return None

"""Shared data contracts for Keepline.

Every module codes against these types. Two worlds are kept strictly apart:

* **Ground truth** (``TruthFact``, ``Question`` gold fields, ``EvidenceMap``) lives under ``data/truth`` and
  ``data/questions``. Only ``keepline.data`` (which writes it) and ``keepline.eval`` (which grades against it)
  may read it. The product pipeline never sees it -- ``tests/test_isolation.py`` enforces this.
* **Product world** (``Person``, ``Area``, ``SourceDoc``, ``Fact``, ``Edge``, ``Answer`` ...) is what a real
  customer deployment would have: an HR roster, a list of systems/areas, and raw work-tool data.

All dates are ISO-8601 strings in JSON and ``datetime.date`` / ``datetime.datetime`` in Python.
Serialization helpers at the bottom convert both ways.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Iterator, TypeVar

# --------------------------------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------------------------------


class FactKind(StrEnum):
    """What a piece of knowledge is. Ordered roughly by how badly its loss hurts."""

    ACCESS = "access"  # "Sarah is the only Stripe admin"; "creds live in 1Password vault 'Core'"
    VENDOR_CONTACT = "vendor_contact"  # "Our rep at Fiserv is Dan Holt; only Sarah's email is on file"
    RECURRING_TASK = "recurring_task"  # "Sarah renews the SSL cert every March"
    LANDMINE = "landmine"  # "never rotate the CoreLink API key on a Friday"
    PROCEDURE = "procedure"  # how-to steps
    DECISION = "decision"  # "we decided to move reconciliation to 02:00"
    OWNER = "owner"  # "Priya owns payroll"
    FACT = "fact"  # everything else that is true about the org/systems


class SourceType(StrEnum):
    SLACK = "slack"
    EMAIL = "email"
    TICKET = "ticket"
    INTERVIEW = "interview"  # gap-interviewer transcript
    DOC = "doc"  # wiki page / README


class Visibility(StrEnum):
    PUBLIC = "public"  # public channel / shared doc
    TEAM = "team"  # private channel for a team
    PRIVATE = "private"  # DM or 1:1 email -- EXCLUDED from ingestion by default


class Epistemic(StrEnum):
    SAID = "said"  # directly stated in a source (quote-able)
    INFERRED = "inferred"  # derived by reasoning over sources; must be labeled


class Verification(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"


class ReviewStatus(StrEnum):
    PENDING = "pending"  # everything starts private in the owner's review queue
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"


class Action(StrEnum):
    ANSWER = "answer"
    ABSTAIN = "abstain"
    ROUTE = "route"


class QType(StrEnum):
    FACT = "fact"  # plain factual lookup
    CURRENT = "current"  # target fact has been superseded; must return newest version
    ROUTING = "routing"  # "who handles X?" -> expected action ROUTE (or ANSWER naming the person)
    UNANSWERABLE = "unanswerable"  # not in data -> expected ABSTAIN (or ROUTE to plausible owner)
    LANDMINE = "landmine"  # "anything I should never do with X?"


class Split(StrEnum):
    TRAIN = "train"
    DEV = "dev"
    TEST = "test"  # frozen; hashed in data/questions/test.sha256; run only for final numbers


class DepartureType(StrEnum):
    RESIGNATION = "resignation"
    RETIREMENT = "retirement"
    LEAVE = "leave"
    CONTRACT_END = "contract_end"


# --------------------------------------------------------------------------------------------------
# Org config (product world -- what a customer would provide: HR roster + list of systems/areas)
# Files: data/org/people.json, data/org/areas.json
# --------------------------------------------------------------------------------------------------


@dataclass
class Person:
    id: str  # slug, e.g. "sarah"
    name: str  # "Sarah Chen"
    role: str  # "Senior Backend Engineer"
    team: str  # "engineering" | "finance" | "operations" | "member_services" | "leadership" | "it"
    email: str
    start_date: date
    departure_date: date | None = None  # known future/past departure (from HR)
    departure_type: DepartureType | None = None
    manager_id: str | None = None


@dataclass
class Area:
    """A topic / system / responsibility the org cares about ("payroll", "core banking reconciliation")."""

    id: str  # slug, e.g. "reconciliation"
    name: str
    description: str
    keywords: list[str]  # seed lexicon for linking docs/facts to this area (customer-provided or discovered)
    systems: list[str] = field(default_factory=list)  # e.g. ["CoreLink", "Jenkins"]
    criticality: int = 2  # 1 (nice-to-have) .. 3 (business-critical); customer-provided prior


# --------------------------------------------------------------------------------------------------
# Raw corpus (product world). File: data/corpus/{slack,email,tickets,docs}.jsonl
# --------------------------------------------------------------------------------------------------


@dataclass
class SourceDoc:
    id: str  # globally unique, e.g. "slack-000123", "email-000045", "ticket-HCU-212"
    source_type: SourceType
    author_id: str  # Person.id
    timestamp: datetime
    text: str
    container: str  # slack channel ("#eng-core"), email subject thread id, ticket key, doc path
    thread_id: str | None = None  # groups replies
    title: str | None = None  # email subject / ticket title / doc title
    participants: list[str] = field(default_factory=list)  # Person.ids who can see it (for private/team)
    visibility: Visibility = Visibility.PUBLIC
    url: str = ""  # deep link (fake but stable), e.g. "https://harbourline.slack.com/archives/eng-core/p123"
    meta: dict[str, Any] = field(default_factory=dict)  # ticket status/assignee/closed_at, email to/cc, etc.


# --------------------------------------------------------------------------------------------------
# Memory / versioned knowledge graph (product world). SQLite: data/memory/keepline.db
# Mirrors snowflake/sql/01_schema.sql 1:1.
# --------------------------------------------------------------------------------------------------


@dataclass
class Fact:
    id: str
    text: str  # normalized statement, e.g. "The nightly reconciliation job must skip the 1st and 15th."
    kind: FactKind
    area_id: str | None
    stated_by: str | None  # Person.id who said it (None if inferred)
    source_doc_ids: list[str]  # receipts
    quote: str  # verbatim span from the primary source doc (empty only if INFERRED)
    valid_from: date  # when it became true in the world (bi-temporal: valid time)
    valid_to: date | None = None  # None = still current
    learned_at: datetime | None = None  # when Keepline learned it (bi-temporal: transaction time)
    supersedes: str | None = None  # Fact.id this replaces
    superseded_by: str | None = None
    epistemic: Epistemic = Epistemic.SAID
    verification: Verification = Verification.UNVERIFIED
    visibility: Visibility = Visibility.PUBLIC
    confidence: float = 0.5  # extraction confidence in [0, 1]
    review_status: ReviewStatus = ReviewStatus.PENDING
    subject: str | None = None  # the system/entity the fact is about ("CoreLink API key")
    extractor: str = "heuristic"  # "heuristic" | "claude" | "cortex"

    @property
    def is_current(self) -> bool:
        return self.valid_to is None and self.superseded_by is None


class EdgeRel(StrEnum):
    KNOWS = "knows"  # person -> area (weight = evidence strength)
    OWNS = "owns"  # person -> area/system
    DECIDED = "decided"  # person -> decision fact
    HAS_ACCESS = "has_access"  # person -> system
    ABOUT = "about"  # fact -> area
    SUPPORTED_BY = "supported_by"  # fact -> source doc
    SUPERSEDES = "supersedes"  # fact -> fact
    ASKED = "asked"  # person -> area (query log)


@dataclass
class Edge:
    src: str
    dst: str
    rel: EdgeRel
    weight: float = 1.0
    valid_from: date | None = None
    valid_to: date | None = None
    evidence_doc_ids: list[str] = field(default_factory=list)


@dataclass
class Expertise:
    """Evidence that a person knows an area. Doing > talking: closed tickets weigh more than messages."""

    person_id: str
    area_id: str
    score: float  # normalized evidence strength in [0, 1]
    n_docs: int
    n_tickets_closed: int
    n_facts_stated: int
    last_active: date | None
    confirmed_by_person: bool = False
    enough_data: bool = True  # False => "unknown", never treated as zero


# --------------------------------------------------------------------------------------------------
# Answers (product world)
# --------------------------------------------------------------------------------------------------


@dataclass
class Citation:
    doc_id: str
    quote: str
    author_id: str
    timestamp: datetime
    url: str
    fact_id: str | None = None
    is_current: bool = True  # False if citing a superseded fact (shown as "replaced by ...")


@dataclass
class Answer:
    question: str
    action: Action
    text: str  # final natural-language answer (or "I don't know..." / "Ask Mike...")
    said: list[Citation] = field(default_factory=list)  # layer 1: quotes with link + date
    inferred: list[str] = field(default_factory=list)  # layer 2: clearly-labeled reasoning
    no_evidence_note: str | None = None  # layer 3: "I don't know. Mike worked on this in 2025, ask him."
    route_to: list[str] = field(default_factory=list)  # Person.ids
    confidence: float = 0.0  # calibrated P(correct)
    area_id: str | None = None
    fact_ids: list[str] = field(default_factory=list)  # facts the answer relies on
    policy: dict[str, Any] = field(default_factory=dict)  # PolicyParams used (for RL logging)
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyParams:
    """The knobs the bandit tunes (RL over the agent's *decisions*, never the LLM's weights)."""

    k: int = 8  # retrieval depth
    abstain_threshold: float = 0.35  # below this confidence -> abstain/route
    route_threshold: float = 0.15  # below abstain but above this with a known expert -> route
    source_weights: dict[str, float] = field(
        default_factory=lambda: {"ticket": 1.2, "slack": 1.0, "email": 1.0, "doc": 0.9, "interview": 1.3}
    )
    prefer_current: bool = True  # drop superseded facts from the answer set

    def key(self) -> str:
        return f"k{self.k}-a{self.abstain_threshold:.2f}-r{self.route_threshold:.2f}"


# --------------------------------------------------------------------------------------------------
# Ground truth (EVAL world ONLY). Files: data/truth/truth.json, data/truth/evidence_map.json
# --------------------------------------------------------------------------------------------------


@dataclass
class TruthFact:
    id: str  # "T001"
    kind: FactKind
    area_id: str
    statement: str  # canonical statement
    answer_keywords: list[list[str]]  # CNF: every inner list is an any-of group; all groups must match
    known_by: list[str]  # Person.ids who genuinely know it (drives redundancy ground truth)
    stated_by: str  # who says it in the rendered data
    valid_from: date
    valid_to: date | None = None
    supersedes: str | None = None  # TruthFact.id
    importance: int = 2  # 1..3
    is_landmine: bool = False
    in_corpus: bool = True  # False => deliberately NOT rendered (for unanswerable/gap questions)
    visibility: Visibility = Visibility.PUBLIC
    notes: str = ""


@dataclass
class Question:
    id: str  # "Q0001"
    split: Split
    text: str
    asker_id: str
    as_of: date  # the question is asked "on this date" (answers must reflect facts current at as_of)
    qtype: QType
    area_id: str | None
    expected_action: Action
    gold_fact_ids: list[str] = field(default_factory=list)  # TruthFact.ids that answer it
    gold_answer_keywords: list[list[str]] = field(default_factory=list)  # CNF, copied from truth
    gold_route_person_ids: list[str] = field(default_factory=list)  # acceptable routes
    forbidden_keywords: list[list[str]] = field(default_factory=list)  # e.g. superseded answer -> wrong


# EvidenceMap: {TruthFact.id: [SourceDoc.id, ...]} -- which rendered docs express each truth fact.
EvidenceMap = dict[str, list[str]]


# --------------------------------------------------------------------------------------------------
# Handoff pack / onboarding brief (product world)
# --------------------------------------------------------------------------------------------------


@dataclass
class HandoffItem:
    section: str  # "access" | "vendor_contacts" | "recurring_tasks" | "unresolved_work" | "landmines" | ...
    title: str
    detail: str
    area_id: str | None
    fact_ids: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    suggested_owner_id: str | None = None
    status: str = "pending_review"  # "pending_review" | "confirmed" | "corrected" | "removed"


@dataclass
class GapQuestion:
    """A question for the gap interviewer, ranked by risk x expected information gain."""

    person_id: str  # who to ask
    area_id: str | None
    question: str  # "Why does the reconciliation job skip the 15th? What breaks if it runs?"
    reason: str  # signal that produced it: "decision with no recorded reason", "agent abstained 4x", ...
    priority: float  # risk x info gain, higher first
    related_fact_ids: list[str] = field(default_factory=list)


@dataclass
class HandoffPack:
    person_id: str
    generated_at: datetime
    last_day: date | None
    items: list[HandoffItem]
    gaps: list[GapQuestion]  # gap-interview questions to ask before the last day
    signed_off: bool = False
    signed_off_at: datetime | None = None


@dataclass
class AreaRisk:
    """Topic-level knowledge risk. risk = importance x (1 - redundancy) x departure_likelihood."""

    area_id: str
    area_name: str
    importance: float  # [0, 1]: criticality prior + incidents + decisions + dependencies + ask frequency
    redundancy: float  # [0, 1]: how many people have strong evidence of knowing it (saturating)
    departure_likelihood: float  # [0, 1]: max over the area's strong experts; ~1.0 when a date is known & near
    risk: float  # [0, 1]
    bus_factor: int  # number of people with strong evidence (score >= threshold)
    experts: list[tuple[str, float]]  # (person_id, expertise score), strongest first
    countdown_days: int | None = None  # days until the top expert's known departure
    at_risk_person_id: str | None = None  # the expert whose departure drives the risk
    n_facts: int = 0
    n_landmines: int = 0
    last_touched: date | None = None
    trend: list[float] = field(default_factory=list)  # monthly risk history (oldest -> newest)
    enough_data: bool = True
    explanation: str = ""  # "Only Sarah has touched reconciliation in 6 months (41 docs, 9 closed tickets)."


@dataclass
class BriefSection:
    title: str  # "Who to ask about what" | "Recent decisions" | "Landmines" | "Jargon" | "Starter tasks"
    items: list[dict[str, Any]]  # free-form rows; every row that makes a claim carries "citations": [Citation]


@dataclass
class OnboardingBrief:
    person_id: str
    generated_at: datetime
    team: str
    sections: list[BriefSection]


# --------------------------------------------------------------------------------------------------
# Serialization helpers (JSON <-> dataclasses; handles date/datetime/enums/nesting)
# --------------------------------------------------------------------------------------------------

T = TypeVar("T")


def _default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, date):
        return o.isoformat()
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    raise TypeError(f"Unserializable: {type(o)!r}")


def to_json(obj: Any, **kw: Any) -> str:
    return json.dumps(obj, default=_default, ensure_ascii=False, **kw)


def to_dict(obj: Any) -> Any:
    return json.loads(to_json(obj))


def _coerce(tp: Any, value: Any) -> Any:
    """Best-effort coercion of JSON values into annotated dataclass field types."""
    import types
    import typing

    if value is None:
        return None
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (typing.Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        return _coerce(non_none[0], value) if len(non_none) == 1 else value
    if origin is list:
        return [_coerce(args[0], v) for v in value] if args else list(value)
    if origin is dict:
        return dict(value)
    if tp is datetime:
        return value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if tp is date:
        if isinstance(value, datetime):
            return value.date()
        return value if isinstance(value, date) else date.fromisoformat(value[:10])
    if isinstance(tp, type) and issubclass(tp, StrEnum):
        return tp(value)
    if dataclasses.is_dataclass(tp):
        return from_dict(tp, value)
    return value


def from_dict(cls: type[T], data: dict[str, Any]) -> T:
    import typing

    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):  # type: ignore[arg-type]
        if f.name in data:
            kwargs[f.name] = _coerce(hints[f.name], data[f.name])
    return cls(**kwargs)


def write_jsonl(path: Path, items: Iterable[Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(to_json(it) + "\n")
            n += 1
    return n


def read_jsonl(path: Path, cls: type[T]) -> Iterator[T]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield from_dict(cls, json.loads(line))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(obj, indent=2), encoding="utf-8")


def read_json_list(path: Path, cls: type[T]) -> list[T]:
    return [from_dict(cls, d) for d in json.loads(path.read_text(encoding="utf-8"))]

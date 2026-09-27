"""Who knows what: person x area expertise from *behaviour*, plus the graph's person/fact edges.

Doing beats talking: closing a ticket in an area is much stronger evidence than chatting about it, and
answering someone else's question beats asking one. Scores are saturating (1 - exp(-evidence)) and blended with
the person's *share* of the area's evidence, so one prolific poster does not look like an expert everywhere and
a quiet specialist is not buried. Too little evidence yields ``enough_data=False``: unknown is not zero.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Sequence

from keepline.contracts import Edge, EdgeRel, Expertise, Fact, FactKind, Person, SourceDoc, SourceType
from keepline.memory.extract import group_threads, is_question
from keepline.memory.store import CLOSED_TICKET_STATUSES, ticket_fields
from keepline.retrieval.text import split_sentences

W_TICKET_CLOSED = 3.0
W_TICKET_OPEN = 1.0
W_FACT = 1.5
W_ANSWER = 1.0
W_DOC = 0.4
HALF_LIFE_DAYS = 180.0
SATURATION = 6.0  # evidence units at which the saturating part reaches ~63%
MIN_ITEMS = 3


@dataclass
class _Acc:
    evidence: float = 0.0
    items: int = 0
    n_docs: int = 0
    n_closed: int = 0
    n_facts: int = 0
    n_answers: int = 0
    last: date | None = None

    def add(self, w: float, when: date, ref: date) -> None:
        self.evidence += w * math.exp2(-max(0, (ref - when).days) / HALF_LIFE_DAYS)
        self.items += 1
        self.last = max(self.last, when) if self.last else when


def compute_expertise(
    docs: Sequence[SourceDoc],
    doc_areas: dict[str, list[tuple[str, float]]],
    facts: Sequence[Fact],
    *,
    ref_date: date | None = None,
) -> tuple[list[Expertise], dict[tuple[str, str], int]]:
    """Returns expertise rows and the per (person, area) count of thread answers given."""
    ref = ref_date or max((d.timestamp.date() for d in docs), default=date.today())
    acc: dict[tuple[str, str], _Acc] = defaultdict(_Acc)
    areas_of = {d: [a for a, _ in lst] for d, lst in doc_areas.items()}

    for d in docs:
        for a in areas_of.get(d.id, [])[:2]:
            x = acc[(d.author_id, a)]
            x.add(W_DOC, d.timestamp.date(), ref)
            x.n_docs += 1

    for thread in group_threads(docs):
        t_areas = list(dict.fromkeys(a for d in thread for a in areas_of.get(d.id, [])))[:2]
        if not t_areas:
            continue
        if thread[0].source_type == SourceType.TICKET:
            status, assignee, closed_at = ticket_fields(thread[-1].meta)
            assignee = assignee or next((ticket_fields(d.meta)[1] for d in reversed(thread) if ticket_fields(d.meta)[1]), None)
            if assignee:
                closed = bool(closed_at) or (status in CLOSED_TICKET_STATUSES)
                for a in t_areas:
                    x = acc[(assignee, a)]
                    x.add(W_TICKET_CLOSED if closed else W_TICKET_OPEN, thread[-1].timestamp.date(), ref)
                    x.n_closed += int(closed)
        askers: set[str] = set()
        for d in thread:
            if askers - {d.author_id}:
                for a in t_areas:
                    x = acc[(d.author_id, a)]
                    x.add(W_ANSWER, d.timestamp.date(), ref)
                    x.n_answers += 1
            if any(is_question(s) for s in split_sentences(d.text)):
                askers.add(d.author_id)

    for f in facts:
        if f.stated_by and f.area_id:
            x = acc[(f.stated_by, f.area_id)]
            x.add(W_FACT * (0.5 + f.confidence), f.valid_from, ref)
            x.n_facts += 1

    area_total: dict[str, float] = defaultdict(float)
    area_max_share: dict[str, float] = defaultdict(float)
    for (p, a), x in acc.items():
        area_total[a] += x.evidence
    for (p, a), x in acc.items():
        area_max_share[a] = max(area_max_share[a], x.evidence / area_total[a] if area_total[a] else 0.0)

    rows: list[Expertise] = []
    answers: dict[tuple[str, str], int] = {}
    for (p, a), x in sorted(acc.items()):
        share = (x.evidence / area_total[a]) / area_max_share[a] if area_total[a] and area_max_share[a] else 0.0
        score = (1 - math.exp(-x.evidence / SATURATION)) * (0.4 + 0.6 * share)
        rows.append(
            Expertise(
                person_id=p,
                area_id=a,
                score=round(score, 4),
                n_docs=x.n_docs,
                n_tickets_closed=x.n_closed,
                n_facts_stated=x.n_facts,
                last_active=x.last,
                enough_data=x.items >= MIN_ITEMS,
            )
        )
        answers[(p, a)] = x.n_answers
    return rows, answers


def mentioned_people(text: str, people: Sequence[Person]) -> list[str]:
    """People named in a sentence (full name, or first name as a whole word). Shallow but general."""
    out = []
    for p in people:
        first = p.name.split()[0]
        if re.search(rf"\b({re.escape(p.name)}|{re.escape(first)}|@{re.escape(p.id)})\b", text, re.I):
            out.append(p.id)
    return out


_FIRST_PERSON = re.compile(r"\b(i|i'm|i am|i've|me|my)\b", re.I)


def build_edges(facts: Sequence[Fact], expertise: Sequence[Expertise], people: Sequence[Person]) -> list[Edge]:
    edges: list[Edge] = []
    for e in expertise:
        edges.append(Edge(e.person_id, e.area_id, EdgeRel.KNOWS, weight=e.score, valid_from=e.last_active))
    for f in facts:
        if f.area_id:
            edges.append(Edge(f.id, f.area_id, EdgeRel.ABOUT, valid_from=f.valid_from, valid_to=f.valid_to))
        for d in f.source_doc_ids:
            edges.append(Edge(f.id, d, EdgeRel.SUPPORTED_BY, valid_from=f.valid_from, evidence_doc_ids=[d]))
        if f.supersedes:
            edges.append(Edge(f.id, f.supersedes, EdgeRel.SUPERSEDES, valid_from=f.valid_from))
        if f.kind == FactKind.DECISION and f.stated_by:
            edges.append(Edge(f.stated_by, f.id, EdgeRel.DECIDED, valid_from=f.valid_from, evidence_doc_ids=f.source_doc_ids[:1]))
        if f.kind in (FactKind.OWNER, FactKind.ACCESS) and f.area_id:
            who = mentioned_people(f.quote or f.text, people)
            if not who and f.stated_by and _FIRST_PERSON.search(f.quote or ""):
                who = [f.stated_by]
            rel = EdgeRel.OWNS if f.kind == FactKind.OWNER else EdgeRel.HAS_ACCESS
            dst = f.area_id if rel == EdgeRel.OWNS else (f.subject or f.area_id)
            for p in who:
                edges.append(Edge(p, dst, rel, weight=f.confidence, valid_from=f.valid_from, valid_to=f.valid_to,
                                  evidence_doc_ids=list(f.source_doc_ids)))
    return edges


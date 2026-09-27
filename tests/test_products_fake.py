"""A tiny in-memory ``MemoryStore`` stand-in (Harbourline in miniature) for product tests.

Implements the documented MemoryStore interface (BuildFlow §B) so products are tested without the generated
dataset or the SQLite graph.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from keepline.contracts import (
    Answer,
    Area,
    DepartureType,
    Expertise,
    Fact,
    FactKind,
    Person,
    ReviewStatus,
    SourceDoc,
    SourceType,
    Visibility,
)


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


class FakeStore:
    def __init__(self) -> None:
        self._people = [
            Person("sarah", "Sarah Chen", "Senior Backend Engineer", "engineering", "sarah@hcu.ca", _d("2022-01-10"),
                   _d("2026-09-11"), DepartureType.RESIGNATION, "dana"),
            Person("mike", "Mike Okafor", "Backend Engineer", "engineering", "mike@hcu.ca", _d("2023-05-01"), manager_id="dana"),
            Person("alex", "Alex Rivera", "Backend Engineer", "engineering", "alex@hcu.ca", _d("2026-09-14"), manager_id="dana"),
            Person("tom", "Tom Bouchard", "Compliance Officer", "leadership", "tom@hcu.ca", _d("2001-03-01"),
                   _d("2026-12-18"), DepartureType.RETIREMENT),
            Person("priya", "Priya Nair", "Finance Lead", "finance", "priya@hcu.ca", _d("2020-02-01")),
            Person("dana", "Dana Kim", "Engineering Manager", "engineering", "dana@hcu.ca", _d("2019-02-01")),
        ]
        self._areas = [
            Area("reconciliation", "Core banking reconciliation", "Nightly ledger reconciliation against CoreLink",
                 ["reconciliation", "recon", "ledger"], ["CoreLink", "Jenkins"], 3),
            Area("vendor_api", "CoreLink vendor API", "Integration with the CoreLink processor",
                 ["CoreLink", "API key"], ["CoreLink"], 3),
            Area("payroll", "Payroll", "Bi-weekly payroll run", ["payroll"], ["ADP"], 2),
            Area("compliance", "FINTRAC compliance", "Regulatory reporting", ["FINTRAC", "LCTR"], ["FINTRAC portal"], 3),
        ]
        self._docs = [
            SourceDoc("slack-1", SourceType.SLACK, "sarah", _dt("2026-04-02T10:00"),
                      "Heads up: the nightly reconciliation job must skip the 1st.", "#eng-core",
                      url="https://harbourline.slack.com/archives/eng-core/p1"),
            SourceDoc("slack-2", SourceType.SLACK, "sarah", _dt("2026-07-15T09:00"),
                      "Update: recon must skip the 1st and 15th now because CoreLink batches settle then.", "#eng-core",
                      url="https://harbourline.slack.com/archives/eng-core/p2"),
            SourceDoc("slack-3", SourceType.SLACK, "sarah", _dt("2026-06-01T09:00"),
                      "Never rotate the CoreLink API key on a Friday.", "#eng-core",
                      url="https://harbourline.slack.com/archives/eng-core/p3"),
            SourceDoc("email-1", SourceType.EMAIL, "sarah", _dt("2026-05-01T09:00"),
                      "Our CoreLink rep is Dan Holt, dan@corelink.example. Only my address is on file.", "thread-9",
                      url="mailto:thread-9"),
            SourceDoc("ticket-HCU-7", SourceType.TICKET, "sarah", _dt("2026-08-20T09:00"),
                      "Migrate recon job to Jenkins agent 2", "HCU-7", title="Migrate recon job",
                      url="https://jira.example/HCU-7", meta={"status": "open", "assignee": "sarah", "area_id": "reconciliation"}),
            SourceDoc("slack-4", SourceType.SLACK, "sarah", _dt("2026-08-29T16:00"),
                      "I'll send the runbook for the cert renewal Monday.", "#eng-core",
                      url="https://harbourline.slack.com/archives/eng-core/p4"),
            SourceDoc("slack-5", SourceType.SLACK, "priya", _dt("2026-05-10T09:00"),
                      "Payroll runs every second Thursday from ADP.", "#finance", url="https://harbourline.slack.com/p5"),
            SourceDoc("slack-6", SourceType.SLACK, "sarah", _dt("2026-03-20T09:00"),
                      "We decided to move reconciliation to 02:00.", "#eng-core", url="https://harbourline.slack.com/p6"),
            SourceDoc("slack-7", SourceType.SLACK, "mike", _dt("2026-06-20T09:00"),
                      "Outage on CoreLink sync last night, recon failed.", "#eng-core", url="https://harbourline.slack.com/p7"),
            SourceDoc("dm-1", SourceType.SLACK, "sarah", _dt("2026-08-01T09:00"), "private chat", "dm-sarah-mike",
                      participants=["sarah", "mike"], visibility=Visibility.PRIVATE),
        ]
        self._facts = [
            Fact("F1", "The nightly reconciliation job must skip the 1st.", FactKind.LANDMINE, "reconciliation", "sarah",
                 ["slack-1"], "must skip the 1st", _d("2026-04-02"), valid_to=_d("2026-07-15"), superseded_by="F2",
                 subject="reconciliation job schedule"),
            Fact("F2", "The nightly reconciliation job must skip the 1st and 15th because CoreLink batches settle then.",
                 FactKind.LANDMINE, "reconciliation", "sarah", ["slack-2"], "must skip the 1st and 15th",
                 _d("2026-07-15"), supersedes="F1", subject="reconciliation job schedule", confidence=0.9),
            Fact("F3", "Never rotate the CoreLink API key on a Friday.", FactKind.LANDMINE, "vendor_api", "sarah",
                 ["slack-3"], "Never rotate the CoreLink API key on a Friday", _d("2026-06-01"), subject="CoreLink API key"),
            Fact("F4", "Our CoreLink rep is Dan Holt; only Sarah's address is on file.", FactKind.VENDOR_CONTACT,
                 "vendor_api", "sarah", ["email-1"], "Our CoreLink rep is Dan Holt", _d("2026-05-01")),
            Fact("F5", "Payroll runs every second Thursday from ADP.", FactKind.RECURRING_TASK, "payroll", "priya",
                 ["slack-5"], "Payroll runs every second Thursday", _d("2026-05-10")),
            Fact("F6", "We decided to move reconciliation to 02:00.", FactKind.DECISION, "reconciliation", "sarah",
                 ["slack-6"], "move reconciliation to 02:00", _d("2026-08-20")),
            Fact("F7", "Outage on CoreLink sync last night, recon failed.", FactKind.FACT, "reconciliation", "mike",
                 ["slack-7"], "Outage on CoreLink sync", _d("2026-06-20")),
            Fact("F8", "Sarah is the only admin on the CoreLink portal; credentials are in 1Password vault Core. "
                 "password: hunter2", FactKind.ACCESS, "vendor_api", "sarah", ["email-1"], "only admin",
                 _d("2026-05-01"), subject="CoreLink portal admin"),
            Fact("F9", "Private DM fact", FactKind.FACT, "reconciliation", "sarah", ["dm-1"], "private",
                 _d("2026-08-01"), visibility=Visibility.PRIVATE),
        ]
        self._exp = [
            Expertise("sarah", "reconciliation", 0.92, 41, 9, 6, _d("2026-09-02")),
            Expertise("mike", "reconciliation", 0.2, 8, 1, 1, _d("2026-06-20")),
            Expertise("sarah", "vendor_api", 0.7, 20, 4, 3, _d("2026-08-30")),
            Expertise("mike", "vendor_api", 0.5, 12, 3, 1, _d("2026-08-01")),
            Expertise("priya", "payroll", 0.8, 30, 6, 2, _d("2026-09-01")),
            Expertise("dana", "payroll", 0.4, 10, 2, 0, _d("2026-08-01")),
            Expertise("tom", "compliance", 0.85, 25, 5, 4, _d("2026-08-28")),
        ]
        self._log: list[dict[str, Any]] = [
            {"asker_id": "alex", "question": "Who is our CoreLink rep?", "area_id": "vendor_api", "action": "answer",
             "fact_ids": ["F4"], "timestamp": "2026-09-01T10:00"},
            {"asker_id": "dana", "question": "Why does recon run at 02:00?", "area_id": "reconciliation", "action": "abstain",
             "fact_ids": [], "timestamp": "2026-09-02T10:00"},
        ]
        self.review: dict[str, tuple[ReviewStatus, str | None]] = {}

    # --- people / areas / docs
    def people(self) -> list[Person]:
        return list(self._people)

    def person(self, id: str) -> Person | None:
        return next((p for p in self._people if p.id == id), None)

    def areas(self) -> list[Area]:
        return list(self._areas)

    def area(self, id: str) -> Area | None:
        return next((a for a in self._areas if a.id == id), None)

    def doc(self, id: str) -> SourceDoc | None:
        return next((d for d in self._docs if d.id == id), None)

    def docs(self, ids: Sequence[str]) -> list[SourceDoc]:
        return [d for i in ids if (d := self.doc(i))]

    # --- facts
    def facts(self, *, area_id: str | None = None, person_id: str | None = None, kinds: Any = None,
              current_only: bool = False, as_of: date | None = None, include_private_for: str | None = None) -> list[Fact]:
        out = []
        for f in self._facts:
            if f.visibility == Visibility.PRIVATE and include_private_for != f.stated_by:
                continue
            if area_id and f.area_id != area_id:
                continue
            if person_id and f.stated_by != person_id:
                continue
            if kinds and f.kind not in kinds:
                continue
            if current_only and not f.is_current:
                continue
            if as_of and not (f.valid_from <= as_of and (f.valid_to is None or f.valid_to > as_of)):
                continue
            out.append(f)
        return out

    def fact(self, id: str) -> Fact | None:
        return next((f for f in self._facts if f.id == id), None)

    def supersession_chain(self, fact_id: str) -> list[Fact]:
        f = self.fact(fact_id)
        if f is None:
            return []
        while f.supersedes and (prev := self.fact(f.supersedes)):
            f = prev
        chain = [f]
        while chain[-1].superseded_by and (nxt := self.fact(chain[-1].superseded_by)):
            chain.append(nxt)
        return chain

    def expertise(self, *, area_id: str | None = None, person_id: str | None = None) -> list[Expertise]:
        return [e for e in self._exp if (area_id is None or e.area_id == area_id) and (person_id is None or e.person_id == person_id)]

    def docs_by(self, person_id: str, *, since: datetime | None = None) -> list[SourceDoc]:
        return [d for d in self._docs if d.author_id == person_id and (since is None or d.timestamp >= since)
                and d.visibility != Visibility.PRIVATE]

    def open_tickets(self, person_id: str) -> list[SourceDoc]:
        return [d for d in self._docs if d.source_type == SourceType.TICKET and d.meta.get("assignee") == person_id
                and d.meta.get("status") == "open"]

    # --- log / review
    def log_query(self, asker_id: str, question: str, answer: Answer) -> None:
        self._log.append({"asker_id": asker_id, "question": question, "area_id": answer.area_id,
                          "action": str(answer.action), "fact_ids": answer.fact_ids})

    def query_log(self, *, about_person_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._log
        if about_person_id:
            mine = {f.id for f in self._facts if f.stated_by == about_person_id}
            rows = [r for r in rows if set(r.get("fact_ids", [])) & mine]
        return rows[:limit]

    def set_review_status(self, fact_id: str, status: ReviewStatus, corrected_text: str | None = None) -> None:
        self.review[fact_id] = (status, corrected_text)

    def area_doc_counts_by_month(self, area_id: str) -> dict[str, int]:
        return {"2026-06": 3, "2026-07": 5, "2026-08": 9}


def test_fake_store_supersession_chain() -> None:
    s = FakeStore()
    assert [f.id for f in s.supersession_chain("F2")] == ["F1", "F2"]
    assert all(f.visibility != Visibility.PRIVATE for f in s.facts())

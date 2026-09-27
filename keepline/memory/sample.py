"""A tiny hand-written org + corpus for fast unit tests (independent of the generated Harbourline data).

Other agents may import it for fixture-based tests: ``from keepline.memory.sample import sample_org``.
"""

from __future__ import annotations

from datetime import date, datetime

from keepline.contracts import Area, DepartureType, Person, SourceDoc, SourceType, Visibility


def _p(id: str, name: str, role: str, team: str, **kw: object) -> Person:
    return Person(id=id, name=name, role=role, team=team, email=f"{id}@example.org",
                  start_date=date(2022, 1, 10), **kw)  # type: ignore[arg-type]


def sample_people() -> list[Person]:
    return [
        _p("sarah", "Sarah Chen", "Senior Backend Engineer", "engineering",
           departure_date=date(2026, 9, 11), departure_type=DepartureType.RESIGNATION),
        _p("mike", "Mike Doyle", "Controller", "finance"),
        _p("priya", "Priya Nair", "Payroll Specialist", "finance"),
        _p("dana", "Dana Brooks", "IT Administrator", "it"),
        _p("alex", "Alex Rivera", "Backend Engineer", "engineering"),
    ]


def sample_areas() -> list[Area]:
    return [
        Area("reconciliation", "Core banking reconciliation", "Nightly ledger reconciliation against the core.",
             ["reconciliation", "recon", "ledger", "interest posting", "mismatch"], ["Jenkins"], 3),
        Area("core_integration", "CoreLink integration", "API integration with the CoreLink core banking vendor.",
             ["api key", "integration", "vendor api", "key rotation"], ["CoreLink"], 3),
        Area("payroll", "Payroll", "Bi-weekly payroll and year-end slips.",
             ["payroll", "pay run", "t4", "deductions"], ["Ceridian"], 3),
        Area("it_access", "IT access & accounts", "Password manager, SSO, admin accounts.",
             ["password manager", "sso", "mfa", "admin account", "laptop"], ["1Password", "Okta"], 2),
    ]


def _d(id: str, st: SourceType, author: str, ts: str, text: str, container: str, **kw: object) -> SourceDoc:
    return SourceDoc(id=id, source_type=st, author_id=author, timestamp=datetime.fromisoformat(ts), text=text,
                     container=container, url=f"https://example.org/{id}", **kw)  # type: ignore[arg-type]


def sample_docs() -> list[SourceDoc]:
    S, E, T = SourceType.SLACK, SourceType.EMAIL, SourceType.TICKET
    return [
        _d("s1", S, "sarah", "2026-03-10T09:00:00",
           "Heads up: never run the reconciliation job on the 1st of the month. CoreLink posts interest that "
           "morning and the ledger double-posts.", "#eng-core"),
        _d("s2", S, "dana", "2026-03-20T10:00:00",
           "Reminder from Sarah: never run the reconciliation job on the 1st of the month.", "#eng-core"),
        _d("s3", S, "mike", "2026-04-02T13:00:00", "Is it ok to rotate the CoreLink API key this afternoon?",
           "#eng-core", thread_id="t-rotate"),
        _d("s4", S, "sarah", "2026-04-02T13:05:00",
           "Whatever you do, don't rotate the CoreLink API key on a Friday. Their weekend batch still uses the "
           "old key and fails.", "#eng-core", thread_id="t-rotate"),
        _d("e1", E, "priya", "2026-04-20T08:30:00",
           "Payroll runs every second Thursday. The Ceridian admin login is in the Finance vault in 1Password.",
           "payroll-schedule", title="Payroll schedule"),
        _d("t1", T, "mike", "2026-05-02T09:00:00",
           "Reconciliation mismatch after the May 1 run. Root cause: the job ran on the 1st during interest "
           "posting. Re-ran the reconciliation after CoreLink finished.", "HCU-12", title="Recon mismatch",
           meta={"status": "closed", "assignee": "sarah", "closed_at": "2026-05-03"}),
        _d("s5", S, "sarah", "2026-05-16T11:00:00",
           "Update: the reconciliation job now has to skip the 1st and the 15th. CoreLink added a mid-month "
           "interest run.", "#eng-core"),
        _d("dm1", S, "sarah", "2026-05-20T16:00:00", "The Jenkins admin password is on a sticky note, don't tell.",
           "dm-sarah-mike", visibility=Visibility.PRIVATE, participants=["sarah", "mike"]),
        _d("s6", S, "mike", "2026-05-22T12:00:00", "Anyone up for lunch Friday? Taco place on Spring Garden!",
           "#random"),
        _d("s7", S, "dana", "2026-06-01T09:00:00",
           "The Jenkins admin credentials are in the Engineering vault in 1Password.", "#it-private",
           visibility=Visibility.TEAM, participants=["dana", "sarah"]),
        _d("e2", E, "sarah", "2026-06-10T15:00:00",
           "Our rep at CoreLink is Dan Holt (dan.holt@corelink.example). Only my email is on file with them.",
           "corelink-contacts", title="CoreLink contacts"),
        _d("t2", T, "priya", "2026-07-01T09:00:00", "Ceridian T4 export failing for two employees.", "HCU-40",
           title="T4 export", meta={"status": "closed", "assignee": "priya", "closed_at": "2026-07-02"}),
        _d("t3", T, "mike", "2026-08-20T09:00:00", "Reconciliation report missing branch totals.", "HCU-51",
           title="Recon report", meta={"status": "open", "assignee": "sarah"}),
    ]


def sample_org() -> tuple[list[Person], list[Area], list[SourceDoc]]:
    return sample_people(), sample_areas(), sample_docs()

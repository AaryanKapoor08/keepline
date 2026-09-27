"""Harbourline Credit Union (Halifax, NS): HR roster, areas, and Slack channels.

People and areas are *product-world* inputs (what a customer would hand over). Nothing here states a truth fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from keepline.contracts import Area, DepartureType, Person, Visibility

DOMAIN = "harbourlinecu.ca"
WINDOW_START = date(2026, 3, 1)
WINDOW_END = date(2026, 8, 31)


def _p(pid: str, name: str, role: str, team: str, start: str, mgr: str | None, email_local: str | None = None,
       dep: str | None = None, dep_type: DepartureType | None = None) -> Person:
    local = email_local or name.lower().replace("'", "").replace(" ", ".")
    return Person(id=pid, name=name, role=role, team=team, email=f"{local}@{DOMAIN}",
                  start_date=date.fromisoformat(start),
                  departure_date=date.fromisoformat(dep) if dep else None, departure_type=dep_type, manager_id=mgr)


PEOPLE: list[Person] = [
    _p("marc", "Marc Leblanc", "Chief Executive Officer", "leadership", "2011-04-04", None),
    _p("dave", "Dave MacLeod", "Chief Operating Officer", "leadership", "2014-09-02", "marc"),
    _p("sarah", "Sarah Chen", "Senior Backend Engineer", "engineering", "2020-06-15", "dave",
       dep="2026-09-11", dep_type=DepartureType.RESIGNATION),
    _p("aisha", "Aisha Rahman", "Junior Backend Engineer", "engineering", "2025-08-05", "dave"),
    _p("alex", "Alex Rivera", "Backend Engineer", "engineering", "2026-09-14", "dave"),
    _p("mike", "Mike O'Brien", "IT Infrastructure Specialist (part-time contract)", "it", "2009-02-02", "dave",
       dep="2026-10-30", dep_type=DepartureType.CONTRACT_END),
    _p("nadia", "Nadia Kaur", "IT Support Analyst", "it", "2023-01-09", "dave"),
    _p("tom", "Tom Bouchard", "Compliance Officer", "operations", "2004-05-17", "marc",
       dep="2026-12-18", dep_type=DepartureType.RETIREMENT),
    _p("priya", "Priya Nair", "Finance & Payroll Manager", "finance", "2017-03-06", "dave"),
    _p("jen", "Jen Theriault", "Member Services Lead", "member_services", "2015-10-13", "dave"),
    _p("colin", "Colin Doucette", "Member Services Representative", "member_services", "2022-05-30", "jen"),
]
PEOPLE_BY_ID = {p.id: p for p in PEOPLE}
FIRST = {p.id: p.name.split()[0] for p in PEOPLE}
# People who produce corpus data (Alex starts after the window).
ACTIVE = [p.id for p in PEOPLE if p.id != "alex"]


AREAS: list[Area] = [
    Area("reconciliation", "Nightly core-banking reconciliation",
         "Nightly job that reconciles CoreLink core-banking balances against the general ledger.",
         ["reconciliation", "recon", "nightly job", "general ledger", "GL", "mismatch", "suspense account",
          "recon report"], ["CoreLink", "Jenkins"], 3),
    Area("corelink_api", "CoreLink core-banking API",
         "Integration with the CoreLink core-banking vendor: API keys, webhooks, vendor support.",
         ["CoreLink", "core banking", "API key", "API", "vendor portal", "webhook", "rate limit", "sandbox"],
         ["CoreLink"], 3),
    Area("ach_payments", "ACH / EFT payments",
         "Outbound and inbound EFT batches through Payments Canada (AFT/ACSS), returns, direct deposits.",
         ["ACH", "EFT", "AFT", "Payments Canada", "batch", "CPA 005", "returns", "direct deposit", "cutoff"],
         ["ACH batch server", "Payments Canada ACSS"], 3),
    Area("payroll", "Payroll",
         "Bi-weekly staff payroll, CRA remittances, T4s.",
         ["payroll", "pay run", "T4", "CRA", "remittance", "timesheets", "pay stub", "Paylane"], ["Paylane"], 3),
    Area("member_portal", "Member portal & online banking",
         "Member-facing online banking portal and mobile app: logins, 2FA, password resets, outages.",
         ["member portal", "online banking", "portal", "login", "2FA", "mobile app", "password reset"],
         ["Member Portal", "Twilio"], 2),
    Area("backups_dr", "Backups & disaster recovery",
         "Server backups, offsite copies, replication, and the disaster-recovery plan.",
         ["backup", "restore", "DR", "disaster recovery", "Veeam", "replication", "retention", "offsite"],
         ["Veeam", "NAS"], 3),
    Area("fintrac_reporting", "FINTRAC reporting & AML",
         "Regulatory reporting to FINTRAC (LCTR, STR, EFTR) and the AML compliance program.",
         ["FINTRAC", "LCTR", "large cash", "STR", "suspicious transaction", "AML", "EFTR", "compliance report"],
         ["FINTRAC API", "AML monitor"], 3),
    Area("identity_access", "Identity & access",
         "Okta, legacy Active Directory, admin rights, service accounts, joiner/leaver access.",
         ["Okta", "Active Directory", "AD", "admin rights", "MFA", "access request", "offboarding", "1Password",
          "service account"], ["Okta", "Active Directory", "1Password"], 2),
    Area("card_processing", "Debit card processing",
         "Debit card issuing and processing through the card vendor: Interac, disputes, card orders.",
         ["debit card", "card", "Interac", "chargeback", "dispute", "card processor", "PIN", "card order"],
         ["Tidewater Card Services"], 2),
    Area("ssl_dns", "SSL certificates & DNS",
         "TLS certificates for member-facing sites, DNS zones, and the domain registrar.",
         ["SSL", "TLS", "certificate", "cert", "DNS", "domain", "registrar", DOMAIN], ["Registrar", "DNS"], 2),
]
AREA_IDS = [a.id for a in AREAS]


@dataclass(frozen=True)
class Channel:
    name: str
    cid: str
    visibility: Visibility
    members: tuple[str, ...]


_ALL = tuple(ACTIVE)
CHANNELS: dict[str, Channel] = {c.name: c for c in [
    Channel("#general", "C01GENERAL", Visibility.PUBLIC, _ALL),
    Channel("#random", "C02RANDOM", Visibility.PUBLIC, _ALL),
    Channel("#eng-core", "C03ENGCORE", Visibility.PUBLIC, ("sarah", "aisha", "dave", "nadia", "mike")),
    Channel("#ops", "C04OPS", Visibility.PUBLIC, _ALL),
    Channel("#it-help", "C05ITHELP", Visibility.PUBLIC, _ALL),
    Channel("#incidents", "C06INCIDENTS", Visibility.PUBLIC, _ALL),
    Channel("#member-services", "C07MEMBERSVC", Visibility.PUBLIC, ("jen", "colin", "dave", "aisha", "sarah",
                                                                     "nadia", "tom")),
    Channel("#finance", "G08FINANCE", Visibility.TEAM, ("priya", "dave", "marc", "sarah")),
    Channel("#compliance", "G09COMPLIANCE", Visibility.TEAM, ("tom", "dave", "marc", "jen", "priya")),
    Channel("#leadership", "G10LEADERSHIP", Visibility.TEAM, ("marc", "dave", "tom", "priya")),
]}

# Where facts about an area are usually discussed (first = most likely).
AREA_CHANNELS: dict[str, list[str]] = {
    "reconciliation": ["#eng-core", "#finance", "#incidents"],
    "corelink_api": ["#eng-core", "#ops"],
    "ach_payments": ["#eng-core", "#finance", "#ops"],
    "payroll": ["#finance", "#general"],
    "member_portal": ["#member-services", "#eng-core", "#it-help"],
    "backups_dr": ["#ops", "#it-help"],
    "fintrac_reporting": ["#compliance", "#member-services"],
    "identity_access": ["#it-help", "#ops"],
    "card_processing": ["#member-services", "#finance", "#ops"],
    "ssl_dns": ["#eng-core", "#ops"],
}

# Who usually asks about an area (learners / adjacent roles).
AREA_ASKERS: dict[str, list[str]] = {
    "reconciliation": ["aisha", "priya", "dave"],
    "corelink_api": ["aisha", "dave", "nadia"],
    "ach_payments": ["aisha", "priya", "jen"],
    "payroll": ["dave", "jen", "colin", "nadia"],
    "member_portal": ["jen", "colin", "aisha"],
    "backups_dr": ["nadia", "dave", "sarah"],
    "fintrac_reporting": ["jen", "dave", "colin"],
    "identity_access": ["jen", "aisha", "dave", "colin"],
    "card_processing": ["colin", "jen", "priya"],
    "ssl_dns": ["aisha", "nadia", "dave"],
}

# Who does the hands-on work in an area (ticket assignees; standup mentions). Drives expertise signal.
AREA_DOERS: dict[str, list[str]] = {
    "reconciliation": ["sarah"],
    "corelink_api": ["sarah"],
    "ach_payments": ["sarah", "sarah", "aisha"],
    "payroll": ["priya"],
    "member_portal": ["aisha", "sarah", "aisha"],
    "backups_dr": ["mike", "mike", "nadia"],
    "fintrac_reporting": ["tom"],
    "identity_access": ["nadia", "nadia", "mike"],
    "card_processing": ["jen", "priya"],
    "ssl_dns": ["sarah"],
}

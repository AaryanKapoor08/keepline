"""Generate the eval question sets from the truth specs.

Split by *fact group* (a supersession chain or a single fact): every question about a group lands in exactly one
split, so test facts are never seen in train/dev. Quotas per qtype roughly follow the build plan
(fact 35%, current 15%, routing 10%, landmine 10%, unanswerable ~28%).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from keepline.contracts import Action, FactKind, QType, Question, Split
from keepline.data.company import AREA_DOERS, PEOPLE_BY_ID
from keepline.data.spec import FactSpec

SPLIT_FRAC = {Split.TRAIN: 350 / 700, Split.DEV: 150 / 700, Split.TEST: 200 / 700}
# Target questions per group, by category.
PER_GROUP = {"fact": 4, "current": 6, "routing": 7, "landmine": 7, "nic": 4, "private": 4, "never": 2}
ASKER_WEIGHTS = {"alex": 5, "aisha": 3, "jen": 2, "dave": 2, "colin": 1, "nadia": 1, "priya": 1}
ASOF_START, ASOF_END = date(2026, 9, 1), date(2026, 9, 30)

PREFIXES = ["Quick question — ", "Hey, ", "Sorry if this is obvious, but ", "For my onboarding notes: ",
            "Before I touch anything: ", "Does anyone know: ", "Hi! ", "Random one: ", "Can someone remind me — "]
SUFFIXES = ["", "", " Thanks!", " Asking for the handoff doc.", " Want to get this right."]
_LOWER_OK = {"what", "who", "how", "when", "where", "is", "are", "do", "does", "can", "should", "which", "any",
             "why", "if", "whose", "will", "was", "were", "has", "have", "did", "could", "would", "anything"}

# Plausible questions about things the org never discussed (no truth fact). (area, [phrasings])
NEVER_DISCUSSED: list[tuple[str, list[str]]] = [
    ("reconciliation", ["Is ATM cash part of the nightly recon job?",
                        "Do we reconcile the ATM cash cassettes in the recon run?"]),
    ("reconciliation", ["What's the SLA for clearing items out of the suspense account?",
                        "How quickly are we supposed to clear suspense account items?"]),
    ("reconciliation", ["Are mortgages part of the nightly recon?",
                        "Does the recon job cover the mortgage sub-ledger too?"]),
    ("corelink_api", ["Does CoreLink offer a GraphQL endpoint we're allowed to use?",
                      "Can we query CoreLink through GraphQL?"]),
    ("corelink_api", ["What's our annual spend with CoreLink?", "How much do we pay CoreLink per year?"]),
    ("corelink_api", ["Which city hosts CoreLink's production data centre?",
                      "Where physically is CoreLink's data centre?"]),
    ("corelink_api", ["Does CoreLink support webhooks for loan payments?",
                      "Can CoreLink push us an event when a loan payment posts?"]),
    ("corelink_api", ["How much has the board set aside to replace the core banking system?",
                      "What's the budget for a core-banking replacement project?"]),
    ("ach_payments", ["Can members send same-day ACH payments to American banks?",
                      "Do we support same-day ACH to US banks?"]),
    ("ach_payments", ["Is there a cap on the total value of one EFT batch file?",
                      "What's the maximum dollar amount for a single EFT batch?"]),
    ("ach_payments", ["Do we have a Bank of Canada liaison?", "Who is our contact at the Bank of Canada?"]),
    ("ach_payments", ["What's the incoming wire fee for members?", "Do we charge members for incoming wires?"]),
    ("payroll", ["What overtime multiplier do tellers get under the collective agreement?",
                 "Which union agreement governs overtime for tellers?"]),
    ("payroll", ["Is there employer RRSP matching through payroll?",
                 "Do we offer an RRSP matching program for staff?"]),
    ("payroll", ["When are salary bands being reviewed next?", "What's the date of the next salary benchmarking?"]),
    ("payroll", ["Is there a payroll advance policy for staff?", "Can an employee get an advance on their pay?"]),
    ("member_portal", ["When is dark mode coming to online banking?", "Is there a dark mode planned for the portal?"]),
    ("member_portal", ["Do we promise members a specific uptime for online banking?",
                       "What's the portal's uptime target in the member agreement?"]),
    ("member_portal", ["Is the member portal certified WCAG 2.1 AA?",
                       "Which accessibility standard does the portal certify against?"]),
    ("member_portal", ["Will the app support Face ID login?", "What's the plan for biometric login in the app?"]),
    ("member_portal", ["Will the mobile app support e-Transfer autodeposit?",
                       "Are we adding Interac e-Transfer auto-deposit to the app?"]),
    ("backups_dr", ["Are staff laptops included in the backup jobs?", "Do we back up employees' laptops?"]),
    ("backups_dr", ["Who is our cyber insurance broker?", "Which company brokers our cyber insurance?"]),
    ("backups_dr", ["Are the ATMs covered by the disaster recovery plan?", "Is the ATM network in the DR plan?"]),
    ("backups_dr", ["Is the phone system config included in backups?",
                    "Do we back up the phone system configuration?"]),
    ("fintrac_reporting", ["What's our process for virtual currency transaction reports?",
                           "Do we report crypto transactions to FINTRAC?"]),
    ("fintrac_reporting", ["What tool do we use for sanctions screening?",
                           "Which sanctions list vendor do we screen members against?"]),
    ("fintrac_reporting", ["How many STRs did we file in 2025?",
                           "What was our suspicious transaction report count last year?"]),
    ("identity_access", ["How often does the branch guest Wi-Fi password change?",
                         "What's the rotation policy for the guest Wi-Fi password?"]),
    ("identity_access", ["Is there a separate Okta group for contractors?",
                         "Do contractors get their own Okta group?"]),
    ("identity_access", ["Can I read work email on my personal phone?",
                         "Is there a policy on personal devices accessing email?"]),
    ("card_processing", ["When will members be able to add their debit card to Apple Pay?",
                         "Are we launching Apple Pay for our debit cards?"]),
    ("card_processing", ["How much does a member pay to replace a lost debit card?",
                         "What's the replacement fee for a lost card?"]),
    ("card_processing", ["Do members earn points on debit purchases?", "Is there a rewards program on our cards?"]),
    ("card_processing", ["Who designed the new debit card artwork?",
                         "Which agency did the 2025 card design refresh?"]),
    ("ssl_dns", ["Do we own harbourline.com as well?", "Is the harbourline.com domain ours?"]),
    ("ssl_dns", ["Is the marketing site changing hosts?", "Are we moving the public website to a new host?"]),
    ("ssl_dns", ["Is DNSSEC turned on for our domain?", "Do we have DNSSEC enabled on harbourlinecu.ca?"]),
]


@dataclass
class Group:
    key: str
    category: str  # fact | current | routing | landmine | nic | private | never
    area: str
    head: FactSpec | None
    chain: list[FactSpec]
    texts: list[str]
    known_by: list[str]


def _chains(specs: list[FactSpec]) -> list[list[FactSpec]]:
    by_key = {s.key: s for s in specs}
    has_successor = {s.supersedes for s in specs if s.supersedes}
    chains = []
    for s in specs:
        if s.key in has_successor:
            continue
        chain = [s]
        while chain[0].supersedes:
            chain.insert(0, by_key[chain[0].supersedes])
        chains.append(chain)
    return chains


def _category(head: FactSpec, chain: list[FactSpec]) -> str:
    if not head.in_corpus:
        return "nic"
    if head.private:
        return "private"
    if head.landmine:
        return "landmine"
    if len(chain) > 1:
        return "current"
    if head.kind is FactKind.OWNER:
        return "routing"
    return "fact"


def build_groups(specs: list[FactSpec]) -> list[Group]:
    groups = []
    for chain in _chains(specs):
        head = chain[-1]
        groups.append(Group(head.key, _category(head, chain), head.area, head, chain, list(head.qs),
                            list(head.known_by)))
    for i, (area, texts) in enumerate(NEVER_DISCUSSED):
        doers = list(dict.fromkeys(AREA_DOERS[area]))
        groups.append(Group(f"never.{i:02d}", "never", area, None, [], list(texts), doers))
    return groups


def _employed(pid: str, on: date) -> bool:
    p = PEOPLE_BY_ID[pid]
    return p.start_date <= on and (p.departure_date is None or p.departure_date >= on)


def routes(known_by: list[str], on: date, asker: str) -> list[str]:
    """Acceptable people to route to on ``on``: knowers still employed; if none, departed knowers + manager."""
    live = [p for p in known_by if p != asker and _employed(p, on)]
    if live:
        return live
    fallback = [p for p in known_by if p != asker]
    mgrs = [PEOPLE_BY_ID[p].manager_id for p in fallback if PEOPLE_BY_ID[p].manager_id]
    return list(dict.fromkeys([*fallback, *(m for m in mgrs if m and m != asker and _employed(m, on))]))


def _decap(q: str) -> str:
    first = q.split(" ", 1)[0].lower().strip(",?")
    return q[0].lower() + q[1:] if first in _LOWER_OK else q


def _variants(texts: list[str], n: int, rng: random.Random) -> list[str]:
    out = list(dict.fromkeys(texts))[: max(n, 0)] if len(texts) >= n else list(dict.fromkeys(texts))
    tries = 0
    while len(out) < n and tries < 50:
        tries += 1
        base = rng.choice(texts)
        v = rng.choice(PREFIXES) + _decap(base) + rng.choice(SUFFIXES)
        if v not in out:
            out.append(v)
    return out


def _assign_splits(groups: list[Group], sizes: dict[str, int], rng: random.Random) -> dict[str, Split]:
    out: dict[str, Split] = {}
    by_cat: dict[str, list[Group]] = {}
    for g in groups:
        by_cat.setdefault(g.category, []).append(g)
    for cat in sorted(by_cat):
        gs = sorted(by_cat[cat], key=lambda g: g.key)
        rng.shuffle(gs)
        got = {s: 0 for s in Split}
        total = 0
        for g in gs:
            total += sizes[g.key]
            split = max(Split, key=lambda s: (SPLIT_FRAC[s] * total - got[s], -list(Split).index(s)))
            got[split] += sizes[g.key]
            out[g.key] = split
    return out


def _asker(rng: random.Random, exclude: set[str]) -> str:
    people = [p for p in ASKER_WEIGHTS if p not in exclude]
    return rng.choices(people, weights=[ASKER_WEIGHTS[p] for p in people])[0]


def _as_of(rng: random.Random, asker: str) -> date:
    start = date(2026, 9, 14) if asker == "alex" else ASOF_START
    return start + timedelta(days=rng.randint(0, (ASOF_END - start).days))


def build_questions(specs: list[FactSpec], ids: dict[str, str], seed: int = 7) -> dict[Split, list[Question]]:
    rng = random.Random(seed * 1009 + 17)
    groups = build_groups(specs)
    texts = {g.key: _variants(g.texts, max(PER_GROUP[g.category], min(len(g.texts), PER_GROUP[g.category] + 2)),
                              rng) for g in groups}
    splits = _assign_splits(groups, {k: len(v) for k, v in texts.items()}, rng)
    out: dict[Split, list[Question]] = {s: [] for s in Split}
    for g in groups:
        head = g.head
        for i, text in enumerate(texts[g.key]):
            exclude = set(g.known_by) | ({head.stated_by} if head else set())
            asker = _asker(rng, exclude)
            as_of = _as_of(rng, asker)
            qtype, action = {
                "fact": (QType.FACT, Action.ANSWER), "current": (QType.CURRENT, Action.ANSWER),
                "routing": (QType.ROUTING, Action.ROUTE), "landmine": (QType.LANDMINE, Action.ANSWER),
                "nic": (QType.UNANSWERABLE, Action.ABSTAIN), "private": (QType.UNANSWERABLE, Action.ROUTE),
                "never": (QType.UNANSWERABLE, Action.ABSTAIN),
            }[g.category]
            if g.category == "landmine" and len(g.chain) > 1 and i % 2:
                qtype = QType.CURRENT
            forbid = head.forbid if head and qtype is QType.CURRENT else []
            route_pool = list(g.known_by)
            if head and head.kind is FactKind.OWNER:
                route_pool = [p for p in head.known_by if p not in ("dave", "marc")] or route_pool
            out[splits[g.key]].append(Question(
                id="", split=splits[g.key], text=text, asker_id=asker, as_of=as_of, qtype=qtype,
                area_id=g.area, expected_action=action,
                gold_fact_ids=[ids[head.key]] if head else [],
                gold_answer_keywords=[list(x) for x in head.kw] if head else [],
                gold_route_person_ids=routes(route_pool, as_of, asker),
                forbidden_keywords=[list(x) for x in forbid]))
    n = 0
    for split in Split:
        rng.shuffle(out[split])
        for q in out[split]:
            n += 1
            q.id = f"Q{n:04d}"
    return out

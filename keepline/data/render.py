"""Render the Harbourline corpus (Slack, email, tickets, wiki docs) from the truth specs.

Truth-first: every fact statement is embedded verbatim from a ``FactSpec.say`` variant, and every doc that carries
one is recorded in the evidence map. Everything else is chatter from ``phrasing`` that never states a tracked fact.
Deterministic for a given seed: all randomness flows through one ``random.Random``.
"""

from __future__ import annotations

import random
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Iterator

from keepline.contracts import SourceDoc, SourceType, Visibility
from keepline.data import phrasing as P
from keepline.data.company import (ACTIVE, AREA_ASKERS, AREA_CHANNELS, AREA_DOERS, AREAS, CHANNELS, DOMAIN, FIRST,
                                   PEOPLE_BY_ID, WINDOW_END, WINDOW_START, Channel)
from keepline.data.spec import FactSpec

EPOCH = datetime(1970, 1, 1)
AREA_NAME = {a.id: a.name for a in AREAS}
MIKE_FADE = date(2026, 6, 1)  # Mike's part-time activity thins out after May
# Phrasings anchored to the day of a change; only valid close to valid_from.
FRESH = re.compile(r"\b(today|tonight|this week|this morning|yesterday|last night|new rule|from now on|going forward|"
                   r"effective immediately|just (?:moved|switched|changed|finished|got|flipped))\b", re.I)


def business_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


DAYS = business_days(WINDOW_START, WINDOW_END)


def works_on(pid: str, d: date) -> bool:
    """Mike is part-time (Tue/Thu); Alex has not started."""
    if pid == "alex":
        return False
    if pid == "mike":
        return d.weekday() in (1, 3)
    return True


@dataclass
class Draft:
    source_type: SourceType
    author: str
    ts: datetime
    text: str
    container: str
    thread: str | None = None
    title: str | None = None
    participants: list[str] = field(default_factory=list)
    visibility: Visibility = Visibility.PUBLIC
    meta: dict[str, Any] = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    seq: int = 0
    cid: str = ""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class Renderer:
    def __init__(self, specs: list[FactSpec], seed: int = 7) -> None:
        self.rng = random.Random(seed)
        self.specs = specs
        self.drafts: list[Draft] = []
        self._seq = 0
        self._thread_n = 0
        self._variants: dict[str, list[str]] = {}
        self._fresh_used: dict[str, set[str]] = {}
        self._doc_queue: list[tuple[date, FactSpec, str]] = []

    # ------------------------------------------------------------------ primitives
    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _new_thread(self, prefix: str = "th") -> str:
        self._thread_n += 1
        return f"{prefix}{self._thread_n:05d}"

    def _at(self, d: date, lo: float = 8.5, hi: float = 17.0) -> datetime:
        minutes = self.rng.randint(int(lo * 60), int(hi * 60))
        return datetime.combine(d, time(0, 0)) + timedelta(minutes=minutes, seconds=self.rng.randint(0, 59))

    def _variant(self, s: FactSpec, d: date) -> str:
        """Cycle through a fact's phrasings in a seeded order so repeated renders use different wordings.

        Time-anchored phrasings ("starting today", "new rule") are only used within a few days of the change;
        later renders use the timeless ones, so no doc claims a change happened "today" three months later.
        """
        fresh_ok = timedelta(0) <= d - s.vfrom <= timedelta(days=4)
        fresh = [v for v in s.say if FRESH.search(v)]
        if fresh_ok and fresh:
            used = self._fresh_used.setdefault(s.key, set())
            unused = [v for v in fresh if v not in used]
            if unused:
                used.add(unused[0])
                return unused[0]
        pool = self._variants.get(s.key)
        if not pool:
            pool = [v for v in s.say if not FRESH.search(v)] or list(s.say)
            self.rng.shuffle(pool)
            self._variants[s.key] = pool
        return pool.pop()

    def _add(self, **kw: Any) -> Draft:
        dr = Draft(seq=self._next_seq(), **kw)
        self.drafts.append(dr)
        return dr

    # ------------------------------------------------------------------ slack
    def _channel_for(self, name: str, needed: list[str]) -> Channel:
        ch = CHANNELS.get(name, CHANNELS["#ops"])
        if ch.visibility is Visibility.TEAM and any(p not in ch.members for p in needed):
            return CHANNELS["#ops"]
        return ch

    def slack_thread(self, channel: Channel | str, d: date, msgs: list[tuple[str, str, list[str]]],
                     start: datetime | None = None) -> list[Draft]:
        """Post a root message plus replies. ``msgs`` = [(author, text, fact_keys)]."""
        if isinstance(channel, str):
            ch = CHANNELS[channel]
            container, cid, vis = ch.name, ch.cid, ch.visibility
        else:
            container, cid, vis = channel.name, channel.cid, channel.visibility
        ts = start or self._at(d)
        thread = self._new_thread() if len(msgs) > 1 else None
        authors = sorted({a for a, _, _ in msgs})
        if vis is Visibility.TEAM:
            parts = sorted(CHANNELS[container].members)
        else:
            parts = authors
        out = []
        for i, (author, text, facts) in enumerate(msgs):
            if i:
                ts = ts + timedelta(minutes=self.rng.randint(1, 45), seconds=self.rng.randint(0, 59))
            out.append(self._add(source_type=SourceType.SLACK, author=author, ts=ts, text=text,
                                 container=container, thread=thread, participants=list(parts), visibility=vis,
                                 facts=list(facts), cid=cid))
        return out

    def dm_thread(self, a: str, b: str, d: date, msgs: list[tuple[str, str, list[str]]]) -> list[Draft]:
        x, y = sorted((a, b))
        ch = Channel(f"D-{x}-{y}", f"D{x[:4].upper()}{y[:4].upper()}", Visibility.PRIVATE, (x, y))
        out = self.slack_thread(ch, d, msgs)
        for dr in out:
            dr.participants = [x, y]
        return out

    # ------------------------------------------------------------------ email
    def email_thread(self, d: date, subject: str, msgs: list[tuple[str, list[str], str, list[str]]],
                     to_list: str | None = None) -> list[Draft]:
        """``msgs`` = [(author, recipients, body, fact_keys)]. Visibility from the audience size."""
        thread = self._new_thread("mail")
        ts = self._at(d)
        everyone = sorted({m[0] for m in msgs} | {r for m in msgs for r in m[1]})
        if to_list:
            vis = Visibility.PUBLIC
        elif len(everyone) >= 3:
            vis = Visibility.TEAM
        else:
            vis = Visibility.PRIVATE
        out = []
        for i, (author, recips, body, facts) in enumerate(msgs):
            if i:
                ts = ts + timedelta(minutes=self.rng.randint(20, 300))
            to = [to_list] if to_list else [PEOPLE_BY_ID[r].email for r in recips]
            meta = {"from": PEOPLE_BY_ID[author].email, "to": to, "cc": []}
            title = subject if i == 0 else f"Re: {subject.removeprefix('Re: ')}"
            out.append(self._add(source_type=SourceType.EMAIL, author=author, ts=ts, text=body,
                                 container=f"mail:{thread}", thread=thread, title=title,
                                 participants=list(everyone), visibility=vis, meta=meta, facts=list(facts)))
        return out

    def _email_body(self, author: str, recips: list[str], core: str) -> str:
        greet = self.rng.choice(P.EMAIL_GREET).format(to=FIRST[recips[0]] if recips else "all")
        close = self.rng.choice(P.EMAIL_CLOSE)
        sign = f"{close}{FIRST[author]}" if close == "- " else f"{close}\n{FIRST[author]}"
        return f"{greet}\n\n{core}\n\n{sign}"

    # ------------------------------------------------------------------ tickets
    def ticket(self, *, area: str, title: str, reporter: str, assignee: str, created: datetime, status: str,
               closed_at: datetime | None, comments: list[tuple[str, datetime, str]], description: str,
               priority: str, facts: list[str] | None = None) -> Draft:
        last = max([created, *(c[1] for c in comments)] + ([closed_at] if closed_at else []))
        lines = [title, f"Reporter: {PEOPLE_BY_ID[reporter].name} | Assignee: {PEOPLE_BY_ID[assignee].name} | "
                        f"Priority: {priority} | Status: {status}", "", description]
        if comments:
            lines += ["", "Comments:"]
            lines += [f"- {PEOPLE_BY_ID[a].name} ({t:%Y-%m-%d %H:%M}): {c}" for a, t, c in comments]
        meta = {"status": status, "assignee": assignee, "reporter": reporter, "priority": priority,
                "area_hint": area, "created_at": created.isoformat(),
                "closed_at": closed_at.isoformat() if closed_at else None}
        return self._add(source_type=SourceType.TICKET, author=assignee, ts=last, text="\n".join(lines),
                         container="HCU", title=title, participants=sorted({reporter, assignee}),
                         visibility=Visibility.PUBLIC, meta=meta, facts=list(facts or []))

    # ------------------------------------------------------------------ fact rendering
    def _fact_dates(self, s: FactSpec, n: int) -> list[date]:
        lo = max(s.vfrom, WINDOW_START)
        hi = min(s.vto - timedelta(days=1), WINDOW_END) if s.vto else WINDOW_END
        if s.stated_by == "mike" and lo < MIKE_FADE:
            hi = min(hi, MIKE_FADE + timedelta(days=20))
        pool = [d for d in DAYS if lo <= d <= hi and works_on(s.stated_by, d)]
        if not pool:
            pool = [d for d in DAYS if lo <= d <= hi] or [next((d for d in DAYS if d >= lo), WINDOW_END)]
        first: list[date] = []
        if s.vfrom >= WINDOW_START:  # the change/decision is announced the day it happens
            first = [pool[0]]
        rest = [d for d in pool if d not in first]
        k = max(0, min(n - len(first), len(rest)))
        picked = sorted(first + self.rng.sample(rest, k))
        return picked or pool[:1]

    def _asker(self, s: FactSpec, exclude: set[str], channel: Channel | None = None) -> str:
        cands = [p for p in (s.askers or AREA_ASKERS[s.area]) if p not in exclude and p != "alex"]
        if channel is not None and channel.visibility is Visibility.TEAM:
            cands = [p for p in cands if p in channel.members] or [
                p for p in channel.members if p not in exclude]
        if not cands:
            cands = [p for p in ACTIVE if p not in exclude]
        return self.rng.choice(cands)

    def _prompt(self, s: FactSpec, knower: str) -> str:
        if s.prompts and self.rng.random() < 0.55:
            return self.rng.choice(s.prompts)
        topic = self.rng.choice(P.TOPIC[s.area])
        return self.rng.choice(P.GENERIC_PROMPTS).format(knower=FIRST[knower].lower(), topic=topic)

    def render_fact(self, s: FactSpec) -> None:
        if not s.in_corpus:
            return
        n = s.renders or {3: 4, 2: 3, 1: 2}[s.importance]
        if s.private:
            n = min(n, 2)
        dates = self._fact_dates(s, n)
        where = ["dm"] if s.private else (s.where or [*AREA_CHANNELS[s.area][:2], "email", "ticket"])
        contra_pending = list(s.contra)
        offset = self.rng.randrange(len(where))
        for i, d in enumerate(dates):
            w = where[(i + offset) % len(where)]
            if contra_pending and w in ("email", "ticket", "doc", "dm"):
                w = next((x for x in where if x.startswith("#")), AREA_CHANNELS[s.area][0])
            say = self._variant(s, d)
            if w == "dm":
                self._fact_dm(s, d, say)
            elif w == "email":
                self._fact_email(s, d, say)
            elif w == "ticket":
                self._fact_ticket(s, d, say)
            elif w == "doc":
                self._doc_queue.append((d, s, say))
            else:
                contra = contra_pending.pop(0) if contra_pending else None
                self._fact_slack(s, d, say, w, contra)

    def _fact_slack(self, s: FactSpec, d: date, say: str, channel_name: str,
                    contra: tuple[str, str] | None) -> None:
        k = s.stated_by
        extra = [contra[0]] if contra else []
        ch = self._channel_for(channel_name, [k, *extra])
        if contra is None and self.rng.random() < 0.3:
            text = self.rng.choice(P.ANNOUNCE_WRAP).format(say=say)
            msgs = [(k, text, [s.key])]
            if self.rng.random() < 0.5:
                msgs.append((self._asker(s, {k}, ch), self.rng.choice(P.THANKS), []))
            self.slack_thread(ch, d, msgs)
            return
        asker = self._asker(s, {k}, ch)
        msgs: list[tuple[str, str, list[str]]] = [(asker, self._prompt(s, k), [])]
        if contra:
            who, wrong = contra
            if who != asker:
                msgs.append((who, wrong, []))
            else:
                msgs[0] = (asker, f"{msgs[0][1]} {wrong}", [])
            msgs.append((k, self.rng.choice(P.CORRECT_WRAP).format(say=say), [s.key]))
        else:
            msgs.append((k, self.rng.choice(P.ANSWER_WRAP).format(say=say, asker=FIRST[asker].lower()), [s.key]))
        if self.rng.random() < 0.6:
            msgs.append((asker, self.rng.choice(P.THANKS), []))
        self.slack_thread(ch, d, msgs)

    def _fact_dm(self, s: FactSpec, d: date, say: str) -> None:
        k = s.stated_by
        partner = s.askers[0] if s.askers else self._asker(s, {k})
        msgs = [(partner, self._prompt(s, k), []), (k, say, [s.key])]
        if self.rng.random() < 0.5:
            msgs.append((partner, self.rng.choice(P.THANKS), []))
        self.dm_thread(k, partner, d, msgs)

    def _audience(self, s: FactSpec, asker: str) -> list[str]:
        pool = [p for p in dict.fromkeys([*AREA_ASKERS[s.area], *AREA_DOERS[s.area], "dave"])
                if p not in (s.stated_by, asker, "alex")]
        self.rng.shuffle(pool)
        return sorted({asker, *pool[:2]})

    def _fact_email(self, s: FactSpec, d: date, say: str) -> None:
        k = s.stated_by
        asker = self._asker(s, {k})
        recips = self._audience(s, asker)
        subject = self.rng.choice(P.EMAIL_SUBJECTS[s.area])
        if self.rng.random() < 0.5:
            q = self.rng.choice(P.EMAIL_ASK).format(prompt=self._prompt(s, k), knower=FIRST[k])
            q_recips = sorted({k, *[r for r in recips if r != asker]})
            msgs = [(asker, q_recips, self._email_body(asker, [k], q), []),
                    (k, recips, self._email_body(k, [asker], say), [s.key])]
            self.email_thread(d, subject.removeprefix("Re: "), msgs)
        else:
            self.email_thread(d, subject, [(k, recips, self._email_body(k, recips, say), [s.key])])

    def _fact_ticket(self, s: FactSpec, d: date, say: str) -> None:
        k = s.stated_by
        reporter = self._asker(s, {k})
        closed = self._at(d, 10, 17)
        created = closed - timedelta(days=self.rng.randint(0, 4), hours=self.rng.randint(1, 6))
        if created.date() < WINDOW_START:
            created = datetime.combine(WINDOW_START, time(9, 0))
        desc = f"{self._prompt(s, k)}\n\nOpening a ticket so the answer is written down somewhere."
        comments = [(k, closed - timedelta(minutes=self.rng.randint(5, 90)), say)]
        if self.rng.random() < 0.5:
            comments.append((reporter, closed, self.rng.choice(P.THANKS)))
        self.ticket(area=s.area, title=self.rng.choice(P.TICKET_FACT_TITLES[s.area]), reporter=reporter,
                    assignee=k, created=created, status="Closed", closed_at=closed, comments=comments,
                    description=desc, priority=self.rng.choice(["Low", "Medium", "Medium", "High"]),
                    facts=[s.key])

    def _flush_docs(self) -> None:
        """Group queued doc renders into wiki pages: one page per (area, author, month)."""
        groups: dict[tuple[str, str, str], list[tuple[date, FactSpec, str]]] = defaultdict(list)
        for d, s, say in self._doc_queue:
            groups[(s.area, s.stated_by, f"{d:%Y-%m}")].append((d, s, say))
        titles = ["runbook", "notes", "how-to", "FAQ", "cheat sheet"]
        for (area, author, _month), items in sorted(groups.items()):
            page_day = max(d for d, _, _ in items)
            keep = [(d, s, v) for d, s, v in items if s.vfrom <= page_day and (s.vto is None or s.vto > page_day)]
            for d, s, v in items:
                if (d, s, v) not in keep:
                    self._fact_slack(s, d, v, AREA_CHANNELS[s.area][0], None)
            if not keep:
                continue
            seen: set[str] = set()
            bullets = []
            for _, s, v in keep:
                if s.key not in seen:
                    seen.add(s.key)
                    bullets.append((s.key, v))
            title = f"{AREA_NAME[area]} — {self.rng.choice(titles)}"
            ts = self._at(page_day, 15, 18)
            intro = self.rng.choice([
                f"Working notes on {self.rng.choice(P.TOPIC[area])}. Not exhaustive — ask in Slack if unsure.",
                "Things worth knowing, collected from threads and tickets.",
                "Living page. If something here is wrong, fix it or ping the owner.",
            ])
            text = "\n".join([f"# {title}", f"Owner: {PEOPLE_BY_ID[author].name} · Last updated {page_day}", "",
                              intro, "", *[f"- {v}" for _, v in bullets]])
            self._add(source_type=SourceType.DOC, author=author, ts=ts, text=text,
                      container=f"wiki/{area}/{_slug(title)}", title=title, participants=[author],
                      visibility=Visibility.PUBLIC, facts=[k for k, _ in bullets])

    # ------------------------------------------------------------------ chatter
    def _pick_author(self, pool: list[str] | tuple[str, ...], d: date) -> str:
        cands = [p for p in pool if works_on(p, d) and (p != "mike" or d < MIKE_FADE or self.rng.random() < 0.3)]
        return self.rng.choice(cands or [p for p in pool if p not in ("alex", "mike")])

    def render_noise(self) -> None:
        r = self.rng
        for d in DAYS:
            for _ in range(r.randint(1, 4)):
                self._chat("#random", d, P.RANDOM, replies=0.35)
            if r.random() < 0.35:
                text = r.choice(P.GENERAL).format(who=FIRST[r.choice(ACTIVE)])
                self.slack_thread("#general", d, [(r.choice(["dave", "marc", "jen", "priya"]), text, [])])
            for pid in ("sarah", "aisha"):
                if r.random() < 0.85:
                    tasks = P.STANDUP_TASKS[pid]
                    text = P.STANDUP.format(y=r.choice(tasks), t=r.choice(tasks), b=r.choice(P.STANDUP_BLOCKERS))
                    self.slack_thread("#eng-core", d, [(pid, text, [])], start=self._at(d, 9.1, 9.6))
            for _ in range(r.randint(1, 3)):
                text = r.choice(P.ENG).format(thing=r.choice(P.ENG_THINGS))
                self._chat("#eng-core", d, [text], replies=0.3, pool=("sarah", "aisha", "sarah", "nadia", "dave"))
            for _ in range(r.randint(0, 2)):
                self._chat("#ops", d, P.OPS, replies=0.2, pool=("nadia", "mike", "dave", "mike"))
            for _ in range(r.randint(1, 2)):
                asker = self._pick_author([p for p in ACTIVE if p not in ("nadia",)], d)
                helper = "mike" if works_on("mike", d) and r.random() < 0.3 else "nadia"
                msgs = [(asker, r.choice(P.ITHELP_Q), []), (helper, r.choice(P.ITHELP_A), [])]
                if r.random() < 0.5:
                    msgs.append((asker, r.choice(P.THANKS), []))
                self.slack_thread("#it-help", d, msgs)
            for _ in range(r.randint(1, 3)):
                self._chat("#member-services", d, P.MEMBER, replies=0.3, pool=("jen", "colin", "colin", "jen"))
            if r.random() < 0.6:
                self._chat("#finance", d, P.FINANCE, replies=0.3, pool=("priya", "priya", "dave", "marc"))
            if r.random() < 0.3:
                self._chat("#compliance", d, P.COMPLIANCE, replies=0.3, pool=("tom", "tom", "jen", "dave"))
            if r.random() < 0.25:
                self._chat("#leadership", d, P.LEADERSHIP, replies=0.5, pool=("marc", "dave", "tom", "priya"))
            for _ in range(r.randint(0, 3)):
                a, b = r.sample([p for p in ACTIVE if works_on(p, d)], 2)
                msgs = [(a, r.choice(P.DM), [])]
                if r.random() < 0.7:
                    msgs.append((b, r.choice(P.DM), []))
                self.dm_thread(a, b, d, msgs)
            if r.random() < 0.8:
                subj, body = r.choice(P.EMAIL_NOISE)
                author = r.choice(["dave", "marc", "priya", "jen", "tom"])
                self.email_thread(d, subj, [(author, [], self._email_body(author, [], body), [])],
                                  to_list=f"all@{DOMAIN}")
            if r.random() < 0.3:
                a, b = r.sample([p for p in ACTIVE if works_on(p, d)], 2)
                subj = r.choice(["Quick question", "Catch up", "Tomorrow", "Re: notes", "Friday"])
                self.email_thread(d, subj, [(a, [b], self._email_body(a, [b], r.choice(P.DM).capitalize() + "."),
                                             [])])

    def _chat(self, channel: str, d: date, bank: list[str], replies: float,
              pool: tuple[str, ...] | None = None) -> None:
        ch = CHANNELS[channel]
        authors = pool or ch.members
        a = self._pick_author(authors, d)
        msgs = [(a, self.rng.choice(bank), [])]
        if self.rng.random() < replies:
            b = self._pick_author([p for p in ch.members if p != a], d)
            msgs.append((b, self.rng.choice(P.THANKS + P.DM[:6]), []))
        self.slack_thread(ch, d, msgs)

    def render_tickets(self) -> None:
        r = self.rng
        for area in sorted(P.BG_TICKETS):
            for _ in range(18):
                d = r.choice(DAYS[:-8])
                assignee = r.choice(AREA_DOERS[area])
                if not works_on(assignee, d):
                    d = next((x for x in DAYS if x >= d and works_on(assignee, x)), d)
                reporter = r.choice([p for p in AREA_ASKERS[area] if p != assignee] or ["dave"])
                title = r.choice(P.BG_TICKETS[area]).format(
                    d=f"{d:%b %d}", n=r.randint(2, 99), who=FIRST[r.choice(ACTIVE)])
                created = self._at(d)
                closed = created + timedelta(days=r.randint(0, 6), hours=r.randint(1, 5))
                comments = [(assignee, created + timedelta(hours=r.randint(1, 20)), r.choice(P.TICKET_COMMENTS))
                            for _ in range(r.randint(1, 3))]
                comments.sort(key=lambda c: c[1])
                closed = max(closed, comments[-1][1] + timedelta(minutes=5))
                if closed.date() > WINDOW_END:
                    closed = datetime.combine(WINDOW_END, time(16, 0))
                self.ticket(area=area, title=title, reporter=reporter, assignee=assignee, created=created,
                            status="Closed", closed_at=closed, comments=comments,
                            description=f"Raised from #{r.choice(['eng-core', 'ops', 'it-help', 'finance'])}.",
                            priority=r.choice(["Low", "Medium", "Medium", "High"]))
        for assignee, area, title, desc, created_s in P.OPEN_TICKETS:
            created = self._at(date.fromisoformat(created_s))
            comments = [(assignee, created + timedelta(days=r.randint(1, 10), hours=r.randint(0, 5)),
                         r.choice(["Started on this.", "Partway through, notes in the branch.", "Blocked on vendor "
                                   "reply.", "Picking this back up next week."]))]
            self.ticket(area=area, title=title, reporter=r.choice(["dave", "priya", "jen"]), assignee=assignee,
                        created=created, status=r.choice(["Open", "In Progress"]), closed_at=None,
                        comments=comments, description=desc, priority=r.choice(["Medium", "High"]))

    def render_events(self) -> None:
        """Scripted org events: announcements, the May 15 recon incident, Sarah's notice."""
        r = self.rng
        for ds, author, text in P.EXTRA_GENERAL:
            d = date.fromisoformat(ds)
            replies = [(p, r.choice(P.EXTRA_GENERAL_REPLIES), []) for p in r.sample(
                [x for x in ACTIVE if x != author and x != "mike"], 3)]
            self.slack_thread("#general", d, [(author, text, []), *replies], start=self._at(d, 13, 15))
        d = date(2026, 5, 15)
        self.slack_thread("#incidents", d, [
            ("sarah", "Recon threw a wall of mismatches overnight and the suspense account is way off. Finance, please "
                      "hold off on clearing anything from suspense until I dig in.", []),
            ("priya", "Ugh. Ok, holding.", []),
            ("dave", "Keep us posted. Anything member-facing?", []),
            ("sarah", "Not member-facing as far as I can tell — balances in the portal are fine. Looks like the job "
                      "picked up something mid-month it shouldn't have. Will write it up.", []),
            ("sarah", "Cleaned up suspense by hand, reran for yesterday. Postmortem + job change coming.", []),
        ], start=datetime(2026, 5, 15, 7, 42))
        self.ticket(area="reconciliation", title="INC: reconciliation mismatches on May 15", reporter="priya",
                    assignee="sarah", created=datetime(2026, 5, 15, 8, 5), status="Closed",
                    closed_at=datetime(2026, 5, 20, 11, 30),
                    comments=[("sarah", datetime(2026, 5, 15, 16, 10), "Suspense cleaned up manually, rerun done."),
                              ("sarah", datetime(2026, 5, 20, 11, 20), "Job change deployed. Closing.")],
                    description="Nightly recon flagged ~1,200 mismatches. Suspense account out of balance.",
                    priority="Highest")
        d = date(2026, 6, 23)
        self.slack_thread("#incidents", d, [
            ("jen", "Members calling that the portal is down — anyone?", []),
            ("aisha", "Looking. Getting 502s.", []),
            ("sarah", "App pool recycled itself, back up now. ~20 min outage.", []),
            ("jen", "Thank you!! I'll let the branches know", []),
        ], start=datetime(2026, 6, 23, 10, 12))
        body = ("Hi Dave,\n\nI wanted you to hear it from me first: I've accepted another offer and my last day will be "
                "Friday, September 11. I've really loved working here and I'll do everything I can to leave things "
                "in good shape — I'll start writing handoff notes this week.\n\nThanks for everything,\nSarah")
        self.email_thread(date(2026, 8, 28), "Resignation", [("sarah", ["dave"], body, [])])

    # ------------------------------------------------------------------ build
    def render(self) -> tuple[list[SourceDoc], dict[str, list[str]]]:
        for s in self.specs:
            self.render_fact(s)
        self._flush_docs()
        self.render_noise()
        self.render_tickets()
        self.render_events()
        return self._finalize()

    def _finalize(self) -> tuple[list[SourceDoc], dict[str, list[str]]]:
        drafts = sorted(self.drafts, key=lambda x: (x.ts, x.seq))
        counters: dict[SourceType, int] = defaultdict(int)
        ids: dict[int, str] = {}
        tickets = sorted((x for x in drafts if x.source_type is SourceType.TICKET),
                         key=lambda x: (x.meta["created_at"], x.seq))
        ticket_key = {x.seq: f"HCU-{101 + i}" for i, x in enumerate(tickets)}
        for x in drafts:
            if x.source_type is SourceType.TICKET:
                ids[x.seq] = f"ticket-{ticket_key[x.seq]}"
                continue
            counters[x.source_type] += 1
            n = counters[x.source_type]
            ids[x.seq] = {SourceType.SLACK: f"slack-{n:06d}", SourceType.EMAIL: f"email-{n:06d}",
                          SourceType.DOC: f"doc-{n:04d}"}[x.source_type]
        roots: dict[str, Draft] = {}
        for x in drafts:
            if x.thread and x.thread not in roots:
                roots[x.thread] = x
        docs: list[SourceDoc] = []
        evidence: dict[str, list[str]] = defaultdict(list)
        for x in drafts:
            did = ids[x.seq]
            thread_id = ids[roots[x.thread].seq] if x.thread else None
            container, title = x.container, x.title
            if x.source_type is SourceType.SLACK:
                url = f"https://harbourline.slack.com/archives/{x.cid}/p{_micros(x)}"
                if x.thread and roots[x.thread] is not x:
                    root = roots[x.thread]
                    url += f"?thread_ts={_micros(root) // 1_000_000}.{_micros(root) % 1_000_000:06d}"
            elif x.source_type is SourceType.EMAIL:
                container = f"mail:{thread_id}"
                url = f"https://mail.{DOMAIN}/thread/{thread_id}/{did}"
            elif x.source_type is SourceType.TICKET:
                key = ticket_key[x.seq]
                container, title = key, f"[{key}] {x.title}"
                x.text = f"[{key}] {x.text}"
                url = f"https://harbourline.atlassian.net/browse/{key}"
            else:
                url = f"https://harbourline.atlassian.net/wiki/spaces/HCU/pages/{100000 + int(did[4:])}/" \
                      f"{_slug(x.title or did)}"
            docs.append(SourceDoc(id=did, source_type=x.source_type, author_id=x.author, timestamp=x.ts,
                                  text=x.text, container=container, thread_id=thread_id, title=title,
                                  participants=x.participants, visibility=x.visibility, url=url, meta=x.meta))
            for k in x.facts:
                evidence[k].append(did)
        return docs, {k: sorted(v) for k, v in evidence.items()}


def _micros(x: Draft) -> int:
    return int((x.ts - EPOCH).total_seconds()) * 1_000_000 + (x.seq * 7919) % 1_000_000


def iter_by_source(docs: list[SourceDoc]) -> Iterator[tuple[SourceType, list[SourceDoc]]]:
    for st in SourceType:
        yield st, [d for d in docs if d.source_type is st]

"""Extraction: raw work-tool messages -> atomic, receipt-backed ``Fact`` candidates.

Two extractors share one interface (``Extractor.extract_thread``):

* ``HeuristicExtractor`` (default, offline, deterministic). A general cue-phrase classifier of the kind a
  real deployment would ship on day one: segment sentences, classify each by linguistic cues into the
  operational kinds that hurt most when lost (landmines, access, vendor contacts, recurring tasks, decisions,
  owners, procedures), link to areas through the customer's area lexicon, detect the subject (system/entity),
  and resolve Q&A threads (a terse answer inherits the question's area and subject). It is intentionally NOT
  tuned to any particular generator's phrasing -- the benchmark must measure a real extractor.
* ``LLMExtractor`` (Claude or Cortex via ``keepline.llm``): one JSON-schema call per thread; every returned
  quote must be a verbatim span of its source doc or the fact is dropped (receipts are non-negotiable).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, Sequence

from keepline.contracts import Area, Fact, FactKind, Person, SourceDoc, SourceType, Visibility
from keepline.retrieval.text import raw_tokens, split_sentences, stem, tokenize

log = logging.getLogger(__name__)

# ------------------------------------------------------------------------------------------------ cue lexicon

_DONT_OK = r"(?!know|think|worry|have|see|mind|remember|care|want|need|get|understand|recall|believe|agree|like)"
KIND_CUES: list[tuple[FactKind, re.Pattern[str], float]] = [
    (
        FactKind.LANDMINE,
        re.compile(
            r"\b(never|must not|mustn'?t|do not|shouldn'?t ever|under no circumstances|whatever you do|"
            rf"don'?t {_DONT_OK}\w+|do ?n[o']t ever|avoid|watch out|beware|be careful|careful (with|not)|gotcha|"
            r"will (break|fail|corrupt|lock)|it (breaks|fails|locks)|blows up|double[- ]post|learned the hard way|"
            r"bad things happen|do not touch|hands off|landmine)\b",
            re.I,
        ),
        0.75,
    ),
    (
        FactKind.ACCESS,
        re.compile(
            r"\b(admin(istrator)?s?|admin rights|credentials?|creds|passwords?|vault|1password|lastpass|bitwarden|"
            r"keepass|password manager|api keys?|ssh keys?|login|log ?in to|access to|has access|root access|"
            r"secrets?|tokens?|mfa|2fa|yubikey|super ?user|service account|break[- ]glass|keys? (is|are) (in|stored))\b",
            re.I,
        ),
        0.7,
    ),
    (
        FactKind.VENDOR_CONTACT,
        re.compile(
            r"\b(our (\w+ ){0,2}(rep|account (manager|exec\w*)|contact|csm)|(new |their )?rep is|account manager|account exec\w*|rep (at|from|for)|"
            r"contact (at|from|for)|point of contact|support (line|number|desk|portal)|escalat\w+ (to|with)|"
            r"customer success|vendor contact|sales engineer|reach (out to|them at)|their (support|rep))\b",
            re.I,
        ),
        0.7,
    ),
    (
        FactKind.RECURRING_TASK,
        re.compile(
            r"\b(every (other |second |2nd |third |first |last )?(day|night|week|month|quarter|year|morning|evening|weekday|business day|monday|tuesday|wednesday|thursday|"
            r"friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|"
            r"december)|each (day|week|month|quarter|year)|(bi)?weekly|monthly|quarterly|nightly|daily|annually|"
            r"yearly|fortnightly|bi-weekly|renews?|renewal|expires?|recurring|month[- ]end|year[- ]end|quarter[- ]end|twice a|"
            r"once a (week|month|quarter|year)|on the \d+(st|nd|rd|th) of (each|every) month|cron)\b",
            re.I,
        ),
        0.65,
    ),
    (
        FactKind.DECISION,
        re.compile(
            r"\b(we decided|decided to|decided that|decision (is|was)|going forward|from now on|we'?re switching|"
            r"we are switching|switched (to|over)|we'?ll use|we will use|we'?re moving|we are moving|moving to|"
            r"we agreed|agreed to|approved|signed off|the plan is|policy is|we chose|we'?re going with|"
            r"we are going with|no longer)\b",
            re.I,
        ),
        0.65,
    ),
    (
        FactKind.OWNER,
        re.compile(
            r"\b(owns?|owner of|responsible for|in charge of|point person|go-?to (person|for)|handles?|looks after|"
            r"takes care of|maintains?|is on point|accountable for|runs point)\b",
            re.I,
        ),
        0.6,
    ),
    (
        FactKind.PROCEDURE,
        re.compile(
            r"(^\s*(\d+[.)]|step \d+|first,?|then,?|next,?|after that,?|finally,?)\s|\b(to (do|run|fix|restart|reset|"
            r"rerun|re-run|export|import|deploy|rotate|renew|submit|file|close|reconcile) (it|this|the|a)\b|"
            r"^always\b|you (have|need) to|make sure (you|to)|the steps|runbook|restart the|rerun the|re-run the|log into|"
            r"click |go to |ssh (in|into)|run the)|->|\b(must|has to|have to|needs to|need to|required to)\b)",
            re.I,
        ),
        0.55,
    ),
]

UPDATE_CUE = re.compile(
    r"\b(update[ds]?|now|changed?|no longer|anymore|actually|correction|instead|as of|also|going forward|"
    r"from now on|new|moved to|switched|replac\w+|revised|turns out|scratch that|not .{1,30} anymore)\b",
    re.I,
)
HEDGE = re.compile(r"\b(i think|maybe|not sure|probably|iirc|i guess|might be|possibly|i believe|could be)\b", re.I)
NEGATION = re.compile(r"\b(never|not|no|don'?t|doesn'?t|isn'?t|mustn'?t|shouldn'?t|can'?t|won'?t)\b", re.I)
PERSONAL = re.compile(
    r"\b(weekend|kids?|daughter|son|wife|husband|partner|birthday|vacation|lunch|dinner|coffee|movie|netflix|"
    r"hockey|soccer|gym|dentist|doctor|sick day|feeling (better|sick|unwell)|wedding|baby|dog|puppy|cat|hike|"
    r"camping|beach|recipe|traffic|potluck|bbq|brunch|cottage|concert|leftovers|cake)\b",
    re.I,
)
COURTESY = re.compile(
    r"^(thanks|thank you|ty|cheers|sounds good|will do|ok(ay)?|great|awesome|nice|np|no problem|lol|haha|\+1|done|"
    r"on it|yep|yes|no|perfect|got it|noted|appreciate it|good call|agreed)\b[\s.!,:)]*(thanks|all|team|\w+)?[.!]*$",
    re.I,
)
HEAD_NOUNS = frozenset(
    """job jobs key keys cert certs certificate certificates server servers report reports process script scripts vault
    portal account accounts contract contracts license licenses licence invoice invoices backup backups cron pipeline
    integration export exports file files batch batches renewal renewals run feed token tokens password passwords
    credentials login domain dns firewall vpn router printer database db queue endpoint sftp upload uploads
    payroll reconciliation audit filing return returns deposit deposits statement statements schedule policy form
    forms rotation deadline window migration build deploy release""".split()
)
MODIFIERS = frozenset(
    "api admin nightly batch sftp prod production service month-end monthly weekly daily quarterly annual year-end "
    "ssl tls root master main shared backup test staging vendor core member".split()
)
PRONOUN_START = re.compile(r"^(it|that|this|they|those|these|yes|yeah|yep|no|nope|so|and|but|also)\b", re.I)
SUBJECT_RE = re.compile(
    r"\b(?:the|our|their|this|that)\s+((?:[A-Za-z0-9][\w.-]*\s+){0,2}(?:" + "|".join(sorted(HEAD_NOUNS)) + r"))\b",
    re.I,
)
CAPSEQ = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][A-Za-z0-9]+(?:[ -][A-Z0-9][A-Za-z0-9]+)*)\b")


# ------------------------------------------------------------------------------------------------ area linking


@dataclass
class AreaLinker:
    """Links text to areas via the customer's lexicon (keywords, systems, name).

    Multi-word phrases match as phrases; single words match on stems. Systems weigh most (they are
    unambiguous), generic single keywords least.
    """

    areas: Sequence[Area]
    _phrases: list[tuple[str, re.Pattern[str], float]] = field(default_factory=list, init=False)
    _single: dict[str, list[tuple[str, float]]] = field(default_factory=dict, init=False)
    systems: list[tuple[str, str]] = field(default_factory=list, init=False)  # (system name, area_id)

    def __post_init__(self) -> None:
        df: dict[str, int] = {}
        for a in self.areas:
            for w in {stem(t) for kw in a.keywords for t in raw_tokens(kw)}:
                df[w] = df.get(w, 0) + 1
        n = max(1, len(self.areas))
        for a in self.areas:
            entries = [(s, 2.0) for s in a.systems] + [(kw, 1.0) for kw in a.keywords] + [(a.name, 1.5)]
            for text, w in entries:
                toks = raw_tokens(text)
                if not toks:
                    continue
                if len(toks) > 1:
                    pat = re.compile(r"\b" + r"[\s_-]+".join(re.escape(t) for t in toks) + r"\w*", re.I)
                    self._phrases.append((a.id, pat, w * 1.3))
                else:
                    s = stem(toks[0])
                    # a keyword shared by many areas is weak evidence for any one of them
                    weight = w / max(1.0, df.get(s, 1) / max(1.0, n / 6))
                    self._single.setdefault(s, []).append((a.id, weight))
            for s in a.systems:
                self.systems.append((s, a.id))
        self.systems.sort(key=lambda x: -len(x[0]))

    def link(self, text: str) -> list[tuple[str, float]]:
        scores: dict[str, float] = {}
        for aid, pat, w in self._phrases:
            if pat.search(text):
                scores[aid] = scores.get(aid, 0.0) + w
        for t in set(tokenize(text)):
            for aid, w in self._single.get(t, ()):
                scores[aid] = scores.get(aid, 0.0) + w
        return sorted(((a, s) for a, s in scores.items() if s >= 0.9), key=lambda x: (-x[1], x[0]))

    def best(self, text: str) -> str | None:
        links = self.link(text)
        return links[0][0] if links else None


# ------------------------------------------------------------------------------------------------ sentence analysis


def classify_kind(sentence: str) -> tuple[FactKind | None, float]:
    """(kind, cue confidence) by priority order; (None, 0) when no operational cue fires."""
    for kind, pat, conf in KIND_CUES:
        if pat.search(sentence):
            return kind, conf
    return None, 0.0


def is_question(sentence: str) -> bool:
    s = sentence.strip()
    return s.endswith("?") or bool(re.match(r"^(does|do|is|are|can|could|who|what|when|where|why|how|anyone|any)\b", s, re.I)) and len(s) < 160 and "?" in s


def is_noise(sentence: str) -> bool:
    toks = raw_tokens(sentence)
    return len(toks) < 4 or bool(COURTESY.match(sentence.strip()))


_NOT_SUBJECTS = frozenset(
    "i ok fyi pr eod asap monday tuesday wednesday thursday friday saturday sunday january february march april may "
    "june july august september october november december update heads reminder note also root".split()
)


def detect_subject(sentence: str, linker: AreaLinker, person_names: frozenset[str]) -> str | None:
    """The system/entity a sentence is about: a known system (+ head noun), a 'the X job' phrase, or a
    capitalised product name. Deliberately shallow: good enough to bucket facts for supersession."""
    low = sentence.lower()
    for name, _aid in linker.systems:
        i = low.find(name.lower())
        if i >= 0:
            start = end = i + len(name)
            # extend "CoreLink" -> "CoreLink API key": up to 3 modifier words ending in a head noun
            m = re.match(r"((?:[\s-]+[\w-]+){1,3})", sentence[end:])
            if m:
                pos = end
                for w in re.finditer(r"[\s-]+([\w-]+)", m.group(1)):
                    word = w.group(1).lower()
                    if word not in HEAD_NOUNS and word not in MODIFIERS:
                        break
                    if word in HEAD_NOUNS:
                        end = pos + w.end()
                        break
            return sentence[i:end] if end > start else sentence[i:start]
    m = SUBJECT_RE.search(sentence)
    if m:
        words = [w for w in m.group(1).split() if w.lower() not in {"the", "our", "a", "an"}]
        return " ".join(words)
    for m in CAPSEQ.finditer(sentence):
        cand = m.group(1)
        if cand.split()[0].lower() in person_names or cand.split()[0].lower() in _NOT_SUBJECTS:
            continue
        if len(cand) > 2:
            return cand
    return None


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def fact_id_for(doc_id: str, idx: int, text: str) -> str:
    return "F" + hashlib.sha1(f"{doc_id}|{idx}|{text}".encode()).hexdigest()[:11]


# ------------------------------------------------------------------------------------------------ extractors


@dataclass
class ExtractionContext:
    people: Sequence[Person]
    areas: Sequence[Area]
    linker: AreaLinker = field(init=False)
    person_names: frozenset[str] = field(init=False)
    name_to_id: dict[str, str] = field(init=False)  # "sarah chen" / "sarah" / id -> person id
    names: dict[str, str] = field(init=False)  # person id -> display name

    def __post_init__(self) -> None:
        self.linker = AreaLinker(self.areas)
        names: set[str] = set()
        self.name_to_id, self.names = {}, {}
        for p in self.people:
            names.update(t.lower() for t in p.name.split())
            names.add(p.id.lower())
            self.names[p.id] = p.name
            self.name_to_id.setdefault(p.name.lower(), p.id)
            self.name_to_id.setdefault(p.name.split()[0].lower(), p.id)
            self.name_to_id.setdefault(p.id.lower(), p.id)
        self.person_names = frozenset(names)


class Extractor(Protocol):
    name: str

    def extract_thread(self, docs: Sequence[SourceDoc], ctx: ExtractionContext) -> list[Fact]: ...


def _base_fact(
    doc: SourceDoc, idx: int, text: str, quote: str, kind: FactKind, area_id: str | None, subject: str | None,
    conf: float, extractor: str, *, author_id: str | None = None, ts: datetime | None = None,
) -> Fact:
    ts = ts or doc.timestamp
    return Fact(
        id=fact_id_for(doc.id, idx, quote),
        text=text,
        kind=kind,
        area_id=area_id,
        stated_by=author_id or doc.author_id,
        source_doc_ids=[doc.id],
        quote=quote,
        valid_from=ts.date(),
        learned_at=ts,
        visibility=doc.visibility,
        confidence=round(min(0.95, max(0.05, conf)), 3),
        subject=subject,
        extractor=extractor,
    )


# Common export formats: ticket comments "- Name (2026-03-02 15:39): text", header/metadata lines, wiki owners.
COMMENT_LINE = re.compile(
    r"^\s*[-*•]?\s*([A-Z][\w'.-]+(?:\s[A-Z][\w'.-]+){0,2})\s*\((\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?\)\s*:\s*(.+)$"
)
META_LINE = re.compile(
    r"^\s*(#+\s|(reporter|assignee|priority|status|raised from|comments|last updated|from|to|cc|bcc|subject|date|"
    r"labels?|component|created|updated)\s*:|\[[A-Z][A-Z0-9]+-\d+\]\s|(raised|moved|escalated) from #)",
    re.I,
)
META_KV = re.compile(r"\b\w+:\s[^|]{1,60}\|\s*\w+:")
OWNER_LINE = re.compile(
    r"^\s*(?:owner|owned by|maintainer|point of contact)\s*:\s*([A-Z][\w'.-]+(?:\s[A-Z][\w'.-]+){0,2})", re.I
)
DISCOURSE_PREFIX = re.compile(
    r"^(?:(?:heads[- ]up|fyi|reminder|note|quick note|side note|short version|pro tip|psa|tl;?dr|ps|important|"
    r"warning|for the record|just so you know|context|btw|update|also)\b[^:\d]{0,40}:(?=\s)|(?:fyi|btw|also|so)\b,?)\s*",
    re.I,
)


@dataclass
class Segment:
    """A span of a doc with its own speaker and time (a ticket comment, or the doc body)."""

    text: str
    author_id: str
    ts: datetime


def segments(doc: SourceDoc, name_to_id: dict[str, str]) -> tuple[list[Segment], list[tuple[str, str]]]:
    """Split a doc into attributed segments; also return (owner person id, verbatim line) header claims."""
    segs: list[Segment] = []
    owners: list[tuple[str, str]] = []
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            segs.append(Segment(body, doc.author_id, doc.timestamp))
        buf.clear()

    for line in doc.text.splitlines():
        m = COMMENT_LINE.match(line)
        if m:
            flush()
            pid = name_to_id.get(m.group(1).lower()) or name_to_id.get(m.group(1).split()[0].lower())
            try:
                ts = datetime.fromisoformat(f"{m.group(2)} {m.group(3) or '00:00'}")
            except ValueError:
                ts = doc.timestamp
            segs.append(Segment(m.group(4), pid or doc.author_id, max(ts, doc.timestamp)))
            continue
        om = OWNER_LINE.match(line)
        if om:
            pid = name_to_id.get(om.group(1).lower()) or name_to_id.get(om.group(1).split()[0].lower())
            if pid:
                owners.append((pid, normalize_ws(re.split(r"[·|]", line)[0])))
            continue
        if META_LINE.match(line) or META_KV.search(line) or (doc.title and line.strip() == doc.title.strip()):
            continue
        buf.append(line)
    flush()
    return segs, owners


def strip_discourse(sentence: str) -> str:
    """'Heads up all: never X' -> 'Never X' (the verbatim quote keeps the original)."""
    out = DISCOURSE_PREFIX.sub("", sentence, count=1).strip()
    return out[:1].upper() + out[1:] if len(raw_tokens(out)) >= 4 else sentence


class HeuristicExtractor:
    """Cue-phrase extractor. See module docstring for the why."""

    name = "heuristic"

    def extract_thread(self, docs: Sequence[SourceDoc], ctx: ExtractionContext) -> list[Fact]:
        facts: list[Fact] = []
        thread_area: str | None = None
        q_area: str | None = None  # context set by the most recent question in the thread
        q_subject: str | None = None
        for doc in docs:
            header = doc.title or ""
            doc_links = ctx.linker.link(f"{header}\n{doc.text}")
            doc_area = doc_links[0][0] if doc_links else None
            thread_area = thread_area or doc_area
            header_subject = detect_subject(header, ctx.linker, ctx.person_names) if header else None
            segs, owners = segments(doc, ctx.name_to_id)
            for j, (pid, line) in enumerate(owners):
                if doc_area:
                    what = header.lstrip("# ").strip() or area_name(ctx, doc_area)
                    facts.append(_base_fact(doc, 900 + j, f"{ctx.names.get(pid, pid)} owns {what}.", line,
                                            FactKind.OWNER, doc_area, header_subject, 0.7, self.name))
            idx = 0
            for seg in segs:
                for sent in split_sentences(seg.text):
                    idx += 1
                    f = self._sentence_fact(doc, seg, idx, normalize_ws(sent), ctx, doc_area, thread_area,
                                            header_subject, (q_area, q_subject))
                    if isinstance(f, tuple):  # a question: it becomes the context for the answers that follow
                        q_area, q_subject = f
                    elif f is not None:
                        facts.append(f)
        return facts

    def _sentence_fact(
        self, doc: SourceDoc, seg: Segment, idx: int, sent: str, ctx: ExtractionContext, doc_area: str | None,
        thread_area: str | None, header_subject: str | None, q_ctx: tuple[str | None, str | None],
    ) -> Fact | tuple[str | None, str | None] | None:
        q_area, q_subject = q_ctx
        s_links = ctx.linker.link(sent)
        s_area = s_links[0][0] if s_links else None
        subject = detect_subject(sent, ctx.linker, ctx.person_names)
        if is_question(sent):
            return (s_area or doc_area or q_area, subject or q_subject or header_subject)
        if is_noise(sent) or (PERSONAL.search(sent) and not s_area):
            return None
        kind, conf = classify_kind(sent)
        inherited = False
        area = s_area
        if area is None:
            area = q_area or doc_area or thread_area
            inherited = area is not None
        if subject is None:
            subject = q_subject or header_subject
        if kind is None:
            # plain "fact" only when clearly about a known area and concrete (numbers / named things)
            if s_area is None or not (re.search(r"\d", sent) or subject):
                return None
            kind, conf = FactKind.FACT, 0.4
        if area is None and kind in (FactKind.PROCEDURE, FactKind.OWNER):
            return None  # too generic without an area to anchor it
        conf += 0.08 if s_area else (0.0 if inherited else -0.1)
        conf += 0.04 if subject else 0.0
        conf += 0.04 if doc.source_type in (SourceType.TICKET, SourceType.DOC) else 0.0
        conf -= 0.2 if HEDGE.search(sent) else 0.0
        text = strip_discourse(sent)
        if subject and subject.lower() not in text.lower() and (PRONOUN_START.match(sent) or inherited):
            text = f"{subject}: {text}"  # resolve terse thread answers against the question's subject
        return _base_fact(doc, idx, text, sent, kind, area, subject, conf, self.name,
                          author_id=seg.author_id, ts=seg.ts)


def area_name(ctx: "ExtractionContext", area_id: str) -> str:
    return next((a.name for a in ctx.areas if a.id == area_id), area_id)


# ------------------------------------------------------------------------------------------------ LLM extractor

LLM_SYSTEM = (
    "You extract durable operational knowledge from a company's work messages. Return only facts a new "
    "employee would need: access/credentials locations, vendor contacts, recurring tasks, landmines (things "
    "that must never be done), procedures, decisions, owners, and other concrete facts about systems. "
    "Every fact must include `quote`: an exact, verbatim, contiguous substring copied from that doc's text. "
    "Ignore small talk and personal topics. Never invent facts."
)
LLM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "quote": {"type": "string"},
                    "text": {"type": "string"},
                    "kind": {"type": "string", "enum": [k.value for k in FactKind]},
                    "area_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["doc_id", "quote", "text", "kind", "area_id", "subject", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}


class LLMExtractor:
    """Thread-batched JSON extraction through ``keepline.llm``; falls back to heuristics per thread on failure."""

    def __init__(self, llm: Any, max_chars: int = 12000) -> None:
        self.llm = llm
        self.name = getattr(llm, "name", "claude")
        self.max_chars = max_chars
        self.fallback = HeuristicExtractor()

    def _prompt(self, docs: Sequence[SourceDoc], ctx: ExtractionContext) -> str:
        areas = "\n".join(f"- {a.id}: {a.name} ({', '.join(a.systems[:4])})" for a in ctx.areas)
        people = {p.id: p.name for p in ctx.people}
        body = "\n\n".join(
            f"[doc_id={d.id}] {d.timestamp:%Y-%m-%d} {people.get(d.author_id, d.author_id)} "
            f"({d.source_type}, {d.container}){' | ' + d.title if d.title else ''}:\n{d.text}"
            for d in docs
        )[: self.max_chars]
        return (
            f"Areas (use one of these ids for area_id, or \"none\"):\n{areas}\n\n"
            f"Thread (answers inherit the context of the question they reply to):\n{body}\n\n"
            "Extract the facts as JSON. `text` = a short self-contained restatement (resolve 'it'/'that' to the "
            "subject). `subject` = the system/entity (e.g. 'CoreLink API key'). confidence in [0,1]."
        )

    def extract_thread(self, docs: Sequence[SourceDoc], ctx: ExtractionContext) -> list[Fact]:
        try:
            out = self.llm.complete_json(self._prompt(docs, ctx), LLM_SCHEMA, system=LLM_SYSTEM)
        except Exception as exc:  # noqa: BLE001 -- any LLM failure degrades to the deterministic path
            log.warning("LLM extraction failed for thread %s (%s); using heuristics", docs[0].thread_id, exc)
            return self.fallback.extract_thread(docs, ctx)
        by_id = {d.id: d for d in docs}
        valid_areas = {a.id for a in ctx.areas}
        facts: list[Fact] = []
        for i, item in enumerate(out.get("facts", []) if isinstance(out, dict) else []):
            doc = by_id.get(item.get("doc_id", ""))
            quote = normalize_ws(item.get("quote", ""))
            if doc is None or not quote or quote not in normalize_ws(doc.text):
                continue  # no verbatim receipt -> not a fact
            try:
                kind = FactKind(item.get("kind", "fact"))
            except ValueError:
                kind = FactKind.FACT
            area = item.get("area_id") if item.get("area_id") in valid_areas else ctx.linker.best(quote)
            facts.append(
                _base_fact(doc, 1000 + i, normalize_ws(item.get("text") or quote), quote, kind, area,
                           item.get("subject") or None, float(item.get("confidence", 0.6)), self.name)
            )
        return facts


# ------------------------------------------------------------------------------------------------ threading


def thread_key(doc: SourceDoc) -> str:
    """Docs that form one conversation: explicit thread id, else the ticket/email container, else the doc."""
    if doc.thread_id:
        return f"{doc.source_type}:{doc.thread_id}"
    if doc.source_type in (SourceType.TICKET, SourceType.EMAIL):
        return f"{doc.source_type}:{doc.container}"
    return f"{doc.source_type}:{doc.id}"


def group_threads(docs: Sequence[SourceDoc]) -> list[list[SourceDoc]]:
    groups: dict[str, list[SourceDoc]] = {}
    for d in sorted(docs, key=lambda d: (d.timestamp, d.id)):
        groups.setdefault(thread_key(d), []).append(d)
    return sorted(groups.values(), key=lambda g: (g[0].timestamp, g[0].id))


def is_personal_doc(doc: SourceDoc, linker: AreaLinker) -> bool:
    """Social chatter with no link to any work area is dropped before extraction (privacy + noise)."""
    return bool(PERSONAL.search(doc.text)) and not linker.link(f"{doc.title or ''}\n{doc.text}")


def visible_doc(doc: SourceDoc, include_private: bool) -> bool:
    return include_private or doc.visibility != Visibility.PRIVATE


def dump_fact_debug(f: Fact) -> str:  # handy in notebooks / CLI debugging
    return json.dumps({"kind": str(f.kind), "area": f.area_id, "subject": f.subject, "text": f.text,
                       "conf": f.confidence, "from": str(f.valid_from)}, ensure_ascii=False)


def now_utc_naive() -> datetime:
    return datetime.now().replace(microsecond=0)

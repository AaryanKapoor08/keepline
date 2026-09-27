"""AnswerAgent: answer with receipts, or say "I don't know" and route to who does.

Pipeline (deterministic offline, <50 ms):
  classify area -> BM25 over facts+docs (as_of + permission filtered) -> resolve every candidate fact to its
  version current at ``as_of`` (never cite a dead fact as current; remember what it replaced) -> score support
  (idf-weighted query coverage, intent/kind match, area match) -> calibrated confidence -> decide
  ANSWER / ROUTE / ABSTAIN with the bandit-tunable ``PolicyParams`` thresholds.

Three answer layers (``Answer``): ``said`` = verbatim quotes with author/date/link; ``inferred`` = explicitly
labelled reasoning; ``no_evidence_note`` = what we could not find and who to ask instead.
"""

from __future__ import annotations

import math
import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Sequence

import json
from pathlib import Path

from keepline.config import DEMO_TODAY, RESULTS_DIR
from keepline.contracts import (
    Action,
    Answer,
    Citation,
    EdgeRel,
    Expertise,
    Fact,
    FactKind,
    Person,
    PolicyParams,
    Verification,
    Visibility,
)
from keepline.memory.extract import AreaLinker, classify_kind, is_noise, is_question, normalize_ws, segments
from keepline.memory.store import MemoryStore
from keepline.retrieval.search import Hit, SearchIndex
from keepline.retrieval.text import content_set, jaccard, split_sentences, stem, tokenize

# ------------------------------------------------------------------------------------------------ question intent

ROUTING_Q = re.compile(
    r"\b(who (owns|handles|handled|knows|is responsible|was responsible|runs|manages|maintains|looks after|takes care|"
    r"is the (go-?to|point|owner|contact)|do i (ask|talk to|contact)|should i (ask|talk to|contact)|can i ask|"
    r"to ask|is in charge|covers|has the most)|whom? (do|should) i (ask|contact|talk to)|"
    r"who's (the|in charge|responsible)|which person|ask about)\b",
    re.I,
)
INTENT_CUES: list[tuple[FactKind, re.Pattern[str]]] = [
    (FactKind.LANDMINE, re.compile(r"\b(never|avoid|careful|watch out|gotcha|landmine|should ?n[o']?t|safe|risk|"
                                   r"can i|could i|is it ok|okay to|allowed|anything i should|dangerous|break|"
                                   r"not run|don'?t|must not|when (should|shouldn'?t)|pitfall)\b", re.I)),
    (FactKind.ACCESS, re.compile(r"\b(password|credential|creds|login|log in|access|admin|vault|stored|where (are|is) "
                                 r"the|key|token|account)\b", re.I)),
    (FactKind.VENDOR_CONTACT, re.compile(r"\b(contact|rep|account manager|call|email|phone|support|vendor|reach)\b", re.I)),
    (FactKind.RECURRING_TASK, re.compile(r"\b(when|how often|every|schedule|renew|due|deadline|expire|cadence|"
                                         r"what day|which day|monthly|weekly|annual)\b", re.I)),
    (FactKind.PROCEDURE, re.compile(r"\b(how (do|should|can) (i|we)|how to|steps|process|procedure|what do i do|"
                                    r"fix|restart|rerun|re-run)\b", re.I)),
    (FactKind.DECISION, re.compile(r"\b(why|decided|decision|did we|chose|choose|policy|switch|moved? to|still use)\b", re.I)),
    (FactKind.OWNER, re.compile(r"\b(who|owner|owns|responsible)\b", re.I)),
]
QUESTION_FILLER = frozenset(
    stem(w)
    for w in """anything something thing things tell today tomorrow tonight ok okay safe fine allowed question help current
    currently still right exactly use used do know need happen happens anyone someone else really actually our we i us
    would should could can is are was were what which when where why how who whom""".split()
)
NUMBER_Q = re.compile(
    r"\b(how (many|much|long|often|late|early|soon)|what time|when|what day|which day|deadline|cutoff|cut-off|"
    r"limit|number|phone|version|id|how old|what date|window|retention|how fast|threshold|amount)\b", re.I)
WHO_Q = re.compile(r"\b(who|whom|whose|contact|rep|account manager)\b", re.I)
WHERE_Q = re.compile(r"\bwhere\b", re.I)
_NUMBERISH = re.compile(
    r"\d|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|sixty|ninety|"
    r"first|second|third|last|monday|tuesday|wednesday|thursday|friday|saturday|sunday|daily|weekly|monthly|"
    r"quarterly|annually|yearly|nightly|morning|noon|midnight|evening|week|month|year|day)s?\b", re.I)
_NAMEISH = re.compile(r"(?<!^)(?<![.!?] )\b[A-Z][a-z]+(?: [A-Z][a-z'-]+)+|@\w+|\S+@\S+\.\w+")
_PLACEISH = re.compile(r"\b(in|on|at|under|inside)\s+(the\s+)?[A-Z0-9#]|\b(vault|drive|folder|share|wiki|sheet|"
                       r"server|portal|binder|safe|cabinet|channel|repo|confluence|sharepoint|1password)\b", re.I)


_PHONE = re.compile(r"\+?\d[\d ().-]{6,}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def answer_type(question: str, is_routing: bool) -> str | None:
    """Expected shape of the answer: 'phone' | 'email' | 'number' | 'person' | 'place' | None."""
    if re.search(r"\b(phone|call|dial|extension|hotline)\b", question, re.I):
        return "phone"
    if re.search(r"\bemail (address)?\b|\be-mail\b", question, re.I):
        return "email"
    if NUMBER_Q.search(question):
        return "number"
    if WHERE_Q.search(question):
        return "place"
    if WHO_Q.search(question) and not is_routing:
        return "person"
    return None


def type_matches(atype: str | None, text: str) -> float:
    if atype is None:
        return 0.0
    pat = {"number": _NUMBERISH, "person": _NAMEISH, "place": _PLACEISH, "phone": _PHONE, "email": _EMAIL}[atype]
    return 1.0 if pat.search(text) else 0.0


NEG_TERM = "__neg__"
NEG_Q = re.compile(r"\b(not|never|n't|avoid|shouldn'?t|mustn'?t|don'?t|can'?t)\b|n't\b", re.I)
NEG_FACT = re.compile(r"\b(never|not|no|don'?t|doesn'?t|mustn'?t|shouldn'?t|can'?t|won'?t|skips?|skipped|except|"
                      r"avoid|without|off[- ]limits)\b", re.I)
# Small, general business-vocabulary synonym groups (stemmed). Not tuned to any corpus.
_SYN_GROUPS = [
    "rep representative account-manager contact am csm",
    "password credential creds login passphrase",
    "start begin kick kickoff",
    "cutoff deadline window due",
    "skip except exclude",
    "owner owns responsible handle lead",
    "phone number call",
    "stored lives kept store keep",
]
SYNONYMS: dict[str, frozenset[str]] = {}
for _g in _SYN_GROUPS:
    _ws = [stem(w.split("-")[-1]) if "-" in w else stem(w) for w in _g.split()]
    for _w in _ws:
        SYNONYMS[_w] = SYNONYMS.get(_w, frozenset()) | frozenset(x for x in _ws if x != _w)


def term_hit(t: str, fact_terms: frozenset[str], fact_text: str) -> float:
    """How well a fact covers one question term: exact 1.0; synonym 0.9; abbreviation/prefix ("recon" ~
    "reconciliation") 0.8; the negation pseudo-term matches negated/skip-style statements."""
    if t == NEG_TERM:
        return 1.0 if NEG_FACT.search(fact_text) else 0.0
    if t in fact_terms:
        return 1.0
    if SYNONYMS.get(t, frozenset()) & fact_terms:
        return 0.9
    if len(t) >= 4 and not t[:1].isdigit():
        for x in fact_terms:
            if len(x) >= 4 and (x.startswith(t) or t.startswith(x)):
                return 0.8
    return 0.0


SHAPE_WORDS = frozenset(stem(w) for w in "time date day number long often many much phone call email address".split())
TODAY_WORDS = re.compile(r"\b(today|now|right now|this (morning|afternoon|evening)|tonight)\b", re.I)
YESNO_Q = re.compile(r"^\s*(can|could|may|should|is it (ok|okay|safe|fine)|am i allowed|do i need)\b", re.I)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# ------------------------------------------------------------------------------------------------ calibration

# Logistic confidence model. Every coefficient is >= 0 on a "more support" feature (and <= 0 on contradiction),
# so confidence is monotone: more coverage / receipts / agreement can only raise it. Coefficients were set by
# hand on our own sanity questions; the bandit then learns the *thresholds* per area on train questions.
CAL = {
    "bias": -6.0,
    "coverage": 8.0,  # idf-weighted share of the question's content words found in the fact (+its subject/area)
    "kind_match": 0.8,  # fact kind matches the question's intent (landmine question -> landmine fact)
    "area_match": 0.5,  # fact is in the area the question is about
    "receipts": 0.5,  # x ln(1 + independent receipts)
    "fact_conf": 1.2,  # extraction confidence
    "margin": 1.0,  # support gap to the best *competing* fact
    "agreement": 0.3,  # other retrieved facts in the same area/kind agree (non-contradicted)
    "type_match": 0.8,  # the fact has the shape the question asks for (a number for "what time", a name for "who")
    "missing_key": -1.8,  # the question's most specific word (highest idf) is absent from the fact
    "contradicted": -1.5,  # the fact is marked contradicted by a conflicting statement
}


def calibrated_confidence(f: dict[str, float]) -> float:
    z = CAL["bias"] + sum(CAL[k] * f.get(k, 0.0) for k in CAL if k != "bias")
    return 1.0 / (1.0 + math.exp(-z))


# ------------------------------------------------------------------------------------------------ internals


@dataclass
class _Cand:
    fact: Fact
    retrieval: float
    coverage: float
    kind_match: float
    area_match: float
    missing_key: float = 0.0
    type_match: float = 0.0
    rel: float = 0.0  # retrieval score relative to the best hit for this question
    raw: bool = False  # a sentence straight from a retrieved doc (extraction missed it), not a stored fact
    replaced: list[Fact] = field(default_factory=list)

    @property
    def support(self) -> float:
        return (0.45 * self.coverage + 0.08 * self.kind_match + 0.07 * self.area_match
                + 0.08 * (1 - self.missing_key) + 0.12 * self.type_match + 0.2 * self.rel)


@dataclass
class _Analysis:
    question: str
    asker_id: str
    as_of: date
    area_id: str | None
    is_routing: bool
    intents: list[FactKind]
    cands: list[_Cand]
    doc_hits: list[Hit]
    experts: list[tuple[str, float, Expertise | None]]
    features: dict[str, float]
    confidence: float


def _fmt(d: date | datetime) -> str:
    return f"{d:%b} {d.day}, {d.year}"


class AnswerAgent:
    """See module docstring. Construct via ``load_default_agent()`` or with explicit store/index for tests."""

    CACHE_SIZE = 4096

    def __init__(self, store: MemoryStore, index: SearchIndex, llm: Any | None = None) -> None:
        self.store = store
        self.index = index
        self.llm = llm
        self.people: dict[str, Person] = {p.id: p for p in store.people()}
        self.areas = {a.id: a for a in store.areas()}
        self.linker = AreaLinker(list(self.areas.values()))
        self.facts: dict[str, Fact] = {f.id: f for f in store.all_facts() if str(f.review_status) != "rejected"}
        self.participants = store.fact_participants()
        self.doc_meta: dict[str, tuple[str, datetime, str]] = {
            r["id"]: (r["url"] or "", datetime.fromisoformat(r["ts"]), r["author_id"])
            for r in store.conn.execute("SELECT id, url, ts, author_id FROM documents")
        }
        self.expertise: dict[str, list[Expertise]] = defaultdict(list)
        for e in store.expertise():
            self.expertise[e.area_id].append(e)
        self.owners: dict[str, dict[str, float]] = defaultdict(dict)  # area -> person -> weight (OWNS edges)
        for e in store.edges(rel=EdgeRel.OWNS):
            self.owners[e.dst][e.src] = max(self.owners[e.dst].get(e.src, 0.0), e.weight)
        self.by_area_kind: dict[tuple[str | None, str], list[Fact]] = defaultdict(list)
        for f in self.facts.values():
            self.by_area_kind[(f.area_id, str(f.kind))].append(f)
        self.area_lex = {aid: content_set(" ".join([a.name, *a.keywords, *a.systems])) for aid, a in self.areas.items()}
        self.doc_facts: dict[str, list[Fact]] = defaultdict(list)  # doc -> facts it is a receipt for
        for f in self.facts.values():
            for d in f.source_doc_ids:
                self.doc_facts[d].append(f)
        self.thread_root: dict[str, str] = {}  # doc -> first doc of its thread (question context for replies)
        first: dict[str, str] = {}
        for r in store.conn.execute("SELECT id, thread_id FROM documents WHERE thread_id IS NOT NULL ORDER BY ts, id"):
            root = first.setdefault(r["thread_id"], r["id"])
            if root != r["id"]:
                self.thread_root[r["id"]] = root
        self.name_to_id: dict[str, str] = {}
        for p in self.people.values():
            self.name_to_id.setdefault(p.name.lower(), p.id)
            self.name_to_id.setdefault(p.name.split()[0].lower(), p.id)
        self._sentences: dict[tuple[str, bool], list[tuple[int, str, str, datetime]]] = {}
        self._ctx_cache: dict[str, frozenset[str]] = {}
        self.calibrator = load_calibrator()
        self.doc_titles = {r["id"]: r["title"] for r in store.conn.execute("SELECT id, title FROM documents")}
        self.thread_children: dict[str, list[str]] = defaultdict(list)
        for d, root in self.thread_root.items():
            self.thread_children[root].append(d)
        self._cache: OrderedDict[tuple[Any, ...], _Analysis] = OrderedDict()

    # ------------------------------------------------------------------ public API
    def classify_area(self, question: str) -> str | None:
        named = self.index.areas_named(question)
        if named:
            return named[0]
        linked = self.linker.best(question)
        if linked:
            return linked
        return self._vote_area(self.index.search(question, k=8), plurality=True)

    def context_features(self, question: str, asker_id: str, *, as_of: date | None = None) -> dict[str, float]:
        return dict(self._analyze(question, asker_id, as_of, PolicyParams()).features)

    def answer(
        self, question: str, asker_id: str, *, as_of: date | None = None, params: PolicyParams | None = None,
        log: bool = False,
    ) -> Answer:
        params = params or PolicyParams()
        an = self._analyze(question, asker_id, as_of, params)
        ans = self._decide(an, params)
        if self.llm is not None and ans.action == Action.ANSWER:
            ans = self._llm_rewrite(ans, an)
        if log:
            self.store.log_query(asker_id, question, ans)
        return ans

    # ------------------------------------------------------------------ analysis
    def _analyze(self, question: str, asker_id: str, as_of: date | None, params: PolicyParams) -> _Analysis:
        as_of = as_of or DEMO_TODAY
        key = (question, asker_id, as_of, params.k, params.prefer_current, tuple(sorted(params.source_weights.items())))
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        is_routing = bool(ROUTING_Q.search(question))
        intents = [k for k, pat in INTENT_CUES if pat.search(question)]
        hits = self.index.search(question, k=max(3 * params.k, 24), as_of=as_of, visible_to=asker_id,
                                 source_weights=params.source_weights)
        area_id = (self.index.areas_named(question) or [None])[0] or self.linker.best(question) \
            or self._vote_area(hits, plurality=True)
        atype = answer_type(question, is_routing)
        q_terms = self._query_terms(question, atype)
        cands = self._candidates(hits, q_terms, intents, area_id, as_of, asker_id, params, atype)
        doc_hits = [h for h in hits if h.fact_id is None][: params.k]
        experts = self._experts(area_id, asker_id, as_of)
        feats = self._features(cands, doc_hits, area_id, is_routing, experts, q_terms)
        feats["formula_confidence"] = calibrated_confidence(feats) if cands else 0.0
        conf = self._calibrate(feats) if cands else 0.0
        feats["confidence"] = conf
        an = _Analysis(question, asker_id, as_of, area_id, is_routing, intents, cands, doc_hits, experts, feats, conf)
        self._cache[key] = an
        if len(self._cache) > self.CACHE_SIZE:
            self._cache.popitem(last=False)
        return an

    def _calibrate(self, feats: dict[str, float]) -> float:
        """Learned calibrator (``data/results/calibrator.json``: {"bias": b, "weights": {feature: w}}) when present,
        else the documented hand-set formula. Missing features count as 0."""
        if self.calibrator is None:
            return feats["formula_confidence"]
        w = self.calibrator.get("weights", {})
        z = float(self.calibrator.get("bias", 0.0)) + sum(float(v) * feats.get(k, 0.0) for k, v in w.items())
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))

    def _query_terms(self, question: str, atype: str | None = None) -> dict[str, float]:
        """Content terms of the question with idf weights (filler like 'anything'/'today' removed; for
        "what time / how long / which number" questions the shape words are handled by the answer-type check)."""
        drop = QUESTION_FILLER | (SHAPE_WORDS if atype in ("number", "phone", "email") else frozenset())
        terms = {t for t in tokenize(question) if t not in drop}
        if NEG_Q.search(question):
            terms.add(NEG_TERM)  # "when should X *not* run" is answered by "X skips / never / except ..."
        top = max(self.index.idf.values(), default=1.0)
        return {t: (self.index.idf.get(t, top) if t != NEG_TERM else 0.6 * top) for t in terms}

    def _vote_area(self, hits: Sequence[Hit], plurality: bool = False) -> str | None:
        votes: dict[str, float] = defaultdict(float)
        for h in hits[:8]:
            if h.area_id:
                votes[h.area_id] += h.score
        if not votes:
            return None
        best = max(sorted(votes), key=lambda a: votes[a])
        return best if plurality or votes[best] >= 0.5 * sum(votes.values()) else None

    def _visible(self, f: Fact, asker_id: str) -> bool:
        return str(f.visibility) == Visibility.PUBLIC or asker_id in self.participants.get(f.id, ())

    def _current_version(self, f: Fact, as_of: date) -> tuple[Fact, list[Fact]]:
        """Follow superseded_by while the newer version was already true (and known) at ``as_of``."""
        replaced: list[Fact] = []
        seen = {f.id}
        while f.superseded_by and f.superseded_by not in seen:
            nxt = self.facts.get(f.superseded_by)
            if nxt is None or nxt.valid_from > as_of:
                break
            replaced.append(f)
            seen.add(nxt.id)
            f = nxt
        # also note what this version itself replaced (for "replaced X on <date>")
        prev = self.facts.get(f.supersedes) if f.supersedes else None
        if prev is not None and prev not in replaced:
            replaced.append(prev)
        return f, replaced

    def _fact_terms(self, f: Fact) -> frozenset[str]:
        extra = " ".join(filter(None, [f.subject, self.areas[f.area_id].name if f.area_id in self.areas else None]))
        return content_set(f"{f.text} {extra}")

    def _context_terms(self, doc_id: str) -> frozenset[str]:
        """Words of the thread's opening question and the doc title: the context a terse reply answers."""
        if doc_id not in self._ctx_cache:
            parts = [self.doc_titles.get(doc_id) or ""]
            root = self.thread_root.get(doc_id)
            if root:
                parts.append(" ".join(s for _, s, _, _ in self._doc_sentences(root, keep_questions=True)[:2]))
            self._ctx_cache[doc_id] = content_set(" ".join(parts))
        return self._ctx_cache[doc_id]

    def _coverage(self, q_terms: dict[str, float], f: Fact) -> tuple[float, float]:
        """(idf-weighted coverage of the question by the fact, 1.0 if the most specific question word is missing).

        Words only in the fact's area lexicon count half: "payroll" in the question is satisfied by a payroll fact
        that never says the word, but that alone must not make a fact look like an answer.
        """
        if not q_terms:
            return 0.0, 0.0
        ft = self._fact_terms(f)
        area_terms = self.area_lex.get(f.area_id or "", frozenset())
        if f.source_doc_ids:
            area_terms = area_terms | self._context_terms(f.source_doc_ids[0])
        hit = {t: term_hit(t, ft, f.text) or (0.5 if t in area_terms else 0.0) for t in q_terms}
        got = sum(w * hit[t] for t, w in q_terms.items())
        key = max(sorted(q_terms), key=lambda t: q_terms[t])
        missing = 0.0 if hit[key] >= 0.5 else 1.0
        return got / sum(q_terms.values()), missing

    def _candidates(
        self, hits: Sequence[Hit], q_terms: dict[str, float], intents: list[FactKind], area_id: str | None,
        as_of: date, asker_id: str, params: PolicyParams, atype: str | None = None,
    ) -> list[_Cand]:
        raw: dict[str, float] = {}
        for h in hits:
            if h.fact_id and h.fact_id in self.facts:
                raw[h.fact_id] = max(raw.get(h.fact_id, 0.0), h.score)
        # intent-driven recall: "anything I should never do with CoreLink?" -> all landmines in that area
        if area_id:
            for k in intents[:2]:
                for f in self.by_area_kind.get((area_id, str(k)), []):
                    raw.setdefault(f.id, 0.0)
        out: dict[str, _Cand] = {}
        for fid, score in raw.items():
            f0 = self.facts[fid]
            if f0.valid_from > as_of or (f0.learned_at and f0.learned_at.date() > as_of):
                continue
            f, replaced = self._current_version(f0, as_of) if params.prefer_current else (f0, [])
            if not self._visible(f, asker_id) or (f.valid_to is not None and f.valid_to <= as_of and params.prefer_current):
                continue
            c = out.get(f.id)
            if c is None:
                cov, missing = self._coverage(q_terms, f)
                c = _Cand(
                    fact=f,
                    retrieval=score,
                    coverage=cov,
                    missing_key=missing,
                    kind_match=1.0 if f.kind in intents[:3] else 0.0,
                    area_match=1.0 if area_id and f.area_id == area_id else 0.0,
                    type_match=type_matches(atype, f.text),
                    replaced=replaced,
                )
                out[f.id] = c
            else:
                c.retrieval = max(c.retrieval, score)
                c.replaced = c.replaced or replaced
        for c in self._raw_candidates(hits, q_terms, intents, area_id, as_of, params, atype, set(out)):
            out[c.fact.id] = c
        top = max((c.retrieval for c in out.values()), default=0.0)
        for c in out.values():
            c.rel = c.retrieval / top if top > 0 else 0.0
        return sorted(out.values(), key=lambda c: (-c.support, -c.fact.valid_from.toordinal(), c.fact.id))

    def _doc_sentences(self, doc_id: str, keep_questions: bool = False) -> list[tuple[int, str, str, datetime]]:
        """(idx, sentence, speaker, time) for a doc -- ticket comments keep their own author and date."""
        key = (doc_id, keep_questions)
        if key not in self._sentences:
            doc = self.store.doc(doc_id)
            out: list[tuple[int, str, str, datetime]] = []
            if doc is not None:
                segs, _owners = segments(doc, self.name_to_id)
                i = 0
                for seg in segs:
                    for sent in split_sentences(seg.text):
                        i += 1
                        sent = normalize_ws(sent)
                        if keep_questions or (not is_question(sent) and not is_noise(sent)):
                            out.append((i, sent, seg.author_id, seg.ts))
            self._sentences[key] = out
        return self._sentences[key]

    def _raw_candidates(
        self, hits: Sequence[Hit], q_terms: dict[str, float], intents: list[FactKind], area_id: str | None,
        as_of: date, params: PolicyParams, atype: str | None, have: set[str],
    ) -> list[_Cand]:
        """Recall safety net: the best sentence of each top retrieved doc, when extraction produced no fact for it.

        If the sentence is (a restatement of) a stored fact, that fact -- resolved to its current version -- is used
        instead, so a stale message can never sneak back in as "current" through this path.
        """
        out: list[_Cand] = []
        seen_docs: set[str] = set()
        doc_hits = [h for h in hits if h.fact_id is None]
        for h in doc_hits[: params.k]:
            if h.doc_id in seen_docs:
                continue
            seen_docs.add(h.doc_id)
            best: tuple[float, float, int, str, str, datetime] | None = None
            best_doc = h.doc_id
            # a retrieved question's answer lives in the replies below it
            for doc_id in [h.doc_id, *self.thread_children.get(h.doc_id, [])[:6]]:
                meta = self.doc_meta.get(doc_id)
                if meta is None or meta[1].date() > as_of:
                    continue
                for i, sent, who, ts in self._doc_sentences(doc_id):
                    if ts.date() > as_of:
                        continue
                    probe = Fact(id="", text=sent, kind=FactKind.FACT, area_id=h.area_id, stated_by=who,
                                 source_doc_ids=[doc_id], quote=sent, valid_from=ts.date())
                    cov, _m = self._coverage(q_terms, probe)
                    key = (cov + 0.15 * type_matches(atype, sent), cov)
                    if best is None or key > best[:2]:
                        best, best_doc = (key[0], cov, i, sent, who, ts), doc_id
            if best is None or best[1] < 0.15:
                continue
            _, cov, i, sent, who, ts = best
            sset = content_set(sent)
            stored = [f for f in self.doc_facts.get(best_doc, []) if jaccard(content_set(f.quote), sset) >= 0.5]
            if stored:
                continue  # already represented by a stored (and currency-resolved) fact
            kind, conf = classify_kind(sent)
            fact = Fact(id=f"raw:{best_doc}:{i}", text=sent, kind=kind or FactKind.FACT, area_id=h.area_id,
                        stated_by=who, source_doc_ids=[best_doc], quote=sent, valid_from=ts.date(), learned_at=ts,
                        confidence=round(0.45 + 0.2 * conf, 3), subject=None, extractor="raw")
            if fact.id in have:
                continue
            cov, missing = self._coverage(q_terms, fact)
            out.append(_Cand(fact=fact, retrieval=h.score, coverage=cov, missing_key=missing,
                             kind_match=1.0 if fact.kind in intents[:3] else 0.0,
                             area_match=1.0 if area_id and fact.area_id == area_id else 0.0,
                             type_match=type_matches(atype, sent), raw=True))
        return out

    def _independent_receipts(self, f: Fact) -> int:
        authors = {self.doc_meta[d][2] for d in f.source_doc_ids if d in self.doc_meta}
        return max(1, len(authors))

    def _features(
        self, cands: list[_Cand], doc_hits: list[Hit], area_id: str | None, is_routing: bool,
        experts: list[tuple[str, float, Expertise | None]], q_terms: dict[str, float],
    ) -> dict[str, float]:
        top = cands[0] if cands else None
        rival = next((c for c in cands[1:] if top and not self._same_story(top, c)), None)
        agree = 0.0
        if top:
            agree = float(sum(1 for c in cands[1:4] if c.fact.area_id == top.fact.area_id and c.fact.kind == top.fact.kind
                              and c.fact.verification != Verification.CONTRADICTED and c.support >= 0.5 * top.support))
        return {
            "bias": 1.0,
            "coverage": top.coverage if top else 0.0,
            "kind_match": top.kind_match if top else 0.0,
            "area_match": top.area_match if top else 0.0,
            "receipts": math.log1p(self._independent_receipts(top.fact)) if top else 0.0,
            "fact_conf": top.fact.confidence if top else 0.0,
            "margin": max(0.0, top.support - (rival.support if rival else 0.0)) if top else 0.0,
            "agreement": min(1.0, agree / 2),
            "missing_key": top.missing_key if top else 1.0,
            "type_match": top.type_match if top else 0.0,
            "top_is_raw": 1.0 if top and top.raw else 0.0,
            "contradicted": 1.0 if top and top.fact.verification == Verification.CONTRADICTED else 0.0,
            "top_support": top.support if top else 0.0,
            "top_retrieval": math.log1p(top.retrieval) if top else 0.0,
            "n_candidates": float(len(cands)),
            "n_doc_hits": float(len(doc_hits)),
            "top_doc_score": math.log1p(doc_hits[0].score) if doc_hits else 0.0,
            "top_fact_score": math.log1p(max((c.retrieval for c in cands if not c.raw), default=0.0)),
            "top_rel": top.rel if top else 0.0,
            "doc_fact_agree": self._doc_fact_agree(top, cands),
            "n_raw_candidates": float(sum(c.raw for c in cands)),
            "area_known": 1.0 if area_id else 0.0,
            "is_routing": 1.0 if is_routing else 0.0,
            "has_expert": 1.0 if experts else 0.0,
            "expert_score": experts[0][1] if experts else 0.0,
            "has_superseded": 1.0 if top and top.replaced else 0.0,
            "n_query_terms": float(len(q_terms)),
        }

    @staticmethod
    def _doc_fact_agree(top: _Cand | None, cands: list[_Cand]) -> float:
        """1.0 when the best raw doc sentence and the best stored fact say the same thing (or are the same
        candidate), 0.0 when they disagree, 0.5 when only one kind of evidence exists."""
        best_raw = next((c for c in cands if c.raw), None)
        best_fact = next((c for c in cands if not c.raw), None)
        if top is None or best_raw is None or best_fact is None:
            return 0.5
        a, b = content_set(best_raw.fact.text), content_set(best_fact.fact.text)
        return 1.0 if jaccard(a, b) >= 0.3 else 0.0

    @staticmethod
    def _same_story(a: _Cand, b: _Cand) -> bool:
        return a.fact.area_id == b.fact.area_id and a.fact.kind == b.fact.kind and (
            (a.fact.subject or "").lower() == (b.fact.subject or "").lower()
        )

    # ------------------------------------------------------------------ experts / routing
    def _experts(self, area_id: str | None, asker_id: str, as_of: date) -> list[tuple[str, float, Expertise | None]]:
        """(person, score, expertise) strongest first; owner statements add weight; the asker is excluded."""
        if not area_id:
            return []
        scores: dict[str, tuple[float, Expertise | None]] = {}
        for e in self.expertise.get(area_id, []):
            if e.last_active is not None and e.last_active > as_of:
                pass  # evidence after as_of still counts as "who works on it"; keep it simple
            scores[e.person_id] = (e.score, e)
        for pid, w in self.owners.get(area_id, {}).items():
            s, e = scores.get(pid, (0.0, None))
            scores[pid] = (min(1.0, s + 0.3 * w), e)
        ranked = sorted(((p, s, e) for p, (s, e) in scores.items() if p != asker_id and p in self.people),
                        key=lambda x: (-x[1], x[0]))
        return [r for r in ranked if r[1] >= 0.1][:4]

    def _status(self, pid: str, as_of: date) -> str:
        p = self.people.get(pid)
        if p is None or p.departure_date is None:
            return ""
        if p.departure_date <= as_of:
            return f"left on {_fmt(p.departure_date)}"
        return f"is leaving on {_fmt(p.departure_date)}"

    def _route_targets(self, an: _Analysis) -> tuple[list[str], list[str]]:
        """(route_to ids, human notes). People who already left are mentioned but never routed to."""
        route, notes = [], []
        for pid, _s, e in an.experts:
            st = self._status(pid, an.as_of)
            name = self.people[pid].name
            if st.startswith("left"):
                when = f" (last active {_fmt(e.last_active)})" if e and e.last_active else ""
                notes.append(f"{name} worked on this{when} but {st}.")
                continue
            route.append(pid)
            if len(route) >= 2:
                break
        return route, notes

    def _evidence_blurb(self, pid: str, e: Expertise | None) -> str:
        if e is None:
            return f"{self.people[pid].name} (named as owner)"
        bits = []
        if e.n_tickets_closed:
            bits.append(f"{e.n_tickets_closed} closed ticket{'s' * (e.n_tickets_closed != 1)}")
        if e.n_facts_stated:
            bits.append(f"{e.n_facts_stated} fact{'s' * (e.n_facts_stated != 1)} stated")
        if e.n_docs:
            bits.append(f"{e.n_docs} message{'s' * (e.n_docs != 1)}")
        last = f", last active {_fmt(e.last_active)}" if e.last_active else ""
        return f"{self.people[pid].name} ({', '.join(bits) or 'little evidence'}{last})"

    # ------------------------------------------------------------------ decision + composition
    def _decide(self, an: _Analysis, params: PolicyParams) -> Answer:
        area_name = self.areas[an.area_id].name if an.area_id in self.areas else None
        base = dict(question=an.question, area_id=an.area_id,
                    policy={"key": params.key(), "k": params.k, "abstain_threshold": params.abstain_threshold,
                            "route_threshold": params.route_threshold, "prefer_current": params.prefer_current},
                    debug={"features": an.features, "intents": [str(k) for k in an.intents]})
        route, notes = self._route_targets(an)

        if an.is_routing:
            return self._routing_answer(an, route, notes, area_name, base)

        if an.cands and an.confidence >= params.abstain_threshold:
            return self._compose_answer(an, base)

        weak = an.cands[0] if an.cands else None
        if route and (an.confidence >= params.route_threshold or an.area_id):
            who = self.people[route[0]]
            e = next((x[2] for x in an.experts if x[0] == route[0]), None)
            when = f" in {e.last_active:%b %Y}" if e and e.last_active else ""
            st = self._status(route[0], an.as_of)
            text = (f"I don't know -- I found no reliable evidence answering this. {who.name} worked on "
                    f"{area_name or 'this'}{when} -- ask {who.name.split()[0]}."
                    + (f" ({who.name.split()[0]} {st}.)" if st else "") + (" " + " ".join(notes) if notes else ""))
            inferred = [f"Inferred: routed to {self._evidence_blurb(route[0], e)} based on work history in "
                        f"{area_name or 'this area'}."]
            if weak:
                inferred.append(f"Inferred: closest (insufficient) evidence was: \"{weak.fact.quote[:140]}\".")
            return Answer(action=Action.ROUTE, text=text, inferred=inferred, no_evidence_note=text, route_to=route,
                          confidence=round(an.confidence, 4), **base)

        text = "I don't know -- I couldn't find anything about this in the company's messages, email or tickets."
        if notes:
            text += " " + " ".join(notes)
        return Answer(action=Action.ABSTAIN, text=text, no_evidence_note=text, confidence=round(an.confidence, 4),
                      **base)

    def _routing_answer(self, an: _Analysis, route: list[str], notes: list[str], area_name: str | None,
                        base: dict[str, Any]) -> Answer:
        if not route:
            text = ("I don't know who handles this -- I found no one with work history in "
                    f"{area_name or 'this area'}." + (" " + " ".join(notes) if notes else ""))
            return Answer(action=Action.ABSTAIN, text=text, no_evidence_note=text, confidence=0.0, **base)
        exp = {p: e for p, _s, e in an.experts}
        lead = self.people[route[0]]
        st = self._status(route[0], an.as_of)
        text = f"Ask {self._evidence_blurb(route[0], exp.get(route[0]))} -- strongest evidence in {area_name}."
        if st:
            text += f" Note: {lead.name.split()[0]} {st}."
            if len(route) > 1:
                text += f" Backup: {self._evidence_blurb(route[1], exp.get(route[1]))}."
        elif len(route) > 1:
            text += f" Also knows it: {self._evidence_blurb(route[1], exp.get(route[1]))}."
        if notes:
            text += " " + " ".join(notes)
        said = [self._cite(c.fact) for c in an.cands[:3] if c.fact.kind == FactKind.OWNER and c.coverage > 0.3]
        conf = max(an.experts[0][1], 0.3) if (an.experts and exp.get(route[0]) and exp[route[0]].enough_data) else 0.3
        inferred = [f"Inferred: ranked by work evidence in {area_name} (closed tickets weigh most, then facts stated, "
                    "then messages)."]
        return Answer(action=Action.ROUTE, text=text, said=said, inferred=inferred, route_to=route,
                      confidence=round(min(0.95, conf), 4), fact_ids=[c.fact_id for c in said if c.fact_id], **base)

    def _answer_group(self, an: _Analysis) -> list[_Cand]:
        top = an.cands[0]
        group = [top]
        for c in an.cands[1:6]:
            if len(group) >= 3:
                break
            if (c.fact.area_id == top.fact.area_id and c.support >= 0.8 * top.support
                    and (c.fact.kind == top.fact.kind or c.coverage >= top.coverage)):
                group.append(c)
        return group

    def _cite(self, f: Fact, is_current: bool = True) -> Citation:
        doc_id = f.source_doc_ids[0] if f.source_doc_ids else ""
        url, ts, author = self.doc_meta.get(doc_id, ("", datetime.combine(f.valid_from, datetime.min.time()), f.stated_by or ""))
        stored = f.id in self.facts
        return Citation(doc_id=doc_id, quote=f.quote, author_id=f.stated_by or author,
                        timestamp=(f.learned_at or ts) if not stored else ts, url=url,
                        fact_id=f.id if stored else None, is_current=is_current)

    def _compose_answer(self, an: _Analysis, base: dict[str, Any]) -> Answer:
        group = self._answer_group(an)
        said: list[Citation] = []
        parts: list[str] = []
        inferred: list[str] = []
        for c in group:
            f = c.fact
            who = self.people[f.stated_by].name if f.stated_by in self.people else "a colleague"
            parts.append(f"Per {who} ({_fmt(f.valid_from)}): {f.text.rstrip('.')}.")
            said.append(self._cite(f))
            for old in c.replaced[:1]:
                parts.append(f"(Current as of {_fmt(f.valid_from)} -- this replaced an earlier version from "
                             f"{_fmt(old.valid_from)}.)")
                said.append(self._cite(old, is_current=False))
            if f.verification == Verification.CONTRADICTED:
                inferred.append("Inferred: another colleague stated something conflicting about this; treat with care.")
            extra = self._independent_receipts(f)
            if extra > 1:
                inferred.append(f"Inferred: {extra} different people said this independently.")
        prefix = self._today_reasoning(an, group, inferred)
        text = (prefix + " " if prefix else "") + " ".join(parts)
        for pid in (f.stated_by for f in (c.fact for c in group)):
            st = self._status(pid, an.as_of) if pid else ""
            if st:
                inferred.append(f"Inferred: {self.people[pid].name} {st}; confirm with the current owner if critical.")
                break
        return Answer(action=Action.ANSWER, text=text, said=said, inferred=inferred,
                      confidence=round(an.confidence, 4), fact_ids=[c.fact.id for c in group if c.fact.id in self.facts], **base)

    def _today_reasoning(self, an: _Analysis, group: list[_Cand], inferred: list[str]) -> str:
        """'Can I rotate the key today?' + a weekday rule -> reason explicitly about as_of's weekday."""
        if not (TODAY_WORDS.search(an.question) or YESNO_Q.search(an.question)):
            return ""
        today = WEEKDAYS[an.as_of.weekday()]
        for c in group:
            low = c.fact.text.lower()
            days = [d for d in WEEKDAYS if re.search(rf"\b{d}s?\b", low)]
            if days and c.fact.kind == FactKind.LANDMINE:
                if today in days:
                    inferred.append(f"Inferred: {an.question.strip()!r} is asked on {_fmt(an.as_of)}, a "
                                    f"{today.title()} -- the rule below applies today.")
                    return f"No -- today ({_fmt(an.as_of)}) is a {today.title()}."
                inferred.append(f"Inferred: {_fmt(an.as_of)} is a {today.title()}, so this {days[0].title()} rule "
                                "does not block it today.")
                return f"Today ({_fmt(an.as_of)}) is a {today.title()}, so the rule below does not block it -- but note:"
            if c.fact.kind == FactKind.LANDMINE and YESNO_Q.search(an.question):
                return "Careful --"
        return ""

    # ------------------------------------------------------------------ optional LLM wording
    def _llm_rewrite(self, ans: Answer, an: _Analysis) -> Answer:
        """LLM writes the final wording strictly from the cited snippets; it may downgrade to abstain."""
        snippets = "\n".join(
            f"[{i + 1}] {self.people[c.author_id].name if c.author_id in self.people else c.author_id} "
            f"({_fmt(c.timestamp)}{'' if c.is_current else ', SUPERSEDED'}): \"{c.quote}\""
            for i, c in enumerate(ans.said)
        )
        schema = {"type": "object", "properties": {"answer": {"type": "string"}, "abstain": {"type": "boolean"}},
                  "required": ["answer", "abstain"], "additionalProperties": False}
        prompt = (f"Question (asked {_fmt(an.as_of)}, a {WEEKDAYS[an.as_of.weekday()].title()}): {an.question}\n\n"
                  f"Snippets:\n{snippets}\n\nAnswer in 1-3 sentences using ONLY the snippets; name who said it and "
                  "when; never present a SUPERSEDED snippet as current. If the snippets do not answer the question, "
                  "set abstain=true.")
        try:
            out = self.llm.complete_json(prompt, schema, system="You answer strictly from cited evidence.")
        except Exception:  # noqa: BLE001 -- keep the deterministic answer
            return ans
        if out.get("abstain"):
            ans.action = Action.ROUTE if an.experts else Action.ABSTAIN
            ans.route_to = [p for p, _s, _e in an.experts[:1]]
            ans.no_evidence_note = "The cited snippets do not directly answer this."
            ans.text = "I don't know -- the closest evidence doesn't answer this directly."
            ans.confidence = round(ans.confidence * 0.5, 4)
        elif out.get("answer"):
            ans.text = str(out["answer"]).strip()
        return ans


def load_calibrator(path: Path | None = None) -> dict[str, Any] | None:
    p = path or (RESULTS_DIR / "calibrator.json")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("weights"), dict) else None
    except (OSError, ValueError):
        return None


FEATURE_NAMES = (
    "bias", "coverage", "kind_match", "area_match", "receipts", "fact_conf", "margin", "agreement", "missing_key",
    "type_match", "top_is_raw", "contradicted", "top_support", "top_retrieval", "n_candidates", "n_doc_hits",
    "top_doc_score", "top_fact_score", "top_rel", "doc_fact_agree", "n_raw_candidates", "area_known", "is_routing",
    "has_expert", "expert_score", "has_superseded", "n_query_terms", "formula_confidence", "confidence",
)
"""Stable names of ``context_features()`` / ``Answer.debug["features"]`` (inputs for a learned calibrator)."""


def load_default_agent(*, use_llm: bool | None = None) -> AnswerAgent:
    """Store + search index from ``data/memory``. The LLM (Claude/Cortex via ``keepline.llm``) is only attached
    when ``use_llm=True`` or env ``KEEPLINE_ANSWER_LLM=1``: the benchmark and bandit need a fast deterministic
    agent, the app opts into LLM wording."""
    import os

    from keepline.llm import get_llm

    if use_llm is None:
        use_llm = os.environ.get("KEEPLINE_ANSWER_LLM", "0") == "1"
    return AnswerAgent(MemoryStore(), SearchIndex().load(), llm=get_llm() if use_llm else None)

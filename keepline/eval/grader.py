"""Deterministic grader: compares an ``Answer`` to the *truth file*, never to what Keepline extracted.

Why deterministic keyword grading (and not an LLM judge by default): the benchmark must be reproducible
byte-for-byte on a laptop with no network, and every verdict must be explainable to a judge ("it said 1st but
the rule changed to 1st and 15th on 2026-06-02"). An optional LLM judge (:func:`llm_judge`) exists only to
measure agreement with the keyword grader.

Matching rules
--------------
* Text searched = ``answer.text`` + quotes of the answer's citations (a quote the answer shows is part of
  what the asker reads). Superseded citations (``is_current=False``, rendered as "replaced by ...") count for
  gold matching but NOT for the stale check -- showing history is fine, asserting it as current is not.
* Normalisation: lowercase, punctuation -> space, thousands separators dropped, number words -> digits
  ("fifteenth" -> "15th", "two" -> "2"), crude plural folding (trailing "s" on tokens > 3 chars).
* Keywords are CNF: every inner list is an any-of group, all groups must match; each keyword is a phrase
  matched on token boundaries.
* Citation valid iff some cited doc_id is in the evidence map of some gold fact.

Outcome table (see ``keepline.rl.rewards`` for the reward attached to each)
---------------------------------------------------------------------------
expected ANSWER (fact / current / landmine):
    ANSWER, gold matched    -> correct_cited | correct_uncited
    ANSWER, forbidden matched and gold not matched -> stale_answer
    ANSWER, otherwise       -> hallucination
    ABSTAIN / ROUTE         -> unnecessary_abstain
expected ABSTAIN (unanswerable):
    ABSTAIN                 -> correct_abstain
    ROUTE to a gold person  -> correct_route;  ROUTE with no gold routes listed -> correct_abstain
    ROUTE to someone else   -> wrong_route
    ANSWER                  -> hallucination
expected ROUTE (routing):
    ROUTE to a gold person  -> correct_route;  ROUTE to someone else -> wrong_route
    ANSWER naming a gold person (route_to, name in text, or gold keywords) -> correct_cited | correct_route
    ANSWER otherwise        -> hallucination
    ABSTAIN                 -> unnecessary_abstain
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence

from keepline.contracts import Action, Answer, EvidenceMap, Question, TruthFact
from keepline.rl.rewards import CORRECT_OUTCOMES, Grade, Outcome, reward

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------------------
# Text normalisation
# --------------------------------------------------------------------------------------------------

_CARDINALS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90, "hundred": 100,
}  # fmt: skip
_ORDINALS = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th", "sixth": "6th",
    "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th", "eleventh": "11th",
    "twelfth": "12th", "thirteenth": "13th", "fourteenth": "14th", "fifteenth": "15th",
    "sixteenth": "16th", "twentieth": "20th", "thirtieth": "30th", "thirty-first": "31st",
    "twenty-first": "21st", "twenty-second": "22nd", "twenty-third": "23rd", "twenty-fifth": "25th",
}  # fmt: skip
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_HYPHEN_ORD = re.compile(r"\b(" + "|".join(k for k in _ORDINALS if "-" in k) + r")\b")
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _fold(token: str) -> str:
    if token in _ORDINALS:
        return _ORDINALS[token]
    if token in _CARDINALS:
        return str(_CARDINALS[token])
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss") and not token.isdigit():
        return token[:-1]
    return token


def normalize(text: str) -> str:
    """Canonical token string used on both sides of every keyword comparison."""
    t = text.lower()
    t = _THOUSANDS.sub("", t)
    t = _HYPHEN_ORD.sub(lambda m: _ORDINALS[m.group(1)], t)
    tokens = [_fold(tok) for tok in _NON_WORD.split(t) if tok]
    return " ".join(tokens)


def phrase_in(phrase: str, haystack_norm: str) -> bool:
    """Token-boundary phrase match on already-normalised haystack."""
    p = normalize(phrase)
    return bool(p) and f" {p} " in f" {haystack_norm} "


def cnf_match(groups: Sequence[Sequence[str]], haystack_norm: str) -> bool:
    """All any-of groups must match. An empty CNF matches nothing (callers decide what empty means)."""
    groups = [g for g in groups if g]
    return bool(groups) and all(any(phrase_in(kw, haystack_norm) for kw in g) for g in groups)


# --------------------------------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------------------------------


def _answer_haystacks(a: Answer) -> tuple[str, str]:
    """(everything the asker sees, only what is asserted as current)."""
    current = [a.text] + [c.quote for c in a.said if c.is_current]
    history = [c.quote for c in a.said if not c.is_current]
    return normalize(" ".join(current + history)), normalize(" ".join(current))


def citation_valid(q: Question, a: Answer, ev: EvidenceMap) -> bool:
    gold_docs = {d for fid in q.gold_fact_ids for d in ev.get(fid, [])}
    return any(c.doc_id in gold_docs for c in a.said)


def _names_gold_person(q: Question, a: Answer, full_norm: str, people: Mapping[str, str] | None) -> bool:
    if set(a.route_to) & set(q.gold_route_person_ids):
        return True
    for pid in q.gold_route_person_ids:
        name = (people or {}).get(pid, "")
        candidates = [pid.replace("_", " ")] + ([name, name.split()[0]] if name else [])
        if any(phrase_in(c, full_norm) for c in candidates if c):
            return True
    return cnf_match(q.gold_answer_keywords, full_norm)


def _calibration_target(q: Question, a: Answer, correct: bool) -> float:
    if a.action == Action.ANSWER:
        return 1.0 if correct else 0.0
    return 1.0 if q.expected_action == Action.ANSWER else 0.0


def _outcome_expected_answer(q: Question, a: Answer, cite_ok: bool, notes: list[str]) -> Outcome:
    if a.action != Action.ANSWER:
        return Outcome.UNNECESSARY_ABSTAIN
    full, current = _answer_haystacks(a)
    gold_hit = cnf_match(q.gold_answer_keywords, full) if q.gold_answer_keywords else cite_ok
    if not q.gold_answer_keywords:
        notes.append("no gold keywords: correctness judged by citation only")
    stale_hit = cnf_match(q.forbidden_keywords, current)
    if stale_hit and not gold_hit:
        notes.append("asserted a superseded value")
        return Outcome.STALE_ANSWER
    if gold_hit:
        if stale_hit:
            notes.append("also mentions a superseded value")
        return Outcome.CORRECT_CITED if cite_ok else Outcome.CORRECT_UNCITED
    return Outcome.HALLUCINATION


def _outcome_expected_abstain(q: Question, a: Answer, notes: list[str]) -> Outcome:
    if a.action == Action.ABSTAIN:
        return Outcome.CORRECT_ABSTAIN
    if a.action == Action.ROUTE:
        if not q.gold_route_person_ids:
            notes.append("route accepted as abstain: no gold routes listed")
            return Outcome.CORRECT_ABSTAIN
        return Outcome.CORRECT_ROUTE if set(a.route_to) & set(q.gold_route_person_ids) else Outcome.WRONG_ROUTE
    return Outcome.HALLUCINATION


def _outcome_expected_route(
    q: Question, a: Answer, cite_ok: bool, people: Mapping[str, str] | None, notes: list[str]
) -> Outcome:
    if a.action == Action.ABSTAIN:
        return Outcome.UNNECESSARY_ABSTAIN
    if a.action == Action.ROUTE:
        return Outcome.CORRECT_ROUTE if set(a.route_to) & set(q.gold_route_person_ids) else Outcome.WRONG_ROUTE
    full, _ = _answer_haystacks(a)
    if _names_gold_person(q, a, full, people):
        notes.append("answered by naming the right person")
        return Outcome.CORRECT_CITED if cite_ok else Outcome.CORRECT_ROUTE
    return Outcome.HALLUCINATION


def grade(
    q: Question,
    a: Answer,
    truth: Mapping[str, TruthFact] | None = None,
    ev: EvidenceMap | None = None,
    *,
    people: Mapping[str, str] | None = None,
) -> Grade:
    """Grade one answer against the truth-derived gold fields of ``q``.

    ``truth`` is accepted for interface stability and sanity checks (gold facts must exist); the gold keywords
    are already copied onto the question by the data generator. ``people`` (id -> full name) lets an ANSWER
    that names the right person count on routing questions.
    """
    ev = ev or {}
    notes: list[str] = []
    missing = [f for f in q.gold_fact_ids if truth is not None and f not in truth]
    if missing:
        notes.append(f"gold facts missing from truth: {missing}")
    cite_ok = citation_valid(q, a, ev)
    if q.expected_action == Action.ABSTAIN:
        outcome = _outcome_expected_abstain(q, a, notes)
    elif q.expected_action == Action.ROUTE:
        outcome = _outcome_expected_route(q, a, cite_ok, people, notes)
    else:
        outcome = _outcome_expected_answer(q, a, cite_ok, notes)
    correct = outcome in CORRECT_OUTCOMES
    g = Grade(correct=correct, citation_valid=cite_ok, outcome=outcome, notes=notes)
    g.calibration_target = _calibration_target(q, a, correct)
    g.reward = reward(g, a.confidence)
    return g


# --------------------------------------------------------------------------------------------------
# Optional LLM judge (off by default; used only to measure agreement with the keyword grader)
# --------------------------------------------------------------------------------------------------

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"correct": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["correct", "reason"],
    "additionalProperties": False,
}


def llm_judge(q: Question, a: Answer, truth: Mapping[str, TruthFact]) -> bool | None:
    """Ask the configured LLM whether the answer states the gold facts. None when no LLM is available.

    Responses are cached on disk by ``keepline.llm``, so re-running the agreement check is free.
    """
    from keepline.llm import get_llm

    llm = get_llm()
    if llm is None:
        return None
    gold = [truth[f].statement for f in q.gold_fact_ids if f in truth]
    prompt = json.dumps(
        {
            "question": q.text,
            "expected_action": str(q.expected_action),
            "gold_statements": gold,
            "acceptable_route_person_ids": q.gold_route_person_ids,
            "answer_action": str(a.action),
            "answer_text": a.text,
            "answer_route_to": a.route_to,
        },
        ensure_ascii=False,
    )
    system = (
        "You grade a workplace Q&A assistant. Mark correct=true only if the answer's action matches the expected "
        "action (abstain/route counts for unanswerable questions) and any stated facts agree with the gold "
        "statements as of the question date. Superseded values are wrong."
    )
    try:
        out = llm.complete_json(prompt, _JUDGE_SCHEMA, system=system, max_tokens=300)
        return bool(out.get("correct"))
    except Exception as exc:  # noqa: BLE001 -- judge is advisory; never break the benchmark
        log.warning("LLM judge failed for %s: %s", q.id, exc)
        return None


def truth_index(facts: Iterable[TruthFact]) -> dict[str, TruthFact]:
    return {f.id: f for f in facts}

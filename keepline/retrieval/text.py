"""Tiny, dependency-free text utilities shared by extraction, search and the answer agent.

Kept deliberately simple and deterministic: the same tokenizer is used to index and to query, so a light
suffix-stripping stemmer is enough to make "rotate / rotating / rotated" meet without pulling in NLTK.
"""

from __future__ import annotations

import re
from functools import lru_cache

STOPWORDS = frozenset(
    """
    a an the and or but if then else of to in on at by for with from into onto about as is are was were be been
    being am do does did doing have has had having i me my we our ours us you your yours he him his she her hers
    it its they them their this that these those there here what which who whom whose when where why how can
    could should would will shall may might must not no yes so than too very just also any all some each every
    s t re ve ll d m o y hi hey thanks thank please ok okay yeah yep sure get got go going let lets let's up out
    over again only one own same such both few more most other now need needs want like know think via per
    """.split()
)

# Words that carry meaning for our cue detection must never be dropped as stopwords when we build cue sets,
# but they are fine to drop from the BM25 bag (they are too common to discriminate).

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:['\-][a-z0-9]+)*")
_ORDINAL_RE = re.compile(r"^\d+(st|nd|rd|th)$")
_NUM_RE = re.compile(r"\b(\d{1,4})(?:st|nd|rd|th)?\b")


@lru_cache(maxsize=65536)
def stem(word: str) -> str:
    """Light English suffix stripping. Numbers and ordinals ('15th') are normalised to their digits."""
    if word[:1].isdigit():
        m = _ORDINAL_RE.match(word)
        return word[: -2] if m else word
    if len(word) <= 3:
        return word
    for suf, rep, min_len in (
        ("ies", "y", 5),
        ("ing", "", 6),
        ("ed", "", 5),
        ("es", "", 5),
        ("s", "", 4),
    ):
        if word.endswith(suf) and len(word) >= min_len:
            if suf == "s" and word.endswith("ss"):
                return word
            base = word[: -len(suf)] + rep
            if suf in ("ing", "ed") and len(base) >= 3 and base[-1] == base[-2] and base[-1] not in "ls":
                base = base[:-1]  # "running" -> "run", "planned" -> "plan"
            return base
    return word


def raw_tokens(text: str) -> list[str]:
    """Lower-cased word tokens, hyphen/apostrophe compounds split into parts."""
    out: list[str] = []
    for tok in _TOKEN_RE.findall(text.lower()):
        out.extend(p for p in re.split(r"['\-]", tok) if p)
    return out


def tokenize(text: str) -> list[str]:
    """Content tokens for BM25 / overlap: stopwords removed, stemmed."""
    return [stem(t) for t in raw_tokens(text) if t not in STOPWORDS]


@lru_cache(maxsize=65536)
def content_set(text: str) -> frozenset[str]:
    return frozenset(tokenize(text))


@lru_cache(maxsize=65536)
def numbers(text: str) -> frozenset[str]:
    """Numeric values mentioned ('the 1st and 15th' -> {'1', '15'}); used to detect changed values."""
    return frozenset(m.group(1) for m in _NUM_RE.finditer(text))


def jaccard(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def containment(small: frozenset[str] | set[str], big: frozenset[str] | set[str]) -> float:
    """Share of ``small`` covered by ``big`` -- asymmetric overlap, good for short queries vs long text."""
    if not small:
        return 0.0
    return len(small & big) / len(small)


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])|\n+\s*(?:[-*•]|\d+[.)])?\s*")
_ABBREV_END = re.compile(r"\b(e\.g|i\.e|etc|vs|approx|mr|mrs|ms|dr|no|st)\.$", re.I)


def split_sentences(text: str) -> list[str]:
    """Sentence/line segmentation that keeps bullet and numbered steps as separate units."""
    parts = [p.strip() for p in _SENT_SPLIT.split(text or "") if p and p.strip()]
    merged: list[str] = []
    for p in parts:
        if merged and _ABBREV_END.search(merged[-1]):
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return [m.strip(" \t-*•") for m in merged if len(m.strip(" \t-*•")) > 1]

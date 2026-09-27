"""Assemble the Harbourline truth file from the hand-written fact tables."""

from __future__ import annotations

from keepline.contracts import TruthFact, Visibility
from keepline.data.company import AREA_IDS, PEOPLE_BY_ID
from keepline.data.facts_engit import FACTS as ENGIT
from keepline.data.facts_ops import FACTS as OPS
from keepline.data.facts_sarah import FACTS as SARAH
from keepline.data.spec import FactSpec, validate

ALL_SPECS: list[FactSpec] = [*SARAH, *ENGIT, *OPS]


def load_specs() -> list[FactSpec]:
    errs = validate(ALL_SPECS, set(PEOPLE_BY_ID), set(AREA_IDS))
    if errs:
        raise ValueError("invalid fact tables:\n  " + "\n  ".join(errs))
    return ALL_SPECS


def truth_ids(specs: list[FactSpec]) -> dict[str, str]:
    return {s.key: f"T{i:03d}" for i, s in enumerate(specs, 1)}


def to_truth(specs: list[FactSpec]) -> list[TruthFact]:
    ids = truth_ids(specs)
    out = []
    for s in specs:
        notes = s.notes
        if s.contra:
            notes = (notes + " " if notes else "") + "Conflict: " + "; ".join(
                f"{who} stated an outdated/wrong version ({wrong!r}); {s.stated_by} corrected it."
                for who, wrong in s.contra)
        out.append(TruthFact(
            id=ids[s.key], kind=s.kind, area_id=s.area, statement=s.statement, answer_keywords=s.kw,
            known_by=list(s.known_by), stated_by=s.stated_by, valid_from=s.vfrom, valid_to=s.vto,
            supersedes=ids[s.supersedes] if s.supersedes else None, importance=s.importance,
            is_landmine=s.landmine, in_corpus=s.in_corpus,
            visibility=Visibility.PRIVATE if s.private else Visibility.PUBLIC, notes=notes.strip()))
    return out

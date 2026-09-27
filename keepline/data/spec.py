"""Authoring format for Harbourline ground truth.

Truth is written by hand as ``FactSpec`` rows (see ``facts_*.py``). Each row carries the canonical statement that
goes into ``data/truth/truth.json`` *plus* everything the renderer and question generator need:

* ``say``      -- several phrasings in the knower's own voice. Every variant MUST satisfy ``kw`` (CNF, case-
                  insensitive substring match). The renderer embeds variants verbatim, so evidence docs always
                  contain the answer keywords (checked by ``validate`` and by tests/test_data.py).
* ``prompts``  -- what a colleague might ask in a thread before the knower answers (optional).
* ``qs``       -- eval question phrasings. They ask *for* the fact without copying the ``say`` wording.
* ``where``    -- preferred containers: slack channel names ("#eng-core"), "email", "ticket", "doc", "dm".
* ``contra``   -- (person_id, wrong statement) pairs: someone states an outdated/wrong version first and the
                  knower corrects them in the same thread. Contra text is never evidence.

Keys are stable slugs ("recon.skip_days.v1"); truth ids ("T001") are assigned at build time in file order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from keepline.contracts import FactKind

K = FactKind  # short alias for fact tables


@dataclass
class FactSpec:
    key: str
    kind: FactKind
    area: str
    statement: str
    kw: list[list[str]]
    known_by: list[str]
    stated_by: str
    valid_from: str
    valid_to: str | None = None
    supersedes: str | None = None  # key of the fact this one replaces
    importance: int = 2
    landmine: bool = False
    in_corpus: bool = True
    private: bool = False  # expressed only in DMs
    notes: str = ""
    say: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    qs: list[str] = field(default_factory=list)
    where: list[str] = field(default_factory=list)
    askers: list[str] = field(default_factory=list)
    renders: int = 0  # 0 => default by importance
    forbid: list[list[str]] = field(default_factory=list)  # old-version-only keywords (current questions)
    contra: list[tuple[str, str]] = field(default_factory=list)

    @property
    def vfrom(self) -> date:
        return date.fromisoformat(self.valid_from)

    @property
    def vto(self) -> date | None:
        return date.fromisoformat(self.valid_to) if self.valid_to else None


def cnf_match(text: str, cnf: list[list[str]]) -> bool:
    """True iff every any-of group has at least one keyword appearing (case-insensitively) in ``text``."""
    low = text.casefold()
    return all(any(k.casefold() in low for k in group) for group in cnf)


def validate(specs: list[FactSpec], people: set[str], areas: set[str]) -> list[str]:
    """Return a list of human-readable problems (empty == valid)."""
    errs: list[str] = []
    keys: dict[str, FactSpec] = {}
    for s in specs:
        if s.key in keys:
            errs.append(f"{s.key}: duplicate key")
        keys[s.key] = s
    superseded = {s.supersedes for s in specs if s.supersedes}
    for s in specs:
        p = f"{s.key}:"
        if s.area not in areas:
            errs.append(f"{p} unknown area {s.area}")
        for pid in [*s.known_by, s.stated_by, *s.askers, *(c[0] for c in s.contra)]:
            if pid not in people:
                errs.append(f"{p} unknown person {pid}")
        if not s.kw or any(not g for g in s.kw):
            errs.append(f"{p} empty keyword group")
        if s.in_corpus and not s.say:
            errs.append(f"{p} in-corpus fact has no say variants")
        for v in s.say:
            if not cnf_match(v, s.kw):
                errs.append(f"{p} say variant misses keywords: {v[:70]!r}")
        for _, wrong in s.contra:
            if cnf_match(wrong, s.kw):
                errs.append(f"{p} contra statement accidentally satisfies keywords: {wrong[:60]!r}")
        if s.key not in superseded and len(s.qs) < 3:
            errs.append(f"{p} needs >= 3 questions (has {len(s.qs)})")
        if s.supersedes:
            old = keys.get(s.supersedes)
            if old is None:
                errs.append(f"{p} supersedes unknown {s.supersedes}")
            elif old.valid_to != s.valid_from:
                errs.append(f"{p} predecessor valid_to {old.valid_to} != valid_from {s.valid_from}")
        if s.key in superseded and not s.valid_to:
            errs.append(f"{p} is superseded but has no valid_to")
        if s.private and s.where and s.where != ["dm"]:
            errs.append(f"{p} private fact must use where=['dm']")
        if s.importance not in (1, 2, 3):
            errs.append(f"{p} importance must be 1..3")
        if s.vto and s.vto < s.vfrom:
            errs.append(f"{p} valid_to before valid_from")
    return errs

"""Integrity tests for the Harbourline truth file, rendered corpus, and question splits.

The build takes well under a second, so the fixture builds a fresh copy into a temp dir (twice, for determinism).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

from keepline.config import QUESTIONS_DIR
from keepline.contracts import Action, QType, Split, Visibility
from keepline.data.build import build
from keepline.data.company import WINDOW_END, WINDOW_START
from keepline.data.spec import cnf_match
from keepline.data.truth import ALL_SPECS
from keepline.data.truth_io import load_evidence_map, load_questions, load_truth, verify_test_frozen
from keepline.io import load_corpus, load_people


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("world")
    build(seed=7, out=out)
    return out


@pytest.fixture(scope="module")
def truth(world: Path):
    return {t.id: t for t in load_truth(world / "truth")}


@pytest.fixture(scope="module")
def evidence(world: Path):
    return load_evidence_map(world / "truth")


@pytest.fixture(scope="module")
def docs(world: Path):
    return {d.id: d for d in load_corpus(world / "corpus")}


@pytest.fixture(scope="module")
def questions(world: Path):
    return {s: load_questions(s, world / "questions") for s in Split}


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_build_is_deterministic(world: Path, tmp_path: Path) -> None:
    build(seed=7, out=tmp_path)
    a, b = _files(world), _files(tmp_path)
    assert a.keys() == b.keys()
    assert [k for k in a if a[k] != b[k]] == []


def test_every_in_corpus_fact_has_evidence(truth, evidence) -> None:
    for t in truth.values():
        if t.in_corpus:
            assert evidence.get(t.id), f"{t.id} has no evidence docs"
        else:
            assert not evidence.get(t.id), f"{t.id} is not-in-corpus but has evidence"


def test_evidence_docs_contain_answer_keywords(truth, evidence, docs) -> None:
    for tid, doc_ids in evidence.items():
        for did in doc_ids:
            assert did in docs, f"{tid}: unknown doc {did}"
            assert cnf_match(docs[did].text, truth[tid].answer_keywords), f"{tid}: {did} misses keywords"


def test_superseded_chains_are_consistent(truth, evidence, docs) -> None:
    successors = defaultdict(list)
    for t in truth.values():
        if t.supersedes:
            old = truth[t.supersedes]
            successors[old.id].append(t.id)
            assert old.area_id == t.area_id
            assert old.valid_to == t.valid_from, f"{old.id}->{t.id} dates do not chain"
            for did in evidence.get(old.id, []):
                assert docs[did].timestamp.date() < old.valid_to, f"{did} states {old.id} after it expired"
            for did in evidence.get(t.id, []):
                assert docs[did].timestamp.date() >= t.valid_from, f"{did} states {t.id} before it was true"
    assert all(len(v) == 1 for v in successors.values())
    for t in truth.values():
        if t.valid_to is not None:
            assert t.id in successors, f"{t.id} expired but nothing supersedes it"
    assert len(successors) >= 15


def test_required_scenarios_present(truth) -> None:
    landmines = [t for t in truth.values() if t.is_landmine]
    assert len(landmines) >= 5
    assert sum(1 for t in truth.values() if not t.in_corpus) >= 15
    assert sum(1 for t in truth.values() if t.visibility is Visibility.PRIVATE) >= 5
    assert any("Conflict:" in t.notes for t in truth.values())
    text = " ".join(t.statement for t in landmines).lower()
    for needle in ("15th", "friday", "restart", "primary", "registrar"):
        assert needle in text, f"missing planted landmine about {needle}"


def test_visibility_matches_fact_privacy(truth, evidence, docs) -> None:
    for tid, doc_ids in evidence.items():
        private = truth[tid].visibility is Visibility.PRIVATE
        for did in doc_ids:
            assert (docs[did].visibility is Visibility.PRIVATE) == private, f"{tid}/{did} visibility mismatch"


def test_corpus_is_clean_and_in_window(world: Path, docs, truth) -> None:
    people = {p.id for p in load_people(world / "org")}
    marker = re.compile(r"\bT\d{3}\b|" + "|".join(re.escape(s.key) + r"\b" for s in ALL_SPECS))
    for d in docs.values():
        assert d.author_id in people and d.author_id != "alex"
        assert WINDOW_START <= d.timestamp.date() <= WINDOW_END
        assert not marker.search(d.text), f"machine marker leaked into {d.id}"
        assert d.url.startswith("https://")
    assert len({d.url for d in docs.values()}) == len(docs)
    assert len(docs) > 2500
    open_sarah = [d for d in docs.values() if d.source_type.value == "ticket" and d.meta.get("assignee") == "sarah"
                  and d.meta.get("status") != "Closed"]
    assert len(open_sarah) >= 4


def test_org_files_do_not_leak_facts(world: Path) -> None:
    """people.json / areas.json are customer inputs: they may name systems, never state a tracked fact."""
    org = ((world / "org" / "areas.json").read_text(encoding="utf-8")
           + (world / "org" / "people.json").read_text(encoding="utf-8")).lower()
    for spec in ALL_SPECS:
        for text in [spec.statement, *spec.say]:
            for i in range(0, max(1, len(text) - 40), 20):
                chunk = text[i:i + 40].lower()
                assert len(chunk) < 40 or chunk not in org, f"{spec.key} leaks into org files: {chunk!r}"


def test_split_sizes_and_types(questions) -> None:
    sizes = {s: len(q) for s, q in questions.items()}
    assert 600 <= sum(sizes.values()) <= 850
    assert sizes[Split.TRAIN] > sizes[Split.TEST] > sizes[Split.DEV] >= 120
    for split, qs in questions.items():
        assert {q.qtype for q in qs} == set(QType), f"{split} is missing a qtype"
    ids = [q.id for qs in questions.values() for q in qs]
    assert len(ids) == len(set(ids))


def test_no_leakage_across_splits(questions) -> None:
    text_split: dict[str, Split] = {}
    fact_split: dict[str, Split] = {}
    for split, qs in questions.items():
        for q in qs:
            key = q.text.strip().lower()
            assert text_split.setdefault(key, split) == split, f"question text in two splits: {q.text}"
            for fid in q.gold_fact_ids:
                assert fact_split.setdefault(fid, split) == split, f"{fid} appears in two splits"


def test_question_gold_is_coherent(questions, truth) -> None:
    for qs in questions.values():
        for q in qs:
            assert date(2026, 9, 1) <= q.as_of <= date(2026, 9, 30)
            facts = [truth[f] for f in q.gold_fact_ids]
            if q.qtype is QType.CURRENT:
                assert facts and facts[0].supersedes and facts[0].valid_to is None
            if q.qtype is QType.LANDMINE:
                assert facts and facts[0].is_landmine
            if q.qtype is QType.UNANSWERABLE:
                assert all(not f.in_corpus or f.visibility is Visibility.PRIVATE for f in facts)
                assert q.expected_action in (Action.ABSTAIN, Action.ROUTE)
            if q.expected_action is Action.ROUTE:
                assert q.gold_route_person_ids
            if q.expected_action is Action.ANSWER:
                assert facts and all(f.in_corpus and f.visibility is not Visibility.PRIVATE for f in facts)
                assert q.gold_answer_keywords


def test_test_split_hash(world: Path) -> None:
    assert verify_test_frozen(world / "questions")
    if (QUESTIONS_DIR / "test.jsonl").exists():
        assert verify_test_frozen(), "data/questions/test.jsonl changed since it was frozen"
        built = json.loads(json.dumps((world / "questions" / "test.sha256").read_text(encoding="utf-8")))
        assert built == (QUESTIONS_DIR / "test.sha256").read_text(encoding="utf-8"), "committed test split is stale"

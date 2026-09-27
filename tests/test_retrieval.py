"""BM25 index: relevance, as_of (no time travel), permission filtering, persistence, area naming."""

from __future__ import annotations

from datetime import date

from keepline.memory.sample import sample_areas, sample_docs
from keepline.retrieval.search import SearchIndex
from keepline.retrieval.text import numbers, stem


def _index(tmp_path) -> SearchIndex:
    return SearchIndex(tmp_path / "i.pkl").build(sample_docs(), [], areas=sample_areas())


def test_relevance_and_persistence(tmp_path) -> None:
    ix = _index(tmp_path)
    hits = ix.search("rotate the CoreLink API key", k=3)
    assert hits[0].doc_id in {"s3", "s4"}
    ix.save()
    again = SearchIndex(tmp_path / "i.pkl").load()
    assert [h.doc_id for h in again.search("rotate the CoreLink API key", k=3)] == [h.doc_id for h in hits]


def test_as_of_filter(tmp_path) -> None:
    ix = _index(tmp_path)
    ids = {h.doc_id for h in ix.search("reconciliation job skip 15th", k=20, as_of=date(2026, 4, 1))}
    assert "s5" not in ids and "s1" in ids


def test_permission_filter(tmp_path) -> None:
    ix = _index(tmp_path)
    q = "Jenkins admin credentials vault"
    assert "s7" not in {h.doc_id for h in ix.search(q, k=20, visible_to="alex")}
    assert "s7" in {h.doc_id for h in ix.search(q, k=20, visible_to="dana")}


def test_area_naming_uses_phrases(tmp_path) -> None:
    ix = _index(tmp_path)
    assert ix.areas_named("When should the reconciliation job not run?")[0] == "reconciliation"
    assert "payroll" not in ix.areas_named("When should the job run?")  # "pay run" needs both words


def test_text_helpers() -> None:
    assert stem("rotating") == stem("rotate") or stem("rotating") == "rotat"
    assert numbers("[HCU-118] skip the 1st and the 15th, email a@b.com") == frozenset({"1", "15"})
    assert numbers("five business days") == frozenset({"5"})

"""Memory pipeline on a tiny hand-written fixture: extraction kinds, privacy, supersession, expertise, store API."""

from __future__ import annotations

from datetime import date

import pytest

from keepline.contracts import FactKind, ReviewStatus, Visibility
from keepline.memory.build import build_memory
from keepline.memory.extract import classify_kind
from keepline.memory.sample import sample_org
from keepline.memory.store import MemoryStore


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory):
    tmp = tmp_path_factory.mktemp("mem")
    people, areas, docs = sample_org()
    store = MemoryStore(tmp / "k.db")
    stats, index = build_memory(people, areas, docs, store=store, index_path=tmp / "idx.pkl")
    return store, stats, index


@pytest.mark.parametrize(
    ("sentence", "kind"),
    [
        ("Never restart the batch server during business hours.", FactKind.LANDMINE),
        ("Whatever you do, don't delete the staging bucket.", FactKind.LANDMINE),
        ("The admin credentials are in the Ops vault in the password manager.", FactKind.ACCESS),
        ("Our account manager at Acme is Jo Park.", FactKind.VENDOR_CONTACT),
        ("The SSL certificate renews every March.", FactKind.RECURRING_TASK),
        ("Going forward we will switch the export to Tuesdays.", FactKind.DECISION),
        ("We decided to move the export to Tuesdays.", FactKind.DECISION),
        ("Priya is responsible for vendor sign-off.", FactKind.OWNER),
        ("Kim is the point person for vendor invoices.", FactKind.OWNER),
    ],
)
def test_extraction_kinds(sentence: str, kind: FactKind) -> None:
    assert classify_kind(sentence)[0] == kind


def test_no_kind_for_chatter() -> None:
    assert classify_kind("Great game last night, what a finish!")[0] is None


def test_privacy_filter(built) -> None:
    store, stats, _ = built
    assert stats.excluded_private == 1 and stats.excluded_personal == 1
    assert store.doc("dm1") is None and store.doc("s6") is None
    assert all(f.visibility != Visibility.PRIVATE for f in store.all_facts())


def test_supersession_chain(built) -> None:
    store, stats, _ = built
    assert stats.superseded >= 1
    new = next(f for f in store.facts(area_id="reconciliation") if "15th" in f.text)
    chain = store.supersession_chain(new.id)
    assert [("15th" in f.text) for f in chain] == [False, True]
    old = chain[0]
    assert old.valid_to == new.valid_from and old.superseded_by == new.id and new.supersedes == old.id
    assert new.kind == FactKind.LANDMINE  # a new version of a landmine stays a landmine
    current = store.facts(area_id="reconciliation", current_only=True)
    assert old.id not in {f.id for f in current}
    # bi-temporal: before the update, the old rule was current
    then = store.facts(area_id="reconciliation", current_only=True, as_of=date(2026, 4, 1))
    assert old.id in {f.id for f in then} and new.id not in {f.id for f in then}


def test_dedup_merges_receipts(built) -> None:
    store, stats, _ = built
    assert stats.merged >= 1
    old = next(f for f in store.all_facts() if f.superseded_by)
    assert set(old.source_doc_ids) >= {"s1", "s2"}


def test_expertise_doing_beats_talking(built) -> None:
    store, _, _ = built
    top = store.expertise(area_id="reconciliation")[0]
    assert top.person_id == "sarah" and top.n_tickets_closed >= 1 and 0 < top.score <= 1
    assert any(not e.enough_data for e in store.expertise())


def test_open_tickets_and_counts(built) -> None:
    store, _, _ = built
    assert [d.id for d in store.open_tickets("sarah")] == ["t3"]
    assert sum(store.area_doc_counts_by_month("reconciliation").values()) >= 3


def test_review_and_query_log(built) -> None:
    store, _, _ = built
    f = store.facts(person_id="priya")[0]
    store.set_review_status(f.id, ReviewStatus.CORRECTED, corrected_text="Payroll runs every second Thursday at 9am.")
    assert store.fact(f.id).text.endswith("9am.") and store.review_events(f.id)


def test_graph_for_person(built) -> None:
    store, _, _ = built
    g = store.graph_for_person("sarah")
    types = {n["type"] for n in g["nodes"]}
    assert {"person", "area", "fact", "doc"} <= types
    assert any(link["rel"] == "supersedes" for link in g["links"])
    assert store.graph_for_person("nobody") == {"nodes": [], "links": []}

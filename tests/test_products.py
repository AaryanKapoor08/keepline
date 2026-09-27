"""Product-layer tests against the in-memory FakeStore (no generated data, no LLM)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from keepline.contracts import DepartureType, FactKind, Person
from keepline.products import signoff
from keepline.products._common import departure_likelihood, redact_secrets
from keepline.products.gaps import gap_questions
from keepline.products.handoff import build_handoff_pack, pack_to_markdown
from keepline.products.onboarding import build_onboarding_brief
from keepline.products.risk import redundancy_from_bus_factor, risk_history, risk_map
from keepline.products.simulate import areas_in_brief, newly_orphaned, staff_project, what_if_leaves
from tests.test_products_fake import FakeStore

TODAY = date(2026, 9, 4)


def test_departure_likelihood_shape() -> None:
    sarah = Person("s", "S", "r", "eng", "e", date(2020, 1, 1), date(2026, 9, 11), DepartureType.RESIGNATION)
    tom = Person("t", "T", "r", "lead", "e", date(2000, 1, 1), date(2026, 12, 18), DepartureType.RETIREMENT)
    stay = Person("m", "M", "r", "eng", "e", date(2020, 1, 1))
    assert departure_likelihood(sarah, TODAY) > 0.95
    assert 0.6 < departure_likelihood(tom, TODAY) < 0.9
    assert departure_likelihood(stay, TODAY) < 0.1


def test_redundancy_saturates() -> None:
    assert redundancy_from_bus_factor(0) == 0 == redundancy_from_bus_factor(1)
    assert 0.5 < redundancy_from_bus_factor(2) < redundancy_from_bus_factor(3) < 1


def test_risk_map_ranks_sarahs_areas_first() -> None:
    risks = risk_map(FakeStore(), TODAY)
    assert risks[0].area_id == "reconciliation"
    top = risks[0]
    assert top.bus_factor == 1 and top.at_risk_person_id == "sarah" and top.countdown_days == 7
    assert "Only Sarah" in top.explanation and "41 messages" in top.explanation
    assert all(0 <= r.risk <= 1 for r in risks)
    assert len(top.trend) == 6
    payroll = next(r for r in risks if r.area_id == "payroll")
    assert payroll.risk < top.risk and payroll.bus_factor == 2


def test_risk_history_rises_near_departure() -> None:
    trend = risk_history(FakeStore(), "reconciliation", months=6, today=TODAY)
    assert trend[-1] > trend[0]


def test_what_if_removes_holder() -> None:
    before, after = what_if_leaves(FakeStore(), "sarah", TODAY)
    assert [r.area_id for r in before] == [r.area_id for r in after]
    assert "reconciliation" in newly_orphaned(before, after)
    vend_b = next(r for r in before if r.area_id == "vendor_api")
    vend_a = next(r for r in after if r.area_id == "vendor_api")
    assert vend_a.bus_factor == vend_b.bus_factor - 1


def test_handoff_pack_sections_and_receipts(tmp_path: Path) -> None:
    store = FakeStore()
    pack = build_handoff_pack(store, "sarah", TODAY)
    sections = {it.section for it in pack.items}
    assert {"access", "vendor_contacts", "landmines", "unresolved_work", "suggested_owners"} <= sections
    assert pack.last_day == date(2026, 9, 11)
    landmines = [it for it in pack.items if it.section == "landmines"]
    assert all(it.citations for it in landmines)
    assert all("skip the 1st." not in it.detail for it in landmines), "superseded fact must not appear"
    assert not any("hunter2" in it.detail for it in pack.items), "secrets must be redacted"
    assert any("Promised follow-up" in it.title for it in pack.items)
    assert any("HCU-7" in it.title for it in pack.items)
    assert all("private" not in it.detail.lower() for it in pack.items)
    assert pack.gaps
    md = pack_to_markdown(store, pack)
    assert md.startswith("# Handoff pack: Sarah Chen") and "receipt:" in md


def test_signoff_roundtrip(tmp_path: Path) -> None:
    store = FakeStore()
    path = tmp_path / "signoffs.json"
    pack = build_handoff_pack(store, "sarah", TODAY)
    key = signoff.item_key(pack.items[0])
    signoff.set_item("sarah", key, "corrected", "Fixed text", path=path)
    signoff.sign_off("sarah", path=path)
    again = signoff.apply_state(build_handoff_pack(store, "sarah", TODAY), path=path)
    assert again.signed_off and again.items[0].status == "corrected" and again.items[0].detail == "Fixed text"
    signoff.set_item("sarah", key, "confirmed", path=path)
    assert not signoff.person_state("sarah", path=path)["signed_off"], "edits re-open the pack"


def test_gap_questions_ranked() -> None:
    gaps = gap_questions(FakeStore(), "sarah", n=5, today=TODAY)
    assert 0 < len(gaps) <= 5
    assert gaps == sorted(gaps, key=lambda g: g.priority, reverse=True)
    reasons = {g.reason for g in gaps}
    assert "Decision with no recorded reason" in reasons or "Landmine with no recorded reason" in reasons


def test_onboarding_brief_for_alex() -> None:
    brief = build_onboarding_brief(FakeStore(), "alex", TODAY)
    titles = [s.title for s in brief.sections]
    assert titles == ["Who to ask about what", "Recent decisions & why", "Open risks & landmines", "Jargon", "Starter tasks"]
    who = brief.sections[0].items
    recon = next(r for r in who if r["area_id"] == "reconciliation")
    assert recon["person_id"] == "sarah" and "after that ask Mike" in (recon["after"] or "")
    landmines = [r for r in brief.sections[2].items if r["type"] == "landmine"]
    assert landmines and all(r["citations"] for r in landmines)
    assert any(r["term"] == "CoreLink" for r in brief.sections[3].items)
    assert all(r["buddy_id"] != "sarah" for r in brief.sections[4].items), "never pair a joiner with a leaver"


def test_staffing_helper() -> None:
    store = FakeStore()
    assert set(areas_in_brief(store, "Rework the reconciliation job and CoreLink API key handling")) >= {"reconciliation", "vendor_api"}
    plans = staff_project(store, "reconciliation revamp", ["mike", "alex"], TODAY)
    assert plans and plans[0].area_id == "reconciliation" and plans[0].bus_factor_before == 0


def test_redact_secrets() -> None:
    assert "hunter2" not in redact_secrets("password: hunter2")
    assert "1Password vault Core" in redact_secrets("creds in 1Password vault Core")


def test_kinds_cover_handoff() -> None:
    assert {FactKind.ACCESS, FactKind.LANDMINE} <= set(FactKind)

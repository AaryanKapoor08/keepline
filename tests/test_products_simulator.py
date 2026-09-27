"""Decision check, project staffing and what-breaks (simulator backends) against the FakeStore."""

from __future__ import annotations

import json
from datetime import date

from keepline.products.decision_check import check_decision, target_dates
from keepline.products.simulate import what_breaks, what_if_report
from keepline.products.staffing import plan_project
from tests.test_products_fake import FakeStore

FRIDAY = date(2026, 9, 4)


def test_target_dates_resolve_against_today() -> None:
    assert target_dates("rotate it this Friday", FRIDAY) == [FRIDAY]
    assert target_dates("do it next Friday", FRIDAY) == [date(2026, 9, 11)]
    assert target_dates("run on the 15th", FRIDAY) == [date(2026, 9, 15)]
    assert target_dates("tomorrow", FRIDAY) == [date(2026, 9, 5)]
    assert target_dates("no date here", FRIDAY) == []


def test_friday_rotation_conflicts_with_landmine() -> None:
    r = check_decision(FakeStore(), "Rotate the CoreLink API key this Friday", today=FRIDAY)
    assert r["verdict"] == "conflict"
    top = r["conflicts"][0]
    assert top["fact_id"] == "F3" and top["severity"] == "conflict" and "Friday" in top["why"]
    assert top["doc_id"] == "slack-3" and top["url"] and top["stated_by"] == "sarah"
    assert r["suggested_reviewer"] == "mike", "reviewer must be a holder who is staying"
    json.dumps(r)


def test_tuesday_rotation_is_not_a_conflict() -> None:
    r = check_decision(FakeStore(), "Rotate the CoreLink API key next Tuesday", today=FRIDAY)
    assert r["verdict"] != "conflict"
    assert any(c["fact_id"] == "F3" and c["severity"] == "info" for c in r["conflicts"])


def test_day_of_month_conflict_uses_current_fact_only() -> None:
    r = check_decision(FakeStore(), "Run the reconciliation job on the 15th", today=FRIDAY)
    assert r["verdict"] == "conflict"
    ids = [c["fact_id"] for c in r["conflicts"]]
    assert "F2" in ids and "F1" not in ids, "superseded rule must not be cited"


def test_unrelated_proposal_is_clear() -> None:
    r = check_decision(FakeStore(), "Order new office chairs", today=FRIDAY)
    assert r["verdict"] == "clear" and r["conflicts"] == []


def test_plan_project_pairs_learner_and_reviewer() -> None:
    plan = plan_project(FakeStore(), "Rebuild the reconciliation job and CoreLink API key rotation", FRIDAY)
    json.dumps(plan)
    by_area = {a["area_id"]: a for a in plan["areas"]}
    assert {"reconciliation", "vendor_api"} <= set(by_area)
    recon = by_area["reconciliation"]
    assert recon["bus_factor_before"] == 0 and recon["bus_factor_after"] == 1 and recon["learner"] == "mike"
    assert recon["holders"][0]["leaving_in_days"] == 7
    assert plan["summary"]["single_points_of_failure"] >= 1


def test_what_breaks_lists_concrete_losses() -> None:
    breaks = what_breaks(FakeStore(), "sarah", FRIDAY)
    types = {b["type"] for b in breaks}
    assert {"sole_access", "orphaned_landmine", "vendor_contact_lost"} <= types
    assert all(b["fact_id"] != "F1" for b in breaks), "superseded facts do not break anything"
    report = what_if_report(FakeStore(), "sarah", FRIDAY)
    json.dumps(report)
    assert "reconciliation" in report["orphaned_areas"] and report["break_counts"]["sole_access"] >= 1

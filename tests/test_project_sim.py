from __future__ import annotations

import json
from datetime import date

import pytest

from keepline.config import MEMORY_DB
from keepline.products.project_sim import TEMPLATES, simulate_project

pytestmark = pytest.mark.skipif(not MEMORY_DB.exists(), reason="memory not built")
TODAY = date(2026, 9, 4)


def _store():
    from keepline.memory.store import MemoryStore

    return MemoryStore()


def test_templates_touch_areas_and_are_json_safe() -> None:
    s = _store()
    for t in TEMPLATES:
        r = simulate_project(s, t["brief"], TODAY, weeks=t["weeks"], runs=200)
        assert r["areas"], t["name"]
        json.dumps(r)
        assert {o["id"] for o in r["options"]} == {"fastest", "balanced", "resilient"}
        for o in r["options"]:
            assert 0.0 <= o["p_any_uncovered"] <= 1.0


def test_deterministic_for_seed() -> None:
    s = _store()
    a = simulate_project(s, TEMPLATES[0]["brief"], TODAY, runs=300, seed=3)
    b = simulate_project(s, TEMPLATES[0]["brief"], TODAY, runs=300, seed=3)
    assert a == b


def test_forced_departure_never_lowers_risk() -> None:
    s = _store()
    base = simulate_project(s, TEMPLATES[2]["brief"], TODAY, weeks=16, runs=400)
    lead = next(o for o in base["options"] if o["id"] == "fastest")["areas"][0]["lead"]
    worse = simulate_project(s, TEMPLATES[2]["brief"], TODAY, weeks=16, runs=400, leaves={lead: 4})
    f0 = next(o for o in base["options"] if o["id"] == "fastest")["p_any_uncovered"]
    f1 = next(o for o in worse["options"] if o["id"] == "fastest")["p_any_uncovered"]
    assert f1 >= f0


def _focus_at_end(r: dict, option: str, area_id: str) -> float:
    o = next(o for o in r["options"] if o["id"] == option)
    return next(a for a in o["areas"] if a["area_id"] == area_id)["p_uncovered_at_end"]


def test_default_view_unchanged_by_stress_options() -> None:
    """The demo's planned-departures numbers (CoreLink v2 sunset: 100% without pairing, 40% pairing Aisha)."""
    s = _store()
    t = TEMPLATES[0]
    base = simulate_project(s, t["brief"], TODAY, weeks=t["weeks"])
    explicit = simulate_project(s, t["brief"], TODAY, weeks=t["weeks"], ignore_departures=False, absence_scale=1.0)
    assert base == explicit
    assert base["scenario"] == {"departures": "planned", "forced": [], "absence_scale": 1.0}
    assert _focus_at_end(base, "fastest", "corelink_api") == 1.0
    assert round(_focus_at_end(base, "balanced", "corelink_api"), 2) == 0.40
    bal = next(o for o in base["options"] if o["id"] == "balanced")
    assert next(a for a in bal["areas"] if a["area_id"] == "corelink_api")["learner"] == "aisha"


def test_nobody_leaves_never_raises_risk() -> None:
    s = _store()
    for t in TEMPLATES:
        base = simulate_project(s, t["brief"], TODAY, weeks=t["weeks"], runs=800)
        calm = simulate_project(s, t["brief"], TODAY, weeks=t["weeks"], runs=800, ignore_departures=True)
        assert calm["timeline"] == [], t["id"]
        assert calm["scenario"]["departures"] == "none"
        for o0, o1 in zip(base["options"], calm["options"]):
            assert o1["p_uncovered_at_end"] <= o0["p_uncovered_at_end"], (t["id"], o0["id"])
            assert o1["p_any_uncovered"] <= o0["p_any_uncovered"], (t["id"], o0["id"])
            assert o1["lose"] == []


def test_nobody_leaves_still_shows_thin_coverage_and_is_deterministic() -> None:
    s = _store()
    t = next(x for x in TEMPLATES if x["id"] == "mobile_app")
    a = simulate_project(s, t["brief"], TODAY, weeks=t["weeks"], runs=800, ignore_departures=True)
    b = simulate_project(s, t["brief"], TODAY, weeks=t["weeks"], runs=800, ignore_departures=True)
    assert a == b
    fastest = next(o for o in a["options"] if o["id"] == "fastest")
    assert fastest["p_any_uncovered"] > 0  # sick days and vacation alone still open gaps on one-person areas


def test_busy_season_raises_everyday_disruption() -> None:
    from keepline.products.project_sim import BUSY_SEASON_ABSENCE_SCALE

    s = _store()
    t = next(x for x in TEMPLATES if x["id"] == "mobile_app")
    calm = simulate_project(s, t["brief"], TODAY, weeks=t["weeks"], ignore_departures=True)
    busy = simulate_project(s, t["brief"], TODAY, weeks=t["weeks"], ignore_departures=True,
                            absence_scale=BUSY_SEASON_ABSENCE_SCALE)
    for o0, o1 in zip(calm["options"], busy["options"]):
        assert o1["p_any_uncovered"] >= o0["p_any_uncovered"], o0["id"]
    assert busy["assumptions"]["unplanned_absence_per_month"] > calm["assumptions"]["unplanned_absence_per_month"]

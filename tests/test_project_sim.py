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

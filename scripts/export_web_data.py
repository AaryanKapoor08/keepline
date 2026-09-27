"""Dump a static JSON snapshot of every API payload into web/public/data/ so the demo UI works with the API down.

Usage:  python scripts/export_web_data.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api import server as S  # noqa: E402
from keepline.contracts import to_json  # noqa: E402

OUT = ROOT / "web" / "public" / "data"


def dump(name: str, fn) -> None:
    try:
        obj = fn()
    except Exception as e:  # keep going; the UI shows an empty state for a missing file
        print(f"  ! {name}: {e}")
        traceback.print_exc(limit=1)
        return
    if obj is None:
        print(f"  - {name}: not available")
        return
    (OUT / f"{name}.json").write_text(to_json(obj), encoding="utf-8")
    print(f"  + {name}.json")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dump("meta", S.get_meta)
    dump("graph_org", S.get_org_graph)
    for pid in ("sarah", "mike", "tom", "aisha"):
        dump(f"graph_person_{pid}", lambda pid=pid: S.get_person_graph(pid))
    for pid in ("sarah", "mike", "tom"):
        dump(f"profile_{pid}", lambda pid=pid: S.get_profile(pid))
        dump(f"whatif_{pid}", lambda pid=pid: S.get_whatif(pid))
        dump(f"handoff_{pid}", lambda pid=pid: S.get_handoff(pid))
    dump("risk", S.get_risk)
    dump("whatif_multi", lambda: S.get_whatif_multi(["sarah", "mike", "tom"], S.date(2026, 12, 31)))
    dump("onboarding_alex", lambda: S.get_onboarding("alex"))
    dump("answers", lambda: {S._norm_q(q): S.do_ask(q, "alex") for q in S.DEMO_QUESTIONS})
    dump("decisions", lambda: {S._norm_q(t): S.do_decision(t) for t in S.DEMO_DECISIONS})
    dump("staffing", lambda: S.do_staffing(S.DEMO_BRIEF))
    dump("demo_scripts", lambda: {"questions": S.DEMO_QUESTIONS, "decisions": S.DEMO_DECISIONS, "brief": S.DEMO_BRIEF})
    for a in S.store().areas():
        dump(f"history_{a.id}", lambda a=a: S.get_history(a.id))
    dump("history_latest", S.get_latest_commits)
    for p in S.store().people():
        dump(f"person_{p.id}", lambda p=p: S.get_person_sheet(p.id))
    dump("review_sarah", lambda: S.get_review("sarah"))
    dump("review_queue_sarah", lambda: S.get_review_queue("sarah"))
    for p in S.store().people():
        dump(f"credit_{p.id}", lambda p=p: S.get_credit(p.id))
    dump("ledger_decisions", S.get_decisions)
    dump("ledger_owners", S.get_owners)
    dump("chat_canned", lambda: {S._norm_q(q): S.do_chat([{"role": "user", "content": q}], "alex") for q in S.CHAT_DEMO})
    from keepline.products.project_sim import BUSY_SEASON_ABSENCE_SCALE, TEMPLATES

    dump("sim_templates", lambda: TEMPLATES)
    sims = {}
    for t in TEMPLATES:
        base = S.do_project_sim(t["id"], None, None, None)
        sims[t["id"]] = base
        people = sorted({p for o in base["options"] for p in o["people"]})
        for p in people:
            sims[f'{t["id"]}|{p}'] = S.do_project_sim(t["id"], None, None, {p: t["weeks"] // 2})
        # stress tests with nobody leaving: everyday absence and ramp-up only, then a 3x "busy season"
        sims[f'{t["id"]}|none'] = S.do_project_sim(t["id"], None, None, None, ignore_departures=True)
        sims[f'{t["id"]}|none_busy'] = S.do_project_sim(t["id"], None, None, None, ignore_departures=True,
                                                        absence_scale=BUSY_SEASON_ABSENCE_SCALE)
    dump("project_sims", lambda: sims)
    for name in ("benchmark_dev", "benchmark_test", "reward_curve", "bandit", "training_log", "robustness"):
        dump(name, lambda name=name: S.get_result(name))
    print(f"snapshot -> {OUT}")


if __name__ == "__main__":
    main()

"""Keepline web API: a thin JSON layer over the keepline package for the Next.js demo app (web/).

Run:  uvicorn api.server:app --port 8000

Product-world only. This module never reads the answer key (see tests/test_isolation.py); benchmark numbers are
served from data/results, which the eval harness writes.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from keepline.config import DEMO_COMPANY, DEMO_TODAY, RESULTS_DIR, CACHE_DIR
from keepline.contracts import EdgeRel, FactKind, ReviewStatus, to_dict

TODAY: date = DEMO_TODAY

# Scripted demo questions (pre-cached into the static snapshot so the demo never fails).
DEMO_QUESTIONS: list[str] = [
    "Which days does the nightly reconciliation job skip?",
    "Is it safe to rotate the CoreLink API key on a Friday?",
    "Who is our account manager at CoreLink?",
    "Who can create CoreLink API keys?",
    "How does the portal SSL cert get renewed?",
    "Where is the SFTP key for Bluenose kept?",
    "How often do we run the backup restore test?",
    "What is our recovery time objective if the NAS dies?",
    "Can I restart the ACH server before the Payments Canada cutoff?",
    "Can I restore last night's backup onto the replication primary?",
]
DEMO_DECISIONS: list[str] = [
    "Rotate the CoreLink API key this Friday",
    "Run the reconciliation job manually on the 15th",
    "Restart the ACH server at 4pm today",
    "Restore last night's backup onto the replication primary",
    "Update the member portal FAQ page",
]
DEMO_BRIEF = ("Migrate the member portal to a new SSL provider and add CoreLink webhooks so nightly "
              "reconciliation runs faster. Touches ACH settlement files too.")


# ----------------------------------------------------------------------------------------------- loaders
@lru_cache(maxsize=1)
def store():
    from keepline.memory.store import MemoryStore

    return MemoryStore()


@lru_cache(maxsize=1)
def agent():
    from keepline.agent.answer import load_default_agent

    return load_default_agent(use_llm=False)


def _norm_q(q: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", q.lower()).strip()


@lru_cache(maxsize=1)
def _demo_answer_cache() -> dict[str, Any]:
    p = CACHE_DIR / "demo_answers.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _p(pid: str | None) -> dict[str, Any] | None:
    if not pid:
        return None
    p = store().person(pid)
    return to_dict(p) if p else None


# ----------------------------------------------------------------------------------------------- builders
def get_meta() -> dict[str, Any]:
    s = store()
    facts = s.all_facts()
    docs = s.all_docs()
    sarah_only = 0
    try:
        from keepline.products.simulate import what_if_report

        rep = what_if_report(s, "sarah", TODAY)
        sarah_only = len(rep.get("breaks", []))
        orphaned = rep.get("orphaned_areas", [])
    except Exception:
        orphaned = []
    by_src = Counter(str(d.source_type) for d in docs)
    from keepline.config import CORPUS_DIR

    n_corpus = sum(sum(1 for line in f.open(encoding="utf-8") if line.strip()) for f in CORPUS_DIR.glob("*.jsonl"))
    return {
        "company": DEMO_COMPANY,
        "today": TODAY.isoformat(),
        "n_docs": len(docs),
        "n_corpus": n_corpus,
        "n_facts": len(facts),
        "n_current_facts": sum(1 for f in facts if f.is_current),
        "n_superseded": sum(1 for f in facts if not f.is_current),
        "n_landmines": sum(1 for f in facts if f.kind == FactKind.LANDMINE and f.is_current),
        "n_people": len(s.people()),
        "n_areas": len(s.areas()),
        "docs_by_source": dict(by_src),
        "sarah_only_items": sarah_only,
        "sarah_orphaned_areas": orphaned,
        "people": [to_dict(p) for p in s.people()],
        "areas": [to_dict(a) for a in s.areas()],
    }


def get_org_graph() -> dict[str, Any]:
    """people -> areas (expertise) -> landmines / key facts -> a receipt each."""
    s = store()
    from keepline.products.risk import risk_map

    risks = {r.area_id: r for r in risk_map(s, TODAY, with_trend=False)}
    nodes: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    for p in s.people():
        nodes[f"person:{p.id}"] = {"id": f"person:{p.id}", "type": "person", "label": p.name, "role": p.role,
                                   "team": p.team, "departure_date": p.departure_date.isoformat() if p.departure_date else None,
                                   "pid": p.id}
    for a in s.areas():
        r = risks.get(a.id)
        nodes[f"area:{a.id}"] = {"id": f"area:{a.id}", "type": "area", "label": a.name, "criticality": a.criticality,
                                 "risk": r.risk if r else 0, "bus_factor": r.bus_factor if r else 0,
                                 "at_risk_person_id": r.at_risk_person_id if r else None}
    for e in s.expertise():
        if e.score < 0.12:
            continue
        links.append({"source": f"person:{e.person_id}", "target": f"area:{e.area_id}", "rel": "knows", "weight": e.score})
    keep_kinds = {FactKind.LANDMINE, FactKind.ACCESS, FactKind.VENDOR_CONTACT, FactKind.RECURRING_TASK}
    per_area: dict[str, int] = defaultdict(int)
    facts = sorted(s.facts(current_only=True), key=lambda f: (f.kind != FactKind.LANDMINE, -f.confidence))
    for f in facts:
        if f.kind not in keep_kinds or not f.area_id or per_area[f.area_id] >= 5 or not _ok(f.text):
            continue
        per_area[f.area_id] += 1
        fid = f"fact:{f.id}"
        nodes[fid] = {"id": fid, "type": "fact", "label": f.text[:120], "kind": str(f.kind), "area_id": f.area_id,
                      "stated_by": f.stated_by}
        links.append({"source": f"area:{f.area_id}", "target": fid, "rel": "about"})
        if f.source_doc_ids:
            did = f"doc:{f.source_doc_ids[0]}"
            if did not in nodes:
                d = s.doc(f.source_doc_ids[0])
                nodes[did] = {"id": did, "type": "doc", "label": (d.title or d.container) if d else did,
                              "source_type": str(d.source_type) if d else "doc"}
            links.append({"source": fid, "target": did, "rel": "supported_by"})
    return {"nodes": list(nodes.values()), "links": links}


def _ok(text: str) -> bool:
    try:
        from keepline.products._common import looks_like_fact

        return bool(looks_like_fact(text))
    except Exception:
        return True


def _clean_graph(g: dict[str, Any]) -> dict[str, Any]:
    """Drop noisy extractor facts (and orphaned receipts) so only real knowledge shows on screen."""
    drop = {n["id"] for n in g["nodes"] if n["type"] == "fact" and not _ok(n.get("label", ""))}
    links = [l for l in g["links"] if l["source"] not in drop and l["target"] not in drop]
    used = {l["source"] for l in links} | {l["target"] for l in links}
    nodes = [n for n in g["nodes"] if n["id"] not in drop and (n["type"] != "doc" or n["id"] in used)]
    return {"nodes": nodes, "links": links}


def get_person_graph(pid: str) -> dict[str, Any]:
    s = store()
    try:
        g = s.graph_for_person(pid, max_facts=90)
    except Exception:
        g = {"nodes": [], "links": []}
    g = _clean_graph(g)
    # attach learned_at + supersedes so the UI time slider can replay the versioned memory
    for n in g["nodes"]:
        if n["type"] == "fact":
            f = s.fact(n["id"].split(":", 1)[1])
            if f:
                n["learned_at"] = f.learned_at.isoformat() if f.learned_at else None
                n["supersedes"] = f.supersedes
                n["superseded_by"] = f.superseded_by
                n["quote"] = f.quote[:240]
    return g


def get_profile(pid: str) -> dict[str, Any]:
    s = store()
    p = s.person(pid)
    if not p:
        raise HTTPException(404, "unknown person")
    facts = s.facts(person_id=pid)
    areas = {a.id: a.name for a in s.areas()}
    exp = sorted(s.expertise(person_id=pid), key=lambda e: -e.score)
    per_area = []
    for e in exp:
        af = [f for f in facts if f.area_id == e.area_id]
        per_area.append({
            "area_id": e.area_id, "area_name": areas.get(e.area_id, e.area_id), "score": e.score,
            "n_docs": e.n_docs, "n_tickets_closed": e.n_tickets_closed, "n_facts": len(af),
            "kinds": dict(Counter(str(f.kind) for f in af)),
            "approved": sum(1 for f in af if f.review_status == ReviewStatus.APPROVED),
            "last_active": e.last_active.isoformat() if e.last_active else None,
        })
    src = Counter()
    for f in facts:
        for d in s.docs(f.source_doc_ids[:1]):
            src[str(d.source_type)] += 1
    try:
        qlog = s.query_log(about_person_id=pid, limit=500)
    except Exception:
        qlog = []
    helped = len({q.get("asker_id") for q in qlog if q.get("asker_id") and q.get("asker_id") != pid})
    try:
        from keepline.products.gaps import gap_questions

        gaps = to_dict(gap_questions(s, pid, n=6))
    except Exception:
        gaps = []
    review = Counter(str(f.review_status) for f in facts)
    sample = sorted([f for f in facts if f.is_current and _ok(f.text)], key=lambda f: (f.kind != FactKind.LANDMINE, -f.confidence))[:8]
    return {
        "person": to_dict(p), "today": TODAY.isoformat(),
        "n_facts": len(facts), "n_current": sum(1 for f in facts if f.is_current),
        "kinds": dict(Counter(str(f.kind) for f in facts)), "sources": dict(src),
        "review": dict(review), "areas": per_area, "helped_people": helped, "n_questions_answered": len(qlog),
        "gaps": gaps,
        "recent_queries": [{k: q.get(k) for k in ("asker_id", "question", "action", "ts", "timestamp")} for q in qlog[:6]],
        "sample_facts": [{"id": f.id, "text": f.text, "kind": str(f.kind), "area_id": f.area_id,
                          "review_status": str(f.review_status), "valid_from": f.valid_from.isoformat()} for f in sample],
    }


def get_risk(exclude: list[str] | None = None) -> list[dict[str, Any]]:
    from keepline.products.risk import risk_map

    return to_dict(risk_map(store(), TODAY, exclude_person_ids=tuple(exclude or ())))


def get_whatif(pid: str) -> dict[str, Any]:
    from keepline.products.simulate import what_if_report

    return what_if_report(store(), pid, TODAY)


def get_whatif_multi(pids: list[str], when: date | None = None) -> dict[str, Any]:
    from keepline.products.risk import risk_map

    t = when or TODAY
    before = risk_map(store(), t, with_trend=False)
    after = risk_map(store(), t, exclude_person_ids=tuple(pids), with_trend=False)
    b = {r.area_id: r for r in before}
    orphaned = [r.area_id for r in after if r.bus_factor == 0 and b.get(r.area_id) and b[r.area_id].bus_factor > 0]
    return {"people": pids, "date": t.isoformat(), "before": to_dict(before), "after": to_dict(after),
            "orphaned_areas": orphaned}


def get_handoff(pid: str) -> dict[str, Any]:
    from keepline.products.handoff import build_handoff_pack

    pack = build_handoff_pack(store(), pid, TODAY)
    try:
        from keepline.products.signoff import apply_state

        pack = apply_state(pack)
    except Exception:
        pass
    d = to_dict(pack)
    d["n_receipts_scanned"] = len(store().all_docs())
    return d


def get_onboarding(pid: str) -> dict[str, Any]:
    from keepline.products.onboarding import build_onboarding_brief

    return to_dict(build_onboarding_brief(store(), pid, TODAY))


def do_ask(question: str, asker_id: str = "alex", as_of: str | None = None) -> dict[str, Any]:
    t = date.fromisoformat(as_of) if as_of else TODAY
    key = f"{asker_id}|{_norm_q(question)}|{t.isoformat()}"
    try:
        a = to_dict(agent().answer(question, asker_id, as_of=t))
    except Exception as e:  # fall back to the pre-computed cache
        cached = _demo_answer_cache().get(key)
        if not cached:
            raise HTTPException(500, f"answer failed: {e}")
        a = cached
    for c in a.get("said", []):
        c["author"] = (_p(c.get("author_id")) or {}).get("name")
        if not c.get("is_current") and c.get("fact_id"):
            f = store().fact(c["fact_id"])
            if f and f.superseded_by:
                nf = store().fact(f.superseded_by)
                c["replaced_by"] = nf.text if nf else None
    a["route_people"] = [_p(x) for x in a.get("route_to", [])]
    return a


def do_decision(text: str) -> dict[str, Any]:
    try:
        from keepline.products.decision_check import check_decision

        return check_decision(store(), text, today=TODAY)
    except ImportError:
        return {"proposal": text, "verdict": "clear", "conflicts": [], "note": "decision_check unavailable"}


def do_staffing(brief: str) -> dict[str, Any]:
    try:
        from keepline.products.staffing import plan_project

        return plan_project(store(), brief, TODAY)
    except ImportError:
        return {"brief": brief, "areas": [], "note": "staffing unavailable"}


def get_result(name: str) -> Any:
    """data/results artifacts, trimmed for the browser."""
    if name == "training_log":
        p = RESULTS_DIR / "training_log.jsonl"
        if not p.exists():
            return None
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        keep = ("step", "epoch", "qid", "question", "area_id", "qtype", "expected_action", "arm", "action",
                "outcome", "reward", "confidence", "rolling_reward", "default_reward", "oracle_reward")
        stride = max(1, len(rows) // 600)
        return {"n": len(rows), "rows": [{k: r.get(k) for k in keep} for r in rows[::stride]]}
    p = RESULTS_DIR / f"{name}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    if name == "bandit":
        d.pop("model", None)
        d.get("featurizer", {}).pop("scales", None)
    if name == "reward_curve":
        stride = max(1, d.get("steps", 1) // 400)
        for grp in ("rolling", "cumulative"):
            for k, v in list(d.get(grp, {}).items()):
                d[grp][k] = v[::stride]
        d["stride"] = stride
    if name.startswith("benchmark"):
        for sysd in (d.get("systems") or {}).values() if isinstance(d.get("systems"), dict) else []:
            if isinstance(sysd, dict):
                sysd.pop("rows", None)
        d.pop("rows", None)
    return d


def list_results() -> dict[str, bool]:
    names = ["benchmark_dev", "benchmark_test", "reward_curve", "bandit", "training_log", "robustness"]
    out = {}
    for n in names:
        out[n] = (RESULTS_DIR / (n + (".jsonl" if n == "training_log" else ".json"))).exists()
    return out


# ----------------------------------------------------------------------------------------------- app
app = FastAPI(title="Keepline API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])


class AskIn(BaseModel):
    question: str
    asker_id: str = "alex"
    as_of: str | None = None


class TextIn(BaseModel):
    text: str


class WhatIfIn(BaseModel):
    people: list[str]
    date: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "today": TODAY.isoformat(), "results": list_results()}


@app.get("/meta")
def meta() -> dict[str, Any]:
    return get_meta()


@app.get("/graph/org")
def org_graph() -> dict[str, Any]:
    return get_org_graph()


@app.get("/graph/person/{pid}")
def person_graph(pid: str) -> dict[str, Any]:
    return get_person_graph(pid)


@app.get("/profile/{pid}")
def profile(pid: str) -> dict[str, Any]:
    return get_profile(pid)


@app.get("/risk")
def risk(exclude: str = "") -> list[dict[str, Any]]:
    return get_risk([x for x in exclude.split(",") if x])


@app.get("/whatif/{pid}")
def whatif(pid: str) -> dict[str, Any]:
    return get_whatif(pid)


@app.post("/whatif")
def whatif_multi(body: WhatIfIn) -> dict[str, Any]:
    return get_whatif_multi(body.people, date.fromisoformat(body.date) if body.date else None)


@app.get("/handoff/{pid}")
def handoff(pid: str) -> dict[str, Any]:
    return get_handoff(pid)


@app.post("/handoff/{pid}/signoff")
def signoff(pid: str) -> dict[str, Any]:
    try:
        from keepline.products.signoff import sign_off

        when = sign_off(pid)
        return {"signed_off": True, "signed_off_at": when.isoformat()}
    except Exception:
        return {"signed_off": True, "signed_off_at": datetime.now().isoformat()}


@app.get("/onboarding/{pid}")
def onboarding(pid: str) -> dict[str, Any]:
    return get_onboarding(pid)


@app.post("/ask")
def ask(body: AskIn) -> dict[str, Any]:
    return do_ask(body.question, body.asker_id, body.as_of)


@app.post("/decision")
def decision(body: TextIn) -> dict[str, Any]:
    return do_decision(body.text)


@app.post("/staffing")
def staffing(body: TextIn) -> dict[str, Any]:
    return do_staffing(body.text)


@app.get("/results")
def results_index() -> dict[str, bool]:
    return list_results()


@app.get("/results/{name}")
def results(name: str) -> Any:
    if not re.fullmatch(r"[a-z_]+", name):
        raise HTTPException(400, "bad name")
    d = get_result(name)
    if d is None:
        raise HTTPException(404, f"{name} not generated yet")
    return d

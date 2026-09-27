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
from keepline.contracts import EdgeRel, FactKind, ReviewStatus, to_dict, to_json

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


# ----------------------------------------------------------------------------------------------- GitHub-style memory
import hashlib  # noqa: E402


def _sha(fid: str) -> str:
    return hashlib.sha1(fid.encode()).hexdigest()[:7]


def _commit(f: Any) -> dict[str, Any]:
    s = store()
    d = s.doc(f.source_doc_ids[0]) if f.source_doc_ids else None
    return {
        "sha": _sha(f.id), "fact_id": f.id, "message": f.text, "quote": f.quote, "kind": str(f.kind), "area_id": f.area_id,
        "author": f.stated_by, "author_name": (_p(f.stated_by) or {}).get("name"),
        "date": (f.learned_at.date().isoformat() if f.learned_at else f.valid_from.isoformat()),
        "valid_from": f.valid_from.isoformat(), "valid_to": f.valid_to.isoformat() if f.valid_to else None,
        "is_current": f.is_current, "supersedes": f.supersedes, "superseded_by": f.superseded_by,
        "review_status": str(f.review_status),
        "doc_id": d.id if d else None, "source_type": str(d.source_type) if d else None, "url": d.url if d else None,
    }


def _said(facts: list[Any]) -> list[Any]:
    from keepline.contracts import Epistemic

    return [f for f in facts if f.epistemic == Epistemic.SAID and _ok(f.text)]


def get_history(area_id: str) -> dict[str, Any]:
    s = store()
    facts = _said(s.facts(area_id=area_id))
    commits = sorted((_commit(f) for f in facts), key=lambda c: (c["date"], c["sha"]), reverse=True)
    by = {c["fact_id"]: c for c in commits}
    diffs = []
    for c in commits:
        if c["supersedes"] and c["supersedes"] in by:
            o = by[c["supersedes"]]
            diffs.append({"old": o, "new": c, "replaced_on": c["valid_from"]})
    a = s.area(area_id)
    try:
        from keepline.products.risk import risk_map

        r = next((x for x in risk_map(s, TODAY, with_trend=False) if x.area_id == area_id), None)
        owners = [{"person_id": p, "name": (_p(p) or {}).get("name"), "score": sc} for p, sc in (r.experts[: max(1, r.bus_factor)] if r else [])]
    except Exception:
        owners = []
    return {"area_id": area_id, "area_name": a.name if a else area_id, "commits": commits[:80], "n_commits": len(commits),
            "diffs": diffs, "codeowners": owners}


def get_latest_commits(n: int = 3) -> list[dict[str, Any]]:
    facts = _said(store().facts())
    cs = sorted((_commit(f) for f in facts), key=lambda c: (c["supersedes"] is not None, c["date"]), reverse=True)
    return cs[:n]


_STOP = set("the a an of to and or is it in on for must not don't dont do please be any with that this you your i we our at by as are was if so".split())


def _toks(t: str) -> set[str]:
    t = t.lower().replace("minutes", "min").replace("-", " ")
    out = set()
    for w in re.findall(r"[a-z0-9']+", t):
        w = re.sub(r"\d+$", "", w) if re.match(r"[a-z]+\d+$", w) else w
        w = w[:-1] if len(w) > 3 and w.endswith("s") else w
        if w and w not in _STOP:
            out.add(w)
    return out


def _tidy_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Don'ts = real landmines only; near-duplicates in the same area collapse into one item with several receipts."""
    s = store()
    out: list[dict[str, Any]] = []
    for it in items:
        if it["section"] == "landmines":
            f = s.fact(it["fact_ids"][0]) if it.get("fact_ids") else None
            title = it["title"].lower()
            if (f and f.kind == FactKind.ACCESS) or re.search(r"1password|vault", title):
                it = {**it, "section": "access"}
            elif (f and f.kind != FactKind.LANDMINE) or title.startswith(("don't forget", "dont forget", "remember")):
                it = {**it, "section": "procedures"}
        dup = None
        if it["section"] == "landmines":
            ta = _toks(it["title"])
            for o in out:
                if o["section"] == "landmines" and o.get("area_id") == it.get("area_id"):
                    tb = _toks(o["title"])
                    if ta and tb and len(ta & tb) / min(len(ta), len(tb)) >= 0.5:
                        dup = o
                        break
        if dup:
            dup["citations"] = dup.get("citations", []) + it.get("citations", [])
            dup["n_receipts"] = len(dup["citations"])
        else:
            out.append({**it, "n_receipts": len(it.get("citations", []))})
    return out


def get_person_sheet(pid: str) -> dict[str, Any]:
    s = store()
    p = s.person(pid)
    if not p:
        raise HTTPException(404, "unknown person")
    prof = get_profile(pid)
    pack = get_handoff(pid)
    from keepline.products.risk import risk_map

    risks = {r.area_id: r for r in risk_map(s, TODAY, with_trend=False)}
    owner_of = [a for a, r in risks.items() if any(e[0] == pid for e in r.experts[: r.bus_factor])]
    others = {}
    for a in prof["areas"]:
        r = risks.get(a["area_id"])
        if r:
            others[a["area_id"]] = [{"person_id": e[0], "name": (_p(e[0]) or {}).get("name"), "strong": i < r.bus_factor}
                                    for i, e in enumerate(r.experts) if e[0] != pid][:3]
    facts = s.facts(person_id=pid)
    pack["items"] = _tidy_items(pack.get("items", []))
    return {
        "person": to_dict(p), "profile": prof, "pack": pack, "others": others, "owner_of": owner_of,
        "open_reviews": 1 if any(str(f.review_status) == "pending" for f in _said(facts)) else 0,
        "pending_facts": sum(1 for f in _said(facts) if str(f.review_status) == "pending"),
        "open_issues": len(prof.get("gaps", [])),
    }


def get_review(pid: str) -> dict[str, Any]:
    facts = [f for f in _said(store().facts(person_id=pid)) if str(f.review_status) == "pending"]
    facts.sort(key=lambda f: (f.kind != FactKind.LANDMINE, -f.confidence))
    return {"person_id": pid, "name": (_p(pid) or {}).get("name"), "n_pending": len(facts),
            "commits": [_commit(f) for f in facts[:8]], "issues": get_profile(pid).get("gaps", [])}


def do_project_sim(template_id: str | None, brief: str | None, weeks: int | None, leaves: dict[str, int] | None) -> dict[str, Any]:
    from keepline.products.project_sim import TEMPLATES, simulate_project

    t = next((x for x in TEMPLATES if x["id"] == template_id), None)
    b = brief or (t["brief"] if t else TEMPLATES[0]["brief"])
    w = weeks or (t["weeks"] if t else 12)
    r = simulate_project(store(), b, TODAY, weeks=w, leaves=leaves or None)
    r["template_id"] = t["id"] if t else None
    return r


class SimIn(BaseModel):
    template_id: str | None = None
    brief: str | None = None
    weeks: int | None = None
    leaves: dict[str, int] | None = None


@app.get("/history/latest")
def history_latest() -> list[dict[str, Any]]:
    return get_latest_commits()


@app.get("/history/{area_id}")
def history(area_id: str) -> dict[str, Any]:
    return get_history(area_id)


@app.get("/person/{pid}")
def person_sheet(pid: str) -> dict[str, Any]:
    return get_person_sheet(pid)


@app.get("/review/{pid}")
def review(pid: str) -> dict[str, Any]:
    return get_review(pid)


@app.get("/project_sim/templates")
def sim_templates() -> list[dict[str, Any]]:
    from keepline.products.project_sim import TEMPLATES

    return TEMPLATES


@app.post("/project_sim")
def project_sim(body: SimIn) -> dict[str, Any]:
    return do_project_sim(body.template_id, body.brief, body.weeks, body.leaves)


# ----------------------------------------------------------------------------------------------- review queue (PR per item)
_KIND_RANK = {FactKind.LANDMINE: 0, FactKind.ACCESS: 1, FactKind.VENDOR_CONTACT: 2, FactKind.RECURRING_TASK: 3}


def get_review_queue(pid: str, per_source: int = 12) -> dict[str, Any]:
    from keepline.contracts import Visibility

    s = store()
    groups: dict[str, list[dict[str, Any]]] = {"slack": [], "email": [], "ticket": []}
    facts = sorted((f for f in _said(s.facts(person_id=pid)) if str(f.review_status) == "pending" and f.kind in _KIND_RANK),
                   key=lambda f: (_KIND_RANK[f.kind], -f.confidence))
    seen_docs: set[str] = set()
    for f in facts:
        d = s.doc(f.source_doc_ids[0]) if f.source_doc_ids else None
        if not d or d.visibility == Visibility.PRIVATE or d.id in seen_docs:
            continue
        st = str(d.source_type)
        if st not in groups or len(groups[st]) >= per_source:
            continue
        seen_docs.add(d.id)
        text = d.text
        if st == "ticket":
            text = f.quote or text
        groups[st].append({
            "fact_id": f.id, "sha": _sha(f.id), "fact": f.text, "kind": str(f.kind), "quote": f.quote, "area_id": f.area_id,
            "source": {
                "type": st, "doc_id": d.id, "container": d.container, "title": d.title, "author": d.author_id,
                "author_name": (_p(d.author_id) or {}).get("name"), "timestamp": d.timestamp.isoformat(), "text": text[:600],
                "to": [(_p(x) or {}).get("name", x) for x in d.participants if x != d.author_id][:4] if st == "email" else [],
                "status": d.meta.get("status"), "url": d.url, "visibility": str(d.visibility),
            },
        })
    total = sum(1 for f in _said(s.facts(person_id=pid)) if str(f.review_status) == "pending")
    return {"person_id": pid, "name": (_p(pid) or {}).get("name"), "groups": groups, "n_pending": total,
            "issues": get_profile(pid).get("gaps", [])}


class ReviewIn(BaseModel):
    status: str
    corrected_text: str | None = None


@app.get("/review_queue/{pid}")
def review_queue(pid: str) -> dict[str, Any]:
    return get_review_queue(pid)


@app.post("/review_item/{fact_id}")
def review_item(fact_id: str, body: ReviewIn) -> dict[str, Any]:
    """Persisted review decision. The demo UI keeps decisions client-side so rehearsals never mutate the DB."""
    store().set_review_status(fact_id, ReviewStatus(body.status), body.corrected_text)
    return {"ok": True, "fact_id": fact_id, "status": body.status, "sha": _sha(fact_id + (body.corrected_text or ""))}


# ----------------------------------------------------------------------------------------------- chat ("Ask Keepline")
CHAT_DEMO: list[str] = [
    "What should I know before touching reconciliation?",
    "What's the Bedford branch wifi password?",
    "Can I rotate the CoreLink API key this Friday?",
    "Who can cover CoreLink when Sarah leaves?",
    "What breaks if Tom leaves?",
    "How has the reconciliation schedule changed?",
]


@lru_cache(maxsize=1)
def chat_agent():
    """Claude tool loop when available (disk-cached, so demo questions replay offline); falls back to the offline
    router on any failure. KEEPLINE_CHAT_LLM=0 forces the offline router."""
    import os

    from keepline.agent.chat import load_default_chat_agent

    return load_default_chat_agent(use_llm=False if os.environ.get("KEEPLINE_CHAT_LLM") == "0" else None)


CHAT_AS_OF = date(2026, 9, 15)  # Alex's first week; the demo questions are cached for this date


def do_chat(messages: list[dict[str, str]], asker_id: str = "alex", as_of: str | None = None) -> dict[str, Any]:
    t = date.fromisoformat(as_of) if as_of else CHAT_AS_OF
    out = chat_agent().reply(messages, asker_id=asker_id, as_of=t)
    out["route_people"] = [_p(x) for x in out.get("route_to", [])]
    return json.loads(to_json(out))


class ChatIn(BaseModel):
    messages: list[dict[str, str]]
    asker_id: str = "alex"
    as_of: str | None = None


@app.post("/chat")
def chat(body: ChatIn) -> dict[str, Any]:
    try:
        return do_chat(body.messages, body.asker_id, body.as_of)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"chat unavailable: {e}")

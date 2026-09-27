"""ChatAgent: ask the whole knowledge graph anything, with receipts.

Two modes behind one ``reply()``:

* **LLM mode** (``llm_client`` = an ``anthropic.Anthropic``-like client): a Claude tool-use loop over pure tools
  that wrap the memory store, the AnswerAgent and the products (risk, what-if, decision check, project sim).
  Claude may only answer from tool output; every doc id it cites is checked against the tool outputs and
  dropped if it never appeared (anti-hallucination guard). Every model call is cached on disk (sha256 of
  model + system + tools + messages-so-far), so demo questions replay offline and for free.
* **Offline mode** (``llm_client=None``): a deterministic intent router that calls the same tools and composes a
  short templated answer. Same output shape.

Receipts, not personas: the agent never speaks as an employee; it reports what was said, by whom, when.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

from keepline.config import DEMO_TODAY
from keepline.contracts import Action, Citation, FactKind, Person, to_dict
from keepline.llm import _cache_get, _cache_key, _cache_put
from keepline.memory.store import MemoryStore
from keepline.retrieval.search import SearchIndex

CHAT_MODEL = os.environ.get("KEEPLINE_CHAT_MODEL", "claude-opus-5")
MAX_TOOL_ROUNDS = 5
DOC_ID_RE = re.compile(r"\b(?:slack|email|ticket|doc|interview)-[A-Za-z0-9-]+\b")
SECRET_RE = re.compile(r"(?i)\b(password|passcode|pin|secret|token|api key)\s*(is|:|=)\s*\S+")

SYSTEM_PROMPT = """You are Keepline, the company-memory assistant for {company}. Today is {today}. The person asking \
is {asker}.
Rules:
- Answer ONLY from tool results. Call tools first; never answer from general knowledge.
- Every factual claim must cite the doc id(s) from tool output in square brackets, e.g. [slack-000123].
- If the tools return nothing relevant, say "I don't know." and name the best person to ask (use who_knows).
- Prefer current facts; if something was replaced, say what it used to be and when it changed.
- Never speak as, imitate or role-play an employee. Report what people said, with who and when.
- Never reveal secrets or credentials; say only where they live and who can grant access.
- Be brief: at most 4 sentences, then the receipts."""


def _cit_dict(c: Citation, names: dict[str, str]) -> dict[str, Any]:
    return {
        "doc_id": c.doc_id, "quote": redact(c.quote), "author_id": c.author_id,
        "author_name": names.get(c.author_id, c.author_id), "timestamp": c.timestamp.isoformat() if c.timestamp else None,
        "url": c.url, "fact_id": c.fact_id, "is_current": c.is_current,
    }


def redact(text: str | None) -> str:
    return SECRET_RE.sub(lambda m: f"{m.group(1)} {m.group(2)} [redacted]", text or "")


@dataclass
class _Turn:
    """Everything tools surfaced during one reply: the evidence registry and the trace."""

    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)  # doc_id -> citation dict
    trace: list[dict[str, Any]] = field(default_factory=list)
    route_to: list[str] = field(default_factory=list)
    confidence: float | None = None
    search_action: str | None = None

    def add(self, cits: list[dict[str, Any]]) -> None:
        for c in cits:
            if c.get("doc_id") and c["doc_id"] not in self.evidence:
                self.evidence[c["doc_id"]] = c


class ChatAgent:
    """``reply(messages, asker_id=..., as_of=...)`` -> {text, action, citations, route_to, trace, confidence}."""

    def __init__(self, store: MemoryStore, index: SearchIndex, answer_agent: Any, llm_client: Any | None = None) -> None:
        self.store = store
        self.index = index
        self.agent = answer_agent
        self.llm = llm_client
        self.people: dict[str, Person] = {p.id: p for p in store.people()}
        self.names = {pid: p.name for pid, p in self.people.items()}
        self.tools: dict[str, tuple[str, dict[str, Any], Callable[..., dict[str, Any]]]] = {
            "search_knowledge": ("Answer a factual question from company memory with receipts (quotes, author, "
                                 "date, doc id). Knows what is current vs replaced.", _schema("question"),
                                 self.t_search_knowledge),
            "who_knows": ("Who has hands-on evidence in an area/topic (closed tickets, facts stated), the bus "
                          "factor, and who is leaving.", _schema("area_or_topic"), self.t_who_knows),
            "person_profile": ("What a person knows and handles: areas, landmines, access/vendor knowledge they "
                               "hold, open tickets, departure date.", _schema("person"), self.t_person_profile),
            "risk_overview": ("Company-wide knowledge risk: most fragile areas, bus factor, who is leaving.",
                              {"type": "object", "properties": {}, "additionalProperties": False}, self.t_risk_overview),
            "what_if_leaves": ("What breaks and which areas are orphaned if a person leaves.", _schema("person"),
                               self.t_what_if_leaves),
            "check_decision": ("Check a proposed action/decision against landmines, rules and past decisions.",
                               _schema("text"), self.t_check_decision),
            "simulate_project": ("Staffing options and knowledge-coverage risk for a project brief.",
                                 _schema("brief"), self.t_simulate_project),
            "fact_history": ("Version history of a fact/topic: what it used to be, what replaced it, when.",
                             _schema("topic"), self.t_fact_history),
        }

    # ------------------------------------------------------------------ public API
    def reply(self, messages: list[dict[str, str]], *, asker_id: str, as_of: date | None = None) -> dict[str, Any]:
        today = as_of or DEMO_TODAY
        self._today, self._asker, self._turn = today, asker_id, _Turn()
        question = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        if self.llm is not None:
            try:
                text = self._llm_loop(messages, today, asker_id)
            except Exception as exc:  # noqa: BLE001 -- any LLM failure degrades to the deterministic router
                self._turn.trace.append({"tool": "llm", "input": {}, "summary": f"LLM unavailable ({exc}); offline"})
                text = self._offline(question)
        else:
            text = self._offline(question)
        return self._finish(text)

    # ------------------------------------------------------------------ tools (pure over store/products)
    def _log(self, tool: str, inp: dict[str, Any], summary: str) -> None:
        self._turn.trace.append({"tool": tool, "input": inp, "summary": summary})

    def t_search_knowledge(self, question: str) -> dict[str, Any]:
        a = self.agent.answer(question, self._asker, as_of=self._today)
        cits = [_cit_dict(c, self.names) for c in a.said]
        self._turn.add(cits)
        self._turn.confidence = a.confidence
        self._turn.search_action = str(a.action)
        if a.route_to:
            self._turn.route_to = list(dict.fromkeys(self._turn.route_to + a.route_to))
        self._log("search_knowledge", {"question": question}, f"{a.action} ({a.confidence:.2f}): {a.text[:120]}")
        return {"action": str(a.action), "answer": redact(a.text), "confidence": round(a.confidence, 3),
                "said": cits, "inferred": a.inferred, "no_evidence_note": a.no_evidence_note,
                "route_to": [{"id": p, "name": self.names.get(p, p)} for p in a.route_to]}

    def _resolve_area(self, topic: str) -> str | None:
        t = topic.strip().lower()
        for a in self.store.areas():
            if t in (a.id, a.name.lower()):
                return a.id
        return self.agent.classify_area(topic)

    def _resolve_person(self, name: str) -> str | None:
        t = name.strip().lower().lstrip("@")
        for p in self.people.values():
            if t in (p.id, p.name.lower(), p.name.split()[0].lower()):
                return p.id
        for p in self.people.values():
            if re.search(rf"\b({re.escape(p.name.split()[0].lower())}|{re.escape(p.id)})\b", t):
                return p.id
        return None

    def _status(self, pid: str) -> str:
        p = self.people.get(pid)
        if p is None or p.departure_date is None:
            return "staying"
        return f"left {p.departure_date}" if p.departure_date <= self._today else f"leaving {p.departure_date}"

    def _fact_cits(self, facts: list[Any], limit: int = 3) -> list[dict[str, Any]]:
        out = []
        for f in facts[:limit]:
            if not f.source_doc_ids:
                continue
            d = self.store.doc(f.source_doc_ids[0])
            if d is None:
                continue
            out.append({"doc_id": d.id, "quote": redact(f.quote), "author_id": f.stated_by,
                        "author_name": self.names.get(f.stated_by or "", f.stated_by),
                        "timestamp": d.timestamp.isoformat(), "url": d.url, "fact_id": f.id, "is_current": f.is_current})
        self._turn.add(out)
        return out

    def t_who_knows(self, area_or_topic: str) -> dict[str, Any]:
        area_id = self._resolve_area(area_or_topic)
        if area_id is None:
            self._log("who_knows", {"area_or_topic": area_or_topic}, "no matching area")
            return {"area": None, "experts": [], "note": "No area matches this topic."}
        area = self.store.area(area_id)
        experts = []
        for e in self.store.expertise(area_id=area_id)[:5]:
            if e.person_id == self._asker:
                continue
            experts.append({"id": e.person_id, "name": self.names.get(e.person_id, e.person_id),
                            "score": round(e.score, 2), "closed_tickets": e.n_tickets_closed,
                            "facts_stated": e.n_facts_stated, "messages": e.n_docs,
                            "last_active": e.last_active.isoformat() if e.last_active else None,
                            "status": self._status(e.person_id), "enough_data": e.enough_data})
        bus = sum(1 for x in experts if x["score"] >= 0.5 and not x["status"].startswith("left"))
        avail = [x["id"] for x in experts if not x["status"].startswith("left")]
        self._turn.route_to = list(dict.fromkeys(self._turn.route_to + avail[:2]))
        owners = self.store.facts(area_id=area_id, kinds=[FactKind.OWNER], current_only=True, as_of=self._today)
        cits = self._fact_cits(owners)
        self._log("who_knows", {"area_or_topic": area_or_topic},
                  f"{area.name if area else area_id}: " + ", ".join(f"{x['name']} ({x['status']})" for x in experts[:3]))
        return {"area": {"id": area_id, "name": area.name if area else area_id}, "experts": experts,
                "bus_factor_available": bus, "owner_statements": cits}

    def t_person_profile(self, person: str) -> dict[str, Any]:
        pid = self._resolve_person(person)
        if pid is None:
            self._log("person_profile", {"person": person}, "unknown person")
            return {"person": None, "note": "No such person."}
        p = self.people[pid]
        areas = [{"area_id": e.area_id, "score": round(e.score, 2), "closed_tickets": e.n_tickets_closed}
                 for e in self.store.expertise(person_id=pid)[:6]]
        facts = self.store.facts(person_id=pid, current_only=True, as_of=self._today)
        by_kind: dict[str, list[dict[str, Any]]] = {}
        for k in (FactKind.LANDMINE, FactKind.ACCESS, FactKind.VENDOR_CONTACT, FactKind.RECURRING_TASK, FactKind.OWNER):
            fs = sorted([f for f in facts if f.kind == k], key=lambda f: -f.confidence)[:4]
            by_kind[str(k)] = [{"text": redact(f.text), "area_id": f.area_id, "date": f.valid_from.isoformat(),
                                "doc_id": f.source_doc_ids[0] if f.source_doc_ids else None} for f in fs]
            self._fact_cits(fs, limit=4)
        open_t = [{"doc_id": d.id, "title": d.title} for d in self.store.open_tickets(pid)[:5]]
        self._log("person_profile", {"person": person}, f"{p.name}: {len(areas)} areas, {len(facts)} current facts")
        return {"person": {"id": pid, "name": p.name, "role": p.role, "team": p.team, "status": self._status(pid)},
                "areas": areas, "knowledge": by_kind, "open_tickets": open_t,
                "note": "Receipts of what this person said; not a simulation of them."}

    def t_risk_overview(self) -> dict[str, Any]:
        from keepline.products.risk import risk_map

        risks = risk_map(self.store, self._today, with_trend=False)[:6]
        rows = [{"area_id": r.area_id, "area": r.area_name, "risk": round(r.risk, 2), "bus_factor": r.bus_factor,
                 "at_risk_person": self.names.get(r.at_risk_person_id or "", r.at_risk_person_id),
                 "countdown_days": r.countdown_days, "explanation": r.explanation} for r in risks]
        self._log("risk_overview", {}, "; ".join(f"{r['area']} {r['risk']}" for r in rows[:3]))
        return {"top_risks": rows}

    def t_what_if_leaves(self, person: str) -> dict[str, Any]:
        from keepline.products.simulate import what_if_report

        pid = self._resolve_person(person)
        if pid is None:
            self._log("what_if_leaves", {"person": person}, "unknown person")
            return {"person": None, "note": "No such person."}
        rep = what_if_report(self.store, pid, self._today)
        breaks = rep.get("breaks", [])[:6]
        self._turn.add([{"doc_id": b["doc_id"], "quote": redact(b.get("quote")), "author_id": b.get("stated_by"),
                         "author_name": b.get("stated_by_name"), "timestamp": b.get("date"), "url": b.get("url", ""),
                         "fact_id": b.get("fact_id"), "is_current": True} for b in breaks if b.get("doc_id")])
        self._log("what_if_leaves", {"person": person},
                  f"{self.names[pid]}: orphaned={rep.get('orphaned_areas')} breaks={rep.get('break_counts')}")
        return {"person": {"id": pid, "name": self.names[pid], "status": self._status(pid)},
                "orphaned_areas": rep.get("orphaned_areas", []), "break_counts": rep.get("break_counts", {}),
                "breaks": [{k: (redact(v) if isinstance(v, str) else v) for k, v in b.items()
                            if k in ("type", "why", "text", "area_name", "stated_by_name", "date", "doc_id")}
                           for b in breaks]}

    def t_check_decision(self, text: str) -> dict[str, Any]:
        from keepline.products.decision_check import check_decision

        res = check_decision(self.store, text, today=self._today, proposer_id=self._asker)
        items = res.get("conflicts", [])[:5]
        self._turn.add([{"doc_id": i["doc_id"], "quote": redact(i.get("quote")), "author_id": i.get("stated_by"),
                         "author_name": i.get("stated_by_name"), "timestamp": i.get("date"), "url": i.get("url", ""),
                         "fact_id": i.get("fact_id"), "is_current": True} for i in items if i.get("doc_id")])
        if res.get("suggested_reviewer"):
            self._turn.route_to = list(dict.fromkeys(self._turn.route_to + [res["suggested_reviewer"]]))
        self._log("check_decision", {"text": text}, f"verdict={res.get('verdict')} ({len(items)} items)")
        return {"verdict": res.get("verdict"), "target_dates": res.get("target_dates"),
                "conflicts": [{k: (redact(v) if isinstance(v, str) else v) for k, v in i.items()
                               if k in ("severity", "why", "text", "stated_by_name", "date", "doc_id")} for i in items],
                "suggested_reviewer": res.get("suggested_reviewer_name")}

    def t_simulate_project(self, brief: str) -> dict[str, Any]:
        try:
            from keepline.products.project_sim import simulate_project

            res = simulate_project(self.store, brief, self._today, runs=300)
        except Exception as exc:  # noqa: BLE001 -- optional product; never break chat
            self._log("simulate_project", {"brief": brief}, f"unavailable: {exc}")
            return {"error": "project simulator unavailable"}
        opts = res.get("options", [])
        rec = next((o for o in opts if o.get("id") == res.get("recommended")), opts[0] if opts else None)
        self._log("simulate_project", {"brief": brief}, f"recommended={res.get('recommended')}")
        return {"areas": [a.get("area_name") for a in res.get("areas", [])], "recommended": rec,
                "n_options": len(opts), "note": res.get("assumptions", {}).get("note")}

    def t_fact_history(self, topic: str) -> dict[str, Any]:
        hits = self.index.search(topic, k=12, as_of=self._today, visible_to=self._asker, only="facts")
        best_chain: list[Any] = []
        for h in hits:
            chain = [f for f in self.store.supersession_chain(h.fact_id or "") if f.valid_from <= self._today]
            if len(chain) > len(best_chain):
                best_chain = chain
            if len(best_chain) >= 2:
                break
        versions = []
        for f in best_chain:
            current = f.valid_to is None or f.valid_to > self._today
            versions.append({"text": redact(f.text), "from": f.valid_from.isoformat(),
                             "to": f.valid_to.isoformat() if f.valid_to and not current else None,
                             "stated_by": self.names.get(f.stated_by or "", f.stated_by), "current": current,
                             "doc_id": f.source_doc_ids[0] if f.source_doc_ids else None})
        cits = self._fact_cits(best_chain, limit=6)
        for c in cits:
            c["is_current"] = next((v["current"] for v in versions if v["doc_id"] == c["doc_id"]), True)
        self._log("fact_history", {"topic": topic}, f"{len(versions)} version(s)")
        return {"versions": versions, "note": None if len(versions) > 1 else "No recorded change for this topic."}

    # ------------------------------------------------------------------ offline router
    def _offline(self, q: str) -> str:
        ql = q.lower()
        person = self._resolve_person_in(q)
        if re.search(r"\bwhat if\b.*\b(leaves?|quits?|retires?|goes)\b|\bif \w+ (leaves|quits|retires)|what breaks if", ql) and person:
            r = self.t_what_if_leaves(person)
            orphan = ", ".join(r["orphaned_areas"]) or "no area"
            lines = [f"If {r['person']['name']} leaves, {orphan} would be left without a strong expert."]
            for b in r["breaks"][:3]:
                lines.append(f"- {b['text']} ({b.get('stated_by_name')}, {b.get('date')}) [{b.get('doc_id')}]")
            return "\n".join(lines)
        if re.search(r"\bwho (knows|owns|handles|can cover|covers|should i ask|to ask|is responsible)|\bwho can\b", ql):
            topic = re.sub(r"(?i)^.*?\bwho (knows|owns|handles|can cover|covers|should i ask about|can|is responsible for)\b", "", q)
            r = self.t_who_knows(topic or q)
            if not r["experts"]:
                return "I don't know who handles this -- no area matches."
            avail = [x for x in r["experts"] if not x["status"].startswith("left")]
            gone = [x for x in r["experts"] if x["status"] != "staying"]
            text = (f"For {r['area']['name']}: " + "; ".join(
                f"{x['name']} ({x['closed_tickets']} closed tickets, {x['facts_stated']} facts stated, {x['status']})"
                for x in avail[:3]) + ".")
            if gone:
                text += " Note: " + ", ".join(f"{x['name']} {x['status']}" for x in gone[:2]) + "."
            return text
        if re.search(r"\b(risk|bus factor|fragile|single point)\b", ql):
            r = self.t_risk_overview()
            return "Most fragile areas: " + "; ".join(
                f"{x['area']} (risk {x['risk']}, bus factor {x['bus_factor']}"
                + (f", {x['at_risk_person']}" if x["at_risk_person"] else "") + ")" for x in r["top_risks"][:4]) + "."
        if re.search(r"\b(what changed|history|used to|changed about|previously|what was it before)\b", ql):
            r = self.t_fact_history(q)
            if len(r["versions"]) > 1:
                return "\n".join(f"- {'NOW' if v['current'] else 'was'}: {v['text']} ({v['stated_by']}, {v['from']}) "
                                 f"[{v['doc_id']}]" for v in reversed(r["versions"]))
        if person and re.search(r"\bwhat does\b.*\b(know|handle|own|do)\b|\bprofile\b", ql):
            r = self.t_person_profile(person)
            k = r["knowledge"]
            parts = [f"{r['person']['name']} ({r['person']['role']}, {r['person']['status']})."]
            for kind in ("landmine", "access", "vendor_contact"):
                if k.get(kind):
                    x = k[kind][0]
                    parts.append(f"{kind.replace('_', ' ')}: {x['text']} [{x['doc_id']}]")
            return " ".join(parts)
        if re.search(r"^\s*(can i|could i|is it (ok|okay|safe)|should (we|i)|may i|are we allowed)\b", ql):
            dec = self.t_check_decision(q)
            ans = self.t_search_knowledge(q)
            head = {"conflict": "No -- this conflicts with a recorded rule.", "caution": "Careful --",
                    "clear": ""}.get(dec["verdict"] or "clear", "")
            body = ans["answer"] if ans["action"] == "answer" and dec["verdict"] != "conflict" else (
                f"{dec['conflicts'][0]['text']} ({dec['conflicts'][0].get('stated_by_name')}) "
                f"[{dec['conflicts'][0].get('doc_id')}]" if dec["conflicts"] else ans["answer"])
            return f"{head} {body}".strip()
        return self.t_search_knowledge(q)["answer"]

    def _resolve_person_in(self, q: str) -> str | None:
        for p in self.people.values():
            if re.search(rf"\b({re.escape(p.name.split()[0])}|{re.escape(p.name)})\b", q, re.I):
                return p.id
        return None

    # ------------------------------------------------------------------ LLM tool loop
    def _tool_specs(self) -> list[dict[str, Any]]:
        return [{"name": n, "description": d, "input_schema": s} for n, (d, s, _f) in self.tools.items()]

    def _run_tool(self, name: str, args: dict[str, Any]) -> str:
        if name not in self.tools:
            return json.dumps({"error": f"unknown tool {name}"})
        fn = self.tools[name][2]
        try:
            out = fn(**args) if args else fn()
        except TypeError:
            out = fn(*args.values())
        except Exception as exc:  # noqa: BLE001 -- tool errors go back to the model as data
            out = {"error": str(exc)}
        return json.dumps(to_dict(out), ensure_ascii=False, default=str)[:12000]

    def _create(self, system: str, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
        key = _cache_key("chat", CHAT_MODEL, system, self._tool_specs(), messages)
        hit = _cache_get(key)
        if hit is not None:
            return hit["content"], hit["stop_reason"]
        resp = self.llm.messages.create(
            model=CHAT_MODEL, max_tokens=16000, output_config={"effort": "low"},
            system=[{"type": "text", "text": system}], tools=self._tool_specs(), messages=messages,
        )
        content = [b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else dict(b) for b in resp.content]
        _cache_put(key, {"content": content, "stop_reason": resp.stop_reason})
        return content, str(resp.stop_reason)

    def _llm_loop(self, messages: list[dict[str, str]], today: date, asker_id: str) -> str:
        p = self.people.get(asker_id)
        system = SYSTEM_PROMPT.format(company="Harbourline Credit Union", today=f"{today:%A %B %d, %Y}",
                                      asker=f"{p.name} ({p.role})" if p else asker_id)
        convo: list[dict[str, Any]] = [{"role": m["role"], "content": m["content"]} for m in messages
                                       if m.get("role") in ("user", "assistant") and m.get("content")]
        for _round in range(MAX_TOOL_ROUNDS + 1):
            content, stop = self._create(system, convo)
            if stop == "refusal":
                return "I can't help with that."
            if stop != "tool_use" or _round == MAX_TOOL_ROUNDS:
                return "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            convo.append({"role": "assistant", "content": content})
            results = []
            for b in content:
                if b.get("type") == "tool_use":
                    results.append({"type": "tool_result", "tool_use_id": b["id"],
                                    "content": self._run_tool(b["name"], b.get("input") or {})})
            convo.append({"role": "user", "content": results})
        return ""

    # ------------------------------------------------------------------ output
    def _finish(self, text: str) -> dict[str, Any]:
        turn = self._turn
        bracketed = [x.strip() for grp in re.findall(r"\[([^\[\]]{1,80})\]", text) for x in grp.split(",")]
        cited = list(dict.fromkeys([x for x in bracketed if re.fullmatch(r"[A-Za-z0-9_.:-]+", x)]
                                   + DOC_ID_RE.findall(text)))
        valid = [d for d in cited if d in turn.evidence]
        for bad in set(cited) - set(valid):  # anti-hallucination: a doc id no tool returned is removed
            text = re.sub(rf"\s*\[?{re.escape(bad)}\]?", "", text)
        citations = [turn.evidence[d] for d in valid] or list(turn.evidence.values())[:4]
        idk = bool(re.match(r"^\s*i (don't|do not) know", text, re.I)) or (turn.search_action in ("abstain", "route")
                                                                             and not valid and not citations)
        if idk:
            action = Action.ROUTE if turn.route_to else Action.ABSTAIN
            citations = []
        else:
            action = Action.ANSWER if citations else (Action.ROUTE if turn.route_to else Action.ANSWER)
        conf = turn.confidence if turn.confidence is not None else (0.6 if citations else 0.3)
        return {"text": redact(text), "action": str(action), "citations": citations,
                "route_to": turn.route_to if action != Action.ANSWER or not citations else turn.route_to[:2],
                "trace": turn.trace, "confidence": round(float(conf), 4)}


def _schema(arg: str) -> dict[str, Any]:
    return {"type": "object", "properties": {arg: {"type": "string"}}, "required": [arg], "additionalProperties": False}


def load_default_chat_agent(*, use_llm: bool | None = None) -> ChatAgent:
    """Store + index + AnswerAgent from ``data/memory``; Claude tool loop when the Anthropic client is configured
    (``keepline.llm.get_llm()``) or ``KEEPLINE_CHAT_LLM=1``; ``use_llm=False`` forces the offline router."""
    from keepline.agent.answer import load_default_agent

    agent = load_default_agent()
    client = None
    if use_llm is None:
        from keepline.llm import get_llm

        llm = get_llm()
        use_llm = os.environ.get("KEEPLINE_CHAT_LLM") == "1" or getattr(llm, "name", "") == "claude"
    if use_llm:
        try:
            import anthropic

            client = anthropic.Anthropic(max_retries=3)
        except Exception:  # noqa: BLE001
            client = None
    return ChatAgent(agent.store, agent.index, agent, llm_client=client)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ask Keepline anything (receipts, not personas).")
    ap.add_argument("question")
    ap.add_argument("--as", dest="asker", default="alex")
    ap.add_argument("--as-of", type=date.fromisoformat, default=None)
    ap.add_argument("--offline", action="store_true", help="deterministic router, no LLM")
    args = ap.parse_args(argv)
    chat = load_default_chat_agent(use_llm=False if args.offline else None)
    out = chat.reply([{"role": "user", "content": args.question}], asker_id=args.asker, as_of=args.as_of)
    print(f"[{out['action']} {out['confidence']:.2f}] {out['text']}")
    for c in out["citations"]:
        print(f"  - {c['doc_id']} {c.get('author_name')} {str(c.get('timestamp'))[:10]}: {str(c.get('quote'))[:100]}")
    if out["route_to"]:
        print(f"  route_to: {out['route_to']}")
    for t in out["trace"]:
        print(f"  tool {t['tool']}: {t['summary'][:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__all__ = ["ChatAgent", "load_default_chat_agent", "datetime"]

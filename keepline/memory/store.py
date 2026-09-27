"""MemoryStore: the read/write API over the SQLite mirror of Keepline's versioned knowledge graph.

Products, the answer agent and the app talk to memory only through this class, so the backing store can be
swapped for Snowflake (same schema, see schema.sql) without touching callers. Rows are converted back into the
shared ``keepline.contracts`` dataclasses on the way out.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from keepline.config import MEMORY_DB
from keepline.contracts import (
    Answer,
    Area,
    Edge,
    EdgeRel,
    Epistemic,
    Expertise,
    Fact,
    FactKind,
    Person,
    ReviewStatus,
    SourceDoc,
    SourceType,
    Verification,
    Visibility,
    from_dict,
    to_json,
)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
CLOSED_TICKET_STATUSES = frozenset({"closed", "resolved", "done", "fixed", "complete", "completed", "cancelled"})


# ------------------------------------------------------------------------------------------------ helpers


def _iso(v: date | datetime | None) -> str | None:
    return v.isoformat() if v is not None else None


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v[:10]) if v else None


def _dt(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


def _j(v: Any) -> str:
    return to_json(v)


def _unj(v: str | None, default: Any) -> Any:
    return json.loads(v) if v else default


def ticket_fields(meta: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Pull (status, assignee, closed_at) out of free-form ticket meta, tolerating common key spellings."""
    status = meta.get("status") or meta.get("state")
    assignee = meta.get("assignee_id") or meta.get("assignee") or meta.get("assigned_to")
    closed = meta.get("closed_at") or meta.get("resolved_at") or meta.get("closed")
    return (str(status).lower() if status else None, str(assignee) if assignee else None, str(closed) if closed else None)


def fact_to_row(f: Fact, participants: Sequence[str] = (), corrected_text: str | None = None) -> dict[str, Any]:
    return {
        "id": f.id,
        "text": f.text,
        "kind": str(f.kind),
        "area_id": f.area_id,
        "stated_by": f.stated_by,
        "source_doc_ids_json": _j(list(f.source_doc_ids)),
        "quote": f.quote,
        "valid_from": _iso(f.valid_from),
        "valid_to": _iso(f.valid_to),
        "learned_at": _iso(f.learned_at),
        "supersedes": f.supersedes,
        "superseded_by": f.superseded_by,
        "epistemic": str(f.epistemic),
        "verification": str(f.verification),
        "visibility": str(f.visibility),
        "participants_json": _j(list(participants)),
        "confidence": float(f.confidence),
        "review_status": str(f.review_status),
        "corrected_text": corrected_text,
        "subject": f.subject,
        "extractor": f.extractor,
    }


def row_to_fact(r: sqlite3.Row) -> Fact:
    text = r["corrected_text"] or r["text"]  # a person's correction wins over the extractor
    return Fact(
        id=r["id"],
        text=text,
        kind=FactKind(r["kind"]),
        area_id=r["area_id"],
        stated_by=r["stated_by"],
        source_doc_ids=_unj(r["source_doc_ids_json"], []),
        quote=r["quote"] or "",
        valid_from=_d(r["valid_from"]) or date.min,
        valid_to=_d(r["valid_to"]),
        learned_at=_dt(r["learned_at"]),
        supersedes=r["supersedes"],
        superseded_by=r["superseded_by"],
        epistemic=Epistemic(r["epistemic"] or "said"),
        verification=Verification(r["verification"] or "unverified"),
        visibility=Visibility(r["visibility"] or "public"),
        confidence=float(r["confidence"] or 0.0),
        review_status=ReviewStatus(r["review_status"] or "pending"),
        subject=r["subject"],
        extractor=r["extractor"] or "heuristic",
    )


def doc_to_row(d: SourceDoc) -> dict[str, Any]:
    status, assignee, closed = ticket_fields(d.meta) if d.source_type == SourceType.TICKET else (None, None, None)
    return {
        "id": d.id,
        "source_type": str(d.source_type),
        "author_id": d.author_id,
        "ts": _iso(d.timestamp),
        "text": d.text,
        "container": d.container,
        "thread_id": d.thread_id,
        "title": d.title,
        "participants_json": _j(list(d.participants)),
        "visibility": str(d.visibility),
        "url": d.url,
        "meta_json": _j(d.meta),
        "ticket_status": status,
        "ticket_assignee": assignee,
        "ticket_closed_at": closed,
    }


def row_to_doc(r: sqlite3.Row) -> SourceDoc:
    return SourceDoc(
        id=r["id"],
        source_type=SourceType(r["source_type"]),
        author_id=r["author_id"],
        timestamp=datetime.fromisoformat(r["ts"]),
        text=r["text"] or "",
        container=r["container"] or "",
        thread_id=r["thread_id"],
        title=r["title"],
        participants=_unj(r["participants_json"], []),
        visibility=Visibility(r["visibility"] or "public"),
        url=r["url"] or "",
        meta=_unj(r["meta_json"], {}),
    )


def _row_to_expertise(r: sqlite3.Row) -> Expertise:
    return Expertise(
        person_id=r["person_id"],
        area_id=r["area_id"],
        score=float(r["score"] or 0.0),
        n_docs=int(r["n_docs"] or 0),
        n_tickets_closed=int(r["n_tickets_closed"] or 0),
        n_facts_stated=int(r["n_facts_stated"] or 0),
        last_active=_d(r["last_active"]),
        confirmed_by_person=bool(r["confirmed_by_person"]),
        enough_data=bool(r["enough_data"]),
    )


# ------------------------------------------------------------------------------------------------ store


class MemoryStore:
    """Read/write access to ``keepline.db``. Cheap to construct; one sqlite connection per instance."""

    def __init__(self, db_path: Path | str = MEMORY_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self._people: dict[str, Person] | None = None
        self._areas: dict[str, Area] | None = None

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ org
    def people(self) -> list[Person]:
        return list(self._people_map().values())

    def person(self, id: str) -> Person | None:
        return self._people_map().get(id)

    def areas(self) -> list[Area]:
        return list(self._areas_map().values())

    def area(self, id: str) -> Area | None:
        return self._areas_map().get(id)

    def _people_map(self) -> dict[str, Person]:
        if self._people is None:
            rows = self.conn.execute("SELECT * FROM people ORDER BY id").fetchall()
            self._people = {r["id"]: from_dict(Person, dict(r)) for r in rows}
        return self._people

    def _areas_map(self) -> dict[str, Area]:
        if self._areas is None:
            rows = self.conn.execute("SELECT * FROM areas ORDER BY id").fetchall()
            self._areas = {
                r["id"]: Area(
                    id=r["id"],
                    name=r["name"],
                    description=r["description"] or "",
                    keywords=_unj(r["keywords_json"], []),
                    systems=_unj(r["systems_json"], []),
                    criticality=int(r["criticality"] or 2),
                )
                for r in rows
            }
        return self._areas

    # ------------------------------------------------------------------ documents
    def doc(self, id: str) -> SourceDoc | None:
        r = self.conn.execute("SELECT * FROM documents WHERE id = ?", (id,)).fetchone()
        return row_to_doc(r) if r else None

    def docs(self, ids: Iterable[str]) -> list[SourceDoc]:
        ids = list(dict.fromkeys(ids))
        if not ids:
            return []
        out: dict[str, SourceDoc] = {}
        for chunk in _chunks(ids, 500):
            q = f"SELECT * FROM documents WHERE id IN ({','.join('?' * len(chunk))})"
            out.update({r["id"]: row_to_doc(r) for r in self.conn.execute(q, chunk)})
        return [out[i] for i in ids if i in out]

    def all_docs(self) -> list[SourceDoc]:
        return [row_to_doc(r) for r in self.conn.execute("SELECT * FROM documents ORDER BY ts, id")]

    def docs_by(self, person_id: str, *, since: date | datetime | None = None) -> list[SourceDoc]:
        q, args = "SELECT * FROM documents WHERE author_id = ?", [person_id]
        if since is not None:
            q += " AND ts >= ?"
            args.append(_iso(since))
        return [row_to_doc(r) for r in self.conn.execute(q + " ORDER BY ts, id", args)]

    def open_tickets(self, person_id: str) -> list[SourceDoc]:
        """Tickets assigned to the person that are not closed -- 'unresolved work' in a handoff pack."""
        rows = self.conn.execute(
            "SELECT * FROM documents WHERE source_type = 'ticket' AND ticket_assignee = ? ORDER BY ts, id",
            (person_id,),
        ).fetchall()
        latest: dict[str, sqlite3.Row] = {}
        for r in rows:  # a ticket may appear as several docs (comments); keep the newest state per ticket
            latest[r["thread_id"] or r["container"] or r["id"]] = r
        return [
            row_to_doc(r)
            for r in latest.values()
            if (r["ticket_status"] or "open") not in CLOSED_TICKET_STATUSES and not r["ticket_closed_at"]
        ]

    def doc_area_ids(self, doc_id: str) -> list[str]:
        rows = self.conn.execute("SELECT area_id FROM doc_areas WHERE doc_id = ? ORDER BY score DESC", (doc_id,))
        return [r["area_id"] for r in rows]

    def doc_area_map(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for r in self.conn.execute("SELECT doc_id, area_id FROM doc_areas ORDER BY doc_id, score DESC"):
            out[r["doc_id"]].append(r["area_id"])
        return dict(out)

    def area_doc_counts_by_month(self, area_id: str) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT substr(d.ts, 1, 7) AS month, COUNT(*) AS n FROM documents d "
            "JOIN doc_areas a ON a.doc_id = d.id WHERE a.area_id = ? GROUP BY substr(d.ts, 1, 7) ORDER BY month",
            (area_id,),
        )
        return {r["month"]: int(r["n"]) for r in rows}

    # ------------------------------------------------------------------ facts
    def facts(
        self,
        *,
        area_id: str | None = None,
        person_id: str | None = None,
        kinds: Iterable[FactKind | str] | None = None,
        current_only: bool = False,
        as_of: date | None = None,
        include_private_for: str | None = None,
    ) -> list[Fact]:
        """Facts filtered by area / speaker / kind / time.

        ``as_of`` returns the world as Keepline knew it on that date: learned by then and valid then (a fact
        superseded *after* ``as_of`` is still current at ``as_of``). ``current_only`` without ``as_of`` means
        "current today". PRIVATE facts are returned only to their participants via ``include_private_for``.
        """
        q, args = "SELECT * FROM facts WHERE 1=1", []  # type: ignore[var-annotated]
        if area_id is not None:
            q += " AND area_id = ?"
            args.append(area_id)
        if person_id is not None:
            q += " AND stated_by = ?"
            args.append(person_id)
        if kinds is not None:
            ks = [str(k) for k in kinds]
            q += f" AND kind IN ({','.join('?' * len(ks))})" if ks else " AND 0"
            args.extend(ks)
        if as_of is not None:
            q += " AND valid_from <= ? AND substr(COALESCE(learned_at, valid_from), 1, 10) <= ?"
            args.extend([as_of.isoformat(), as_of.isoformat()])
            if current_only:
                q += " AND (valid_to IS NULL OR valid_to > ?)"
                args.append(as_of.isoformat())
        elif current_only:
            q += " AND valid_to IS NULL AND superseded_by IS NULL"
        q += " AND COALESCE(review_status, 'pending') != 'rejected'"
        rows = self.conn.execute(q + " ORDER BY valid_from, id", args).fetchall()
        out: list[Fact] = []
        for r in rows:
            if r["visibility"] == Visibility.PRIVATE and (
                include_private_for is None or include_private_for not in _unj(r["participants_json"], [])
            ):
                continue
            out.append(row_to_fact(r))
        return out

    def all_facts(self) -> list[Fact]:
        """Every fact incl. PRIVATE/rejected -- for index building and admin views only."""
        return [row_to_fact(r) for r in self.conn.execute("SELECT * FROM facts ORDER BY valid_from, id")]

    def fact(self, id: str) -> Fact | None:
        r = self.conn.execute("SELECT * FROM facts WHERE id = ?", (id,)).fetchone()
        return row_to_fact(r) if r else None

    def fact_participants(self) -> dict[str, list[str]]:
        """fact_id -> people allowed to see it (only meaningful for TEAM/PRIVATE facts)."""
        rows = self.conn.execute("SELECT id, participants_json FROM facts WHERE visibility != 'public'")
        return {r["id"]: _unj(r["participants_json"], []) for r in rows}

    def supersession_chain(self, fact_id: str) -> list[Fact]:
        """All versions of a fact, oldest -> newest, following supersedes/superseded_by links."""
        f = self.fact(fact_id)
        if f is None:
            return []
        seen = {f.id}
        while f.supersedes and f.supersedes not in seen and (prev := self.fact(f.supersedes)):
            f = prev
            seen.add(f.id)
        chain = [f]
        while chain[-1].superseded_by and chain[-1].superseded_by not in {c.id for c in chain}:
            nxt = self.fact(chain[-1].superseded_by)
            if nxt is None:
                break
            chain.append(nxt)
        return chain

    def conflicts(self, *, area_id: str | None = None) -> list[dict[str, Any]]:
        q, args = "SELECT * FROM conflicts", []
        if area_id:
            q += " WHERE area_id = ?"
            args.append(area_id)
        return [dict(r) for r in self.conn.execute(q + " ORDER BY fact_id_a, fact_id_b", args)]

    def edges(self, *, src: str | None = None, rel: EdgeRel | str | None = None) -> list[Edge]:
        q, args = "SELECT * FROM edges WHERE 1=1", []
        if src:
            q += " AND src = ?"
            args.append(src)
        if rel:
            q += " AND rel = ?"
            args.append(str(rel))
        return [
            Edge(
                src=r["src"],
                dst=r["dst"],
                rel=EdgeRel(r["rel"]),
                weight=float(r["weight"] or 0.0),
                valid_from=_d(r["valid_from"]),
                valid_to=_d(r["valid_to"]),
                evidence_doc_ids=_unj(r["evidence_doc_ids_json"], []),
            )
            for r in self.conn.execute(q, args)
        ]

    # ------------------------------------------------------------------ graph view
    def graph_for_person(self, person_id: str, *, as_of: date | None = None, max_facts: int = 60) -> dict[str, Any]:
        """Knowledge-graph neighbourhood of one employee for the UI: the person, their areas (with expertise score),
        facts they stated (current + superseded, capped), each fact's receipts, and supersedes links.

        Cheap: a handful of indexed queries. ``as_of`` hides facts learned later and marks versions current as of
        that date. Node ids are prefixed by type so they never collide.
        """
        p = self.person(person_id)
        if p is None:
            return {"nodes": [], "links": []}
        nodes: dict[str, dict[str, Any]] = {}
        links: list[dict[str, str]] = []
        pid = f"person:{p.id}"
        nodes[pid] = {"id": pid, "type": "person", "label": p.name, "role": p.role, "team": p.team,
                      "departure_date": _iso(p.departure_date)}
        for e in self.expertise(person_id=person_id):
            a = self.area(e.area_id)
            aid = f"area:{e.area_id}"
            nodes[aid] = {"id": aid, "type": "area", "label": a.name if a else e.area_id, "score": e.score,
                          "criticality": a.criticality if a else None, "enough_data": e.enough_data}
            links.append({"source": pid, "target": aid, "rel": "knows"})
        for e in self.edges(src=person_id, rel=EdgeRel.OWNS):
            aid = f"area:{e.dst}"
            if aid in nodes:
                links.append({"source": pid, "target": aid, "rel": "owns"})
        facts = [f for f in self.facts(person_id=person_id, as_of=as_of) if f.epistemic == Epistemic.SAID]
        rank = {k: i for i, k in enumerate(FactKind)}
        facts.sort(key=lambda f: (rank.get(f.kind, 99), -f.valid_from.toordinal(), f.id))
        facts = facts[:max_facts]
        ids = {f.id for f in facts}
        for f in facts:
            fid = f"fact:{f.id}"
            current = f.is_current if as_of is None else (f.valid_to is None or f.valid_to > as_of)
            nodes[fid] = {"id": fid, "type": "fact", "label": f.text[:120], "kind": str(f.kind),
                          "is_current": current, "valid_from": _iso(f.valid_from), "valid_to": _iso(f.valid_to),
                          "confidence": f.confidence, "review_status": str(f.review_status), "area_id": f.area_id}
            links.append({"source": pid, "target": fid, "rel": "stated"})
            if f.area_id:
                aid = f"area:{f.area_id}"
                if aid not in nodes:
                    a = self.area(f.area_id)
                    nodes[aid] = {"id": aid, "type": "area", "label": a.name if a else f.area_id}
                links.append({"source": fid, "target": aid, "rel": "about"})
            for d in f.source_doc_ids[:3]:
                did = f"doc:{d}"
                nodes.setdefault(did, {"id": did, "type": "doc", "label": d})
                links.append({"source": fid, "target": did, "rel": "supported_by"})
            if f.supersedes and f.supersedes in ids:
                links.append({"source": fid, "target": f"fact:{f.supersedes}", "rel": "supersedes"})
        docs = {d.id: d for d in self.docs([n["label"] for n in nodes.values() if n["type"] == "doc"])}
        for n in nodes.values():
            if n["type"] == "doc" and n["label"] in docs:
                d = docs[n["label"]]
                n.update({"label": d.title or f"{d.source_type} {d.container}", "source_type": str(d.source_type),
                          "url": d.url, "timestamp": _iso(d.timestamp)})
        return {"nodes": list(nodes.values()), "links": links}

    # ------------------------------------------------------------------ expertise
    def expertise(self, *, area_id: str | None = None, person_id: str | None = None) -> list[Expertise]:
        q, args = "SELECT * FROM expertise WHERE 1=1", []
        if area_id is not None:
            q += " AND area_id = ?"
            args.append(area_id)
        if person_id is not None:
            q += " AND person_id = ?"
            args.append(person_id)
        rows = self.conn.execute(q + " ORDER BY score DESC, person_id, area_id", args)
        return [_row_to_expertise(r) for r in rows]

    # ------------------------------------------------------------------ query log / review
    def log_query(self, asker_id: str, question: str, answer: Answer) -> str:
        asked_at = datetime.now().replace(microsecond=0)
        qid = hashlib.sha1(f"{asked_at.isoformat()}|{asker_id}|{question}".encode()).hexdigest()[:16]
        about = set(answer.route_to)
        if answer.fact_ids:
            marks = ",".join("?" * len(answer.fact_ids))
            about.update(
                r["stated_by"]
                for r in self.conn.execute(f"SELECT stated_by FROM facts WHERE id IN ({marks})", answer.fact_ids)
                if r["stated_by"]
            )
        about.update(c.author_id for c in answer.said if c.author_id)
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO query_log VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    qid,
                    asked_at.isoformat(),
                    asker_id,
                    question,
                    str(answer.action),
                    answer.area_id,
                    float(answer.confidence),
                    answer.text,
                    _j(answer.route_to),
                    _j(answer.fact_ids),
                ),
            )
            self.conn.executemany(
                "INSERT OR IGNORE INTO query_about VALUES (?, ?)", [(qid, p) for p in sorted(about)]
            )
        return qid

    def query_log(self, *, about_person_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if about_person_id:
            rows = self.conn.execute(
                "SELECT q.* FROM query_log q JOIN query_about a ON a.query_id = q.id WHERE a.person_id = ? "
                "ORDER BY q.asked_at DESC LIMIT ?",
                (about_person_id, limit),
            )
        else:
            rows = self.conn.execute("SELECT * FROM query_log ORDER BY asked_at DESC LIMIT ?", (limit,))
        out = []
        for r in rows:
            d = dict(r)
            d["route_to"] = _unj(d.pop("route_to_json"), [])
            d["fact_ids"] = _unj(d.pop("fact_ids_json"), [])
            out.append(d)
        return out

    def set_review_status(self, fact_id: str, status: ReviewStatus, corrected_text: str | None = None) -> None:
        """The employee reviews what Keepline captured about them; corrections override extracted text."""
        now = datetime.now().replace(microsecond=0).isoformat()
        eid = hashlib.sha1(f"{fact_id}|{status}|{now}|{corrected_text}".encode()).hexdigest()[:16]
        with self.conn:
            if corrected_text is not None:
                self.conn.execute(
                    "UPDATE facts SET review_status = ?, corrected_text = ? WHERE id = ?",
                    (str(status), corrected_text, fact_id),
                )
            else:
                self.conn.execute("UPDATE facts SET review_status = ? WHERE id = ?", (str(status), fact_id))
            if status in (ReviewStatus.APPROVED, ReviewStatus.CORRECTED):
                self.conn.execute("UPDATE facts SET verification = 'verified' WHERE id = ?", (fact_id,))
            self.conn.execute(
                "INSERT OR REPLACE INTO review_events VALUES (?,?,?,?,?)",
                (eid, fact_id, str(status), corrected_text, now),
            )

    def review_events(self, fact_id: str | None = None) -> list[dict[str, Any]]:
        if fact_id:
            rows = self.conn.execute("SELECT * FROM review_events WHERE fact_id = ? ORDER BY at", (fact_id,))
        else:
            rows = self.conn.execute("SELECT * FROM review_events ORDER BY at")
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ build meta
    def meta(self) -> dict[str, Any]:
        return {r["key"]: json.loads(r["value"]) for r in self.conn.execute("SELECT * FROM build_meta")}

    def set_meta(self, key: str, value: Any) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO build_meta VALUES (?, ?)", (key, _j(value)))

    # ------------------------------------------------------------------ writers (used by memory.build)
    def reset(self) -> None:
        """Drop all derived content (keeps nothing). Query log & review events are wiped too: a rebuild is a new
        memory. Callers that want to preserve reviews should export them first."""
        with self.conn:
            for t in ("people", "areas", "documents", "doc_areas", "facts", "edges", "expertise", "conflicts",
                      "query_log", "query_about", "review_events", "build_meta"):
                self.conn.execute(f"DELETE FROM {t}")
        self._people = self._areas = None

    def write_org(self, people: Sequence[Person], areas: Sequence[Area]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO people VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (p.id, p.name, p.role, p.team, p.email, _iso(p.start_date), _iso(p.departure_date),
                     str(p.departure_type) if p.departure_type else None, p.manager_id)
                    for p in people
                ],
            )
            self.conn.executemany(
                "INSERT OR REPLACE INTO areas VALUES (?,?,?,?,?,?)",
                [(a.id, a.name, a.description, _j(a.keywords), _j(a.systems), a.criticality) for a in areas],
            )
        self._people = self._areas = None

    def write_docs(self, docs: Sequence[SourceDoc], doc_areas: dict[str, list[tuple[str, float]]]) -> None:
        with self.conn:
            rows = [doc_to_row(d) for d in docs]
            if rows:
                cols = list(rows[0])
                self.conn.executemany(
                    f"INSERT OR REPLACE INTO documents ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [tuple(r[c] for c in cols) for r in rows],
                )
            self.conn.executemany(
                "INSERT OR REPLACE INTO doc_areas VALUES (?,?,?)",
                [(doc_id, a, float(s)) for doc_id, lst in doc_areas.items() for a, s in lst],
            )

    def write_facts(self, facts: Sequence[Fact], participants: dict[str, list[str]] | None = None) -> None:
        participants = participants or {}
        rows = [fact_to_row(f, participants.get(f.id, ())) for f in facts]
        if not rows:
            return
        cols = list(rows[0])
        with self.conn:
            self.conn.executemany(
                f"INSERT OR REPLACE INTO facts ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [tuple(r[c] for c in cols) for r in rows],
            )

    def write_edges(self, edges: Sequence[Edge]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT INTO edges VALUES (?,?,?,?,?,?,?)",
                [
                    (e.src, e.dst, str(e.rel), e.weight, _iso(e.valid_from), _iso(e.valid_to), _j(e.evidence_doc_ids))
                    for e in edges
                ],
            )

    def write_expertise(self, rows: Sequence[Expertise], n_answers: dict[tuple[str, str], int] | None = None) -> None:
        n_answers = n_answers or {}
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO expertise VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (e.person_id, e.area_id, e.score, e.n_docs, e.n_tickets_closed, e.n_facts_stated,
                     n_answers.get((e.person_id, e.area_id), 0), _iso(e.last_active), int(e.confirmed_by_person),
                     int(e.enough_data))
                    for e in rows
                ],
            )

    def write_conflicts(self, rows: Sequence[dict[str, Any]]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO conflicts VALUES (?,?,?,?,?)",
                [(r["fact_id_a"], r["fact_id_b"], r.get("area_id"), r.get("subject"), r.get("note")) for r in rows],
            )


def _chunks(seq: Sequence[str], n: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]

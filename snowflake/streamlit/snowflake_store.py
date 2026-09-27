"""Snowflake-backed MemoryStore for Streamlit-in-Snowflake.

Why a snapshot and not a second store implementation: ``KEEPLINE.CORE`` mirrors ``keepline/memory/schema.sql``
table-for-table, so the cheapest *correct* adapter is to pull the caller's view of CORE into the exact SQLite
schema the local engine uses and hand it to the real ``MemoryStore``. Every product (risk map, handoff pack,
onboarding brief, gaps, what-if) then runs unchanged, next to the data.

* Reads go through the caller's Snowpark session, so row access / masking / aggregation policies decide what
  lands in the snapshot: the app can never show more than the viewer is allowed to see.
* The snapshot lives in the Streamlit container's temp dir for the session only; nothing leaves Snowflake.
* Writes the product makes (query log, review decisions) are mirrored back to CORE tables.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

# SQLite table (keepline/memory/schema.sql) -> Snowflake table. Same names, upper-cased.
TABLES = ("people", "areas", "documents", "doc_areas", "facts", "edges", "expertise", "conflicts",
          "query_log", "query_about", "review_events")


def select_expr(column: str, sf_type: str) -> str:
    """Snowflake expression that renders a column the way the SQLite schema stores it (ISO text / JSON text / 0-1)."""
    col = f'"{column.upper()}"'
    t = sf_type.upper()
    if t in ("ARRAY", "VARIANT", "OBJECT"):
        return f"TO_JSON({col})"
    if t == "DATE":
        return f"TO_VARCHAR({col}, 'YYYY-MM-DD')"
    if t.startswith("TIMESTAMP"):
        return f"TO_VARCHAR({col}, 'YYYY-MM-DD\"T\"HH24:MI:SS')"
    if t == "BOOLEAN":
        return f"IFF({col}, 1, 0)"
    return col


def _sqlite_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def materialize_snapshot(session: Any, root: Path, schema_sql: Path, database: str = "KEEPLINE") -> Path:
    """Write ``<root>/data/memory/keepline.db`` from KEEPLINE.CORE as seen by ``session``. Returns the db path."""
    db = root / "data" / "memory" / "keepline.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    try:
        con.executescript(schema_sql.read_text(encoding="utf-8"))
        types = {
            (r[0].lower(), r[1].lower()): r[2]
            for r in session.sql(
                f"SELECT table_name, column_name, data_type FROM {database}.INFORMATION_SCHEMA.COLUMNS "
                "WHERE table_schema = 'CORE'"
            ).collect()
        }
        for table in TABLES:
            cols = [c for c in _sqlite_columns(con, table) if (table, c) in types]
            if not cols:
                continue
            exprs = ", ".join(f"{select_expr(c, types[(table, c)])} AS \"{c.upper()}\"" for c in cols)
            rows = session.sql(f"SELECT {exprs} FROM {database}.CORE.{table.upper()}").collect()
            if rows:
                marks = ",".join("?" * len(cols))
                con.executemany(
                    f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({marks})",
                    [tuple(r[c.upper()] for c in cols) for r in rows],
                )
        con.commit()
    finally:
        con.close()
    return db


def export_product_world(db_path: Path, root: Path) -> None:
    """Write data/org + data/corpus from the snapshot so the app's pipeline checks and index build work.

    These files stay inside the SiS container's temp dir (inside Snowflake) and hold only what the viewer's
    policies allowed into the snapshot.
    """
    from keepline.contracts import write_json, write_jsonl
    from keepline.memory.store import MemoryStore

    store = MemoryStore(db_path)
    try:
        write_json(root / "data" / "org" / "people.json", store.people())
        write_json(root / "data" / "org" / "areas.json", store.areas())
        by_type: dict[str, list[Any]] = {}
        for d in store.all_docs():
            by_type.setdefault(str(d.source_type), []).append(d)
        file_for = {"slack": "slack.jsonl", "email": "email.jsonl", "ticket": "tickets.jsonl",
                    "doc": "docs.jsonl", "interview": "interviews.jsonl"}
        for source_type, docs in by_type.items():
            write_jsonl(root / "data" / "corpus" / file_for.get(source_type, f"{source_type}.jsonl"), docs)
    finally:
        store.close()


def make_store(session: Any, db_path: Path) -> Any:
    """A real MemoryStore over the snapshot whose writes are mirrored to Snowflake."""
    from keepline.memory.store import MemoryStore

    class SnowflakeMirroredStore(MemoryStore):
        """MemoryStore whose query-log and review writes also land in KEEPLINE.CORE."""

        def log_query(self, asker_id: str, question: str, answer: Any) -> str:
            qid = super().log_query(asker_id, question, answer)
            session.sql(
                "INSERT INTO KEEPLINE.CORE.QUERY_LOG (id, asker_id, question, action, area_id, confidence, "
                "answer_text, route_to_json, fact_ids_json) "
                "SELECT ?, ?, ?, ?, ?, ?, ?, PARSE_JSON(?)::ARRAY, PARSE_JSON(?)::ARRAY",
                params=[qid, asker_id, question, str(answer.action), answer.area_id, float(answer.confidence),
                        answer.text, json.dumps(list(answer.route_to)), json.dumps(list(answer.fact_ids))],
            ).collect()
            about = [r[0] for r in self.conn.execute("SELECT person_id FROM query_about WHERE query_id = ?", (qid,))]
            for person_id in about:
                session.sql("INSERT INTO KEEPLINE.CORE.QUERY_ABOUT (query_id, person_id) SELECT ?, ?",
                            params=[qid, person_id]).collect()
            return qid

        def set_review_status(self, fact_id: str, status: Any, corrected_text: str | None = None) -> None:
            super().set_review_status(fact_id, status, corrected_text)
            # The app role may append review events; a pipeline task applies them to FACTS.
            session.sql(
                "INSERT INTO KEEPLINE.CORE.REVIEW_EVENTS (fact_id, status, corrected_text, reviewer_id) "
                "SELECT ?, ?, ?, KEEPLINE.CORE.CURRENT_PERSON_ID()",
                params=[fact_id, str(status), corrected_text],
            ).collect()

    return SnowflakeMirroredStore(db_path)

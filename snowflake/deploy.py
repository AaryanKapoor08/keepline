"""Deploy Keepline to Snowflake: DDL + policies + Cortex pipeline, bulk-load the local world, create the agent.

    python snowflake/deploy.py --dry-run            # print the plan; needs no Snowflake packages or account
    python snowflake/deploy.py                      # everything, in dependency order
    python snowflake/deploy.py --only sql           # just run sql/00..06 in order
    python snowflake/deploy.py --only load          # just (re)load data/org + data/corpus + data/memory
    python snowflake/deploy.py --resume-tasks       # also turn on the incremental extraction task graph

Order for a full deploy (search services and the agent are built after data exists):
    sql 00,01,02,03,04,06 -> load (PUT/COPY -> NORMALIZE_RAW -> local graph) -> sql 05 (Cortex Search)
    -> semantic view (Cortex Analyst) -> agent (Cortex Agent) -> risk snapshot -> Streamlit-in-Snowflake

Connection: ``keepline.snowflake_conn.connect()`` (SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / ... env vars).
The data rule: everything is loaded into *this* account's internal stages and tables and never leaves it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# Running `python snowflake/deploy.py` puts this folder first on sys.path; drop it so the real
# `snowflake` namespace package (snowflake.connector) is never shadowed by our folder's children.
if sys.path and Path(sys.path[0]).resolve() == HERE:
    sys.path.pop(0)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from keepline.config import CORPUS_DIR, DEMO_TODAY, MEMORY_DB, MEMORY_DIR, ORG_DIR  # noqa: E402

log = logging.getLogger("keepline.snowflake.deploy")

SQL_DIR = HERE / "sql"
SEMANTIC_YAML = HERE / "analyst" / "keepline_semantic_model.yaml"
AGENT_JSON = HERE / "agent" / "keepline_agent.json"
STREAMLIT_DIR = HERE / "streamlit"
STAGE = "@KEEPLINE.RAW.LANDING"
SQL_BEFORE_LOAD = ("00_setup.sql", "01_schema.sql", "02_policies.sql", "03_extract.sql", "04_temporal.sql", "06_procs.sql")
SQL_AFTER_LOAD = ("05_search.sql",)

CORPUS_TABLES = {
    "slack.jsonl": "RAW.SLACK_MESSAGES",
    "email.jsonl": "RAW.EMAILS",
    "tickets.jsonl": "RAW.TICKETS",
    "docs.jsonl": "RAW.DOCS",
    "interviews.jsonl": "RAW.INTERVIEWS",
}
ORG_TABLES = {"people.json": "RAW.ORG_PEOPLE", "areas.json": "RAW.ORG_AREAS"}
# Local SQLite graph table (first name that exists wins) -> CORE table. People/areas/docs come from RAW.
GRAPH_TABLES: dict[str, tuple[str, ...]] = {
    "FACTS": ("facts", "fact"),
    "EDGES": ("edges", "edge"),
    "EXPERTISE": ("expertise",),
    "QUERY_LOG": ("query_log", "queries"),
    "REVIEW_EVENTS": ("review_events", "reviews"),
}
POST_GRAPH_SQL = (
    # Facts inherit the owning team of whoever stated them (team-visibility access).
    "UPDATE KEEPLINE.CORE.FACTS f SET owner_team = p.team FROM KEEPLINE.CORE.PEOPLE p "
    "WHERE p.id = f.stated_by AND f.owner_team IS NULL",
    # Non-public facts are visible to the participants of their receipts.
    "MERGE INTO KEEPLINE.CORE.ACL t USING ("
    " SELECT DISTINCT f.id AS object_id, a.person_id FROM KEEPLINE.CORE.FACTS f,"
    " LATERAL FLATTEN(input => f.source_doc_ids) s JOIN KEEPLINE.CORE.ACL a ON a.object_id = s.value::STRING"
    " WHERE f.visibility IN ('team', 'private')) s"
    " ON t.object_id = s.object_id AND t.person_id = s.person_id"
    " WHEN NOT MATCHED THEN INSERT (object_id, person_id) VALUES (s.object_id, s.person_id)",
)


# --------------------------------------------------------------------------------------------------
# SQL splitting
# --------------------------------------------------------------------------------------------------


def split_sql(text: str) -> list[str]:
    """Split a Snowflake script into statements on top-level ``;``.

    Understands single-quoted strings (with ``''`` and backslash escapes), double-quoted identifiers,
    ``$$ ... $$`` bodies (procedures, functions, agent specs), ``--`` and ``/* */`` comments.
    Statements that are only comments are dropped.
    """
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(text)
    has_code = False
    while i < n:
        c = text[i]
        two = text[i : i + 2]
        if two == "--":
            j = text.find("\n", i)
            j = n if j == -1 else j
            buf.append(text[i:j])
            i = j
            continue
        if two == "/*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            buf.append(text[i:j])
            i = j
            continue
        if two == "$$":
            j = text.find("$$", i + 2)
            if j == -1:
                raise ValueError("unterminated $$ block")
            buf.append(text[i : j + 2])
            has_code = True
            i = j + 2
            continue
        if c in ("'", '"'):
            j = i + 1
            while j < n:
                if c == "'" and text[j] == "\\":
                    j += 2
                    continue
                if text[j] == c:
                    if j + 1 < n and text[j + 1] == c:  # doubled quote escape
                        j += 2
                        continue
                    break
                j += 1
            if j >= n:
                raise ValueError(f"unterminated {c} string starting at offset {i}")
            buf.append(text[i : j + 1])
            has_code = True
            i = j + 1
            continue
        if c == ";":
            if has_code:
                out.append("".join(buf).strip())
            buf, has_code = [], False
            i += 1
            continue
        if not c.isspace():
            has_code = True
        buf.append(c)
        i += 1
    if has_code and "".join(buf).strip():
        out.append("".join(buf).strip())
    return out


def sql_statements(name: str) -> list[str]:
    return split_sql((SQL_DIR / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------------------


@dataclass
class Step:
    group: str  # sql | load | search | analyst | agent | refresh | streamlit | tasks
    title: str
    run: Callable[[Any], None]


def _exec(conn: Any, stmt: str, params: Any = None) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(stmt, params) if params is not None else cur.execute(stmt)
        try:
            return cur.fetchall()
        except Exception:  # noqa: BLE001 - DDL has no result set
            return []


def _sql_file_step(name: str, group: str) -> Step:
    stmts = sql_statements(name)

    def run(conn: Any) -> None:
        for k, stmt in enumerate(stmts, 1):
            try:
                _exec(conn, stmt)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"{name} statement {k}/{len(stmts)} failed: {exc}\n---\n{stmt[:400]}") from exc

    return Step(group, f"{name}: {len(stmts)} statements", run)


def _put(conn: Any, path: Path, target: str) -> None:
    _exec(conn, f"PUT 'file://{path.resolve().as_posix()}' {target} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")


def _copy_step(path: Path, table: str, subdir: str) -> Step:
    def run(conn: Any) -> None:
        _put(conn, path, f"{STAGE}/{subdir}")
        _exec(conn, f"TRUNCATE TABLE KEEPLINE.{table}")
        _exec(
            conn,
            f"COPY INTO KEEPLINE.{table} (record, source_file) "
            f"FROM (SELECT $1, METADATA$FILENAME FROM {STAGE}/{subdir}/{path.name}.gz) "
            "FILE_FORMAT = (FORMAT_NAME = 'KEEPLINE.RAW.JSONL_FMT') FORCE = TRUE",
        )

    return Step("load", f"PUT + COPY {path.relative_to(ROOT).as_posix()} -> KEEPLINE.{table}", run)


def _sqlite_tables(db: Path) -> set[str]:
    with sqlite3.connect(db) as con:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}


def _cast(col: str, sf_type: str) -> str:
    """SQLite stores lists/dicts as JSON text, dates as ISO text, booleans as 0/1."""
    t = sf_type.upper()
    src = f"TO_VARCHAR({col})"
    if t in ("ARRAY",):
        return f"TRY_PARSE_JSON({src})::ARRAY"
    if t in ("VARIANT", "OBJECT"):
        return f"TRY_PARSE_JSON({src})"
    if t == "DATE":
        return f"TRY_TO_DATE(LEFT({src}, 10))"
    if t.startswith("TIMESTAMP"):
        return f"TRY_TO_TIMESTAMP_NTZ({src})"
    if t == "BOOLEAN":
        return f"TRY_TO_BOOLEAN({src})"
    if t in ("NUMBER", "FLOAT", "DOUBLE", "REAL", "DECIMAL", "INT", "INTEGER"):
        return f"TRY_TO_DOUBLE({src})"
    return src


def _graph_step(core_table: str, sqlite_table: str) -> Step:
    def run(conn: Any) -> None:
        import pandas as pd
        from snowflake.connector.pandas_tools import write_pandas

        with sqlite3.connect(MEMORY_DB) as con:
            df = pd.read_sql_query(f'SELECT * FROM "{sqlite_table}"', con)
        if df.empty:
            log.info("skip %s: empty", sqlite_table)
            return
        df.columns = [c.upper() for c in df.columns]
        df = df.astype(object).where(df.notna(), None)
        stage_table = f"LOCAL_{core_table}"
        write_pandas(conn, df, stage_table, database="KEEPLINE", schema="RAW",
                     auto_create_table=True, overwrite=True, quote_identifiers=False)
        cols = _exec(conn, "SELECT column_name, data_type FROM KEEPLINE.INFORMATION_SCHEMA.COLUMNS "
                           "WHERE table_schema = 'CORE' AND table_name = %s ORDER BY ordinal_position", (core_table,))
        shared = [(c, t) for c, t in cols if c in set(df.columns)]
        if not shared:
            raise RuntimeError(f"no shared columns between sqlite {sqlite_table} and CORE.{core_table}")
        names = ", ".join(c for c, _ in shared)
        exprs = ", ".join(_cast(c, t) for c, t in shared)
        _exec(conn, f"INSERT OVERWRITE INTO KEEPLINE.CORE.{core_table} ({names}) "
                    f"SELECT {exprs} FROM KEEPLINE.RAW.{stage_table}")
        missing = sorted(set(df.columns) - {c for c, _ in shared})
        if missing:
            log.warning("CORE.%s: sqlite columns not in Snowflake schema (ignored): %s", core_table, missing)

    return Step("load", f"SQLite {MEMORY_DB.name}:{sqlite_table} -> write_pandas -> KEEPLINE.CORE.{core_table}", run)


def _signoffs_step(path: Path) -> Step:
    def run(conn: Any) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [{"person_id": k, **(v if isinstance(v, dict) else {})}
                                                     for k, v in data.items()]
        _exec(conn, "TRUNCATE TABLE KEEPLINE.APP.HANDOFF_SIGNOFFS")
        for r in rows:
            _exec(conn, "INSERT INTO KEEPLINE.APP.HANDOFF_SIGNOFFS (person_id, signed_off, signed_off_at, item_statuses, pack) "
                        "SELECT %s, %s, TRY_TO_TIMESTAMP_NTZ(%s), TRY_PARSE_JSON(%s), TRY_PARSE_JSON(%s)",
                  (r.get("person_id"), bool(r.get("signed_off")), r.get("signed_off_at"),
                   json.dumps(r.get("item_statuses") or r.get("items") or {}), json.dumps(r.get("pack") or {})))

    return Step("load", f"{path.relative_to(ROOT).as_posix()} -> KEEPLINE.APP.HANDOFF_SIGNOFFS", run)


def _analyst_step() -> Step:
    def run(conn: Any) -> None:
        _put(conn, SEMANTIC_YAML, "@KEEPLINE.APP.SEMANTIC_MODELS")
        _exec(conn, "DROP SEMANTIC VIEW IF EXISTS KEEPLINE.APP.KEEPLINE_SEMANTIC")
        _exec(conn, "CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML('KEEPLINE.APP', %s)",
              (SEMANTIC_YAML.read_text(encoding="utf-8"),))

    return Step("analyst", "semantic view KEEPLINE.APP.KEEPLINE_SEMANTIC from analyst/keepline_semantic_model.yaml", run)


def agent_ddl() -> str:
    """CREATE AGENT ... FROM SPECIFICATION $$<yaml>$$ built from agent/keepline_agent.json."""
    import yaml

    doc = json.loads(AGENT_JSON.read_text(encoding="utf-8"))
    spec = yaml.safe_dump(doc["specification"], sort_keys=False, allow_unicode=True, width=10_000)
    if "$$" in spec:
        raise ValueError("agent specification must not contain $$")
    comment = doc.get("comment", "").replace("'", "''")
    profile = json.dumps(doc.get("profile", {})).replace("'", "''")
    return (f"CREATE OR REPLACE AGENT {doc['name']}\n  COMMENT = '{comment}'\n  PROFILE = '{profile}'\n"
            f"  FROM SPECIFICATION\n$$\n{spec}$$")


def _agent_step() -> Step:
    def run(conn: Any) -> None:
        _exec(conn, agent_ddl())
        _exec(conn, "GRANT USAGE ON AGENT KEEPLINE.APP.KEEPLINE_AGENT TO ROLE KEEPLINE_APP")

    return Step("agent", "Cortex Agent KEEPLINE.APP.KEEPLINE_AGENT from agent/keepline_agent.json", run)


def _streamlit_step() -> Step:
    def run(conn: Any) -> None:
        target = "@KEEPLINE.APP.STREAMLIT_SRC"
        for f in sorted(STREAMLIT_DIR.glob("*")):
            if f.suffix in (".py", ".yml", ".toml"):
                _exec(conn, f"PUT 'file://{f.as_posix()}' {target} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        # Ship the keepline package so products/* run next to the data (SnowflakeStore backend).
        for d in sorted({p.parent for p in (ROOT / "keepline").rglob("*.py")}):
            rel = d.relative_to(ROOT).as_posix()
            _exec(conn, f"PUT 'file://{d.as_posix()}/*.py' {target}/{rel} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        _exec(conn, f"CREATE OR REPLACE STREAMLIT KEEPLINE.APP.KEEPLINE_STREAMLIT FROM '{target}' "
                    "MAIN_FILE = 'streamlit_app.py' QUERY_WAREHOUSE = KEEPLINE_WH "
                    "TITLE = 'Keepline' COMMENT = 'Keepline in Snowflake: data never leaves the account.'")
        _exec(conn, "GRANT USAGE ON STREAMLIT KEEPLINE.APP.KEEPLINE_STREAMLIT TO ROLE KEEPLINE_APP")

    return Step("streamlit", "Streamlit-in-Snowflake KEEPLINE.APP.KEEPLINE_STREAMLIT (streamlit/ + keepline/)", run)


def _simple(group: str, title: str, *stmts: str) -> Step:
    def run(conn: Any) -> None:
        for stmt in stmts:
            _exec(conn, stmt)

    return Step(group, title, run)


def _file_or_skip(path: Path, make: Callable[[Path], Step], steps: list[Step], skipped: list[str]) -> None:
    """Missing inputs are a note, not an error: deploy whatever exists."""
    if path.exists():
        steps.append(make(path))
    else:
        skipped.append(f"missing {path}")


def build_plan(only: str = "all", resume_tasks: bool = False) -> tuple[list[Step], list[str]]:
    """Return (steps, skipped-notes). Pure: touches only the local filesystem."""
    steps: list[Step] = []
    skipped: list[str] = []
    want = (lambda g: True) if only == "all" else (lambda g: g == only)

    if want("sql"):
        order = SQL_BEFORE_LOAD + SQL_AFTER_LOAD if only == "sql" else SQL_BEFORE_LOAD
        steps += [_sql_file_step(n, "sql") for n in sorted(order)]
    if want("load"):
        for name, table in ORG_TABLES.items():
            _file_or_skip(ORG_DIR / name, lambda p, t=table: _copy_step(p, t, "org"), steps, skipped)
        for name, table in CORPUS_TABLES.items():
            _file_or_skip(CORPUS_DIR / name, lambda p, t=table: _copy_step(p, t, "corpus"), steps, skipped)
        steps.append(_simple("load", "CALL CORE.NORMALIZE_RAW()  (typed tables, area linking, ACL)",
                             "CALL KEEPLINE.CORE.NORMALIZE_RAW()"))
        if MEMORY_DB.exists():
            present = _sqlite_tables(MEMORY_DB)
            for core_table, candidates in GRAPH_TABLES.items():
                hit = next((c for c in candidates if c in present), None)
                if hit:
                    steps.append(_graph_step(core_table, hit))
                else:
                    skipped.append(f"sqlite has no table for CORE.{core_table} (tried {', '.join(candidates)})")
            steps.append(_simple("load", "post-graph: owner_team + fact ACL", *POST_GRAPH_SQL))
        else:
            skipped.append(f"missing {MEMORY_DB} (run: python -m keepline.memory.build); Cortex extraction can fill FACTS instead")
        _file_or_skip(MEMORY_DIR / "signoffs.json", _signoffs_step, steps, skipped)
    if only in ("all", "search"):
        steps += [_sql_file_step(n, "search") for n in SQL_AFTER_LOAD]
    if want("analyst"):
        steps.append(_analyst_step())
    if want("agent"):
        steps.append(_agent_step())
    if want("refresh"):
        steps.append(_simple("refresh", f"CALL APP.REFRESH_RISK_SNAPSHOT('{DEMO_TODAY}')",
                             f"CALL KEEPLINE.APP.REFRESH_RISK_SNAPSHOT('{DEMO_TODAY.isoformat()}'::DATE)"))
    if want("streamlit"):
        steps.append(_streamlit_step())
    if resume_tasks or only == "tasks":
        steps.append(_simple("tasks", "resume task graph T_NORMALIZE -> T_EXTRACT -> T_SUPERSEDE + nightly risk",
                             "SELECT SYSTEM$TASK_DEPENDENTS_ENABLE('KEEPLINE.CORE.T_NORMALIZE')",
                             "ALTER TASK KEEPLINE.APP.T_NIGHTLY_RISK RESUME"))
    return steps, skipped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print the plan; do not connect")
    ap.add_argument("--only", default="all",
                    choices=["all", "sql", "load", "search", "analyst", "agent", "refresh", "streamlit", "tasks"])
    ap.add_argument("--resume-tasks", action="store_true", help="enable the incremental extraction task graph")
    ap.add_argument("--continue-on-error", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    steps, skipped = build_plan(args.only, args.resume_tasks)
    print(f"Keepline -> Snowflake deploy plan ({len(steps)} steps, only={args.only}):")
    for k, s in enumerate(steps, 1):
        print(f"  {k:2d}. [{s.group}] {s.title}")
    for note in skipped:
        print(f"  skip: {note}")
    if args.dry_run:
        print("dry run: nothing executed.")
        return 0

    from keepline.snowflake_conn import connect

    conn = connect()
    failures = 0
    try:
        for k, s in enumerate(steps, 1):
            print(f"[{k}/{len(steps)}] {s.title} ...", flush=True)
            try:
                s.run(conn)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"  FAILED: {exc}", file=sys.stderr)
                if not args.continue_on_error:
                    return 1
    finally:
        conn.close()
    print(f"done: {len(steps) - failures}/{len(steps)} steps ok.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

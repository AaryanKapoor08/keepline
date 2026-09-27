"""Offline checks for the Snowflake assets: everything parses, splits, plans and mirrors the local schema.

No Snowflake account or connector is needed; nothing here connects anywhere.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SF = ROOT / "snowflake"
SQL_FILES = sorted((SF / "sql").glob("*.sql"))


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def deploy() -> ModuleType:
    return _load("keepline_sf_deploy", SF / "deploy.py")


def test_all_sql_files_present() -> None:
    names = {p.name for p in SQL_FILES}
    for n in ("00_setup", "01_schema", "02_policies", "03_extract", "04_temporal", "05_search", "06_procs"):
        assert f"{n}.sql" in names


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_sql_splits_cleanly(deploy: ModuleType, path: Path) -> None:
    stmts = deploy.split_sql(path.read_text(encoding="utf-8"))
    assert stmts, f"{path.name} has no statements"
    for s in stmts:
        assert s.strip()
        assert s.count("$$") % 2 == 0, f"unbalanced $$ in {path.name}: {s[:120]}"
        body = re.sub(r"--[^\n]*", "", s).strip()
        assert body, f"comment-only statement in {path.name}"


def test_splitter_edge_cases(deploy: ModuleType) -> None:
    text = """
    -- a comment; with a semicolon
    SELECT 'a;b', 'it''s', 'back\\'slash;' FROM t;  /* block; comment */
    CREATE PROCEDURE p() RETURNS STRING LANGUAGE SQL AS $$ BEGIN RETURN 'x;y'; END; $$;
    SELECT "weird;name" FROM u
    """
    stmts = deploy.split_sql(text)
    assert len(stmts) == 3
    assert "'a;b'" in stmts[0] and "RETURN 'x;y'; END;" in stmts[1] and stmts[2].endswith("FROM u")


def test_key_snowflake_features_are_used() -> None:
    sql = "\n".join(p.read_text(encoding="utf-8") for p in SQL_FILES)
    for needle in ("AI_EXTRACT(", "AI_COMPLETE(", "response_format", "CREATE OR REPLACE CORTEX SEARCH SERVICE",
                   "ROW ACCESS POLICY", "MASKING POLICY", "AGGREGATION POLICY", "MIN_GROUP_SIZE => 5",
                   "CREATE STREAM", "CREATE OR REPLACE TASK", "AT(OFFSET =>", "MERGE INTO CORE.FACTS",
                   "LANGUAGE PYTHON", "snowflake-snowpark-python"):
        assert needle in sql, needle


def _columns(block: str) -> set[str]:
    cols = set()
    for line in block.splitlines():
        line = re.sub(r"--.*", "", line).strip()
        if not line or line.upper().startswith(("PRIMARY KEY", "UNIQUE", ")")):
            continue
        cols.add(line.split()[0].strip('"').lower())
    return cols


def test_snowflake_schema_mirrors_local_sqlite_schema() -> None:
    local = ROOT / "keepline" / "memory" / "schema.sql"
    if not local.exists():
        pytest.skip("local memory schema not built yet")
    sf = (SF / "sql" / "01_schema.sql").read_text(encoding="utf-8")
    sf_tables = {m.group(1).lower(): _columns(m.group(2))
                 for m in re.finditer(r"CREATE TABLE IF NOT EXISTS CORE\.(\w+) \((.*?)\n\)", sf, re.S)}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", local.read_text(encoding="utf-8"), re.S):
        table = m.group(1).lower()
        if table == "build_meta":
            continue
        assert table in sf_tables, f"CORE.{table.upper()} missing in 01_schema.sql"
        missing = _columns(m.group(2)) - sf_tables[table]
        assert not missing, f"CORE.{table.upper()} lacks local columns {sorted(missing)}"


def test_semantic_model_yaml() -> None:
    doc = yaml.safe_load((SF / "analyst" / "keepline_semantic_model.yaml").read_text(encoding="utf-8"))
    assert doc["name"] == "KEEPLINE_SEMANTIC"
    tables = {t["name"]: t for t in doc["tables"]}
    assert {"area_risk", "departures"} <= set(tables)
    questions = " ".join(q["question"].lower() for q in doc["verified_queries"])
    assert "bus factor 1" in questions and "days until" in questions


def test_agent_spec(deploy: ModuleType) -> None:
    doc = json.loads((SF / "agent" / "keepline_agent.json").read_text(encoding="utf-8"))
    spec = doc["specification"]
    names = {t["tool_spec"]["name"] for t in spec["tools"]}
    assert names == set(spec["tool_resources"])
    types = {t["tool_spec"]["type"] for t in spec["tools"]}
    assert {"cortex_search", "cortex_analyst_text_to_sql", "generic"} <= types
    assert "I don't know" in spec["instructions"]["response"]
    ddl = deploy.agent_ddl()
    assert ddl.startswith("CREATE OR REPLACE AGENT KEEPLINE.APP.KEEPLINE_AGENT") and "FROM SPECIFICATION" in ddl
    assert yaml.safe_load(ddl.split("$$")[1])["tools"]


def test_plan_is_offline_and_ordered(deploy: ModuleType) -> None:
    steps, _ = deploy.build_plan("all")
    groups = [s.group for s in steps]
    assert groups[0] == "sql" and "extract" not in groups  # no LLM credits unless asked
    assert groups.index("search") > max(i for i, g in enumerate(groups) if g in ("sql", "load"))
    steps, _ = deploy.build_plan("extract", limit=50)
    assert steps and "<= 50" in steps[0].title


def test_dry_run_cli_exits_zero_without_connector() -> None:
    code = (
        "import runpy, sys; sys.argv = ['deploy.py', '--dry-run'];\n"
        "try:\n    runpy.run_path(r'%s', run_name='__main__')\n"
        "except SystemExit as e:\n    assert e.code == 0, e.code\n"
        "assert 'snowflake.connector' not in sys.modules\n" % (SF / "deploy.py")
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert res.returncode == 0, res.stderr
    assert "dry run: nothing executed." in res.stdout


def test_streamlit_select_expr() -> None:
    store = _load("keepline_sf_store", SF / "streamlit" / "snowflake_store.py")
    assert store.select_expr("keywords_json", "ARRAY") == 'TO_JSON("KEYWORDS_JSON")'
    assert store.select_expr("valid_from", "DATE").startswith("TO_VARCHAR(")
    assert store.select_expr("enough_data", "BOOLEAN") == 'IFF("ENOUGH_DATA", 1, 0)'
    assert store.select_expr("name", "TEXT") == '"NAME"'


def test_no_persona_language() -> None:
    bad = re.compile(r"\bclone\b|digital twin|as sarah would say", re.I)
    for p in SF.rglob("*"):
        if p.is_file() and p.suffix in (".sql", ".py", ".md", ".json", ".yaml", ".yml"):
            assert not bad.search(p.read_text(encoding="utf-8")), p

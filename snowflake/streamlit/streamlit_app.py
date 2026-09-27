"""Keepline in Streamlit-in-Snowflake (SiS).

Two modes, same product:

1. **Full app (default)** - reuses the local app (``app/Home.py`` + ``app/views``) unchanged. The caller's view of
   ``KEEPLINE.CORE`` is materialized into the local engine's SQLite schema inside the SiS container
   (``snowflake_store.materialize_snapshot``) and ``KEEPLINE_ROOT`` points the app at it. Row access / masking
   policies decide what lands in the snapshot, so the app can never show more than the viewer may see.
2. **Native (fallback, or set KEEPLINE_SIS_NATIVE=1)** - a compact page that calls the Snowflake objects directly:
   ``APP.RISK_MAP`` (Snowpark proc), ``CORE.RECEIPTS_SEARCH`` / ``CORE.FACTS_SEARCH`` (Cortex Search) +
   ``AI_COMPLETE`` for cite-or-abstain answers, and ``APP.HANDOFF_PACK``.

Packaging (snowflake/deploy.py --only streamlit): this folder, ``keepline/``, ``app/`` and ``data/results/`` are
PUT to ``@KEEPLINE.APP.STREAMLIT_SRC`` preserving paths, then ``CREATE STREAMLIT ... MAIN_FILE='streamlit_app.py'``.
Everything runs inside the account: the data never leaves Snowflake.
"""

from __future__ import annotations

import json
import os
import runpy
import shutil
import sys
import tempfile
from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parent
BUNDLE = HERE  # on the stage, keepline/ and app/ sit next to this file
DEMO_TODAY = "2026-09-04"


def _session():
    from snowflake.snowpark.context import get_active_session

    return get_active_session()


def _prepare_full_app() -> Path | None:
    """Materialize the snapshot once per container and point keepline.config at it. None if not possible."""
    if os.environ.get("KEEPLINE_SIS_NATIVE") == "1" or not (BUNDLE / "app" / "Home.py").exists():
        return None
    if "_kl_root" in st.session_state:
        return Path(st.session_state["_kl_root"])
    sys.path.insert(0, str(BUNDLE))
    root = Path(tempfile.mkdtemp(prefix="keepline_"))
    # keepline.config reads KEEPLINE_ROOT at import time: set it before anything imports keepline.
    os.environ["KEEPLINE_ROOT"] = str(root)
    os.environ.setdefault("KEEPLINE_TODAY", DEMO_TODAY)
    os.environ.setdefault("KEEPLINE_LLM", "none")  # deterministic answer path; native mode shows AI_COMPLETE
    from snowflake_store import export_product_world, materialize_snapshot

    db = materialize_snapshot(_session(), root, BUNDLE / "keepline" / "memory" / "schema.sql")
    export_product_world(db, root)
    if (BUNDLE / "data" / "results").exists():  # benchmark results for the Proof page
        shutil.copytree(BUNDLE / "data" / "results", root / "data" / "results", dirs_exist_ok=True)
    st.session_state["_kl_root"] = str(root)
    return root


# --------------------------------------------------------------------------------------------------
# Native mode
# --------------------------------------------------------------------------------------------------


def _search(service: str, query: str, columns: list[str], flt: dict | None, limit: int = 6) -> list[dict]:
    payload = {"query": query, "columns": columns, "limit": limit}
    if flt:
        payload["filter"] = flt
    row = _session().sql("SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(?, ?) AS r",
                         params=[service, json.dumps(payload)]).collect()[0]
    return json.loads(row["R"]).get("results", [])


def _answer(question: str, asker_team: str, asker_id: str) -> tuple[str, list[dict]]:
    """Cite or abstain: the model only sees receipts the asker may see, and must quote them."""
    visible = {"@or": [{"@eq": {"visibility": "public"}}, {"@eq": {"owner_team": asker_team}},
                       {"@contains": {"participants": asker_id}}]}
    hits = _search("KEEPLINE.CORE.RECEIPTS_SEARCH", question,
                   ["doc_id", "snippet", "author_name", "ts", "url", "source_type"],
                   {"@and": [{"@lte": {"doc_date": DEMO_TODAY}}, visible]})
    if not hits:
        return "I don't know from the records.", []
    context = "\n".join(f"[{i + 1}] {h['author_name']} ({h['ts'][:10]}, {h['source_type']}): {h['snippet'][:600]}"
                        for i, h in enumerate(hits))
    prompt = ("Answer only from the numbered records. Quote the exact words you rely on and cite them like [2]. "
              "Label reasoning as 'Inferred:'. If the records do not answer the question, reply exactly "
              "\"I don't know from the records\" and name who wrote the most relevant record as the person to ask. "
              "Never speak as any employee.\n\nRecords:\n" + context + "\n\nQuestion: " + question)
    text = _session().sql("SELECT AI_COMPLETE('claude-sonnet-4-5', ?) AS a", params=[prompt]).collect()[0]["A"]
    return str(text).strip().strip('"'), hits


def render_native() -> None:
    st.set_page_config(page_title="Keepline", layout="wide")
    st.title("Keepline")
    st.caption("Everything on this page runs inside Snowflake: Snowpark procedures, Cortex Search, AI_COMPLETE.")
    risk_tab, ask_tab, handoff_tab = st.tabs(["Risk map", "Ask", "Handoff pack"])
    session = _session()
    with risk_tab:
        who = st.text_input("What if this person leaves? (person id, blank = today)", "")
        df = session.sql("CALL KEEPLINE.APP.RISK_MAP(?::DATE, ?)", params=[DEMO_TODAY, who or None]).to_pandas()
        st.dataframe(df, use_container_width=True, hide_index=True)
    with ask_tab:
        c1, c2 = st.columns(2)
        asker = c1.text_input("Asker (person id)", "alex")
        team = c2.text_input("Asker team", "engineering")
        q = st.text_input("Question", "When must the nightly reconciliation job not run?")
        if st.button("Ask", type="primary") and q:
            text, hits = _answer(q, team, asker)
            st.markdown(text)
            for i, h in enumerate(hits, 1):
                with st.expander(f"[{i}] {h['author_name']} - {h['ts'][:10]} - {h['source_type']}"):
                    st.write(h["snippet"])
                    if h.get("url"):
                        st.markdown(f"[Open source]({h['url']})")
    with handoff_tab:
        pid = st.text_input("Departing person", "sarah")
        if st.button("Build handoff pack"):
            pack = session.sql("CALL KEEPLINE.APP.HANDOFF_PACK(?, ?::DATE)", params=[pid, DEMO_TODAY]).collect()[0][0]
            st.json(json.loads(pack) if isinstance(pack, str) else pack, expanded=False)


def main() -> None:
    try:
        root = _prepare_full_app()
    except Exception as exc:  # noqa: BLE001 - fall back rather than show a stack trace to a judge
        st.session_state["_kl_error"] = str(exc)
        root = None
    if root is None:
        render_native()
        if err := st.session_state.get("_kl_error"):
            st.caption(f"Full app unavailable ({err}); showing the native view.")
        return
    runpy.run_path(str(BUNDLE / "app" / "Home.py"), run_name="__main__")


main()

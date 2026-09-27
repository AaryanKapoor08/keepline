"""Keepline app entry point: ``streamlit run app/Home.py`` (from the repo root, so .streamlit/config.toml applies).

Uses ``st.navigation`` so the sidebar reads like a product (grouped by the demo loop), not a file listing.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app import ui  # noqa: E402

st.set_page_config(page_title="Keepline · Harbourline", page_icon=":material/link:", layout="wide",
                   initial_sidebar_state="expanded")
st.session_state["_kl_nav"] = True
ui.inject_css()

VIEWS = Path(__file__).resolve().parent / "views"
nav = st.navigation(
    {
        "Overview": [st.Page(VIEWS / "home.py", title="Home", icon=":material/home:", default=True)],
        "Before they leave": [
            st.Page(VIEWS / "risk_map.py", title="Risk Map", icon=":material/crisis_alert:", url_path="risk"),
            st.Page(VIEWS / "handoff.py", title="Handoff Pack", icon=":material/assignment_turned_in:", url_path="handoff"),
        ],
        "After they leave": [
            st.Page(VIEWS / "ask.py", title="Ask", icon=":material/forum:", url_path="ask"),
            st.Page(VIEWS / "onboarding.py", title="Onboarding Brief", icon=":material/waving_hand:", url_path="onboarding"),
            st.Page(VIEWS / "decisions.py", title="Decision History", icon=":material/history:", url_path="decisions"),
        ],
        "Trust": [
            st.Page(VIEWS / "my_knowledge.py", title="My Knowledge", icon=":material/verified_user:", url_path="me"),
            st.Page(VIEWS / "proof.py", title="Proof", icon=":material/query_stats:", url_path="proof"),
        ],
    }
)
ui.sidebar()
nav.run()

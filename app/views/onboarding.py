"""Onboarding Brief: day-one map for a new joiner -- who to ask, what was decided, what not to touch."""

from __future__ import annotations

import sys
from pathlib import Path

_R = Path(__file__).resolve().parents[2]
if str(_R) not in sys.path:
    sys.path.insert(0, str(_R))

import streamlit as st  # noqa: E402

from app import data, ui  # noqa: E402

store = data.store()
ui.page(
    "Onboarding brief",
    "Built from receipts, not from a template: who actually does the work in each area, what changed recently "
    "and why, and the landmines nobody wrote down.",
    kicker="After they leave",
)
if store is None:
    ui.need_pipeline()
    st.stop()

names = data.names()
fn = data.first_names()
ids = [p.id for p in data.people()]
joiner = data.default_person("joiner")
pid = st.selectbox("New joiner", ids, index=ids.index(joiner) if joiner in ids else 0,
                   format_func=lambda i: names.get(i, i), key="brief_person")
person = store.person(pid)
b = data.brief(pid)
if b is None or person is None:
    ui.need_pipeline()
    st.stop()

start = f"starts {person.start_date:%a %b %d}" if person.start_date >= data.today() else f"joined {person.start_date:%b %d, %Y}"
ui.md(f'<div class="kl-banner"><div class="item"><div class="n">Welcome, {ui.h(person.name.split()[0])}</div>'
      f'<div class="t">{ui.h(person.role)} · {ui.h(b.team.replace("_", " ").title())} · {start}</div></div></div>')

sections = {s.title: s for s in b.sections}


def cites(row: dict) -> None:
    cs = row.get("citations") or []
    if cs:
        with st.expander(f"Receipts ({len(cs)})"):
            ui.md(ui.citations_html(cs, names))


tabs = st.tabs(["Who to ask", "Recent decisions", "Risks & landmines", "Jargon", "Starter tasks"])

with tabs[0]:
    rows = sections["Who to ask about what"].items
    cols = st.columns(2)
    for i, r in enumerate(rows):
        with cols[i % 2]:
            after = f'<p style="color:{ui.RED};font-weight:600">{ui.h(r["after"])}</p>' if r.get("after") else ""
            ui.card(f'{r["area"]} → {r["person"]}', f'<p class="kl-muted">Evidence: {ui.h(r["why"])}</p>{after}')
            cites(r)

with tabs[1]:
    rows = sections["Recent decisions & why"].items
    if not rows:
        st.caption("No decisions recorded in the last four months for your areas.")
    for r in rows:
        area = store.area(r["area_id"]) if r.get("area_id") else None
        rep = f'<p class="kl-muted">Replaces: <s>{ui.h(r["replaces"])}</s></p>' if r.get("replaces") else ""
        ui.card(r["decision"], rep, meta=f'{r["date"]} · by {ui.h(r["by"])}',
                badges=(ui.badge(area.name, "grey") if area else "") + ui.badge("CURRENT", "teal"))
        cites(r)

with tabs[2]:
    rows = sections["Open risks & landmines"].items
    for r in rows:
        if r["type"] == "risk":
            ui.card(r["title"], f'<p>{ui.h(r["detail"])}</p>', badges=ui.badge(r["level"].upper(), ui.risk_tone(r["level"])))
        else:
            ui.card(r["title"], f'<p>{ui.h(r["detail"])}</p>', badges=ui.badge("LANDMINE", "red"))
            cites(r)
    if not rows:
        st.caption("No open risks in your areas.")

with tabs[3]:
    rows = sections["Jargon"].items
    cols = st.columns(2)
    for i, r in enumerate(rows):
        with cols[i % 2]:
            ui.card(r["term"], f'<p>{ui.h(r["definition"])}</p>', meta=ui.h(r["area"]))

with tabs[4]:
    for r in sections["Starter tasks"].items:
        area = store.area(r["area_id"]) if r.get("area_id") else None
        ui.card(r["task"], f'<p class="kl-muted">Paired with <b>{ui.h(r["buddy"])}</b>, who stays and reviews your work.</p>',
                badges=ui.badge(area.name, "grey") if area else "")
        cites(r)

"""Decision History: every decision and changing rule, with what it replaced and when -- current vs replaced."""

from __future__ import annotations

import sys
from pathlib import Path

_R = Path(__file__).resolve().parents[2]
if str(_R) not in sys.path:
    sys.path.insert(0, str(_R))

from datetime import timedelta  # noqa: E402

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import data, ui  # noqa: E402
from keepline.contracts import Fact, FactKind  # noqa: E402
from keepline.products._common import citations_for  # noqa: E402

store = data.store()
ui.page(
    "Decision history",
    "Facts are versioned: when it became true, when we learned it, and what replaced it. The agent answers from the "
    "current version and shows the replaced one crossed out, never as current.",
    kicker="After they leave",
)
if store is None:
    ui.need_pipeline()
    st.stop()

names = data.first_names()
full_names = data.names()
today = data.today()
areas = {a.id: a.name for a in store.areas()}


@st.cache_data(show_spinner=False)
def _chains(version: float) -> list[list[Fact]]:
    """Every supersession chain plus stand-alone decisions, newest activity first."""
    facts = store.facts()
    seen: set[str] = set()
    chains: list[list[Fact]] = []
    for f in facts:
        if f.id in seen or not (f.kind == FactKind.DECISION or f.supersedes or f.superseded_by):
            continue
        chain = store.supersession_chain(f.id) or [f]
        seen.update(x.id for x in chain)
        chains.append(chain)
    chains.sort(key=lambda c: max(x.valid_from for x in c), reverse=True)
    return chains


chains = _chains(data._db_version())
if not chains:
    ui.empty_state("No decisions yet", "No decisions or superseded facts were extracted.")
    st.stop()

c1, c2, c3 = st.columns([2, 2, 2])
with c1:
    area_filter = st.selectbox("Area", ["All areas", *sorted({areas.get(c[-1].area_id or "", "Other") for c in chains})])
with c2:
    only_changed = st.toggle("Only facts that changed", value=True, help="Show chains with at least one replaced version")
with c3:
    as_of = st.date_input("What did we believe on…", value=today, min_value=today - timedelta(days=200), max_value=today,
                          help="Time travel: the version that was current on this date is highlighted.")

sel = [c for c in chains if (area_filter == "All areas" or areas.get(c[-1].area_id or "", "Other") == area_filter)
       and (not only_changed or len(c) > 1)]
n_changed = sum(1 for c in chains if len(c) > 1)
ui.kpi_row([
    ("Decisions & rules", len(chains), "tracked with receipts", ""),
    ("Changed over time", n_changed, "have a replaced version", "risk" if n_changed else ""),
    ("Shown", len(sel), area_filter, ""),
])
st.write("")


def current_on(chain: list[Fact], d) -> str | None:
    live = [f for f in chain if f.valid_from <= d and (f.valid_to is None or f.valid_to > d)]
    return live[-1].id if live else None


# --- timeline chart ----------------------------------------------------------------------------------------------
rows = []
for c in sel[:25]:
    label = (c[-1].subject or c[-1].text)[:48]
    for f in c:
        rows.append({"Topic": label, "From": pd.Timestamp(f.valid_from), "To": pd.Timestamp(f.valid_to or today),
                     "Status": "Current" if f.is_current else "Replaced", "Fact": f.text[:120],
                     "Said by": names.get(f.stated_by or "", "inferred")})
if rows:
    df = pd.DataFrame(rows)
    bars = alt.Chart(df).mark_bar(height=12, cornerRadius=3).encode(
        x=alt.X("From:T", title=None), x2="To:T",
        y=alt.Y("Topic:N", title=None, sort=None, axis=alt.Axis(labelLimit=320)),
        color=alt.Color("Status:N", scale=alt.Scale(domain=["Current", "Replaced"], range=[ui.TEAL, "#B8C5D1"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Topic", "Fact", "Said by", alt.Tooltip("From:T", format="%b %d"), alt.Tooltip("To:T", format="%b %d"), "Status"],
    )
    rule = alt.Chart(pd.DataFrame({"d": [pd.Timestamp(as_of)]})).mark_rule(color=ui.NAVY, strokeDash=[4, 3], strokeWidth=2).encode(x="d:T")
    st.altair_chart((bars + rule).properties(height=max(160, 26 * df["Topic"].nunique())), width="stretch")
    st.caption(f"Dashed line: {as_of:%b %d, %Y}. Hover a bar for the exact wording and who said it.")

# --- chains ------------------------------------------------------------------------------------------------------
for c in sel[:40]:
    head = c[-1]
    cur = current_on(c, as_of)
    area = areas.get(head.area_id or "", "")
    badges = (ui.badge(area, "grey") if area else "") + ui.badge(str(head.kind).replace("_", " ").upper(), "navy")
    if len(c) > 1:
        badges += ui.badge(f"{len(c)} VERSIONS", "amber")
    steps = []
    for i, f in enumerate(c):
        is_live = f.id == cur
        state = "current" if f.is_current else "replaced"
        tag = ui.badge("CURRENT", "solid-teal") if f.is_current else ui.badge(f"REPLACED {f.valid_to:%b %d}" if f.valid_to else "REPLACED", "grey")
        if is_live and as_of != today:
            tag += ui.badge(f"BELIEVED ON {as_of:%b %d}", "navy")
        learned = f" · learned {f.learned_at:%b %d}" if f.learned_at else ""
        cits = "".join(ui.citation_card(x, full_names) for x in citations_for(store, f, limit=1))
        steps.append(f'<div class="kl-step {state}"><div class="d">{tag} true from {f.valid_from:%b %d, %Y}{learned} · '
                     f'said by {ui.h(names.get(f.stated_by or "", "inferred"))}</div><div class="txt">{ui.h(f.text)}</div>{cits}</div>')
    ui.md(f'<div class="kl-card"><h4>{badges}{ui.h(head.subject or head.text[:80])}</h4>{"".join(steps)}</div>')

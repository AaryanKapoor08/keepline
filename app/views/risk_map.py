"""Risk Map: which topics is Harbourline about to forget? Includes the what-if ("remove Sarah")."""

from __future__ import annotations

import sys
from pathlib import Path

_R = Path(__file__).resolve().parents[2]
if str(_R) not in sys.path:
    sys.path.insert(0, str(_R))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import data, ui  # noqa: E402
from keepline.contracts import AreaRisk  # noqa: E402
from keepline.products.risk import risk_level  # noqa: E402
from keepline.products.simulate import newly_orphaned  # noqa: E402

ui.page(
    "Knowledge risk map",
    "risk = importance × (1 − redundancy) × departure likelihood. Topic-level only: this map never scores how a "
    "person works, it shows where the company depends on one head.",
    kicker="Before they leave",
)

store = data.store()
if store is None:
    ui.need_pipeline()
    st.stop()

today = data.today()
names = data.names()
fn = data.first_names()
people = data.people()

# --- what-if control -------------------------------------------------------------------------------------------------
default_leaver = data.default_person("leaver")
c1, c2 = st.columns([2, 3])
with c1:
    whatif = st.toggle(f"What if {fn.get(default_leaver or '', 'they')} leaves today?", key="whatif_on",
                       help="Recompute the map with this person's evidence removed. Planning aid only; never tied to performance.")
with c2:
    ids = [p.id for p in people]
    who = st.selectbox("Person to remove", ids, index=ids.index(default_leaver) if default_leaver in ids else 0,
                       format_func=lambda i: names.get(i, i), disabled=not whatif, label_visibility="collapsed")

before = data.risk_map()
risks = data.risk_map(exclude=(who,)) if whatif else before
if not risks:
    ui.empty_state("No areas yet", "The memory has no areas. Check data/org/areas.json and rebuild.")
    st.stop()

high = [r for r in risks if risk_level(r.risk) == "high"]
nearest = min((r.countdown_days for r in risks if r.countdown_days is not None and r.risk >= 0.2), default=None)
ui.kpi_row([
    ("High-risk areas", len(high), f"of {len(risks)} areas", "risk"),
    ("Bus factor ≤ 1", sum(1 for r in risks if r.bus_factor <= 1), "held by one person or nobody", "risk"),
    ("Next knowledge loss", f"{nearest}d" if nearest is not None else "—", "until a sole holder's last day", "risk" if nearest is not None else ""),
    ("Landmines at stake", sum(r.n_landmines for r in risks if r.risk >= 0.2), "in medium/high-risk areas", ""),
])
st.write("")

if whatif:
    orphaned = newly_orphaned(before, risks)
    area_names = {r.area_id: r.area_name for r in risks}
    msg = (f"Without {names.get(who, who)}, **{len(orphaned)}** area(s) would have nobody left who holds them: "
           + ", ".join(area_names[a] for a in orphaned)) if orphaned else f"Removing {names.get(who, who)} orphans no area."
    st.warning(msg, icon=":material/warning:")


# --- heat grid ---------------------------------------------------------------------------------------------------
def tile(r: AreaRisk) -> str:
    bg = ui.risk_rgb(r.risk)
    fg = "#FFFFFF" if r.risk >= 0.42 else ui.INK
    holder = fn.get(r.at_risk_person_id or "", "nobody")
    cd = f"{holder} · {r.countdown_days}d left" if r.countdown_days is not None else f"held by {holder}"
    if r.bus_factor == 0:
        cd = "orphaned: nobody holds it"
    return (f'<div class="kl-tile" style="background:{bg};color:{fg}"><div class="nm">{ui.h(r.area_name)}</div>'
            f'<div class="rk">{r.risk:.0%}</div><div class="ft">bus factor <b>{r.bus_factor}</b> · {ui.h(cd)}</div>'
            f'<div class="ft">{r.n_landmines} landmines · {r.n_facts} facts</div></div>')


ui.md(f'<div class="kl-tiles">{"".join(tile(r) for r in risks)}</div>')

# --- ranked bars + what-if dumbbell ------------------------------------------------------------------------------
df = pd.DataFrame([{
    "Area": r.area_name, "Risk": r.risk, "Importance": r.importance, "Redundancy": r.redundancy,
    "Departure likelihood": r.departure_likelihood, "Bus factor": r.bus_factor,
    "Held by": ", ".join(fn.get(p, p) for p, _ in r.experts[:3]) or "nobody",
    "Countdown (days)": r.countdown_days,
} for r in risks])
order = df["Area"].tolist()
seq = alt.Scale(domain=[0, 0.85], range=["#EEF2F5", "#C8102E"], clamp=True)

left, right = st.columns([3, 2], gap="large")
with left:
    st.markdown("#### Ranked by risk")
    if whatif:
        b = {r.area_id: r.risk for r in before}
        dd = pd.DataFrame([{"Area": r.area_name, "Before": b.get(r.area_id, 0.0), "After": r.risk} for r in risks])
        base = alt.Chart(dd).encode(y=alt.Y("Area:N", sort=order, title=None))
        chart = (
            base.mark_rule(strokeWidth=2, color="#B8C5D1").encode(x=alt.X("Before:Q", title="Risk", axis=alt.Axis(format="%")), x2="After:Q")
            + base.mark_circle(size=90, color="#8C99A6", opacity=1).encode(x="Before:Q", tooltip=["Area", alt.Tooltip("Before:Q", format=".0%")])
            + base.mark_circle(size=110, color=ui.RED, opacity=1).encode(x="After:Q", tooltip=["Area", alt.Tooltip("After:Q", format=".0%")])
        )
        st.altair_chart(chart.properties(height=max(220, 34 * len(dd))), width="stretch")
        st.caption("Grey = today · red = if they leave today")
    else:
        bars = alt.Chart(df).mark_bar(cornerRadiusEnd=4, height=18).encode(
            x=alt.X("Risk:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", grid=True, gridOpacity=0.4), title=None),
            y=alt.Y("Area:N", sort=order, title=None),
            color=alt.Color("Risk:Q", scale=seq, legend=None),
            tooltip=["Area", alt.Tooltip("Risk:Q", format=".0%"), alt.Tooltip("Importance:Q", format=".2f"),
                     alt.Tooltip("Redundancy:Q", format=".2f"), alt.Tooltip("Departure likelihood:Q", format=".2f"),
                     "Bus factor", "Held by", "Countdown (days)"],
        )
        labels = alt.Chart(df).transform_calculate(label="'bus factor ' + datum['Bus factor']").mark_text(
            align="left", dx=6, color=ui.MUTED, fontSize=11
        ).encode(x="Risk:Q", y=alt.Y("Area:N", sort=order), text="label:N")
        st.altair_chart((bars + labels).properties(height=max(220, 34 * len(df))), width="stretch")

with right:
    st.markdown("#### Month-over-month")
    trend_rows = []
    months = len(risks[0].trend) if risks and risks[0].trend else 0
    for r in before[:6]:
        for i, v in enumerate(r.trend):
            trend_rows.append({"Area": r.area_name, "Month": i - months + 1, "Risk": v})
    if trend_rows:
        tdf = pd.DataFrame(trend_rows)
        spark = alt.Chart(tdf).mark_line(strokeWidth=2, color=ui.RED, point=alt.OverlayMarkDef(size=28, color=ui.RED)).encode(
            x=alt.X("Month:O", title=None, axis=alt.Axis(labelExpr="datum.value == 0 ? 'now' : datum.value + 'm'")),
            y=alt.Y("Risk:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", tickCount=2), title=None),
            tooltip=["Area", "Month", alt.Tooltip("Risk:Q", format=".0%")],
        ).properties(height=70, width=260).facet(row=alt.Row("Area:N", sort=[r.area_name for r in before[:6]], title=None,
                                                         header=alt.Header(labelAngle=0, labelAlign="left", labelFontWeight="bold")))
        st.altair_chart(spark, width="content")
    else:
        st.caption("No history yet.")

# --- detail ------------------------------------------------------------------------------------------------------
st.markdown("#### Why each area is at risk")
for r in risks:
    lvl = risk_level(r.risk)
    experts = " ".join(ui.badge(f"{fn.get(p, p)} {s:.2f}", "navy") for p, s in r.experts[:4]) or ui.badge("nobody", "grey")
    with st.expander(f"{r.area_name} · {r.risk:.0%} · bus factor {r.bus_factor}", expanded=(r is risks[0])):
        ui.md(f"<p>{ui.badge(lvl.upper(), ui.risk_tone(lvl))} {ui.h(r.explanation)}</p>")
        a, b, c = st.columns(3)
        a.metric("Importance", f"{r.importance:.2f}", help="Criticality prior + incidents, decisions, landmines, dependencies, ask frequency")
        b.metric("Redundancy", f"{r.redundancy:.2f}", help="Saturating in the number of people with strong evidence")
        c.metric("Departure likelihood", f"{r.departure_likelihood:.2f}", help="From HR dates only; small constant baseline otherwise")
        ui.md(f'<div class="kl-muted">Evidence of knowing it: {experts}</div>')
        if not r.enough_data:
            st.caption("Not enough data to judge this area: treated as unknown, not as safe.")

with st.expander("Table view"):
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=1, format="percent")})

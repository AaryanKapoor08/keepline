"""Home: Harbourline at a glance -- who is leaving, what is at risk, what Keepline does."""

from __future__ import annotations

import sys
from pathlib import Path

_R = Path(__file__).resolve().parents[2]
if str(_R) not in sys.path:
    sys.path.insert(0, str(_R))

import streamlit as st  # noqa: E402

from app import data, ui  # noqa: E402
from keepline.config import DEMO_COMPANY  # noqa: E402
from keepline.products.risk import risk_level  # noqa: E402

ui.page(
    "When Sarah leaves Friday, what breaks Monday?",
    "Glean finds what your company knows. Keepline shows what it's about to forget, and saves it: every fact with "
    "who said it, when it was true, and what replaced it.",
    kicker=f"{DEMO_COMPANY} · knowledge continuity",
)

store = data.store()
if store is None:
    ui.need_pipeline()
    st.stop()

today = data.today()
fn = data.first_names()

# --- departures banner -------------------------------------------------------------------------------------------
items = []
for p in data.departing()[:3]:
    days = (p.departure_date - today).days
    kind = (p.departure_type or "leaving").replace("_", " ")
    items.append(f'<div class="item"><div class="n red">{days}d</div><div class="t">until <b>{ui.h(p.name)}</b> leaves '
                 f'({ui.h(kind)}, {p.departure_date:%b %d})</div></div>')
for p in [j for j in data.joiners() if j.start_date >= today][:1]:
    days = (p.start_date - today).days
    items.append(f'<div class="item"><div class="n teal">{days}d</div><div class="t">until <b>{ui.h(p.name)}</b> starts '
                 f'({p.start_date:%b %d})</div></div>')
if items:
    ui.md(f'<div class="kl-banner">{"".join(items)}</div>')

# --- KPIs --------------------------------------------------------------------------------------------------------
risks = data.risk_map()
high = [r for r in risks if risk_level(r.risk) == "high"]
bf1 = [r for r in risks if r.bus_factor <= 1]
facts = store.facts(current_only=True)
receipts = sum(1 for f in facts if f.source_doc_ids)
ui.kpi_row([
    ("High-risk areas", len(high), f"of {len(risks)} areas", "risk"),
    ("Bus factor ≤ 1", len(bf1), "one person (or nobody) holds it", "risk" if bf1 else ""),
    ("Current facts", len(facts), f"{receipts} with receipts", "good"),
    ("Landmines", sum(r.n_landmines for r in risks), "rules that bite if broken", ""),
])

st.write("")
left, right = st.columns([3, 2], gap="large")
with left:
    st.markdown("#### Most fragile knowledge")
    for r in risks[:4]:
        lvl = risk_level(r.risk)
        who = fn.get(r.at_risk_person_id or "", "")
        cd = f" · {who} leaves in {r.countdown_days}d" if r.countdown_days is not None and r.countdown_days <= 120 else ""
        ui.card(
            r.area_name,
            f"<p>{ui.h(r.explanation)}</p>" + ui.meter(r.risk, ui.risk_rgb(r.risk)),
            meta=f"Risk {r.risk:.0%} · bus factor {r.bus_factor}{ui.h(cd)}",
            badges=ui.badge(lvl.upper(), ui.risk_tone(lvl)),
        )
    if st.session_state.get("_kl_nav"):
        st.page_link("views/risk_map.py", label="Open the risk map", icon=":material/arrow_forward:")
with right:
    st.markdown("#### The loop")
    steps = [
        ("1 · See the risk", "Topic-level map of what only one person knows, with countdowns from HR dates."),
        ("2 · Save it", "A handoff pack with receipts: access, vendors, recurring jobs, landmines. The person signs off."),
        ("3 · Ask it", "Cited answers in three layers: said, inferred, no evidence. Or: “I don't know, ask Mike.”"),
        ("4 · Prove it", "Benchmarked against a plain search baseline with N on every number."),
    ]
    for t, b in steps:
        ui.card(t, f"<p>{ui.h(b)}</p>")
    ui.md('<div class="kl-private">Receipts, not clones: Keepline never imitates a person. It shows what was said, '
          'by whom, and when, and each person reviews what is captured about them.</div>')

"""My Knowledge: the employee's own view -- review what was captured about them, see who asked, control sources.

This is why people participate: nothing about them is used without their review, DMs are off by default, and
the impact report is private to them (never shown to managers, never used for performance).
"""

from __future__ import annotations

import sys
from pathlib import Path

_R = Path(__file__).resolve().parents[2]
if str(_R) not in sys.path:
    sys.path.insert(0, str(_R))

import streamlit as st  # noqa: E402

from app import data, ui  # noqa: E402
from keepline.contracts import Action, ReviewStatus  # noqa: E402
from keepline.products._common import citations_for  # noqa: E402

store = data.store()
ui.page(
    "My knowledge",
    "What Keepline has captured about your work, who has asked about it, and which sources it may read. "
    "Only you see this page.",
    kicker="Trust",
)
if store is None:
    ui.need_pipeline()
    st.stop()

names = data.names()
fn = data.first_names()
ids = [p.id for p in data.people()]
leaver = data.default_person("leaver")
pid = st.selectbox("Signed in as", ids, index=ids.index(leaver) if leaver in ids else 0,
                   format_func=lambda i: names.get(i, i), key="me")
ui.md('<div class="kl-private">Private to you. Managers see topic-level risk only; they never see this queue, '
      'your query log or your impact report.</div>')

facts = store.facts(person_id=pid, include_private_for=pid)
pending = [f for f in facts if str(f.review_status) == ReviewStatus.PENDING]
approved = [f for f in facts if str(f.review_status) in (ReviewStatus.APPROVED, ReviewStatus.CORRECTED)]
log = store.query_log(about_person_id=pid, limit=500)
helped = {r.get("asker_id") for r in log if r.get("action") == Action.ANSWER and r.get("asker_id") != pid}

ui.kpi_row([
    ("Waiting for your review", len(pending), "facts attributed to you", "risk" if pending else ""),
    ("Approved or corrected", len(approved), f"of {len(facts)}", "good"),
    ("Questions about your work", len(log), "in the query log", ""),
    ("People your knowledge helped", len(helped), "answered with your receipts", "good"),
])
st.write("")

tab_q, tab_log, tab_src, tab_asks = st.tabs(["Review queue", "Who asked what", "Source controls", "Questions for you"])

with tab_q:
    if not pending:
        st.success("Nothing waiting. Everything attributed to you has been reviewed.", icon=":material/verified:")
    limit = st.slider("Show", 5, 50, 12, step=1, key="q_limit") if len(pending) > 12 else 12
    for f in pending[:limit]:
        area = store.area(f.area_id) if f.area_id else None
        with st.container(border=True):
            b = ui.badge(str(f.kind).replace("_", " ").upper(), "navy") + (ui.badge(area.name, "grey") if area else "")
            b += ui.badge(f"confidence {f.confidence:.0%}", "grey")
            if not f.is_current:
                b += ui.badge("REPLACED", "grey")
            ui.md(f"<div>{b}</div><div style='font-weight:600;margin:.35rem 0'>{ui.h(f.text)}</div>")
            cs = citations_for(store, f, limit=2)
            if cs:
                with st.expander("Where this came from"):
                    ui.md(ui.citations_html(cs, names))
            c1, c2, c3, _ = st.columns([1, 1, 1, 3])
            if c1.button("Approve", key=f"ap_{f.id}", icon=":material/check:"):
                store.set_review_status(f.id, ReviewStatus.APPROVED)
                st.rerun()
            with c2.popover("Correct", icon=":material/edit:"):
                txt = st.text_area("What is actually true?", value=f.text, key=f"ct_{f.id}")
                if st.button("Save", key=f"cs_{f.id}", type="primary"):
                    store.set_review_status(f.id, ReviewStatus.CORRECTED, txt)
                    st.rerun()
            if c3.button("Reject", key=f"rj_{f.id}", icon=":material/close:"):
                store.set_review_status(f.id, ReviewStatus.REJECTED)
                st.rerun()

with tab_log:
    if not log:
        st.caption("Nobody has asked about your work yet.")
    for r in log[:50]:
        action = str(r.get("action") or "")
        tone = {"answer": "teal", "abstain": "grey", "route": "amber"}.get(action, "grey")
        ui.card(r.get("question") or "", meta=f"{ui.h(names.get(r.get('asker_id') or '', r.get('asker_id') or 'someone'))} · "
                f"{ui.h(str(r.get('asked_at') or '')[:16].replace('T', ' '))}", badges=ui.badge(action.upper() or "ASKED", tone))

with tab_src:
    prefs = data.source_prefs(pid)
    st.caption("Keepline only reads what you allow. Direct messages are off by default; if you turn them on, "
               "facts from DMs stay visible only to the people in that conversation.")
    labels = {"public_channels": "Public Slack channels", "team_channels": "Team channels", "email_threads": "Email threads",
              "tickets": "Tickets", "direct_messages": "Direct messages (DMs)"}
    new = {k: st.toggle(v, value=prefs[k], key=f"src_{pid}_{k}") for k, v in labels.items()}
    if new != prefs:
        data.set_source_prefs(pid, new)
        st.toast("Source preferences saved. They apply on the next memory build.")

with tab_asks:
    asks = data.asks_for(pid)
    if not asks:
        st.caption("No one has routed a question to you yet.")
    for a in reversed(asks[-30:]):
        ui.card(a.get("question", ""), meta=f"from {ui.h(names.get(a.get('asker_id', ''), a.get('asker_id', '')))} · "
                f"{ui.h(a.get('at', '')[:16].replace('T', ' '))} · {ui.h(a.get('note', ''))}", badges=ui.badge("ROUTED TO YOU", "amber"))
    if asks:
        st.caption("Your answers become new receipts, attributed to you and reviewable here.")

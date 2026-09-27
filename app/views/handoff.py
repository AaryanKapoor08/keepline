"""Handoff Pack: what walks out the door with the departing person -- reviewed and signed off by them."""

from __future__ import annotations

import sys
from pathlib import Path

_R = Path(__file__).resolve().parents[2]
if str(_R) not in sys.path:
    sys.path.insert(0, str(_R))

import streamlit as st  # noqa: E402

from app import data, ui  # noqa: E402
from keepline.contracts import HandoffItem, ReviewStatus  # noqa: E402
from keepline.products import signoff  # noqa: E402
from keepline.products.handoff import SECTION_ORDER, SECTION_TITLES, pack_to_markdown  # noqa: E402

store = data.store()
ui.page(
    "Handoff pack",
    "Everything only they know, with receipts: access, vendor contacts, recurring jobs, unresolved work, landmines. "
    "They confirm, correct or remove each item, then sign off.",
    kicker="Before they leave",
)
if store is None:
    ui.need_pipeline()
    st.stop()

names = data.names()
fn = data.first_names()
ids = [p.id for p in data.people()]
leaver = data.default_person("leaver")
pid = st.selectbox("Departing person", ids, index=ids.index(leaver) if leaver in ids else 0,
                   format_func=lambda i: names.get(i, i), key="handoff_person")
person = store.person(pid)
pack = data.handoff(pid)
if pack is None or person is None:
    ui.need_pipeline()
    st.stop()

today = data.today()
statuses = {signoff.item_key(it): it.status for it in pack.items}
reviewed = sum(1 for s in statuses.values() if s != "pending_review")
total = len(pack.items)

# --- header ------------------------------------------------------------------------------------------------------
days = (pack.last_day - today).days if pack.last_day else None
sign_badge = ui.badge("SIGNED OFF", "solid-teal") if pack.signed_off else ui.badge("DRAFT · AWAITING SIGN-OFF", "amber")
last = f"Last day {pack.last_day:%a %b %d} · <b>{days} days</b>" if pack.last_day and days is not None else "No departure date on file"
ui.md(f'<div class="kl-banner"><div class="item"><div class="n">{ui.h(person.name)}</div><div class="t">{ui.h(person.role)} · '
      f'{last}</div></div><div class="item"><div class="n teal">{reviewed}/{total}</div><div class="t">items reviewed by '
      f'{ui.h(person.name.split()[0])}</div></div><div class="item">{sign_badge}'
      + (f'<div class="t">signed {pack.signed_off_at:%b %d %H:%M}</div>' if pack.signed_off_at else "") + "</div></div>")
st.progress(reviewed / total if total else 0.0)


# --- review actions ----------------------------------------------------------------------------------------------
def _review(item: HandoffItem, status: str, correction: str | None = None) -> None:
    signoff.set_item(pid, signoff.item_key(item), status, correction)
    mapping = {"confirmed": ReviewStatus.APPROVED, "corrected": ReviewStatus.CORRECTED, "removed": ReviewStatus.REJECTED}
    for fid in item.fact_ids:  # the person's review flows back into the memory the agent answers from
        try:
            store.set_review_status(fid, mapping[status], correction if status == "corrected" else None)
        except Exception:  # noqa: BLE001 - the pack state is saved either way
            pass
    st.toast({"confirmed": "Confirmed", "corrected": "Correction saved", "removed": "Removed from the pack"}[status])


def render_item(item: HandoffItem, idx: int) -> None:
    key = signoff.item_key(item)
    status = item.status
    tone = {"confirmed": "teal", "corrected": "navy", "removed": "grey"}.get(status, "amber")
    area = store.area(item.area_id) if item.area_id else None
    with st.container(border=True):
        top = ui.badge(status.replace("_", " ").upper(), tone)
        if area:
            top += ui.badge(area.name, "grey")
        if item.suggested_owner_id:
            top += ui.badge(f"suggested owner: {fn.get(item.suggested_owner_id, item.suggested_owner_id)}", "navy")
        style = ' style="text-decoration:line-through;color:#8C99A6"' if status == "removed" else ""
        ui.md(f'<div>{top}</div><div style="font-weight:700;font-size:1.02rem;margin:.35rem 0 .15rem"{style}>{ui.h(item.title)}</div>'
              f'<div class="kl-muted"{style}>{ui.h(item.detail)}</div>')
        if item.citations:
            with st.expander(f"Receipts ({len(item.citations)})"):
                ui.md(ui.citations_html(item.citations, names))
        b1, b2, b3, _ = st.columns([1, 1, 1, 3])
        if b1.button("Confirm", key=f"c_{key}_{idx}", icon=":material/check:", disabled=status == "confirmed"):
            _review(item, "confirmed")
            st.rerun()
        with b2.popover("Correct", icon=":material/edit:"):
            txt = st.text_area("Corrected text", value=item.detail, key=f"t_{key}_{idx}")
            if st.button("Save correction", key=f"s_{key}_{idx}", type="primary"):
                _review(item, "corrected", txt)
                st.rerun()
        if b3.button("Remove", key=f"r_{key}_{idx}", icon=":material/delete:", disabled=status == "removed"):
            _review(item, "removed")
            st.rerun()


sections = [s for s in SECTION_ORDER if any(it.section == s for it in pack.items)]
labels = [f"{SECTION_TITLES[s]} ({sum(1 for it in pack.items if it.section == s)})" for s in sections]
labels.append(f"Ask before the last day ({len(pack.gaps)})")
tabs = st.tabs(labels)
for tab, section in zip(tabs, sections):
    with tab:
        for i, it in enumerate(it for it in pack.items if it.section == section):
            render_item(it, i)
with tabs[-1]:
    st.caption("Gap-interview questions, ranked by area risk × expected information gain. Answers become new receipts.")
    for g in pack.gaps:
        area = store.area(g.area_id) if g.area_id else None
        ui.card(g.question, meta=f"{ui.h(g.reason)} · priority {g.priority:.2f}",
                badges=ui.badge(area.name, "grey") if area else "")
    if not pack.gaps:
        st.caption("No open gaps found.")

# --- sign-off + export -------------------------------------------------------------------------------------------
st.divider()
s1, s2, s3 = st.columns([2, 2, 3])
pending = total - reviewed
with s1:
    if pack.signed_off:
        if st.button("Re-open pack", icon=":material/lock_open:"):
            signoff.reset(pid)
            st.rerun()
    elif st.button(f"Sign off as {person.name.split()[0]}", type="primary", icon=":material/draw:"):
        signoff.sign_off(pid)
        st.toast("Signed off. The pack is now the handoff of record.")
        st.rerun()
with s2:
    st.download_button("Export Markdown", pack_to_markdown(store, pack), file_name=f"handoff_{pid}.md",
                       mime="text/markdown", icon=":material/download:")
with s3:
    if pending and not pack.signed_off:
        st.caption(f"{pending} item(s) not reviewed yet. Signing off records them as reviewed-as-is.")
    st.caption("Suggested owners are suggestions. A manager approves every assignment.")

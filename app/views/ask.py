"""Ask: cited answers in three layers (Said / Inferred / No evidence), or "I don't know, ask Mike"."""

from __future__ import annotations

import sys
from pathlib import Path

_R = Path(__file__).resolve().parents[2]
if str(_R) not in sys.path:
    sys.path.insert(0, str(_R))

from datetime import date  # noqa: E402

import streamlit as st  # noqa: E402

from app import data, demo_cache, ui  # noqa: E402
from keepline.contracts import Action, Answer, ReviewStatus  # noqa: E402

store = data.store()
ui.page(
    "Ask Harbourline",
    "Every answer shows what was said (quoted, linked, dated), what was inferred (labeled), and what there is no "
    "evidence for. When Keepline doesn't know, it says so and tells you who to ask.",
    kicker="After they leave",
)
if store is None:
    ui.need_pipeline()
    st.stop()

names = data.names()
fn = data.first_names()
ids = [p.id for p in data.people()]
script = demo_cache.load_script()
joiner = script.get("asker_id") or data.default_person("joiner")
today = data.today()

c1, c2 = st.columns([1, 3])
with c1:
    asker = st.selectbox("Asking as", ids, index=ids.index(joiner) if joiner in ids else 0,
                         format_func=lambda i: names.get(i, i), key="asker",
                         help="Answers never exceed what this person is allowed to see.")
with c2:
    suggestions = [q["text"] for q in script.get("questions", [])]
    picked = st.pills("Try", suggestions, key="suggest", label_visibility="visible") if suggestions else None

if "chat" not in st.session_state:
    st.session_state.chat = []


@st.cache_data(show_spinner=False)
def _cache(mtime: float) -> dict[str, Answer]:
    return demo_cache.load_cache()


def cached_answer(q: str, who: str, on: date) -> Answer | None:
    p = demo_cache.CACHE_PATH
    return _cache(p.stat().st_mtime if p.exists() else 0.0).get(demo_cache.key(who, q, on))


def ask(q: str) -> None:
    a = cached_answer(q, asker, today)
    source = "cache"
    if a is None:
        agent = data.agent()
        if agent is None:
            st.error("The answer agent is not available. Build the memory and search index first.")
            return
        with st.spinner("Searching receipts…"):
            a = agent.answer(q, asker, as_of=today)
        source = "live"
    try:
        store.log_query(asker, q, a)  # feeds "who asked what about my knowledge" and gap questions
    except Exception:  # noqa: BLE001
        pass
    st.session_state.chat.append({"asker": asker, "q": q, "a": a, "source": source})


ACTION_BADGE = {Action.ANSWER: ("ANSWER", "solid-teal"), Action.ABSTAIN: ("I DON'T KNOW", "grey"), Action.ROUTE: ("ASK A PERSON", "amber")}


def replaced_by(fact_id: str | None) -> str | None:
    if not fact_id:
        return None
    f = store.fact(fact_id)
    if f and f.superseded_by and (n := store.fact(f.superseded_by)):
        return f"{n.text} ({n.valid_from:%b %d})"
    return None


def render(turn: dict, idx: int) -> None:
    a: Answer = turn["a"]
    label, tone = ACTION_BADGE.get(Action(a.action), ("ANSWER", "teal"))
    area = store.area(a.area_id) if a.area_id else None
    conf_color = ui.TEAL if a.confidence >= 0.6 else (ui.AMBER if a.confidence >= 0.35 else "#8C99A6")
    head = ui.badge(label, tone) + (ui.badge(area.name, "grey") if area else "")
    head += ui.badge("demo cache" if turn["source"] == "cache" else "live", "navy")
    ui.md(f'<div>{head}</div><div style="display:flex;align-items:center;gap:.6rem;max-width:360px;margin:.35rem 0">'
          f'<div class="kl-muted" style="white-space:nowrap">Confidence {a.confidence:.0%}</div>'
          f'<div style="flex:1">{ui.meter(a.confidence, conf_color)}</div></div>'
          f'<div class="kl-answer">{ui.h(a.text)}</div>')

    ui.md(f'<div class="kl-layer said">Said · quoted receipts ({len(a.said)})</div>')
    if a.said:
        ui.md("".join(ui.citation_card(c, names, replaced_by(c.fact_id) if not c.is_current else None) for c in a.said))
    else:
        ui.md('<div class="kl-muted">Nothing quotable.</div>')
    ui.md(f'<div class="kl-layer inf">Inferred · reasoning, labeled ({len(a.inferred)})</div>')
    ui.md("".join(f'<div class="kl-card" style="border-left:4px solid {ui.AMBER}"><p>{ui.h(x)}</p></div>' for x in a.inferred)
          or '<div class="kl-muted">Nothing inferred.</div>')
    ui.md('<div class="kl-layer none">No evidence</div>')
    ui.md(f'<div class="kl-muted">{ui.h(a.no_evidence_note)}</div>' if a.no_evidence_note
          else '<div class="kl-muted">Every claim above has a receipt.</div>')

    # "Ask the real person": routes from the agent, else the people who stated the cited facts.
    people = list(dict.fromkeys(a.route_to or [c.author_id for c in a.said]))[:3]
    if people:
        st.write("")
        cols = st.columns(len(people) + 1)
        for col, pid in zip(cols, people):
            if col.button(f"Ask {fn.get(pid, pid)}", key=f"ask_{idx}_{pid}", icon=":material/person_search:",
                          type="primary" if a.action != Action.ANSWER else "secondary"):
                data.record_ask(turn["asker"], pid, turn["q"], note=f"Keepline action: {a.action}")
                st.toast(f"Sent to {names.get(pid, pid)}. Their reply becomes a new receipt.")
        if a.fact_ids and cols[-1].button("This is wrong", key=f"wrong_{idx}", icon=":material/flag:"):
            for fid in a.fact_ids:
                try:
                    store.set_review_status(fid, ReviewStatus.PENDING)  # back to the owner's review queue
                except Exception:  # noqa: BLE001
                    pass
            owner = next((c.author_id for c in a.said), None)
            if owner:
                data.record_ask(turn["asker"], owner, turn["q"], note="Flagged as wrong or outdated")
            st.toast("Flagged. The facts went back to their owner's review queue.")


prompt = st.chat_input("Ask about Harbourline's systems, vendors, decisions…")
q = prompt or (picked if picked and st.session_state.get("_last_pick") != picked else None)
if picked:
    st.session_state["_last_pick"] = picked
if q:
    ask(q)

if not st.session_state.chat:
    ui.empty_state("Ask anything", "Pick a suggested question above or type your own. Answers cite their sources, "
                   "or say who to ask.")
for i, turn in enumerate(st.session_state.chat):
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(f"**{names.get(turn['asker'], turn['asker'])}** · {turn['q']}")
    with st.chat_message("assistant", avatar=":material/link:"):
        render(turn, i)

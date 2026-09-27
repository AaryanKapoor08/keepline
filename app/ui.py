"""Keepline UI kit: CSS, page chrome, and small HTML components (cards, badges, citation cards, meters).

Design rules: deep navy + teal, one warning red reserved for risk; generous spacing; every claim shows its receipt.
Theme colors live in ``.streamlit/config.toml`` (repo root); these CSS tokens mirror them.
"""

from __future__ import annotations

import html
from datetime import date, datetime
from pathlib import Path
from typing import Any

import streamlit as st

from keepline.config import DEMO_COMPANY
from keepline.contracts import Citation

NAVY = "#0F2A44"
INK = "#10243A"
TEAL = "#0E7C7B"
TEAL_SOFT = "#E3F2F1"
RED = "#C8102E"
RED_SOFT = "#FBE9EC"
AMBER = "#B7791F"
MUTED = "#5B6B7C"
LINE = "#D8E0E8"
PAPER = "#FFFFFF"
LOW = (0xEE, 0xF2, 0xF5)
HIGH = (0xC8, 0x10, 0x2E)

# Series colors for system comparisons (validated for CVD/contrast with the dataviz palette validator).
SYSTEM_COLORS = {"plain": "#C27C1E", "keepline": "#3E6FC4", "keepline_rl": "#0F9E9A"}
SYSTEM_LABELS = {"plain": "Plain search", "keepline": "Keepline", "keepline_rl": "Keepline + RL"}

SOURCE_META = {
    "slack": ("Slack", "#4A154B"),
    "email": ("Email", "#1F4E79"),
    "ticket": ("Ticket", "#0E7C7B"),
    "doc": ("Doc", "#5B6B7C"),
    "interview": ("Interview", "#B7791F"),
}

CSS = f"""
<style>
.block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1240px; }}
[data-testid="stSidebar"] .kl-brand {{ font-weight: 800; font-size: 1.35rem; letter-spacing: -0.02em; color: #fff; }}
[data-testid="stSidebar"] .kl-brand span {{ color: #5CC8C2; }}
[data-testid="stSidebar"] .kl-tag {{ color: #A9BCCD; font-size: .82rem; margin-top: -.2rem; }}
.kl-clock {{ background: #17385A; border: 1px solid #2A4A6B; border-radius: 10px; padding: .6rem .8rem; margin: .6rem 0 .4rem; }}
.kl-clock .l {{ color: #A9BCCD; font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; }}
.kl-clock .v {{ color: #fff; font-weight: 700; font-size: 1.02rem; }}
.kl-kicker {{ color: {TEAL}; font-weight: 700; font-size: .78rem; text-transform: uppercase; letter-spacing: .12em; margin-bottom: .1rem; }}
.kl-title {{ color: {INK}; font-weight: 800; font-size: 2.05rem; letter-spacing: -0.025em; line-height: 1.15; margin: 0 0 .25rem; }}
.kl-sub {{ color: {MUTED}; font-size: 1.02rem; margin-bottom: 1.2rem; max-width: 820px; }}
.kl-card {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 12px; padding: 1rem 1.1rem; margin-bottom: .75rem;
           box-shadow: 0 1px 2px rgba(16,36,58,.04); }}
.kl-card h4 {{ margin: 0 0 .35rem; font-size: 1.02rem; color: {INK}; font-weight: 700; }}
.kl-card p {{ margin: .2rem 0; color: #22364B; font-size: .94rem; line-height: 1.45; }}
.kl-card .meta {{ color: {MUTED}; font-size: .82rem; }}
.kl-kpi {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 12px; padding: .85rem 1rem; height: 100%; }}
.kl-kpi .l {{ color: {MUTED}; font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }}
.kl-kpi .v {{ color: {INK}; font-size: 1.85rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.2; }}
.kl-kpi .s {{ color: {MUTED}; font-size: .8rem; }}
.kl-kpi.risk .v {{ color: {RED}; }}
.kl-kpi.good .v {{ color: {TEAL}; }}
.kl-badge {{ display: inline-block; padding: .12rem .5rem; border-radius: 999px; font-size: .72rem; font-weight: 700;
            letter-spacing: .03em; margin-right: .3rem; vertical-align: middle; white-space: nowrap; }}
.kl-badge.teal {{ background: {TEAL_SOFT}; color: {TEAL}; }}
.kl-badge.red {{ background: {RED_SOFT}; color: {RED}; }}
.kl-badge.navy {{ background: #E4EBF2; color: {NAVY}; }}
.kl-badge.grey {{ background: #EEF1F4; color: {MUTED}; }}
.kl-badge.amber {{ background: #FBF1E0; color: {AMBER}; }}
.kl-badge.solid-red {{ background: {RED}; color: #fff; }}
.kl-badge.solid-teal {{ background: {TEAL}; color: #fff; }}
.kl-banner {{ background: {NAVY}; color: #fff; border-radius: 14px; padding: 1.1rem 1.3rem; margin-bottom: 1rem;
             display: flex; gap: 1.6rem; flex-wrap: wrap; align-items: center; }}
.kl-banner .item {{ min-width: 180px; }}
.kl-banner .n {{ font-size: 2rem; font-weight: 800; line-height: 1; }}
.kl-banner .n.red {{ color: #FF6B7F; }}
.kl-banner .n.teal {{ color: #5CC8C2; }}
.kl-banner .t {{ color: #C6D3E0; font-size: .86rem; margin-top: .25rem; }}
.kl-cite {{ border: 1px solid {LINE}; border-left: 4px solid {TEAL}; background: {PAPER}; border-radius: 10px;
           padding: .6rem .8rem; margin: .45rem 0; }}
.kl-cite.stale {{ border-left-color: #A0AEBB; background: #F7F8FA; }}
.kl-cite .q {{ color: {INK}; font-size: .93rem; line-height: 1.4; }}
.kl-cite.stale .q {{ color: {MUTED}; text-decoration: line-through; text-decoration-color: #A0AEBB; }}
.kl-cite .by {{ color: {MUTED}; font-size: .78rem; margin-top: .3rem; }}
.kl-cite .by a {{ color: {TEAL}; text-decoration: none; font-weight: 600; }}
.kl-src {{ display: inline-block; font-size: .68rem; font-weight: 800; color: #fff; border-radius: 4px; padding: .05rem .35rem;
          margin-right: .35rem; letter-spacing: .04em; text-transform: uppercase; }}
.kl-meter {{ height: 8px; background: #E6ECF1; border-radius: 999px; overflow: hidden; margin: .25rem 0 .1rem; }}
.kl-meter > div {{ height: 100%; border-radius: 999px; }}
.kl-tiles {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(215px, 1fr)); gap: .7rem; margin-bottom: 1rem; }}
.kl-tile {{ border-radius: 12px; padding: .8rem .9rem; min-height: 118px; border: 1px solid rgba(16,36,58,.08); }}
.kl-tile .nm {{ font-weight: 700; font-size: .95rem; line-height: 1.2; }}
.kl-tile .rk {{ font-size: 1.6rem; font-weight: 800; letter-spacing: -0.02em; margin-top: .35rem; }}
.kl-tile .ft {{ font-size: .78rem; opacity: .9; margin-top: .15rem; }}
.kl-layer {{ font-size: .74rem; text-transform: uppercase; letter-spacing: .1em; font-weight: 800; margin: .9rem 0 .3rem; }}
.kl-layer.said {{ color: {TEAL}; }} .kl-layer.inf {{ color: {AMBER}; }} .kl-layer.none {{ color: {MUTED}; }}
.kl-answer {{ font-size: 1.12rem; color: {INK}; line-height: 1.5; font-weight: 500; }}
.kl-step {{ border-left: 2px solid {LINE}; padding: 0 0 .9rem 1rem; margin-left: .45rem; position: relative; }}
.kl-step::before {{ content: ""; position: absolute; left: -7px; top: .25rem; width: 12px; height: 12px; border-radius: 50%;
                   background: #A0AEBB; }}
.kl-step.current::before {{ background: {TEAL}; box-shadow: 0 0 0 4px {TEAL_SOFT}; }}
.kl-step.replaced .txt {{ color: {MUTED}; text-decoration: line-through; text-decoration-color: #A0AEBB; }}
.kl-step .txt {{ font-size: .96rem; color: {INK}; }}
.kl-step .d {{ font-size: .78rem; color: {MUTED}; }}
.kl-empty {{ border: 1.5px dashed #B8C5D1; border-radius: 14px; padding: 1.6rem; text-align: center; background: #FAFBFC; }}
.kl-empty h4 {{ margin: 0 0 .3rem; color: {INK}; }}
.kl-empty p {{ color: {MUTED}; margin: .2rem 0; }}
.kl-empty code {{ background: #EEF2F5; padding: .15rem .4rem; border-radius: 6px; }}
.kl-muted {{ color: {MUTED}; font-size: .86rem; }}
.kl-private {{ background: #F1F6F9; border: 1px solid {LINE}; color: {NAVY}; border-radius: 10px; padding: .55rem .8rem;
              font-size: .86rem; margin-bottom: .8rem; }}
div[data-testid="stExpander"] details {{ border-radius: 10px; background: {PAPER}; }}
div[data-testid="stVerticalBlockBorderWrapper"] {{ background: {PAPER}; }}
</style>
"""


def h(s: Any) -> str:
    return html.escape(str(s), quote=True)


def md(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def inject_css() -> None:
    md(CSS)


# ------------------------------------------------------------------------------------------------ chrome


def page(title: str, subtitle: str = "", kicker: str = "") -> None:
    """Page header. When a view runs standalone (tests, direct run) it also draws the CSS + sidebar itself."""
    if not st.session_state.get("_kl_nav"):
        inject_css()
        sidebar()
    if kicker:
        md(f'<div class="kl-kicker">{h(kicker)}</div>')
    md(f'<div class="kl-title">{h(title)}</div>')
    if subtitle:
        md(f'<div class="kl-sub">{h(subtitle)}</div>')


def sidebar() -> None:
    from app import data

    logo = Path(__file__).resolve().parent / "static" / "keepline_logo.svg"
    if logo.exists():
        st.logo(str(logo), size="large")
    with st.sidebar:
        md('<div class="kl-tag">Receipts, not clones.</div>')
        today = data.today()
        md(f'<div class="kl-clock"><div class="l">Demo clock</div><div class="v">{today:%a %b %d, %Y}</div>'
           f'<div class="l" style="margin-top:.25rem;text-transform:none;letter-spacing:0">{h(DEMO_COMPANY)} · Halifax</div></div>')
        status = data.pipeline_status()
        dots = " ".join(
            f'<span class="kl-badge {"teal" if ok else "grey"}">{"●" if ok else "○"} {h(name)}</span>'
            for name, ok in status.items()
        )
        md(f'<div style="margin:.3rem 0 .6rem">{dots}</div>')
        with st.expander("Presenter flow", expanded=False):
            st.markdown(
                "1. **Home**: *When Sarah leaves Friday, what breaks Monday?*\n"
                "2. **Risk Map**: red areas, bus factor 1, countdown\n"
                "3. **Handoff Pack**: Sarah reviews and signs off\n"
                "4. **Ask** as Alex: said / inferred / no evidence, then *ask Mike*\n"
                "5. **Decision History**, **Proof**, what-if\n"
                "6. Close: *everything runs inside Snowflake*"
            )


# ------------------------------------------------------------------------------------------------ components


def badge(text: str, tone: str = "navy") -> str:
    return f'<span class="kl-badge {tone}">{h(text)}</span>'


def kpi(label: str, value: Any, sub: str = "", tone: str = "") -> str:
    return f'<div class="kl-kpi {tone}"><div class="l">{h(label)}</div><div class="v">{h(value)}</div><div class="s">{h(sub)}</div></div>'


def kpi_row(items: list[tuple[str, Any, str, str]]) -> None:
    cols = st.columns(len(items))
    for col, (label, value, sub, tone) in zip(cols, items):
        with col:
            md(kpi(label, value, sub, tone))


def card(title: str, body_html: str = "", meta: str = "", badges: str = "") -> None:
    md(f'<div class="kl-card"><h4>{badges}{h(title)}</h4>{body_html}{f"<div class=meta>{meta}</div>" if meta else ""}</div>')


def empty_state(title: str, body: str, cmd: str | None = None) -> None:
    code = f"<p><code>{h(cmd)}</code></p>" if cmd else ""
    md(f'<div class="kl-empty"><h4>{h(title)}</h4><p>{h(body)}</p>{code}</div>')


def need_pipeline() -> None:
    empty_state(
        "Run the pipeline first",
        "Keepline has no memory built yet. Generate the Harbourline data and build the graph, then refresh.",
        "python -m keepline.data.build && python -m keepline.memory.build --llm none",
    )


def risk_rgb(risk: float) -> str:
    t = max(0.0, min(1.0, risk / 0.85))
    r, g, b = (round(LOW[i] + (HIGH[i] - LOW[i]) * t) for i in range(3))
    return f"#{r:02X}{g:02X}{b:02X}"


def risk_tone(level: str) -> str:
    return {"high": "solid-red", "medium": "red", "low": "grey"}.get(level, "grey")


def meter(value: float, color: str = TEAL) -> str:
    pct = max(0, min(100, round(value * 100)))
    return f'<div class="kl-meter"><div style="width:{pct}%;background:{color}"></div></div>'


def source_of(doc_id: str) -> str:
    head = doc_id.split("-", 1)[0].lower()
    return {"dm": "slack", "jira": "ticket", "wiki": "doc"}.get(head, head)


def source_tag(source: str) -> str:
    label, color = SOURCE_META.get(source, (source.title() or "Source", MUTED))
    return f'<span class="kl-src" style="background:{color}">{h(label)}</span>'


def fmt_date(x: date | datetime | None) -> str:
    if x is None:
        return "—"
    return f"{x:%b %d, %Y}"


def citation_card(c: Citation, names: dict[str, str], replaced_by: str | None = None, source: str | None = None) -> str:
    """One receipt: quote, who, when, where -- and a 'replaced by' badge when the fact is no longer current."""
    stale = not c.is_current
    src = source or source_of(c.doc_id)
    link = f'<a href="{h(c.url)}" target="_blank">open</a>' if c.url else ""
    rep = ""
    if stale:
        rep = badge("REPLACED", "grey") + (f'<span class="kl-muted">by: {h(replaced_by)}</span>' if replaced_by else "")
    return (
        f'<div class="kl-cite{" stale" if stale else ""}"><div class="q">“{h(c.quote)}”</div>'
        f'<div class="by">{source_tag(src)}<b>{h(names.get(c.author_id, c.author_id))}</b> · {fmt_date(c.timestamp)} · '
        f'<span style="font-family:monospace">{h(c.doc_id)}</span> {link} {rep}</div></div>'
    )


def citations_html(cits: list[Citation], names: dict[str, str]) -> str:
    return "".join(citation_card(c, names) for c in cits) or '<div class="kl-muted">No receipts attached.</div>'


def initials(name: str) -> str:
    return "".join(p[0] for p in name.split()[:2]).upper()

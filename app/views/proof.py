"""Proof: benchmark against a plain-search baseline, graded against a hidden truth file. N on every number."""

from __future__ import annotations

import sys
from pathlib import Path

_R = Path(__file__).resolve().parents[2]
if str(_R) not in sys.path:
    sys.path.insert(0, str(_R))

from typing import Any  # noqa: E402

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import data, ui  # noqa: E402

ui.page(
    "Proof",
    "A synthetic credit union is generated truth-first; Keepline only sees the rendered Slack, email and tickets. "
    "Answers are graded against the hidden truth. Same questions, same corpus, plain search as the baseline.",
    kicker="Trust",
)

METRICS = [
    ("accuracy_cited", "Correct with a valid citation", True),
    ("hallucination_rate", "Hallucination rate", False),
    ("abstain_precision", "Abstain precision", True),
    ("current_fact_accuracy", "Current-fact accuracy", True),
    ("routing_accuracy", "Routing accuracy", True),
    ("citation_valid_rate", "Valid citations", True),
]

splits = [s for s in ("test", "dev") if data.results_json(f"benchmark_{s}.json")]
if not splits:
    ui.empty_state("No benchmark results yet", "Run the evaluation to produce data/results/benchmark_dev.json.",
                   "python -m keepline.rl.train && python -m keepline.eval.benchmark --split dev")
    st.stop()

split = st.segmented_control("Split", splits, default=splits[-1] if "dev" in splits else splits[0], key="split") or splits[0]
bench: dict[str, Any] = data.results_json(f"benchmark_{split}.json") or {}
systems: dict[str, Any] = bench.get("systems", {})
order = [s for s in ("plain", "keepline", "keepline_rl") if s in systems] + [s for s in systems if s not in ui.SYSTEM_COLORS]
label = {s: ui.SYSTEM_LABELS.get(s, s) for s in order}
colors = [ui.SYSTEM_COLORS.get(s, ui.MUTED) for s in order]


def val(sys_: str, key: str) -> dict[str, Any]:
    m = systems.get(sys_, {}).get(key) or {}
    return m if isinstance(m, dict) else {"value": m}


best = "keepline_rl" if "keepline_rl" in systems else ("keepline" if "keepline" in systems else (order[-1] if order else None))
st.caption(f"Split **{split}** · N = {bench.get('n_questions', '?')} questions · LLM: {bench.get('llm', 'none')} · "
           f"generated {str(bench.get('generated_at', ''))[:16].replace('T', ' ')}")


def pct(m: dict[str, Any]) -> str:
    v = m.get("value")
    return "—" if v is None else f"{v:.0%}"


if best:
    base = "plain" if "plain" in systems else None
    tiles = []
    for key, name, _ in METRICS[:4]:
        m = val(best, key)
        delta = ""
        if base and m.get("value") is not None and val(base, key).get("value") is not None:
            delta = f"plain search {pct(val(base, key))} · "
        tiles.append((name, pct(m), f"{delta}N={m.get('n', '?')}", "risk" if key == "hallucination_rate" else "good"))
    ui.kpi_row(tiles)
    st.write("")

# --- grouped bars with CI ----------------------------------------------------------------------------------------
rows = []
for key, name, _ in METRICS:
    for s in order:
        m = val(s, key)
        if m.get("value") is None:
            continue
        ci = m.get("ci95") or [m["value"], m["value"]]
        rows.append({"Metric": name, "System": label[s], "Value": m["value"], "lo": ci[0], "hi": ci[1],
                     "N": m.get("n", 0), "k": m.get("k", "")})
if rows:
    df = pd.DataFrame(rows)
    sys_scale = alt.Scale(domain=[label[s] for s in order], range=colors)
    base_c = alt.Chart(df).encode(y=alt.Y("System:N", title=None, sort=[label[s] for s in order], axis=None))
    bars = base_c.mark_bar(cornerRadiusEnd=4, height=14).encode(
        x=alt.X("Value:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", tickCount=5), title=None),
        color=alt.Color("System:N", scale=sys_scale, legend=alt.Legend(orient="top", title=None)),
        tooltip=["Metric", "System", alt.Tooltip("Value:Q", format=".1%"), "k", "N",
                 alt.Tooltip("lo:Q", format=".1%", title="95% CI low"), alt.Tooltip("hi:Q", format=".1%", title="95% CI high")],
    )
    err = base_c.mark_rule(color=ui.INK, strokeWidth=1.5, opacity=0.6).encode(x="lo:Q", x2="hi:Q")
    txt = base_c.mark_text(align="left", dx=4, fontSize=11, color=ui.MUTED).transform_calculate(
        t="format(datum.Value, '.0%') + '  N=' + datum.N").encode(x="hi:Q", text="t:N")
    chart = (bars + err + txt).properties(height=58, width=300).facet(
        facet=alt.Facet("Metric:N", title=None, sort=[m[1] for m in METRICS], header=alt.Header(labelFontWeight="bold", labelAnchor="start")),
        columns=3,
    )
    st.markdown("#### Keepline vs plain search")
    st.altair_chart(chart, width="content")
    st.caption("Error bars: 95% Wilson intervals. Hallucination rate: lower is better. N is the denominator for each metric.")

left, right = st.columns(2, gap="large")

# --- reward curve ------------------------------------------------------------------------------------------------
with left:
    st.markdown("#### Learning to abstain: reward curve")
    curve = data.results_json("reward_curve.json")
    if curve and curve.get("rolling"):
        series_colors = {"bandit": "#0F9E9A", "default": "#3E6FC4", "random": "#C27C1E", "oracle": ui.NAVY}
        long = [{"Step": i + 1, "Series": s, "Reward": v}
                for s, vals in curve["rolling"].items() if s in series_colors for i, v in enumerate(vals) if v is not None]
        cdf = pd.DataFrame(long)
        line = alt.Chart(cdf).mark_line(strokeWidth=2).encode(
            x=alt.X("Step:Q", title="training step"), y=alt.Y("Reward:Q", title=f"rolling mean reward (window {curve.get('window', '?')})"),
            color=alt.Color("Series:N", scale=alt.Scale(domain=list(series_colors), range=list(series_colors.values())),
                            legend=alt.Legend(orient="top", title=None)),
            strokeDash=alt.condition(alt.FieldOneOfPredicate("Series", ["oracle", "random"]), alt.value([4, 3]), alt.value([1, 0])),
            tooltip=["Series", "Step", alt.Tooltip("Reward:Q", format=".3f")],
        )
        st.altair_chart(line.properties(height=280), width="stretch")
        fin = curve.get("final", {})
        st.caption(f"N = {curve.get('n_train', '?')} training questions × {curve.get('epochs', '?')} epochs. Final mean reward: "
                   + " · ".join(f"{k} {v:.2f}" for k, v in fin.items() if isinstance(v, (int, float))))
        bandit = data.results_json("bandit.json")
        if bandit and bandit.get("dev"):
            d = bandit["dev"]
            st.caption(f"Dev (N={d.get('n', '?')}): bandit {d.get('bandit', 0):.2f} vs default {d.get('default', 0):.2f} "
                       f"vs best fixed arm {d.get('best_fixed', 0):.2f}.")
    elif (png := data.results_png("reward_curve.png")):
        st.image(str(png))
    else:
        st.caption("Run `python -m keepline.rl.train` to produce the reward curve.")
    st.markdown("Reward: **+1.0** correct with citation · **+0.5** correct abstain/route · **−0.3** unnecessary abstain · "
                "**−2.0** confident wrong answer · **+0.2 × (1 − |conf − correct|)** calibration.")

# --- calibration -------------------------------------------------------------------------------------------------
with right:
    st.markdown("#### Calibration")
    cal = []
    for s in order:
        for b in systems[s].get("reliability_bins") or []:
            if b.get("n"):
                cal.append({"System": label[s], "Confidence": b["confidence"], "Accuracy": b["accuracy"], "N": b["n"]})
    if cal:
        cdf = pd.DataFrame(cal)
        diag = alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(color="#B8C5D1", strokeDash=[4, 3]).encode(x="x:Q", y="y:Q")
        pts = alt.Chart(cdf).mark_line(point=alt.OverlayMarkDef(size=60, filled=True), strokeWidth=2).encode(
            x=alt.X("Confidence:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%"), title="stated confidence"),
            y=alt.Y("Accuracy:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%"), title="actual accuracy"),
            color=alt.Color("System:N", scale=alt.Scale(domain=[label[s] for s in order], range=colors), legend=alt.Legend(orient="top", title=None)),
            tooltip=["System", alt.Tooltip("Confidence:Q", format=".0%"), alt.Tooltip("Accuracy:Q", format=".0%"), "N"],
        )
        st.altair_chart((diag + pts).properties(height=280), width="stretch")
        eces = " · ".join(f"{label[s]} ECE {val(s, 'ece').get('value', 0) or 0:.3f}" for s in order if val(s, "ece").get("value") is not None)
        st.caption(f"On the dashed line, confidence means what it says. {eces}")
    else:
        st.caption("No calibration bins in the results.")

# --- by question type + table ------------------------------------------------------------------------------------
with st.expander("By question type"):
    trs = []
    for s in order:
        for qt, m in (systems[s].get("by_qtype") or {}).items():
            cr = m.get("correct_rate") or {}
            hr = m.get("hallucination_rate") or {}
            trs.append({"System": label[s], "Question type": qt, "N": m.get("n"),
                        "Correct": cr.get("value") if isinstance(cr, dict) else cr,
                        "Hallucination": hr.get("value") if isinstance(hr, dict) else hr,
                        "Mean reward": (m.get("mean_reward") or {}).get("value") if isinstance(m.get("mean_reward"), dict) else m.get("mean_reward")})
    if trs:
        st.dataframe(pd.DataFrame(trs), hide_index=True, width="stretch",
                     column_config={"Correct": st.column_config.NumberColumn(format="percent"),
                                    "Hallucination": st.column_config.NumberColumn(format="percent")})
with st.expander("Table view of headline metrics"):
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

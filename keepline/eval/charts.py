"""Static PNG charts for the pitch deck / README (the Streamlit app renders its own interactive ones).

Design rules: one palette, one axis per chart, recessive grid, titles that state N, direct value labels on
bars (few bars, so no clutter), systems always in the same colour.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SYSTEM_LABELS = {"plain": "Plain search", "keepline": "Keepline (default policy)", "keepline_rl": "Keepline + RL"}
COLORS = {
    "plain": "#898781",  # muted gray: the status quo
    "keepline": "#2a78d6",
    "keepline_rl": "#eb6834",
    "bandit": "#eb6834",
    "default": "#2a78d6",
    "best_fixed": "#1baf7a",
    "random": "#898781",
    "oracle": "#4a3aa7",
}
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"


def _style(ax: Any, title: str, ylabel: str) -> None:
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=12)
    ax.set_ylabel(ylabel, color=INK2)
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2)


def _save(fig: Any, path: Path) -> Path:
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _grouped_bars(systems: Mapping[str, Any], metrics: list[tuple[str, str]], title: str, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    names = list(systems)
    width = 0.8 / max(1, len(names))
    for j, sys_name in enumerate(names):
        vals = [(systems[sys_name][m]["value"] or 0.0) * 100 for m, _ in metrics]
        xs = [i + (j - (len(names) - 1) / 2) * width for i in range(len(metrics))]
        bars = ax.bar(xs, vals, width * 0.92, color=COLORS.get(sys_name, "#2a78d6"),
                      label=SYSTEM_LABELS.get(sys_name, sys_name))  # fmt: skip
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels([f"{lbl}\n(N={systems[names[0]][m]['n']})" for m, lbl in metrics], color=INK2)
    ax.set_ylim(0, 110)
    _style(ax, title, "%")
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    return _save(fig, path)


def accuracy_chart(bench: Mapping[str, Any], out_dir: Path) -> Path:
    s = bench["systems"]
    metrics = [("accuracy_cited", "Correct + cited"), ("correct_action_rate", "Right action"),
               ("current_fact_accuracy", "Current-fact acc."), ("routing_accuracy", "Routing acc.")]  # fmt: skip
    n = bench["n_questions"]
    return _grouped_bars(s, metrics, f"Keepline vs plain search -- {bench['split']} split, N={n} questions",
                         out_dir / f"accuracy_{bench['split']}.png")  # fmt: skip


def hallucination_chart(bench: Mapping[str, Any], out_dir: Path) -> Path:
    s = bench["systems"]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    names = list(s)
    vals = [(s[k]["hallucination_rate"]["value"] or 0.0) * 100 for k in names]
    bars = ax.bar(range(len(names)), vals, 0.55, color=[COLORS.get(k, "#2a78d6") for k in names])
    for b, k, v in zip(bars, names, vals):
        n = s[k]["hallucination_rate"]["n"]
        ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%  (N={n} answered)", ha="center", fontsize=8, color=INK)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([SYSTEM_LABELS.get(k, k) for k in names], color=INK2)
    ax.set_ylim(0, max(vals + [10]) * 1.25)
    _style(ax, f"Confident wrong answers (hallucination + stale) -- {bench['split']}", "% of answered questions")
    return _save(fig, out_dir / f"hallucination_{bench['split']}.png")


def reliability_chart(bench: Mapping[str, Any], out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(5.2, 5.0))
    ax.plot([0, 1], [0, 1], color=GRID, linewidth=1.5, linestyle="--", label="Perfect calibration")
    for k, m in bench["systems"].items():
        pts = [(b["confidence"], b["accuracy"]) for b in m["reliability_bins"] if b["n"]]
        if not pts:
            continue
        xs, ys = zip(*pts)
        ece = m["ece"]
        ax.plot(xs, ys, marker="o", markersize=6, linewidth=2, color=COLORS.get(k, "#2a78d6"),
                label=f"{SYSTEM_LABELS.get(k, k)}  ECE={ece['value']:.2f} (N={ece['n']})")  # fmt: skip
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Stated confidence", color=INK2)
    _style(ax, f"Calibration (answered questions) -- {bench['split']}", "Observed accuracy")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    return _save(fig, out_dir / f"calibration_{bench['split']}.png")


def reward_curve_chart(curve: Mapping[str, Any], out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 4.8))
    labels = {"bandit": "Bandit (LinUCB)", "default": "Default policy", "best_fixed": "Best fixed arm (hindsight on train)",
              "random": "Random arm", "oracle": "Oracle (per-question best)"}  # fmt: skip
    for k in ("oracle", "best_fixed", "default", "random", "bandit"):
        ys = curve["rolling"].get(k)
        if ys:
            ax.plot(range(1, len(ys) + 1), ys, color=COLORS[k], linewidth=2.4 if k == "bandit" else 1.6,
                    linestyle=":" if k == "oracle" else "-", label=f"{labels[k]}  mean={curve['final'][k]:+.2f}")  # fmt: skip
    ax.set_xlabel(f"Training step ({curve['epochs']} passes over N={curve['n_train']} train questions)", color=INK2)
    _style(ax, f"Reward per decision, rolling mean (window {curve['window']})", "Reward")
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
    return _save(fig, out_dir / "reward_curve.png")

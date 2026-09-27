"""Chaos ladder benchmark: how much real-world mess can Keepline take before it breaks?

    python -m keepline.eval.robustness [--levels 0,1,2,3,4] [--systems plain,keepline,keepline_rl] [--limit N]

For each noise level (``keepline.data.noise``) we build a fresh memory (temp SQLite + index) from that corpus only,
answer the DEV split (never test) with each system, and grade against truth with the evidence map remapped through
the level's ``id_map`` (split/forwarded copies of an evidence doc count as valid citations; dropped docs do not).
Output: ``data/results/robustness.json`` + ``data/results/robustness.png``. Offline, deterministic, no LLM.
"""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from keepline.config import RESULTS_DIR
from keepline.contracts import Answer, PolicyParams, Question, Split, to_json
from keepline.data.noise import LEVELS, NOISE_DIR, build_ladder, remap_evidence
from keepline.eval.benchmark import make_row
from keepline.eval.grader import grade
from keepline.eval.metrics import summarize
from keepline.eval.world import load_world

log = logging.getLogger(__name__)
OUT_JSON = RESULTS_DIR / "robustness.json"
OUT_PNG = RESULTS_DIR / "robustness.png"
HEADLINE = ("accuracy_cited", "hallucination_rate", "abstain_precision", "current_fact_accuracy", "mean_reward")


def _answer_fns(agent: Any, index: Any, store: Any, systems: Sequence[str]) -> dict[str, Any]:
    from keepline.eval.baseline import PlainSearchBaseline

    fns: dict[str, Any] = {}
    if "plain" in systems:
        base = PlainSearchBaseline(index, store)
        fns["plain"] = lambda q: base.answer(q.text, q.asker_id, as_of=q.as_of)
    if "keepline" in systems:
        fns["keepline"] = lambda q: agent.answer(q.text, q.asker_id, as_of=q.as_of, params=PolicyParams())
    if "keepline_rl" in systems:
        try:
            from keepline.rl.policy import bandit_context, load_arm_policy

            arm_policy = load_arm_policy()
        except Exception as exc:  # noqa: BLE001
            log.warning("keepline_rl unavailable: %s", exc)
            arm_policy = None
        if arm_policy is not None:
            def rl(q: Question) -> Answer:
                arm = arm_policy(bandit_context(agent, q.text, q.asker_id, q.as_of))
                return agent.answer(q.text, q.asker_id, as_of=q.as_of, params=arm.params())

            fns["keepline_rl"] = rl
    return fns


def run_level(level: int, questions: Sequence[Question], world: Any, systems: Sequence[str],
              noise_root: Path = NOISE_DIR) -> dict[str, Any]:
    from keepline.agent.answer import AnswerAgent
    from keepline.io import load_areas, load_corpus, load_people
    from keepline.memory.build import build_memory
    from keepline.memory.store import MemoryStore

    ldir = noise_root / f"L{level}"
    id_map = json.loads((ldir / "id_map.json").read_text(encoding="utf-8"))
    ev = remap_evidence(world.ev, id_map)
    cfg = json.loads((ldir / "noise_config.json").read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"keepline_L{level}_") as tmp:
        store = MemoryStore(Path(tmp) / "keepline.db")
        stats, index = build_memory(load_people(), load_areas(), load_corpus(ldir), store=store,
                                    index_path=Path(tmp) / "index.pkl")
        agent = AnswerAgent(store, index)
        out: dict[str, Any] = {}
        for name, fn in _answer_fns(agent, index, store, systems).items():
            rows = [make_row(name, q, a, grade(q, a, world.truth, ev, people=world.people), "robustness")
                    for q in questions for a in [fn(q)]]
            s = summarize(rows)
            out[name] = {k: s[k] for k in (*HEADLINE, "n_questions", "stale_rate", "answer_rate", "outcomes")}
        store.conn.close()
    return {"level": level, "config": cfg["config"], "n_docs": cfg["n_docs"],
            "facts_extracted": getattr(stats, "facts_kept", None), "examples": cfg["examples"],
            "seconds": round(time.perf_counter() - t0, 1), "systems": out}


def _val(m: Any) -> float | None:
    if isinstance(m, dict):
        return m.get("value", m.get("mean", m.get("p")))
    return m


def render_chart(result: dict[str, Any], path: Path = OUT_PNG) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    levels = [r["level"] for r in result["levels"]]
    systems = sorted({s for r in result["levels"] for s in r["systems"]})
    n = result["levels"][0]["systems"][systems[0]]["n_questions"] if systems else 0
    fig, axes = plt.subplots(1, len(HEADLINE), figsize=(4 * len(HEADLINE), 3.6))
    colors = {"plain": "#9a9a9a", "keepline": "#1f6feb", "keepline_rl": "#e36209"}
    for ax, metric in zip(axes, HEADLINE):
        for s in systems:
            ys = [_val(r["systems"][s][metric]) if s in r["systems"] else None for r in result["levels"]]
            ax.plot(levels, ys, marker="o", label=s, color=colors.get(s))
        ax.set_title(metric.replace("_", " "))
        ax.set_xticks(levels, [f"L{x}" for x in levels])
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Chaos ladder — dev split, N={n} questions per system per level (clean L0 → brutal L4)")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def run(levels: Sequence[int] = LEVELS, systems: Sequence[str] = ("plain", "keepline", "keepline_rl"),
        limit: int | None = None, seed: int = 7) -> dict[str, Any]:
    build_ladder(seed, tuple(levels))
    world = load_world()
    questions = world.questions(Split.DEV)  # NEVER the test split
    if limit:
        questions = questions[:limit]
    result = {"split": "dev", "seed": seed, "n_questions": len(questions),
              "levels": [run_level(lv, questions, world, systems) for lv in levels]}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(to_json(result, indent=2), encoding="utf-8")
    render_chart(result)
    return result


def format_table(result: dict[str, Any]) -> str:
    lines = ["level system        acc_cited halluc abst_prec current reward  N"]
    for r in result["levels"]:
        for s, m in r["systems"].items():
            v = [_val(m[k]) for k in HEADLINE]
            lines.append(f"L{r['level']}    {s:13} " + " ".join(
                f"{x:7.3f}" if isinstance(x, (int, float)) else "    n/a" for x in v) + f"  {m['n_questions']}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--levels", default="0,1,2,3,4")
    ap.add_argument("--systems", default="plain,keepline,keepline_rl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    res = run([int(x) for x in args.levels.split(",")], args.systems.split(","), args.limit, args.seed)
    print(format_table(res))


if __name__ == "__main__":
    main()

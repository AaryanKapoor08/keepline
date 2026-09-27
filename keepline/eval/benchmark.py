"""Truth-first benchmark: ``python -m keepline.eval.benchmark --split dev [--systems plain,keepline,keepline_rl]``.

Every system answers the same questions from the same rendered corpus and index; the grader compares each
answer to the truth file (never to what Keepline extracted). The TEST split is frozen: it runs only with
``--i-know-this-is-final``, only if its hash still verifies, and every run is appended to
``data/results/test_runs.log`` so the number of test runs is auditable.

Output ``data/results/benchmark_<split>.json`` (schema v1, read by the Streamlit app)::

    {
      "version": 1, "split": "dev", "generated_at": iso, "n_questions": int, "llm": "none",
      "systems": {
        "<plain|keepline|keepline_rl>": {           # see keepline.eval.metrics for exact definitions
          "n_questions": int,
          "<proportion metric>": {"value": float|None, "k": int, "n": int, "ci95": [lo, hi]|None},
              # accuracy_cited, correct_action_rate, hallucination_rate, abstain_precision, abstain_recall,
              # current_fact_accuracy, stale_rate, routing_accuracy, citation_valid_rate, answer_rate
          "mean_reward": {"value", "n", "ci95"},
          "ece": {"value", "n"}, "reliability_bins": [{"lo","hi","n","confidence","accuracy"}],
          "ece_uncalibrated": {"value", "n", "reliability_bins"} | null,   # agent's hand-set formula confidence
          "outcomes": {outcome: count},
          "by_qtype": {qtype: {"n","correct_rate","hallucination_rate","mean_reward","outcomes"}},
          "by_area":  {area_id: {...same...}}
        }
      },
      "bias_check": {...see bias_check()...},
      "judge_agreement": {...} | null,               # only with --judge
      "examples": {system: {outcome: [row, ...up to 3]}},   # same row schema as "rows"; for UI storytelling
      "rows": [{"system","qid","qtype","area_id","expected_action","question","asker_id","as_of","action",
                "answer","citations":[{"doc_id","quote","is_current"}],"route_to","confidence","outcome",
                "correct","citation_valid","reward","notes","arm"}]
    }
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from keepline.config import RESULTS_DIR
from keepline.contracts import Answer, Question
from keepline.eval.grader import grade, llm_judge
from keepline.eval.metrics import cohen_kappa, proportion, reliability, summarize
from keepline.eval.world import EvalWorld
from keepline.rl.rewards import Grade

log = logging.getLogger(__name__)

ALL_SYSTEMS = ("plain", "keepline", "keepline_rl")
TEST_LOG = RESULTS_DIR / "test_runs.log"
AnswerFn = Callable[[Question], tuple[Answer, str]]  # -> (answer, arm/policy label)


class SplitGuardError(RuntimeError):
    """Raised when someone tries to evaluate on TEST without the freeze check and explicit confirmation."""


def check_test_guard(split: str, confirmed: bool, verify: Callable[[], bool]) -> None:
    """The test set is for final numbers only: require an explicit flag and an intact hash."""
    if split != "test":
        return
    if not confirmed:
        raise SplitGuardError("refusing to run TEST without --i-know-this-is-final (use --split dev to iterate)")
    if not verify():
        raise SplitGuardError("TEST split hash does not match data/questions/test.sha256 -- it was modified")


def log_test_run(systems: Sequence[str], summary: Mapping[str, Any], path: Path = TEST_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"at": datetime.now().isoformat(timespec="seconds"), "systems": list(systems), "summary": summary}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


# --------------------------------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------------------------------


def make_row(system: str, q: Question, a: Answer, g: Grade, arm: str) -> dict[str, Any]:
    return {
        "system": system,
        "qid": q.id,
        "qtype": str(q.qtype),
        "area_id": q.area_id,
        "expected_action": str(q.expected_action),
        "question": q.text,
        "asker_id": q.asker_id,
        "as_of": q.as_of.isoformat(),
        "action": str(a.action),
        "answer": a.text[:800],
        "citations": [{"doc_id": c.doc_id, "quote": c.quote[:300], "is_current": c.is_current} for c in a.said],
        "route_to": list(a.route_to),
        "confidence": round(float(a.confidence), 4),
        "formula_confidence": _formula_conf(a),
        "outcome": str(g.outcome),
        "correct": g.correct,
        "citation_valid": g.citation_valid,
        "reward": round(g.reward, 4),
        "notes": g.notes,
        "arm": arm,
    }


def _formula_conf(a: Answer) -> float | None:
    """The agent's hand-set (uncalibrated) confidence, when it exposes one -- for the before/after ECE."""
    v = ((a.debug or {}).get("features") or {}).get("formula_confidence")
    return round(float(v), 4) if isinstance(v, (int, float)) else None


def run_system(name: str, answer_fn: AnswerFn, questions: Sequence[Question], world: EvalWorld) -> list[dict]:
    rows = []
    for q in questions:
        a, arm = answer_fn(q)
        rows.append(make_row(name, q, a, grade(q, a, world.truth, world.ev, people=world.people), arm))
    return rows


@dataclass
class Systems:
    fns: dict[str, AnswerFn]
    agent: Any
    env: Any  # AnswerEnv | None

    def save(self) -> None:
        if self.env is not None:
            self.env.save()


def build_systems(names: Sequence[str], llm: str, world: EvalWorld) -> Systems:
    """Answer functions for each requested system. Keepline systems go through the cached bandit env."""
    from keepline.eval.baseline import PlainSearchBaseline
    from keepline.eval.world import load_agent
    from keepline.rl.env import AnswerEnv
    from keepline.rl.policy import load_arm_policy

    agent = load_agent(llm)
    fns: dict[str, AnswerFn] = {}
    env: AnswerEnv | None = None
    if any(n != "plain" for n in names):
        env = AnswerEnv(agent, world.truth, world.ev, people=world.people)
    if "plain" in names:
        base = PlainSearchBaseline(agent.index, getattr(agent, "store", None))
        fns["plain"] = lambda q: (base.answer(q.text, q.asker_id, as_of=q.as_of), "top1")
    if "keepline" in names and env is not None:
        fns["keepline"] = lambda q: (env.answer(q, None), "default")
    if "keepline_rl" in names and env is not None:
        arm_policy = load_arm_policy()
        if arm_policy is None:
            log.warning("no trained bandit: keepline_rl == keepline default (run python -m keepline.rl.train)")

        def rl(q: Question) -> tuple[Answer, str]:
            arm = arm_policy(env.context(q)) if arm_policy else None
            return env.answer(q, arm), arm.key if arm else "default"

        fns["keepline_rl"] = rl
    return Systems(fns, agent, env)


# --------------------------------------------------------------------------------------------------
# Bias check: does expertise detection favour people who write a lot?
# --------------------------------------------------------------------------------------------------


def author_volume() -> dict[str, int]:
    from keepline.io import load_corpus

    return dict(Counter(d.author_id for d in load_corpus()))


def bias_check(
    world: EvalWorld,
    store: Any,
    rows: Sequence[Mapping[str, Any]],
    gold_routes: Mapping[str, Sequence[str]],
    volume: Mapping[str, int],
    top_k: int = 3,
) -> dict[str, Any]:
    """Expertise recall and routing accuracy split by how much each true expert writes.

    Ground truth for "who knows area X" = ``known_by`` of the in-corpus truth facts in X. A person is a *high*
    writer if their authored-doc count is >= the median over all authors. If Keepline only finds loud people,
    recall for low writers will be visibly worse -- that is the bias we are checking for.
    """
    if not volume:
        return {"available": False, "reason": "no corpus"}
    median = statistics.median(volume.values())
    group = lambda pid: "high_writers" if volume.get(pid, 0) >= median else "low_writers"  # noqa: E731
    knowers: dict[str, set[str]] = {}
    for f in world.truth.values():
        if f.in_corpus:
            knowers.setdefault(f.area_id, set()).update(f.known_by)
    hits: dict[str, list[bool]] = {"high_writers": [], "low_writers": []}
    try:
        for area, people in sorted(knowers.items()):
            ranked = sorted(store.expertise(area_id=area), key=lambda e: -e.score)
            top = {e.person_id for e in ranked[:top_k]}
            for pid in sorted(people):
                hits[group(pid)].append(pid in top)
        expertise_ok = True
    except Exception as exc:  # noqa: BLE001 -- the store may not expose expertise yet
        log.warning("bias check: expertise unavailable (%s)", exc)
        expertise_ok = False
    routing: dict[str, dict[str, list[bool]]] = {}
    for r in rows:
        if r["qtype"] != "routing":
            continue
        q_gold = gold_routes.get(r["qid"], [])
        if not q_gold:
            continue
        g = group(q_gold[0])
        routing.setdefault(r["system"], {"high_writers": [], "low_writers": []})[g].append(bool(r["correct"]))
    return {
        "available": True,
        "median_docs_authored": median,
        "definition": f"high_writers = authored docs >= median ({median}); expert found = in top-{top_k} of "
        "store.expertise(area)",
        "expertise_recall": {k: proportion(sum(v), len(v)) for k, v in hits.items()} if expertise_ok else None,
        "routing_accuracy": {s: {k: proportion(sum(v), len(v)) for k, v in d.items()} for s, d in routing.items()},
    }


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------


def judge_agreement(world: EvalWorld, questions: Sequence[Question], rows: Sequence[Mapping[str, Any]]) -> dict:
    """Keyword grader vs LLM judge on one system's answers (cached LLM calls; skipped if no LLM)."""
    by_id = {q.id: q for q in questions}
    ours, theirs = [], []
    for r in rows:
        q = by_id[r["qid"]]
        a = Answer(question=q.text, action=r["action"], text=r["answer"], route_to=r["route_to"])
        verdict = llm_judge(q, a, world.truth)
        if verdict is not None:
            ours.append(bool(r["correct"]))
            theirs.append(verdict)
    if not ours:
        return {"available": False}
    agree = sum(x == y for x, y in zip(ours, theirs))
    return {"available": True, "agreement": proportion(agree, len(ours)), "kappa": cohen_kappa(ours, theirs)}


def run_benchmark(split: str, systems: Sequence[str], llm: str = "none", judge: bool = False,
                  confirmed: bool = False, charts: bool = True) -> dict[str, Any]:  # fmt: skip
    from keepline.data.truth_io import verify_test_frozen
    from keepline.eval.world import load_world

    check_test_guard(split, confirmed, verify_test_frozen)
    world = load_world()
    questions = world.questions(split)
    built = build_systems(systems, llm, world)
    rows: list[dict[str, Any]] = []
    per_system: dict[str, Any] = {}
    for name in systems:
        sys_rows = run_system(name, built.fns[name], questions, world)
        per_system[name] = summarize(sys_rows)
        per_system[name]["ece_uncalibrated"] = _uncalibrated_ece(sys_rows)
        rows += sys_rows
        log.info("%s: done (%d rows)", name, len(sys_rows))
    built.save()  # persist newly cached answers
    store = getattr(built.agent, "store", None)
    gold_routes = {q.id: list(q.gold_route_person_ids) for q in questions}
    bench = {
        "version": 1,
        "split": split,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_questions": len(questions),
        "llm": llm,
        "systems": per_system,
        "bias_check": bias_check(world, store, rows, gold_routes, author_volume()),
        "judge_agreement": None,
        "examples": examples(rows),
        "rows": rows,
    }
    if judge:
        target = "keepline_rl" if "keepline_rl" in systems else systems[-1]
        bench["judge_agreement"] = judge_agreement(world, questions, [r for r in rows if r["system"] == target])
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"benchmark_{split}.json").write_text(json.dumps(bench, indent=1), encoding="utf-8")
    if charts:
        render_charts(bench)
    if split == "test":
        log_test_run(systems, {k: _headline(v) for k, v in per_system.items()})
    return bench


def render_charts(bench: Mapping[str, Any]) -> list[Path]:
    from keepline.eval import charts

    out = [charts.accuracy_chart(bench, RESULTS_DIR), charts.hallucination_chart(bench, RESULTS_DIR),
           charts.reliability_chart(bench, RESULTS_DIR)]  # fmt: skip
    curve_path = RESULTS_DIR / "reward_curve.json"
    if curve_path.exists():
        out.append(charts.reward_curve_chart(json.loads(curve_path.read_text(encoding="utf-8")), RESULTS_DIR))
    return out


def examples(rows: Sequence[Mapping[str, Any]], per_outcome: int = 3) -> dict[str, dict[str, list]]:
    """A few rows per (system, outcome), picked in question-id order so they are stable across runs."""
    out: dict[str, dict[str, list]] = {}
    for r in sorted(rows, key=lambda r: r["qid"]):
        bucket = out.setdefault(r["system"], {}).setdefault(r["outcome"], [])
        if len(bucket) < per_outcome:
            bucket.append(r)
    return out


def _uncalibrated_ece(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """ECE of the agent's formula confidence on the same answered rows (None if not exposed)."""
    swapped = [{**r, "confidence": r["formula_confidence"]} for r in rows if r.get("formula_confidence") is not None]
    if not swapped:
        return None
    ece, bins = reliability(swapped)
    return {**ece, "reliability_bins": bins}


def _headline(m: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("accuracy_cited", "correct_action_rate", "hallucination_rate", "abstain_precision",
            "current_fact_accuracy", "routing_accuracy", "mean_reward", "ece")  # fmt: skip
    return {k: {"value": m[k]["value"], "n": m[k]["n"]} for k in keys}


def format_table(bench: Mapping[str, Any]) -> str:
    keys = ("accuracy_cited", "correct_action_rate", "hallucination_rate", "abstain_precision", "abstain_recall",
            "current_fact_accuracy", "routing_accuracy", "mean_reward", "ece")  # fmt: skip
    names = list(bench["systems"])
    lines = [f"{'metric':<24}" + "".join(f"{n:>22}" for n in names)]
    for k in keys:
        cells = []
        for n in names:
            m = bench["systems"][n][k]
            v = "n/a" if m["value"] is None else f"{m['value']:.3f}"
            cells.append(f"{v + ' (N=' + str(m['n']) + ')':>22}")
        lines.append(f"{k:<24}" + "".join(cells))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Keepline truth-first benchmark")
    ap.add_argument("--split", choices=("dev", "test", "train"), default="dev")
    ap.add_argument("--systems", default=",".join(ALL_SYSTEMS))
    ap.add_argument("--llm", choices=("none", "auto"), default="none")
    ap.add_argument("--judge", action="store_true", help="also measure LLM-judge agreement (needs an LLM)")
    ap.add_argument("--no-charts", action="store_true")
    ap.add_argument("--i-know-this-is-final", dest="final", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    unknown = set(systems) - set(ALL_SYSTEMS)
    if unknown:
        ap.error(f"unknown systems: {sorted(unknown)}")
    try:
        bench = run_benchmark(args.split, systems, args.llm, args.judge, args.final, not args.no_charts)
    except SplitGuardError as exc:
        raise SystemExit(f"benchmark: {exc}") from exc
    print(f"split={bench['split']}  N={bench['n_questions']}  -> {RESULTS_DIR / ('benchmark_' + bench['split'] + '.json')}")
    print(format_table(bench))


if __name__ == "__main__":
    main()

"""Human spot-check of the grader: ``python -m keepline.eval.spotcheck [--split dev --system keepline_rl]``.

The keyword grader is only as good as its agreement with a person. This samples 30 answers from the benchmark
rows, stratified by grader outcome (so rare outcomes such as stale answers are represented), and writes
``data/results/spotcheck.csv`` with an empty ``human_grade`` column (1 = correct, 0 = wrong). After a human
fills it in, ``--score`` reports raw agreement and Cohen's kappa, which go on the "how do you know" slide.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from keepline.config import RESULTS_DIR
from keepline.eval.metrics import cohen_kappa, proportion

SPOTCHECK_PATH = RESULTS_DIR / "spotcheck.csv"
FIELDS = ("qid", "system", "qtype", "expected_action", "question", "action", "answer", "citations", "route_to",
          "auto_outcome", "auto_correct", "human_grade", "human_note")  # fmt: skip


def stratified_sample(rows: Sequence[Mapping[str, Any]], n: int, seed: int) -> list[Mapping[str, Any]]:
    """Round-robin over outcome strata (each shuffled with a seeded RNG) until n rows are picked."""
    rng = random.Random(seed)
    strata: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        strata[r["outcome"]].append(r)
    for key in sorted(strata):
        rng.shuffle(strata[key])
    picked: list[Mapping[str, Any]] = []
    while len(picked) < n and any(strata.values()):
        for key in sorted(strata):
            if strata[key] and len(picked) < n:
                picked.append(strata[key].pop())
    return sorted(picked, key=lambda r: r["qid"])


def to_csv_row(r: Mapping[str, Any]) -> dict[str, Any]:
    cites = " | ".join(f"{c['doc_id']}: {c['quote'][:160]}" for c in r.get("citations", []))
    return {
        "qid": r["qid"], "system": r["system"], "qtype": r["qtype"], "expected_action": r["expected_action"],
        "question": r["question"], "action": r["action"], "answer": r["answer"], "citations": cites,
        "route_to": ",".join(r.get("route_to", [])), "auto_outcome": r["outcome"],
        "auto_correct": int(bool(r["correct"])), "human_grade": "", "human_note": "",
    }  # fmt: skip


def _has_human_grades(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open(encoding="utf-8", newline="") as fh:
        return any((row.get("human_grade") or "").strip() for row in csv.DictReader(fh))


def write_spotcheck(rows: Sequence[Mapping[str, Any]], path: Path, n: int = 30, seed: int = 7,
                    force: bool = False) -> int:  # fmt: skip
    if _has_human_grades(path) and not force:
        raise SystemExit(f"{path} already has human grades; use --score, or --force to overwrite")
    sample = stratified_sample(rows, n, seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in sample:
            w.writerow(to_csv_row(r))
    return len(sample)


def score_spotcheck(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8", newline="") as fh:
        graded = [r for r in csv.DictReader(fh) if (r.get("human_grade") or "").strip() in {"0", "1"}]
    auto = [int(r["auto_correct"]) for r in graded]
    human = [int(r["human_grade"]) for r in graded]
    agree = sum(a == h for a, h in zip(auto, human))
    disagreements = [r["qid"] for r, a, h in zip(graded, auto, human) if a != h]
    return {"n": len(graded), "agreement": proportion(agree, len(graded)), "kappa": cohen_kappa(auto, human),
            "disagreements": disagreements}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Grader spot-check for human review")
    ap.add_argument("--split", default="dev", choices=("dev", "train"))
    ap.add_argument("--system", default="keepline_rl")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--score", action="store_true", help="compute grader-human agreement from the filled CSV")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if args.score:
        res = score_spotcheck(SPOTCHECK_PATH)
        (RESULTS_DIR / "spotcheck_score.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(f"grader-human agreement {res['agreement']['value']} kappa={res['kappa']} (N={res['n']})")
        return
    bench_path = RESULTS_DIR / f"benchmark_{args.split}.json"
    if not bench_path.exists():
        raise SystemExit(f"run python -m keepline.eval.benchmark --split {args.split} first")
    rows = [r for r in json.loads(bench_path.read_text(encoding="utf-8"))["rows"] if r["system"] == args.system]
    n = write_spotcheck(rows, SPOTCHECK_PATH, args.n, args.seed, args.force)
    print(f"wrote {n} rows -> {SPOTCHECK_PATH} (fill human_grade with 1/0, then --score)")


if __name__ == "__main__":
    main()

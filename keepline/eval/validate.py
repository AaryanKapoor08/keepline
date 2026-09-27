"""Sanity-check the eval world against the grader: ``python -m keepline.eval.validate``.

If the grader's keyword normalisation cannot find a gold answer inside the very documents that the truth file
says express it, every agent will be marked wrong on that question and we would blame the agent for a grading
bug. This reports, per split, how many ANSWER-type questions are *gradeable* (some evidence doc of a gold fact
satisfies the gold keywords) and whether forbidden (superseded) keywords collide with the current evidence.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from typing import Any

from keepline.contracts import Action, Question, SourceDoc
from keepline.eval.grader import cnf_match, normalize


def check_questions(questions: Sequence[Question], ev: Mapping[str, list[str]], docs: Mapping[str, SourceDoc]) -> dict:
    ungradeable, collisions, no_evidence = [], [], []
    n = 0
    for q in questions:
        if q.expected_action != Action.ANSWER:
            continue
        n += 1
        doc_ids = [d for f in q.gold_fact_ids for d in ev.get(f, [])]
        texts = [normalize(docs[d].text) for d in doc_ids if d in docs]
        if not texts:
            no_evidence.append(q.id)
            continue
        if q.gold_answer_keywords and not any(cnf_match(q.gold_answer_keywords, t) for t in texts):
            ungradeable.append(q.id)
        if q.forbidden_keywords and all(cnf_match(q.forbidden_keywords, t) for t in texts):
            collisions.append(q.id)
    return {"n_answer_questions": n, "no_evidence": no_evidence, "keywords_not_in_evidence": ungradeable,
            "forbidden_in_all_evidence": collisions}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--splits", default="train,dev")
    args = ap.parse_args(argv)
    from keepline.eval.world import load_world
    from keepline.io import load_corpus

    world = load_world()
    docs = {d.id: d for d in load_corpus()}
    report: dict[str, Any] = {}
    for split in args.splits.split(","):
        qs = world.questions(split)
        r = check_questions(qs, world.ev, docs)
        r["n_questions"] = len(qs)
        report[split] = r
        print(f"{split}: N={len(qs)} answer-type={r['n_answer_questions']} no_evidence={len(r['no_evidence'])} "
              f"kw_not_in_evidence={len(r['keywords_not_in_evidence'])} "
              f"forbidden_collisions={len(r['forbidden_in_all_evidence'])}")  # fmt: skip
    print(json.dumps({s: {k: v[:10] for k, v in r.items() if isinstance(v, list) and v} for s, r in report.items()}))


if __name__ == "__main__":
    main()

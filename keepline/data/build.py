"""Build the Harbourline synthetic company: org, truth, corpus, evidence map, question splits.

    python -m keepline.data.build [--seed 7] [--out data] [--mark-ready]

Truth-first: facts are written first (``facts_*.py``), the corpus is rendered from them, and questions are drawn
from them. Same seed => byte-identical files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

from keepline.config import DATA
from keepline.contracts import Split, SourceType, to_json, write_json, write_jsonl
from keepline.data.company import AREAS, PEOPLE
from keepline.data.questions import build_questions
from keepline.data.render import Renderer
from keepline.data.truth import load_specs, to_truth, truth_ids

log = logging.getLogger(__name__)
CORPUS_NAMES = {SourceType.SLACK: "slack", SourceType.EMAIL: "email", SourceType.TICKET: "tickets",
                SourceType.DOC: "docs", SourceType.INTERVIEW: "interviews"}


def build(seed: int = 7, out: Path = DATA) -> dict[str, object]:
    specs = load_specs()
    ids = truth_ids(specs)
    truth = to_truth(specs)

    write_json(out / "org" / "people.json", PEOPLE)
    write_json(out / "org" / "areas.json", AREAS)

    docs, evidence_by_key = Renderer(specs, seed=seed).render()
    counts: dict[str, int] = {}
    for st, name in CORPUS_NAMES.items():
        counts[name] = write_jsonl(out / "corpus" / f"{name}.jsonl", [d for d in docs if d.source_type is st])

    write_json(out / "truth" / "truth.json", truth)
    evidence = {ids[s.key]: evidence_by_key.get(s.key, []) for s in specs if s.in_corpus}
    (out / "truth" / "evidence_map.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    qs = build_questions(specs, ids, seed=seed)
    qdir = out / "questions"
    for split in Split:
        write_jsonl(qdir / f"{split.value}.jsonl", qs[split])
    digest = hashlib.sha256((qdir / "test.jsonl").read_bytes()).hexdigest()
    (qdir / "test.sha256").write_text(f"{digest}  test.jsonl\n", encoding="utf-8")

    return {
        "docs": counts,
        "truth_by_kind": dict(sorted(Counter(t.kind.value for t in truth).items())),
        "truth_total": len(truth),
        "in_corpus": sum(t.in_corpus for t in truth),
        "superseded": sum(t.valid_to is not None for t in truth),
        "landmines": sum(t.is_landmine for t in truth),
        "questions": {s.value: dict(sorted(Counter(q.qtype.value for q in qs[s]).items())) for s in Split},
        "question_totals": {s.value: len(qs[s]) for s in Split},
        "test_sha256": digest,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=DATA)
    ap.add_argument("--mark-ready", action="store_true", help="write data/READY_A.txt with counts")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = build(args.seed, args.out)
    text = to_json(summary, indent=2)
    print(text)
    if args.mark_ready:
        (args.out / "READY_A.txt").write_text(
            f"READY {datetime.now().isoformat(timespec='seconds')} seed={args.seed}\n{text}\n", encoding="utf-8")


if __name__ == "__main__":
    main()

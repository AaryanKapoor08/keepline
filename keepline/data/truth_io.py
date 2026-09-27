"""Loaders for the eval world (truth, evidence map, question splits). Only keepline.data/eval/rl may import this."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from keepline.config import QUESTIONS_DIR, TRUTH_DIR
from keepline.contracts import EvidenceMap, Question, Split, TruthFact, read_json_list, read_jsonl


def load_truth(truth_dir: Path = TRUTH_DIR) -> list[TruthFact]:
    return read_json_list(truth_dir / "truth.json", TruthFact)


def load_truth_by_id(truth_dir: Path = TRUTH_DIR) -> dict[str, TruthFact]:
    return {t.id: t for t in load_truth(truth_dir)}


def load_evidence_map(truth_dir: Path = TRUTH_DIR) -> EvidenceMap:
    return json.loads((truth_dir / "evidence_map.json").read_text(encoding="utf-8"))


def load_questions(split: Split | str, questions_dir: Path = QUESTIONS_DIR) -> list[Question]:
    return list(read_jsonl(questions_dir / f"{Split(split).value}.jsonl", Question))


def current_test_hash(questions_dir: Path = QUESTIONS_DIR) -> str:
    return hashlib.sha256((questions_dir / "test.jsonl").read_bytes()).hexdigest()


def verify_test_frozen(questions_dir: Path = QUESTIONS_DIR) -> bool:
    """True iff test.jsonl still matches the hash written at build time."""
    stored = (questions_dir / "test.sha256").read_text(encoding="utf-8").split()[0].strip()
    return stored == current_test_hash(questions_dir)

"""Truth-first guard: the product pipeline must never see the answer key.

Only ``keepline/data`` (which writes the truth) and ``keepline/eval`` / ``keepline/rl`` (which grade against it)
may reference ground truth or question files. If this test fails, the benchmark numbers are meaningless.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED = {"data", "eval", "rl"}
FORBIDDEN = re.compile(r"truth_io|TRUTH_DIR|QUESTIONS_DIR|TruthFact|evidence_map|data/truth|data/questions")


def _product_files() -> list[Path]:
    files = [p for p in (ROOT / "keepline").rglob("*.py") if p.parent.name not in ALLOWED]
    for extra in ("app", "api", "scripts"):
        files += list((ROOT / extra).rglob("*.py"))
    skip = {ROOT / "keepline" / "contracts.py", ROOT / "keepline" / "config.py"}  # define, never read
    return [p for p in files if p not in skip]


def test_product_code_never_touches_truth() -> None:
    offenders = [
        f"{p.relative_to(ROOT)}:{i}"
        for p in _product_files()
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if FORBIDDEN.search(line)
    ]
    assert not offenders, f"product code references ground truth: {offenders}"

"""One place that loads the eval world (truth, evidence, questions) and the product-world agent/index.

Kept separate so the benchmark, trainer and spot-check all see exactly the same inputs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from keepline.contracts import EvidenceMap, Question, Split, TruthFact

log = logging.getLogger(__name__)


@dataclass
class EvalWorld:
    truth: dict[str, TruthFact]
    ev: EvidenceMap
    people: dict[str, str]  # person id -> full name (lets graders accept "ask Sarah")

    def questions(self, split: Split | str) -> list[Question]:
        from keepline.data.truth_io import load_questions

        return list(load_questions(Split(split)))


def load_world() -> EvalWorld:
    from keepline.data.truth_io import load_evidence_map, load_truth
    from keepline.io import load_people

    try:
        people = {p.id: p.name for p in load_people()}
    except FileNotFoundError:
        people = {}
    return EvalWorld({f.id: f for f in load_truth()}, dict(load_evidence_map()), people)


def load_agent(llm: str = "none") -> Any:
    """The product agent. ``llm="none"`` forces the deterministic path (default for training/benchmarks)."""
    from keepline.agent.answer import load_default_agent

    agent = load_default_agent()
    if llm == "none" and hasattr(agent, "llm"):
        agent.llm = None
    return agent

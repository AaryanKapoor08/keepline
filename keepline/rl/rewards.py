"""Reward table for Keepline's decisions -- the single source of truth.

Everything that scores an answer (grader, bandit env, benchmark, app) imports from here, so the number a judge
sees in the app is the number the bandit optimised.

Table (ProjectSummary.md, "Reward table") plus the three outcomes it leaves open, decided here:

=====================  =======  ==========================================================================
Outcome                Reward   Why
=====================  =======  ==========================================================================
correct_cited          +1.0     the product promise: right answer *with a receipt*
correct_uncited        +0.2     right words but no valid receipt -- the user cannot verify it, so it is
                                barely better than silence; must stay well below +0.5 or the bandit would
                                learn to skip citations
correct_abstain        +0.5     "I don't know" when the corpus really does not know
correct_route          +0.5     "ask Mike" when Mike is (one of) the right people
unnecessary_abstain    -0.3     the answer was there; we wasted the asker's time
wrong_route            -0.3     same cost as an unnecessary abstain: someone else's time is wasted, but
                                nobody was told something false
hallucination          -2.0     confident wrong answer -- the failure that kills trust
stale_answer           -2.0     confident answer that *used to be* true; worst kind of wrong for a memory
                                product, so it is priced like a hallucination (not worse, to keep the
                                reward scale readable)
=====================  =======  ==========================================================================

Calibration bonus: ``+0.2 * (1 - |confidence - target|)`` where ``target`` is 1 if the claim the confidence
refers to was correct. ``Answer.confidence`` is the agent's P(its best corpus answer is correct), so:

* action ANSWER  -> target = 1 if the answer was graded correct else 0;
* action ABSTAIN/ROUTE -> target = 1 if a correct answer *was available* (expected action ANSWER) else 0.
  A correct abstain with low confidence earns the bonus; an unnecessary abstain with low confidence does not.

Rewards therefore lie in [-2.0, +1.2].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Outcome(StrEnum):
    CORRECT_CITED = "correct_cited"
    CORRECT_UNCITED = "correct_uncited"
    CORRECT_ABSTAIN = "correct_abstain"
    CORRECT_ROUTE = "correct_route"
    UNNECESSARY_ABSTAIN = "unnecessary_abstain"
    WRONG_ROUTE = "wrong_route"
    HALLUCINATION = "hallucination"
    STALE_ANSWER = "stale_answer"


BASE_REWARD: dict[Outcome, float] = {
    Outcome.CORRECT_CITED: 1.0,
    Outcome.CORRECT_UNCITED: 0.2,
    Outcome.CORRECT_ABSTAIN: 0.5,
    Outcome.CORRECT_ROUTE: 0.5,
    Outcome.UNNECESSARY_ABSTAIN: -0.3,
    Outcome.WRONG_ROUTE: -0.3,
    Outcome.HALLUCINATION: -2.0,
    Outcome.STALE_ANSWER: -2.0,
}

CALIBRATION_WEIGHT = 0.2

CORRECT_OUTCOMES = frozenset(
    {Outcome.CORRECT_CITED, Outcome.CORRECT_UNCITED, Outcome.CORRECT_ABSTAIN, Outcome.CORRECT_ROUTE}
)
WRONG_ANSWER_OUTCOMES = frozenset({Outcome.HALLUCINATION, Outcome.STALE_ANSWER})

REWARD_MIN = min(BASE_REWARD.values())
REWARD_MAX = max(BASE_REWARD.values()) + CALIBRATION_WEIGHT


@dataclass
class Grade:
    """The grader's verdict on one answer. ``reward`` is filled by :func:`reward` at grading time."""

    correct: bool
    citation_valid: bool
    outcome: Outcome
    reward: float = 0.0
    notes: list[str] = field(default_factory=list)
    calibration_target: float = 0.0  # see module docstring

    def to_dict(self) -> dict[str, object]:
        return {
            "correct": self.correct,
            "citation_valid": self.citation_valid,
            "outcome": str(self.outcome),
            "reward": round(self.reward, 4),
            "notes": list(self.notes),
            "calibration_target": self.calibration_target,
        }


def calibration_bonus(confidence: float, target: float) -> float:
    """Reward honest confidence: max bonus when confidence equals the (0/1) truth of the claim."""
    c = min(1.0, max(0.0, float(confidence)))
    return CALIBRATION_WEIGHT * (1.0 - abs(c - target))


def reward(grade: Grade, confidence: float) -> float:
    """Scalar reward for one graded decision: outcome base value + calibration bonus."""
    return BASE_REWARD[grade.outcome] + calibration_bonus(confidence, grade.calibration_target)

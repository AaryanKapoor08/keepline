"""Grader outcome table on tiny in-memory fixtures (no generated data, no LLM)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from keepline.contracts import Action, Answer, Citation, FactKind, QType, Question, Split, TruthFact
from keepline.eval.grader import cnf_match, grade, normalize
from keepline.rl.rewards import Outcome

TRUTH = {
    "T1": TruthFact("T1", FactKind.LANDMINE, "recon", "Recon skips the 1st and 15th.", [["1st"], ["15th"]],
                    ["sarah"], "sarah", date(2026, 6, 2), supersedes="T0"),
    "T0": TruthFact("T0", FactKind.LANDMINE, "recon", "Recon skips the 1st.", [["1st"]], ["sarah"], "sarah",
                    date(2026, 3, 1), valid_to=date(2026, 6, 2)),
}  # fmt: skip
EV = {"T1": ["slack-2"], "T0": ["slack-1"]}
PEOPLE = {"sarah": "Sarah Chen", "mike": "Mike Ross"}


def q(qtype: QType, expected: Action, **kw) -> Question:  # noqa: ANN003
    base = dict(id="Q1", split=Split.DEV, text="Which days does recon skip?", asker_id="alex",
                as_of=date(2026, 9, 1), qtype=qtype, area_id="recon", expected_action=expected)  # fmt: skip
    base.update(kw)
    return Question(**base)


def cite(doc_id: str, quote: str = "", current: bool = True) -> Citation:
    return Citation(doc_id, quote, "sarah", datetime(2026, 6, 2), "u", is_current=current)


CURRENT_Q = q(QType.CURRENT, Action.ANSWER, gold_fact_ids=["T1"], gold_answer_keywords=[["1st", "first"], ["15th"]],
              forbidden_keywords=[["only the 1st", "just the 1st"]])  # fmt: skip
UNANSWERABLE_Q = q(QType.UNANSWERABLE, Action.ABSTAIN, gold_route_person_ids=["mike"])
ROUTING_Q = q(QType.ROUTING, Action.ROUTE, gold_route_person_ids=["sarah"], gold_fact_ids=["T1"])


def ans(action: Action, text: str = "", said=(), route_to=(), conf: float = 0.8) -> Answer:  # noqa: ANN001
    return Answer("?", action, text, said=list(said), route_to=list(route_to), confidence=conf)


@pytest.mark.parametrize(
    ("question", "answer", "outcome"),
    [
        (CURRENT_Q, ans(Action.ANSWER, "It skips the first and the fifteenth.", [cite("slack-2")]), Outcome.CORRECT_CITED),
        (CURRENT_Q, ans(Action.ANSWER, "Skips the 1st and 15th."), Outcome.CORRECT_UNCITED),
        (CURRENT_Q, ans(Action.ANSWER, "Skips the 1st and 15th.", [cite("slack-1")]), Outcome.CORRECT_UNCITED),
        (CURRENT_Q, ans(Action.ANSWER, "It skips only the 1st.", [cite("slack-1")]), Outcome.STALE_ANSWER),
        (CURRENT_Q, ans(Action.ANSWER, "It runs every day."), Outcome.HALLUCINATION),
        (CURRENT_Q, ans(Action.ABSTAIN, "I don't know."), Outcome.UNNECESSARY_ABSTAIN),
        (CURRENT_Q, ans(Action.ROUTE, "Ask Sarah.", route_to=["sarah"]), Outcome.UNNECESSARY_ABSTAIN),
        (UNANSWERABLE_Q, ans(Action.ABSTAIN, "I don't know."), Outcome.CORRECT_ABSTAIN),
        (UNANSWERABLE_Q, ans(Action.ROUTE, "Ask Mike.", route_to=["mike"]), Outcome.CORRECT_ROUTE),
        (UNANSWERABLE_Q, ans(Action.ROUTE, "Ask Sarah.", route_to=["sarah"]), Outcome.WRONG_ROUTE),
        (UNANSWERABLE_Q, ans(Action.ANSWER, "The password is hunter2."), Outcome.HALLUCINATION),
        (ROUTING_Q, ans(Action.ROUTE, "Ask Sarah.", route_to=["sarah"]), Outcome.CORRECT_ROUTE),
        (ROUTING_Q, ans(Action.ROUTE, "Ask Mike.", route_to=["mike"]), Outcome.WRONG_ROUTE),
        (ROUTING_Q, ans(Action.ANSWER, "Sarah owns reconciliation.", [cite("slack-2")]), Outcome.CORRECT_CITED),
        (ROUTING_Q, ans(Action.ANSWER, "Sarah owns it."), Outcome.CORRECT_ROUTE),
        (ROUTING_Q, ans(Action.ANSWER, "Mike owns it."), Outcome.HALLUCINATION),
        (ROUTING_Q, ans(Action.ABSTAIN, "No idea."), Outcome.UNNECESSARY_ABSTAIN),
    ],
)
def test_outcome_table(question: Question, answer: Answer, outcome: Outcome) -> None:
    g = grade(question, answer, TRUTH, EV, people=PEOPLE)
    assert g.outcome == outcome, g.notes
    assert g.correct == (outcome in {Outcome.CORRECT_CITED, Outcome.CORRECT_UNCITED, Outcome.CORRECT_ABSTAIN,
                                     Outcome.CORRECT_ROUTE})  # fmt: skip


def test_history_citation_does_not_make_answer_stale() -> None:
    a = ans(Action.ANSWER, "Now the 1st and 15th.", [cite("slack-2"), cite("slack-1", "only the 1st", current=False)])
    assert grade(CURRENT_Q, a, TRUTH, EV).outcome == Outcome.CORRECT_CITED


def test_quotes_count_toward_match() -> None:
    a = ans(Action.ANSWER, "See the thread:", [cite("slack-2", "we now skip the 1st and 15th")])
    assert grade(CURRENT_Q, a, TRUTH, EV).outcome == Outcome.CORRECT_CITED


def test_normalization() -> None:
    assert normalize("Fifteenth, TWO keys; $1,000!") == "15th 2 key 1000"
    assert cnf_match([["1st", "first"], ["15th"]], normalize("the First and 15th"))
    assert not cnf_match([["1st"], ["15th"]], normalize("the 1st only"))
    assert not cnf_match([["key"]], normalize("keyboard"))  # token boundaries, not substrings
    assert not cnf_match([], normalize("anything"))


def test_calibration_target_and_reward() -> None:
    right = grade(CURRENT_Q, ans(Action.ANSWER, "1st and 15th", [cite("slack-2")], conf=1.0), TRUTH, EV)
    assert right.reward == pytest.approx(1.2)
    bluff = grade(UNANSWERABLE_Q, ans(Action.ANSWER, "hunter2", conf=0.9), TRUTH, EV)
    assert bluff.reward == pytest.approx(-2.0 + 0.2 * 0.1)
    honest = grade(UNANSWERABLE_Q, ans(Action.ABSTAIN, conf=0.0), TRUTH, EV)
    assert honest.reward == pytest.approx(0.7)
    lazy = grade(CURRENT_Q, ans(Action.ABSTAIN, conf=0.0), TRUTH, EV)
    assert lazy.reward == pytest.approx(-0.3)

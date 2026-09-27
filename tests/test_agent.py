"""AnswerAgent on the fixture: current facts, as_of, weekday reasoning, permissions, route, abstain."""

from __future__ import annotations

from datetime import date

import pytest

from keepline.agent.answer import AnswerAgent, calibrated_confidence
from keepline.contracts import Action, PolicyParams
from keepline.memory.build import build_memory
from keepline.memory.sample import sample_org
from keepline.memory.store import MemoryStore


@pytest.fixture(scope="module")
def agent(tmp_path_factory: pytest.TempPathFactory) -> AnswerAgent:
    tmp = tmp_path_factory.mktemp("agent")
    people, areas, docs = sample_org()
    store = MemoryStore(tmp / "k.db")
    _, index = build_memory(people, areas, docs, store=store, index_path=tmp / "idx.pkl")
    return AnswerAgent(store, index)


def test_answers_current_version(agent: AnswerAgent) -> None:
    a = agent.answer("When should the reconciliation job not run?", "alex", as_of=date(2026, 9, 15))
    assert a.action == Action.ANSWER and "15th" in a.text
    assert any(not c.is_current for c in a.said) and all(c.quote for c in a.said)
    assert a.area_id == "reconciliation"


def test_as_of_before_update(agent: AnswerAgent) -> None:
    a = agent.answer("When should the reconciliation job not run?", "alex", as_of=date(2026, 4, 1))
    assert a.action == Action.ANSWER and "1st" in a.text and "15th" not in a.text


def test_friday_reasoning(agent: AnswerAgent) -> None:
    fri = agent.answer("Can I rotate the CoreLink API key today?", "alex", as_of=date(2026, 9, 18))
    assert fri.action == Action.ANSWER and fri.text.startswith("No") and fri.inferred
    wed = agent.answer("Can I rotate the CoreLink API key today?", "alex", as_of=date(2026, 9, 16))
    assert not wed.text.startswith("No")


def test_permission_filter(agent: AnswerAgent) -> None:
    q = "Where are the Jenkins admin credentials?"
    assert "Engineering vault" not in agent.answer(q, "alex", as_of=date(2026, 9, 15)).text
    assert "Engineering vault" in agent.answer(q, "dana", as_of=date(2026, 9, 15)).text


def test_routing_question(agent: AnswerAgent) -> None:
    a = agent.answer("Who handles payroll?", "alex", as_of=date(2026, 9, 15))
    assert a.action == Action.ROUTE and a.route_to[0] == "priya"


def test_departed_expert_not_routed(agent: AnswerAgent) -> None:
    a = agent.answer("Who owns reconciliation?", "alex", as_of=date(2026, 9, 15))
    assert "sarah" not in a.route_to and "Sarah" in a.text  # mentioned as having left, never routed to


def test_abstain_on_unrelated(agent: AnswerAgent) -> None:
    a = agent.answer("What is the budget for the 2027 marketing campaign?", "alex", as_of=date(2026, 9, 15))
    assert a.action == Action.ABSTAIN and a.no_evidence_note


def test_thresholds_drive_action(agent: AnswerAgent) -> None:
    q = "Who is our contact at CoreLink?"
    never = agent.answer(q, "alex", as_of=date(2026, 9, 15), params=PolicyParams(abstain_threshold=1.01))
    assert never.action != Action.ANSWER


def test_features_and_determinism(agent: AnswerAgent) -> None:
    f = agent.context_features("Who handles payroll?", "alex", as_of=date(2026, 9, 15))
    assert all(isinstance(v, float) for v in f.values()) and f["is_routing"] == 1.0
    q = "When should the reconciliation job not run?"
    assert agent.answer(q, "alex", as_of=date(2026, 9, 15)).text == agent.answer(q, "alex", as_of=date(2026, 9, 15)).text


def test_confidence_monotone() -> None:
    base = {"coverage": 0.5, "kind_match": 0.0, "fact_conf": 0.5}
    assert calibrated_confidence({**base, "coverage": 0.9}) > calibrated_confidence(base)
    assert calibrated_confidence({**base, "contradicted": 1.0}) < calibrated_confidence(base)

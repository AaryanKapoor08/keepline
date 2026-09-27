"""ChatAgent on the fixture: offline router intents, reply shape, and the LLM tool loop with a fake client."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from keepline.agent.answer import AnswerAgent
from keepline.agent.chat import ChatAgent
from keepline.memory.build import build_memory
from keepline.memory.sample import sample_org
from keepline.memory.store import MemoryStore

TODAY = date(2026, 9, 15)
KEYS = {"text", "action", "citations", "route_to", "trace", "confidence"}


@pytest.fixture(scope="module")
def parts(tmp_path_factory: pytest.TempPathFactory):
    tmp = tmp_path_factory.mktemp("chat")
    people, areas, docs = sample_org()
    store = MemoryStore(tmp / "k.db")
    _, index = build_memory(people, areas, docs, store=store, index_path=tmp / "idx.pkl")
    return store, index, AnswerAgent(store, index)


def _ask(chat: ChatAgent, q: str) -> dict[str, Any]:
    out = chat.reply([{"role": "user", "content": q}], asker_id="alex", as_of=TODAY)
    assert set(out) == KEYS
    return out


def test_offline_answer_with_receipts(parts) -> None:
    out = _ask(ChatAgent(*parts), "When should the reconciliation job not run?")
    assert out["action"] == "answer" and "15th" in out["text"]
    assert out["citations"] and all(c["doc_id"] and c["author_name"] for c in out["citations"])


def test_offline_who_knows_and_history(parts) -> None:
    chat = ChatAgent(*parts)
    out = _ask(chat, "Who handles payroll?")
    assert "Priya" in out["text"] and "priya" in out["route_to"]
    hist = _ask(chat, "What changed about the reconciliation job schedule?")
    assert "was" in hist["text"] and any(not c["is_current"] for c in hist["citations"])


def test_offline_abstains(parts) -> None:
    out = _ask(ChatAgent(*parts), "What's the Bedford branch wifi password?")
    assert out["action"] in ("abstain", "route") and not out["citations"]


class _FakeMessages:
    """Scripted Claude: first asks for search_knowledge, then answers citing one real and one invented doc id."""

    def __init__(self) -> None:
        self.calls = 0

    def create(self, **kw: Any) -> Any:
        self.calls += 1
        assert kw["tools"] and "tool_choice" not in kw
        if self.calls == 1:
            block = SimpleNamespace(model_dump=lambda **_: {"type": "tool_use", "id": "tu1", "name": "search_knowledge",
                                                            "input": {"question": "When should the reconciliation job not run?"}})
            return SimpleNamespace(content=[block], stop_reason="tool_use")
        last = kw["messages"][-1]["content"][0]
        assert last["type"] == "tool_result" and last["tool_use_id"] == "tu1"
        text = "The job skips the 1st and 15th [s5]. Also see [slack-999999]."
        return SimpleNamespace(content=[SimpleNamespace(model_dump=lambda **_: {"type": "text", "text": text})],
                               stop_reason="end_turn")


def test_llm_loop_drops_unseen_citations(parts, monkeypatch) -> None:
    monkeypatch.setattr("keepline.agent.chat._cache_get", lambda key: None)
    monkeypatch.setattr("keepline.agent.chat._cache_put", lambda key, value: None)
    fake = _FakeMessages()
    chat = ChatAgent(*parts, llm_client=SimpleNamespace(messages=fake))
    out = chat.reply([{"role": "user", "content": "When is recon skipped?"}], asker_id="alex", as_of=TODAY)
    assert fake.calls == 2 and out["action"] == "answer"
    assert [c["doc_id"] for c in out["citations"]] == ["s5"] and "slack-999999" not in out["text"]
    assert out["trace"][0]["tool"] == "search_knowledge"

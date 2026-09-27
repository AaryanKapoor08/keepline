"""Every app page renders without exceptions -- with a (fake) memory, and with nothing built yet.

Uses ``streamlit.testing.v1.AppTest`` and swaps ``app.data`` accessors for the in-memory FakeStore, so the test
never touches the generated dataset or an LLM.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from app import data  # noqa: E402
from keepline.contracts import Action, Answer, Citation  # noqa: E402
from tests.test_products_fake import FakeStore  # noqa: E402

VIEWS = Path(__file__).resolve().parent.parent / "app" / "views"
PAGES = ["home", "risk_map", "handoff", "ask", "onboarding", "decisions", "my_knowledge", "proof"]

BENCH = {
    "split": "dev", "n_questions": 10, "llm": "none", "generated_at": "2026-09-26T23:00:00",
    "systems": {
        s: {
            "n_questions": 10,
            "accuracy_cited": {"value": v, "k": int(v * 10), "n": 10, "ci95": [v - 0.1, v + 0.1]},
            "hallucination_rate": {"value": 1 - v, "k": 1, "n": 10, "ci95": None},
            "ece": {"value": 0.1, "n": 10},
            "reliability_bins": [{"lo": 0, "hi": 0.5, "n": 4, "confidence": 0.3, "accuracy": 0.25},
                                 {"lo": 0.5, "hi": 1, "n": 6, "confidence": 0.8, "accuracy": 0.7}],
            "by_qtype": {"fact": {"n": 5, "correct_rate": {"value": v}, "hallucination_rate": {"value": 0.1},
                                  "mean_reward": {"value": 0.4}}},
        }
        for s, v in {"plain": 0.4, "keepline": 0.7, "keepline_rl": 0.8}.items()
    },
}
CURVE = {"steps": 3, "window": 2, "n_train": 3, "epochs": 1,
         "rolling": {"bandit": [0.1, 0.3, 0.5], "default": [0.2, 0.2, 0.2], "random": [-0.1, 0.0, -0.2]},
         "final": {"bandit": 0.3, "default": 0.2}}


class FakeAgent:
    def answer(self, question: str, asker_id: str, *, as_of: Any = None, params: Any = None) -> Answer:
        cit = Citation("slack-1", "must skip the 1st", "sarah", datetime(2026, 4, 2), "https://x", fact_id="F1", is_current=False)
        cur = Citation("slack-2", "must skip the 1st and 15th", "sarah", datetime(2026, 7, 15), "https://y", fact_id="F2")
        return Answer(question, Action.ANSWER, "It skips the 1st and 15th.", said=[cur, cit], inferred=["The rule changed in July."],
                      confidence=0.82, area_id="reconciliation", fact_ids=["F2"], route_to=["mike"])


@pytest.fixture()
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeStore:
    store = FakeStore()
    monkeypatch.setattr(data, "store", lambda: store)
    monkeypatch.setattr(data, "agent", lambda: FakeAgent())
    monkeypatch.setattr(data, "_db_version", lambda: -1.0)  # isolates st.cache_data entries from real runs
    monkeypatch.setattr(data, "results_json", lambda name: {"benchmark_dev.json": BENCH, "reward_curve.json": CURVE}.get(name))
    monkeypatch.setattr(data, "ASKS_PATH", tmp_path / "asks.json")
    monkeypatch.setattr(data, "SOURCE_PREFS_PATH", tmp_path / "prefs.json")
    from keepline.products import signoff

    monkeypatch.setattr(signoff, "SIGNOFF_PATH", tmp_path / "signoffs.json")
    return store


def _run(page: str) -> AppTest:
    return AppTest.from_file(str(VIEWS / f"{page}.py"), default_timeout=60).run()


def _errors(at: AppTest) -> list[str]:
    return [e.value for e in at.exception]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_with_memory(fake: FakeStore, page: str) -> None:
    at = _run(page)
    assert not _errors(at), _errors(at)
    text = " ".join(m.value for m in at.markdown)
    assert "Run the pipeline first" not in text
    assert "clone" not in text.lower().replace("receipts, not clones", "") and "digital twin" not in text.lower()


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_empty_state(monkeypatch: pytest.MonkeyPatch, page: str) -> None:
    monkeypatch.setattr(data, "store", lambda: None)
    monkeypatch.setattr(data, "_db_version", lambda: -2.0)
    monkeypatch.setattr(data, "results_json", lambda name: None)
    at = _run(page)
    assert not _errors(at), _errors(at)


def test_ask_renders_three_layers(fake: FakeStore) -> None:
    at = _run("ask")
    at.chat_input[0].set_value("Which days does recon skip?").run()
    assert not _errors(at), _errors(at)
    html = " ".join(m.value for m in at.markdown)
    assert "Said" in html and "Inferred" in html and "No evidence" in html and "REPLACED" in html
    assert any(b.label.startswith("Ask Mike") for b in at.button)


def test_whatif_toggle(fake: FakeStore) -> None:
    at = _run("risk_map")
    at.toggle(key="whatif_on").set_value(True).run()
    assert not _errors(at), _errors(at)
    assert any("would have nobody left" in w.value for w in at.warning)


def test_handoff_confirm_and_sign_off(fake: FakeStore) -> None:
    at = _run("handoff")
    confirm = next(b for b in at.button if b.label == "Confirm")
    confirm.click().run()
    assert not _errors(at), _errors(at)
    sign = next(b for b in at.button if b.label.startswith("Sign off"))
    sign.click().run()
    assert not _errors(at), _errors(at)
    assert any("SIGNED OFF" in m.value for m in at.markdown)

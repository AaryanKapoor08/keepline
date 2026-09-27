"""Data access for the app: cached store/agent singletons, cached product computations, result files.

Pages call only these helpers, so every page degrades to an empty state when the pipeline has not run yet.
Computations are cached on (demo date, DB modification time): reviews/sign-offs write to the DB, which bumps the
mtime and refreshes derived views without a manual cache clear.
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

from keepline.config import CORPUS_DIR, DEMO_TODAY, MEMORY_DB, MEMORY_DIR, ORG_DIR, RESULTS_DIR
from keepline.contracts import AreaRisk, HandoffPack, OnboardingBrief, Person

log = logging.getLogger(__name__)

ASKS_PATH = MEMORY_DIR / "asks.json"
SOURCE_PREFS_PATH = MEMORY_DIR / "source_prefs.json"
DEFAULT_SOURCES = {"public_channels": True, "team_channels": True, "email_threads": True, "tickets": True, "direct_messages": False}


def today() -> date:
    return st.session_state.get("demo_today", DEMO_TODAY)


def _db_version() -> float:
    try:
        return MEMORY_DB.stat().st_mtime
    except OSError:
        return 0.0


def pipeline_status() -> dict[str, bool]:
    return {
        "org": (ORG_DIR / "people.json").exists(),
        "corpus": any(CORPUS_DIR.glob("*.jsonl")) if CORPUS_DIR.exists() else False,
        "memory": MEMORY_DB.exists(),
        "results": any(RESULTS_DIR.glob("benchmark_*.json")) if RESULTS_DIR.exists() else False,
    }


# ------------------------------------------------------------------------------------------------ singletons


@st.cache_resource(show_spinner=False, max_entries=2)
def _store_for(version: float) -> Any:
    from keepline.memory.store import MemoryStore

    s = MemoryStore(MEMORY_DB)
    return s if s.areas() else None


def store() -> Any:
    """The MemoryStore, or None if the graph was not built (never creates an empty DB)."""
    if not MEMORY_DB.exists():
        return None
    try:
        return _store_for(_db_version())  # new DB build => fresh connection
    except Exception as e:  # noqa: BLE001
        log.warning("store unavailable: %s", e)
        return None


@st.cache_resource(show_spinner="Loading the answer agent…")
def agent() -> Any:
    try:
        from keepline.agent.answer import load_default_agent

        return load_default_agent()
    except Exception as e:  # noqa: BLE001
        log.warning("agent unavailable: %s", e)
        return None


# ------------------------------------------------------------------------------------------------ people


def people() -> list[Person]:
    s = store()
    return s.people() if s else []


def names() -> dict[str, str]:
    return {p.id: p.name for p in people()}


def first_names() -> dict[str, str]:
    return {p.id: p.name.split()[0] for p in people()}


def departing(on: date | None = None) -> list[Person]:
    on = on or today()
    return sorted((p for p in people() if p.departure_date and p.departure_date >= on), key=lambda p: p.departure_date)


def joiners(on: date | None = None) -> list[Person]:
    on = on or today()
    return sorted((p for p in people() if p.start_date >= on - timedelta(days=30)), key=lambda p: p.start_date)


def default_person(kind: str) -> str | None:
    """Presenter defaults: the nearest departure for handoff views, the newest joiner for onboarding."""
    ids = [p.id for p in people()]
    if kind == "leaver":
        d = departing()
        return d[0].id if d else (ids[0] if ids else None)
    if kind == "joiner":
        j = joiners()
        return j[-1].id if j else ("alex" if "alex" in ids else (ids[0] if ids else None))
    return ids[0] if ids else None


# ------------------------------------------------------------------------------------------------ products (cached)


@st.cache_data(show_spinner="Scoring knowledge risk…")
def _risk_map(on: date, exclude: tuple[str, ...], version: float) -> list[AreaRisk]:
    from keepline.products.risk import risk_map

    return risk_map(store(), on, exclude_person_ids=exclude)


def risk_map(exclude: tuple[str, ...] = ()) -> list[AreaRisk]:
    return _risk_map(today(), tuple(sorted(exclude)), _db_version()) if store() else []


@st.cache_data(show_spinner="Assembling the handoff pack…")
def _handoff(pid: str, on: date, version: float) -> HandoffPack:
    from keepline.products.handoff import build_handoff_pack

    return build_handoff_pack(store(), pid, on, risks=risk_map())


def handoff(pid: str) -> HandoffPack | None:
    if not store():
        return None
    from keepline.products.signoff import apply_state

    return apply_state(copy.deepcopy(_handoff(pid, today(), _db_version())))


@st.cache_data(show_spinner="Writing the onboarding brief…")
def _brief(pid: str, on: date, version: float) -> OnboardingBrief:
    from keepline.products.onboarding import build_onboarding_brief

    return build_onboarding_brief(store(), pid, on, risks=risk_map())


def brief(pid: str) -> OnboardingBrief | None:
    return _brief(pid, today(), _db_version()) if store() else None


# ------------------------------------------------------------------------------------------------ small JSON state


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def record_ask(asker_id: str, person_id: str, question: str, note: str = "") -> None:
    """'Ask the real person': queue the question for the human expert. Their reply becomes a new receipt."""
    asks = _read_json(ASKS_PATH, [])
    asks.append({"asker_id": asker_id, "person_id": person_id, "question": question, "note": note,
                 "at": datetime.now().isoformat(timespec="seconds"), "status": "open"})
    _write_json(ASKS_PATH, asks)


def asks_for(person_id: str) -> list[dict[str, Any]]:
    return [a for a in _read_json(ASKS_PATH, []) if a.get("person_id") == person_id]


def source_prefs(person_id: str) -> dict[str, bool]:
    return {**DEFAULT_SOURCES, **_read_json(SOURCE_PREFS_PATH, {}).get(person_id, {})}


def set_source_prefs(person_id: str, prefs: dict[str, bool]) -> None:
    allp = _read_json(SOURCE_PREFS_PATH, {})
    allp[person_id] = prefs
    _write_json(SOURCE_PREFS_PATH, allp)


# ------------------------------------------------------------------------------------------------ results (Agent C)


@st.cache_data(show_spinner=False)
def _results_json(name: str, mtime: float) -> Any:
    return _read_json(RESULTS_DIR / name, None)


def results_json(name: str) -> Any:
    p = RESULTS_DIR / name
    return _results_json(name, p.stat().st_mtime) if p.exists() else None


def results_png(name: str) -> Path | None:
    p = RESULTS_DIR / name
    return p if p.exists() else None

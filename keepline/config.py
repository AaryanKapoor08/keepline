"""Paths and runtime settings. Everything is overridable via environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("KEEPLINE_ROOT", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); real environment variables always win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")

# Product world (a real deployment would have these)
ORG_DIR = DATA / "org"  # people.json, areas.json
CORPUS_DIR = DATA / "corpus"  # slack.jsonl, email.jsonl, tickets.jsonl, docs.jsonl
MEMORY_DIR = DATA / "memory"  # keepline.db (SQLite mirror of the Snowflake schema)
MEMORY_DB = MEMORY_DIR / "keepline.db"
CACHE_DIR = DATA / "cache"  # LLM response cache (makes demos + re-runs offline & free)

# Eval world -- ONLY keepline.data and keepline.eval may touch these.
TRUTH_DIR = DATA / "truth"  # truth.json, evidence_map.json
QUESTIONS_DIR = DATA / "questions"  # train.jsonl, dev.jsonl, test.jsonl, test.sha256

# Outputs
RESULTS_DIR = DATA / "results"  # benchmark json, bandit state, charts

# Demo clock: "today" in the Harbourline world. Sarah gave notice; Alex starts Monday.
DEMO_TODAY = date.fromisoformat(os.environ.get("KEEPLINE_TODAY", "2026-09-04"))
DEMO_COMPANY = "Harbourline Credit Union"


@dataclass(frozen=True)
class LLMSettings:
    provider: str = os.environ.get("KEEPLINE_LLM", "auto")  # auto | anthropic | cortex | none
    extract_model: str = os.environ.get("KEEPLINE_EXTRACT_MODEL", "claude-opus-5")
    answer_model: str = os.environ.get("KEEPLINE_ANSWER_MODEL", "claude-opus-5")
    cortex_model: str = os.environ.get("KEEPLINE_CORTEX_MODEL", "claude-sonnet-4-5")
    offline_only: bool = os.environ.get("KEEPLINE_OFFLINE", "0") == "1"  # cache hits only, never call out


LLM = LLMSettings()

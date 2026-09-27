"""Demo answer cache: pre-compute the scripted demo questions so the live demo can never stall.

    python -m app.demo_cache            # answer every question in app/demo_script.json, write the cache
    python -m app.demo_cache --check    # list which scripted questions are cached

The Ask page serves a cached answer instantly when (asker, question, as_of) matches; anything else goes live.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from keepline.config import CACHE_DIR  # noqa: E402
from keepline.contracts import Answer, from_dict, to_dict  # noqa: E402

SCRIPT_PATH = Path(__file__).resolve().parent / "demo_script.json"
CACHE_PATH = CACHE_DIR / "demo_answers.json"


def key(asker_id: str, question: str, as_of: date | str) -> str:
    return f"{asker_id}|{' '.join(question.lower().split()).rstrip('?')}|{as_of}"


def load_script(path: Path = SCRIPT_PATH) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"as_of": None, "asker_id": None, "questions": []}


def load_cache(path: Path = CACHE_PATH) -> dict[str, Answer]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: from_dict(Answer, v) for k, v in raw.items()}


def save_cache(cache: dict[str, Answer], path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: to_dict(v) for k, v in cache.items()}, indent=1, ensure_ascii=False), encoding="utf-8")


def precompute(agent: Any, script: dict[str, Any] | None = None, path: Path = CACHE_PATH) -> dict[str, Answer]:
    """Answer every scripted question with ``agent`` and persist. Existing entries are refreshed."""
    script = script or load_script()
    as_of = date.fromisoformat(script["as_of"])
    cache = load_cache(path)
    for q in script["questions"]:
        asker = q.get("asker_id", script["asker_id"])
        cache[key(asker, q["text"], as_of)] = agent.answer(q["text"], asker, as_of=as_of)
    save_cache(cache, path)
    return cache


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="only report cache coverage")
    args = ap.parse_args()
    script = load_script()
    if args.check:
        cache = load_cache()
        for q in script["questions"]:
            k = key(q.get("asker_id", script["asker_id"]), q["text"], script["as_of"])
            print(("cached  " if k in cache else "MISSING ") + q["text"])
        return
    from keepline.agent.answer import load_default_agent

    cache = precompute(load_default_agent(), script)
    for q in script["questions"]:
        a = cache[key(q.get("asker_id", script["asker_id"]), q["text"], script["as_of"])]
        print(f"[{a.action:>7}] {a.confidence:.2f}  {q['text']}  ->  {a.text[:80]}")
    print(f"cached {len(script['questions'])} demo answers -> {CACHE_PATH}")


if __name__ == "__main__":
    main()

"""Loaders for the *product world* inputs: HR roster, area list, and raw work-tool corpus.

The product pipeline reads its inputs only through here. Ground truth is loaded via ``keepline.data.truth_io``
and may only be imported from ``keepline.data`` and ``keepline.eval``.
"""

from __future__ import annotations

from pathlib import Path

from keepline.config import CORPUS_DIR, ORG_DIR
from keepline.contracts import Area, Person, SourceDoc, read_json_list, read_jsonl

CORPUS_FILES = ("slack.jsonl", "email.jsonl", "tickets.jsonl", "docs.jsonl", "interviews.jsonl")


def load_people(org_dir: Path = ORG_DIR) -> list[Person]:
    return read_json_list(org_dir / "people.json", Person)


def load_areas(org_dir: Path = ORG_DIR) -> list[Area]:
    return read_json_list(org_dir / "areas.json", Area)


def load_corpus(corpus_dir: Path = CORPUS_DIR) -> list[SourceDoc]:
    docs: list[SourceDoc] = []
    for name in CORPUS_FILES:
        path = corpus_dir / name
        if path.exists():
            docs.extend(read_jsonl(path, SourceDoc))
    docs.sort(key=lambda d: d.timestamp)
    return docs

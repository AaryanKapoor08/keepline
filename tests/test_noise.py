"""Chaos-ladder integrity: determinism, L0 == clean, and evidence stays traceable through id_map."""

from __future__ import annotations

import json

import pytest

from keepline.config import CORPUS_DIR, TRUTH_DIR
from keepline.contracts import to_json
from keepline.data.noise import corrupt, remap_evidence
from keepline.io import load_corpus

pytestmark = pytest.mark.skipif(not (TRUTH_DIR / "evidence_map.json").exists(), reason="run keepline.data.build")


@pytest.fixture(scope="module")
def clean():
    return load_corpus(CORPUS_DIR), json.loads((TRUTH_DIR / "evidence_map.json").read_text(encoding="utf-8"))


def _dump(docs) -> list[str]:
    return [to_json(d) for d in docs]


def test_level0_is_clean(clean) -> None:
    docs, ev = clean
    lvl = corrupt(docs, ev, 0)
    assert _dump(lvl.docs) == _dump(docs)
    assert remap_evidence(ev, lvl.id_map) == {t: sorted(v) for t, v in ev.items()}


def test_deterministic(clean) -> None:
    docs, ev = clean
    a, b = corrupt(docs, ev, 3, seed=7), corrupt(docs, ev, 3, seed=7)
    assert _dump(a.docs) == _dump(b.docs) and a.id_map == b.id_map
    assert _dump(corrupt(docs, ev, 3, seed=8).docs) != _dump(a.docs)


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_evidence_mapping_integrity(clean, level: int) -> None:
    docs, ev = clean
    lvl = corrupt(docs, ev, level)
    ids = [d.id for d in lvl.docs]
    assert len(ids) == len(set(ids)), "duplicate doc ids"
    present = set(ids)
    new_ev = remap_evidence(ev, lvl.id_map)
    for tid, doc_ids in new_ev.items():
        assert doc_ids, f"{tid} lost all evidence at L{level}"
        assert set(doc_ids) <= present, f"{tid} maps to missing docs"
    originals = {d.id for d in docs}
    surviving = {d for d in originals if lvl.id_map.get(d)}
    assert surviving <= present  # original ids are stable wherever the doc survives
    if level >= 2:
        assert any(not v for v in lvl.id_map.values()), "dropout should remove some evidence"
    assert len(lvl.docs) > len(docs)

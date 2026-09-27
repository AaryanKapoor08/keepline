"""``python -m keepline.memory.build [--llm auto|none] [--cutoff YYYY-MM-DD] [--include-private]``

Corpus -> privacy filter -> extraction -> dedup/supersession/conflicts -> expertise -> edges -> SQLite + BM25.
Every stage has a deterministic offline path; ``--llm none`` is what tests, the benchmark and the demo use.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence

from keepline.config import MEMORY_DB
from keepline.contracts import Area, Fact, Person, SourceDoc
from keepline.memory.expertise import build_edges, compute_expertise
from keepline.memory.extract import (
    ExtractionContext,
    Extractor,
    HeuristicExtractor,
    LLMExtractor,
    group_threads,
    is_personal_doc,
    visible_doc,
)
from keepline.memory.link import link_facts
from keepline.memory.store import MemoryStore
from keepline.retrieval.search import INDEX_PATH, SearchIndex

log = logging.getLogger(__name__)


@dataclass
class BuildStats:
    docs_total: int = 0
    docs_ingested: int = 0
    excluded_private: int = 0
    excluded_personal: int = 0
    excluded_after_cutoff: int = 0
    facts_extracted: int = 0
    facts_kept: int = 0
    merged: int = 0
    superseded: int = 0
    conflicts: int = 0
    facts_by_kind: dict[str, int] = field(default_factory=dict)
    expertise_rows: int = 0
    expertise_enough_data: int = 0
    edges: int = 0
    extractor: str = "heuristic"
    seconds: float = 0.0

    def summary(self) -> str:
        kinds = ", ".join(f"{k}={v}" for k, v in sorted(self.facts_by_kind.items()))
        return (
            f"docs: {self.docs_ingested}/{self.docs_total} ingested (excluded private={self.excluded_private}, "
            f"personal={self.excluded_personal}, after cutoff={self.excluded_after_cutoff})\n"
            f"facts: {self.facts_extracted} extracted -> {self.facts_kept} kept (merged {self.merged}, "
            f"superseded {self.superseded}, conflicts {self.conflicts}) [{self.extractor}]\n"
            f"by kind: {kinds}\n"
            f"expertise rows: {self.expertise_rows} ({self.expertise_enough_data} with enough data); "
            f"edges: {self.edges}; {self.seconds:.1f}s"
        )


def filter_docs(
    docs: Sequence[SourceDoc], ctx: ExtractionContext, *, cutoff: date | None, include_private: bool, stats: BuildStats
) -> list[SourceDoc]:
    """Privacy first: DMs are never ingested unless explicitly allowed; social chatter is dropped."""
    kept = []
    for d in docs:
        if cutoff is not None and d.timestamp.date() > cutoff:
            stats.excluded_after_cutoff += 1
        elif not visible_doc(d, include_private):
            stats.excluded_private += 1
        elif is_personal_doc(d, ctx.linker):
            stats.excluded_personal += 1
        else:
            kept.append(d)
    return kept


def link_docs_to_areas(docs: Sequence[SourceDoc], ctx: ExtractionContext) -> dict[str, list[tuple[str, float]]]:
    """Doc -> areas; docs in a thread with no own link inherit the thread's areas (replies like "yep, done")."""
    out: dict[str, list[tuple[str, float]]] = {}
    for thread in group_threads(docs):
        thread_links: list[tuple[str, float]] = []
        for d in thread:
            links = ctx.linker.link(f"{d.title or ''}\n{d.text}")[:3]
            hint = component_area(d, ctx)
            if hint:  # a ticket's component/label field is the strongest area signal a tracker gives us
                links = [(hint, 5.0)] + [(a, s) for a, s in links if a != hint][:2]
            out[d.id] = links
            if links and not thread_links:
                thread_links = [(a, s * 0.5) for a, s in links[:1]]
        for d in thread:
            if not out[d.id] and thread_links:
                out[d.id] = thread_links
    return out


def component_area(doc: SourceDoc, ctx: ExtractionContext) -> str | None:
    """Area from a ticket's component/label metadata, when it names a known area."""
    known = {a.id for a in ctx.areas}
    for key in ("component", "area_hint", "area", "project_component", "label"):
        v = doc.meta.get(key)
        if isinstance(v, str) and v in known:
            return v
    return None


def extract_all(docs: Sequence[SourceDoc], ctx: ExtractionContext, extractor: Extractor) -> list[Fact]:
    facts: list[Fact] = []
    for thread in group_threads(docs):
        facts.extend(extractor.extract_thread(thread, ctx))
    return facts


def fact_participants(facts: Sequence[Fact], docs_by_id: dict[str, SourceDoc]) -> dict[str, list[str]]:
    """Who may see a non-public fact: the union of its receipts' participants (plus the speaker)."""
    out: dict[str, list[str]] = {}
    for f in facts:
        if str(f.visibility) == "public":
            continue
        ppl: set[str] = {f.stated_by} if f.stated_by else set()
        for d in f.source_doc_ids:
            if d in docs_by_id:
                ppl.update(docs_by_id[d].participants)
        out[f.id] = sorted(ppl)
    return out


def build_memory(
    people: Sequence[Person],
    areas: Sequence[Area],
    docs: Sequence[SourceDoc],
    *,
    store: MemoryStore,
    index_path: Path | str = INDEX_PATH,
    llm: Any | None = None,
    cutoff: date | None = None,
    include_private: bool = False,
) -> tuple[BuildStats, SearchIndex]:
    """Pure-ish pipeline entry point (tests call this with fixtures; the CLI calls it with the real corpus)."""
    t0 = time.perf_counter()
    stats = BuildStats(docs_total=len(docs))
    ctx = ExtractionContext(people, areas)
    kept = filter_docs(docs, ctx, cutoff=cutoff, include_private=include_private, stats=stats)
    stats.docs_ingested = len(kept)
    doc_areas = link_docs_to_areas(kept, ctx)

    extractor: Extractor = LLMExtractor(llm) if llm is not None else HeuristicExtractor()
    stats.extractor = extractor.name
    raw = extract_all(kept, ctx, extractor)
    stats.facts_extracted = len(raw)
    linked = link_facts(raw)
    facts = linked.facts
    stats.facts_kept, stats.merged, stats.superseded = len(facts), linked.merged, linked.superseded
    stats.conflicts = len(linked.conflicts)
    stats.facts_by_kind = dict(Counter(str(f.kind) for f in facts))

    ref = cutoff or max((d.timestamp.date() for d in kept), default=None)
    expertise, n_answers = compute_expertise(kept, doc_areas, facts, ref_date=ref)
    stats.expertise_rows = len(expertise)
    stats.expertise_enough_data = sum(e.enough_data for e in expertise)
    edges = build_edges(facts, expertise, people)
    stats.edges = len(edges)

    by_id = {d.id: d for d in kept}
    participants = fact_participants(facts, by_id)
    store.reset()
    store.write_org(people, areas)
    store.write_docs(kept, doc_areas)
    store.write_facts(facts, participants)
    store.write_edges(edges)
    store.write_expertise(expertise, n_answers)
    store.write_conflicts(linked.conflicts)

    index = SearchIndex(index_path).build(
        kept, facts, areas=areas, fact_participants=participants,
        doc_areas={d: [a for a, _ in lst] for d, lst in doc_areas.items()},
    )
    index.save()
    stats.seconds = time.perf_counter() - t0
    store.set_meta("build_stats", stats.__dict__)
    store.set_meta("built_at", datetime.now().replace(microsecond=0).isoformat())
    store.set_meta("cutoff", cutoff.isoformat() if cutoff else None)
    return stats, index


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build Keepline memory (graph + search index) from the corpus.")
    ap.add_argument("--llm", choices=["auto", "none"], default="none", help="LLM extraction (auto) or heuristics")
    ap.add_argument("--cutoff", type=date.fromisoformat, default=None, help="ignore docs after this date")
    ap.add_argument("--include-private", action="store_true", help="also ingest PRIVATE docs (DMs); off by default")
    ap.add_argument("--limit", type=int, default=None, help="only the first N docs (smoke runs, e.g. LLM path)")
    ap.add_argument("--db", type=Path, default=MEMORY_DB)
    ap.add_argument("--index", type=Path, default=INDEX_PATH)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from keepline.io import load_areas, load_corpus, load_people
    from keepline.llm import get_llm

    llm = get_llm() if args.llm == "auto" else None
    if args.llm == "auto" and llm is None:
        log.info("no LLM provider available; using heuristic extractor")
    store = MemoryStore(args.db)
    stats, _ = build_memory(
        load_people(), load_areas(), load_corpus()[: args.limit] if args.limit else load_corpus(), store=store, index_path=args.index, llm=llm,
        cutoff=args.cutoff, include_private=args.include_private,
    )
    print(stats.summary())
    print(f"wrote {args.db} and {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

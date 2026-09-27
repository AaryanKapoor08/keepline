# Keepline — Build Plan (Hack Atlantic, Sep 26–27 2026)

Shared contracts: `keepline/contracts.py` (types), `keepline/config.py` (paths), `keepline/io.py` (product-world
loaders), `keepline/llm.py` (LLM + disk cache). **Do not change a contract type without telling the
coordinator**. Adding optional fields with defaults is fine.

## Architecture

```
data/org (HR roster, areas) ─┐
data/corpus (slack/email/    ├─► memory.build ─► SQLite graph (data/memory/keepline.db) ─┬─► products (risk, handoff, brief, gaps, what-if)
  tickets/docs .jsonl)      ─┘   extract → link → supersede → expertise      + search index ├─► agent.answer (said / inferred / no-evidence, route)
                                                                                           └─► app (Streamlit)  ◄── data/results (benchmark, bandit)
data/truth + data/questions ──► eval.grader ◄── agent answers  ──► rl.train (bandit) ──► data/results
      (EVAL WORLD ONLY)
snowflake/ = the same pipeline expressed as Snowflake-native SQL/Cortex (deploy target)
```

Truth-first rule: `keepline.data` writes truth, then renders the corpus from it. Nothing outside `keepline/data`
and `keepline/eval` may read `data/truth` or `data/questions` (enforced by `tests/test_isolation.py`).

## Ownership (parallel agents)

| Agent | Owns (only writes here) | Delivers |
|---|---|---|
| **A · Data** | `keepline/data/`, `data/org`, `data/corpus`, `data/truth`, `data/questions`, `tests/test_data*.py` | Harbourline truth file, renderer, question splits, `truth_io` |
| **B · Memory + Agent** | `keepline/memory/`, `keepline/retrieval/`, `keepline/agent/`, `tests/test_memory*.py`, `tests/test_agent*.py` | extraction → bi-temporal graph, search, answer agent |
| **C · RL + Eval** | `keepline/rl/`, `keepline/eval/`, `data/results/`, `tests/test_rl*.py`, `tests/test_eval*.py` | grader, plain-search baseline, bandit, benchmark, charts |
| **D · Products + App + Snowflake** | `keepline/products/`, `app/`, `snowflake/`, `tests/test_products*.py` | risk map, handoff pack, onboarding brief, gaps, what-if, Streamlit app, Snowflake assets |
| Coordinator | `keepline/contracts.py`, `config.py`, `io.py`, `llm.py`, `claude/*`, `README.md`, `tests/test_isolation.py` | contracts, integration, demo script |

## Binding interfaces (implement these exact names/signatures)

### A · `keepline.data`
- `python -m keepline.data.build [--seed 7]` → writes everything below, deterministic for a seed.
- `data/org/people.json` (`list[Person]`), `data/org/areas.json` (`list[Area]`)
- `data/corpus/{slack,email,tickets,docs,interviews}.jsonl` (`SourceDoc` per line)
- `data/truth/truth.json` (`list[TruthFact]`), `data/truth/evidence_map.json` (`EvidenceMap`)
- `data/questions/{train,dev,test}.jsonl` (`Question`), `data/questions/test.sha256`
- `keepline.data.truth_io`: `load_truth() -> list[TruthFact]`, `load_evidence_map() -> EvidenceMap`,
  `load_questions(split: Split) -> list[Question]`, `verify_test_frozen() -> bool`

### B · `keepline.memory`, `keepline.retrieval`, `keepline.agent`
- `python -m keepline.memory.build [--llm auto|none] [--cutoff YYYY-MM-DD]` → `data/memory/keepline.db` + index
- `keepline.memory.store.MemoryStore(db_path=MEMORY_DB)`:
  `people() / person(id) / areas() / area(id) / doc(id) / docs(ids)`,
  `facts(*, area_id=None, person_id=None, kinds=None, current_only=False, as_of: date|None=None, include_private_for: str|None=None) -> list[Fact]`,
  `fact(id)`, `supersession_chain(fact_id) -> list[Fact]` (oldest→newest),
  `expertise(*, area_id=None, person_id=None) -> list[Expertise]`,
  `docs_by(person_id, *, since=None) -> list[SourceDoc]`, `open_tickets(person_id) -> list[SourceDoc]`,
  `log_query(asker_id, question, answer: Answer)`, `query_log(*, about_person_id=None, limit=100) -> list[dict]`,
  `set_review_status(fact_id, status: ReviewStatus, corrected_text: str|None=None)`,
  `area_doc_counts_by_month(area_id) -> dict[str, int]`
- `keepline.retrieval.search.SearchIndex`: `build(docs, facts) / load() / save()`,
  `search(query, *, k=8, as_of=None, visible_to=None, source_weights=None) -> list[Hit]`
  (`Hit`: doc_id, fact_id|None, score, text, source_type, timestamp)
- `keepline.agent.answer.AnswerAgent(store, index, llm=None)`:
  `.answer(question, asker_id, *, as_of=None, params: PolicyParams|None=None) -> Answer`
  `.context_features(question, asker_id, *, as_of=None) -> dict[str, float]` (for the bandit; cheap)
  `.classify_area(question) -> str|None`
- `keepline.agent.answer.load_default_agent() -> AnswerAgent` (loads store + index + llm)

### C · `keepline.rl`, `keepline.eval`
- `keepline.eval.grader.grade(q: Question, a: Answer, truth: dict[str, TruthFact], ev: EvidenceMap) -> Grade`
  (`Grade`: correct, citation_valid, outcome ∈ {correct_cited, correct_uncited, correct_abstain, correct_route,
  unnecessary_abstain, wrong_route, hallucination, stale_answer}, reward, notes)
- `keepline.rl.rewards.reward(grade, confidence) -> float` (table in ProjectSummary.md)
- `keepline.eval.baseline.PlainSearchBaseline(index).answer(question, asker_id, as_of=None) -> Answer`
- `keepline.rl.bandit.ContextualBandit` (per-area LinUCB/Thompson over discrete `PolicyParams` arms)
- `python -m keepline.rl.train` → `data/results/bandit.json`, `data/results/reward_curve.json`
- `keepline.rl.policy.load_policy() -> Callable[[dict], PolicyParams]`
- `python -m keepline.eval.benchmark --split dev|test [--systems plain,keepline,keepline_rl]` →
  `data/results/benchmark_<split>.json` (metrics per system + N + per-question rows) + PNG charts
- `python -m keepline.eval.spotcheck` → `data/results/spotcheck.csv` (30 answers for human grading)

### D · `keepline.products`, `app`, `snowflake`
- `keepline.products.risk.risk_map(store, today, *, exclude_person_ids=()) -> list[AreaRisk]`
- `keepline.products.risk.risk_history(store, area_id, months=6) -> list[float]`
- `keepline.products.handoff.build_handoff_pack(store, person_id, today) -> HandoffPack`
- `keepline.products.onboarding.build_onboarding_brief(store, person_id, today) -> OnboardingBrief`
- `keepline.products.gaps.gap_questions(store, person_id, *, n=8) -> list[GapQuestion]`
- `keepline.products.simulate.what_if_leaves(store, person_id, today) -> tuple[list[AreaRisk], list[AreaRisk]]`
- `streamlit run app/Home.py`
- `snowflake/` : SQL DDL + row access policies + AI_EXTRACT pipeline + Cortex Search service +
  Cortex Analyst semantic model YAML + Cortex Agent spec + Snowpark procs + `deploy.py` + Streamlit-in-Snowflake

## Milestones (clock = Sep 26 21:00 → Sep 27 judging)
1. **M0 (done)** contracts, plan, repo scaffold.
2. **M1 (+1.5h)** A: org + truth + corpus + questions exist (even v1). B/C/D: skeletons importable, unit tests on fixtures.
3. **M2 (+4h)** End-to-end offline: build memory → answer → grade → benchmark numbers → app renders all pages.
4. **M3 (+7h)** Bandit trained, reward curve, benchmark vs plain search, handoff pack polished, Snowflake assets.
5. **M4 (morning)** Coordinator: integration pass, demo script, cached answers, backup video checklist, README.
6. Stretch: LLM extraction pass (needs ANTHROPIC_API_KEY or Snowflake), Enron/PEP eval, live Snowflake deploy.

## Definition of done
`python -m keepline.data.build && python -m keepline.memory.build --llm none && python -m keepline.rl.train && python -m keepline.eval.benchmark --split dev && pytest -q && streamlit run app/Home.py`
runs clean on a laptop with no network, and the app walks the 4-minute demo.

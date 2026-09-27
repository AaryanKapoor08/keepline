# Keepline

**Keepline keeps the line of knowledge unbroken when people leave.**
Glean finds what your company knows. Keepline shows what it's about to forget, and saves it.

Keepline turns Slack, email and tickets into a versioned, receipt-backed company memory. Every fact records who said
it, when it was true, and what replaced it. From that memory it maps where knowledge is one person deep, writes the
handoff pack the leaver signs off, briefs the new hire, and answers questions with receipts — or says
"I don't know, ask Mike." Receipts, not clones.

## Run the demo

```bash
pip install -e ".[dev,llm,snowflake]" fastapi "uvicorn[standard]"
python -m keepline.data.build                 # truth file -> Harbourline corpus + frozen question splits
python -m keepline.memory.build --llm none    # extraction -> bi-temporal graph + search index (~1 s)
python -m uvicorn api.server:app --port 8000  # JSON API over the product
cd web && npm install && npm run dev          # http://localhost:3000  (→ / Space steps the 2-minute demo)
```

The web app falls back to a static snapshot (`python scripts/export_web_data.py`) if the API is down, so the demo
cannot stall. Presenter script: [`web/README.md`](web/README.md). Streamlit-in-Snowflake version: `streamlit run app/Home.py`.

## Proof (truth-first, frozen test set)

The company's truth file is written first; the Slack/email/tickets are rendered from it; Keepline only ever sees the
rendered data (`tests/test_isolation.py` fails the build otherwise); the grader compares answers to the truth file.
Questions are split by fact, so test facts never appear in train/dev. The test split is sha256-frozen and was run once.

Held-out test split, N = 216 questions (`data/results/benchmark_test.json`):

| Metric | Plain search | **Keepline** |
|---|---|---|
| Correct with a valid citation (N=137 answerable) | 35.8% | **43.1%** |
| Confidently wrong, of all 216 questions | 71.8% | **22.2%** |
| Right action: answer / abstain / route | 28.2% | **50.9%** |
| Routed to the right person (N=21) | 57% | **100%** |
| Current version of a changed fact (N=39) | 25.6% | **46.2%** |
| Calibration error (ECE) | 0.269 | **0.053** |
| Mean reward | −1.07 | **−0.04** |

**Chaos ladder** (`python -m keepline.eval.robustness`, dev split): the corpus is corrupted at 5 levels with 12 kinds
of real-world mess (typos, slang, fragmented messages, bot spam, forwarded duplicates, wrong claims from non-experts,
stale values, evidence dropout, 3× chatter). Plain search collapses; Keepline degrades slowly.

**RL, honestly.** RL tunes the agent's *decisions*, never LLM weights. A logistic confidence calibrator (fit on train)
generalizes: ECE 0.27 → 0.05 on held-out test. A LinUCB contextual bandit over answer/abstain/route thresholds beat
the default on dev, but on the held-out test it over-abstained and did not beat the calibrated default
(reward −0.050 vs −0.038). With 388 training questions the thresholds overfit; real usage data is the roadmap.

Reward table: +1 correct with citation · +0.5 correct abstain/route · −0.3 unnecessary abstain · −2 confident wrong ·
+0.2×(1−|confidence−correct|) calibration bonus.

## Architecture

| Layer | Local engine (offline, deterministic) | Snowflake (`snowflake/`) |
|---|---|---|
| Raw data | `data/corpus/*.jsonl` | RAW tables |
| Extraction | heuristic + optional Claude (`keepline/memory/extract.py`) | `AI_EXTRACT` / `AI_COMPLETE` |
| Versioned graph | SQLite, valid_from/valid_to/learned_at/supersedes | graph tables + Time Travel |
| Permissions | visibility filter at query time | row access policies, DM masking |
| Search | BM25 (`keepline/retrieval`) | Cortex Search |
| Structured questions | — | Cortex Analyst semantic model |
| Answer agent | `keepline/agent/answer.py` | Cortex Agent spec |
| Risk, simulation | `keepline/products` | Snowpark procedures |
| App | Next.js (`web/`) + FastAPI (`api/`) | Streamlit-in-Snowflake (`app/`) |

`risk = importance × (1 − redundancy) × departure likelihood`. Bus factor counts only hands-on evidence
(closed tickets, facts stated), never job titles or message volume.

## Repo map

`keepline/contracts.py` shared types · `keepline/data` truth + renderer + noise · `keepline/memory` extraction, linking,
expertise · `keepline/retrieval` BM25 · `keepline/agent` answer/abstain/route · `keepline/products` risk, handoff,
onboarding, gaps, what-if, decision check, staffing · `keepline/rl` rewards, bandit, calibrator · `keepline/eval`
grader, baseline, benchmark, robustness, spot-check · `api/` · `web/` · `app/` · `snowflake/` · `claude/` plans & progress.

`pytest -q` runs the whole suite offline in under a minute.

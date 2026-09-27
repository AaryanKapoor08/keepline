# Keepline — handoff for the next agent

**What it is:** Keepline turns Slack/email/tickets into a versioned, receipt-backed company memory ("GitHub for company knowledge"): who knows what, what breaks when someone leaves, handoff/review, cited answers or "I don't know, ask X", and a change simulator. Built for Hack Atlantic 2026 (+ Best Use of Snowflake). Demo company: Harbourline Credit Union (synthetic). Sarah leaves Sep 11, Alex joins Sep 14, demo "today" = 2026-09-04 (chat runs as of 2026-09-15).

**Repo:** `C:\dev\hackatlantic` → github.com/AaryanKapoor08/keepline (private, branch main). Read `claude/ProjectSummary.md`, `claude/Progress.md`, `README.md` first.

## Run
```
python -m keepline.data.build                 # synthetic truth + corpus + frozen questions
python -m keepline.memory.build --llm none    # graph → data/memory/keepline.db (~1s)
python -m uvicorn api.server:app --port 8000
cd web && npm run dev                         # http://localhost:3000 (falls back to web/public/data snapshot)
python scripts/export_web_data.py             # refresh snapshot after data changes
pytest -q                                     # all offline
```

## Layout
- `keepline/contracts.py` shared types · `config.py` (loads gitignored `.env`) · `llm.py` (Claude/Cortex, disk-cached)
- `keepline/data` truth file, renderer, noise (EVAL WORLD) · `keepline/eval`, `keepline/rl` grader, benchmark, bandit, calibrator
- `keepline/memory` extraction→supersession→expertise (SQLite) · `retrieval` BM25 · `agent/answer.py`, `agent/chat.py` (Claude tool-use + citation guard)
- `keepline/products` risk, handoff, onboarding, gaps, simulate, decision_check, staffing, project_sim
- `api/server.py` FastAPI · `web/` Next.js (shadcn/Aceternity, React Flow; theme "harbour"; see `web/DESIGN.md`, `web/README.md` presenter script)
- `app/` Streamlit (Snowflake-native) · `snowflake/` SQL, deploy.py, `STAGE_DEMO.md` (verified live queries)
- `docs/JUDGE_QA.md`, `docs/HOW_IT_WORKS.md`

## Rules
- Product code must never read `data/truth` or `data/questions` (`tests/test_isolation.py`).
- Test split is frozen (sha in `data/questions/test.sha256`); run once only; tune on dev.
- Never call LLMs in tests. Cortex is opt-in (`KEEPLINE_LLM=cortex`).
- UI: harbour palette, progressive disclosure, no "AI slop", no clone/digital-twin wording.

## State (headline, test N=216)
Confidently wrong 22% vs 72% plain search · right+cited 43% vs 36% (n=137) · routing 21/21 vs 12/21 · ECE 0.05 vs 0.27. Bandit did NOT beat default on test (honest finding).
**Snowflake:** live in account OQPUNUP-EAB79910 (user AARYAN, key-pair auth `~/.snowflake/keepline_rsa_key.p8`, settings in `.env`). Data, policies, 2 Cortex Search services, risk procs verified. Not exercised: Cortex Agent, Streamlit-in-Snowflake, full extraction, tasks (suspended). Row access demo needs `USE SECONDARY ROLES NONE`.

## Known gaps
Synthetic data only; rule-based extraction by default (some noise); one false supersession (LCTR→disputes) hidden in UI only; live uncached chat latency unmeasured; no customer interviews yet; Slack 2025 API terms → pitch "runs inside customer's Snowflake".

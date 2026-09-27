# Keepline on Snowflake

Keepline's local engine (SQLite + BM25 + optional Claude) mirrors this deployment table-for-table
(`keepline/memory/schema.sql` <-> `sql/01_schema.sql`). On Snowflake, the whole loop — ingest, extract,
supersede, search, answer, score risk, build the handoff pack, show it in an app — runs inside one account.

> **The data rule.** Company data is searched at question time, with the asker's permissions, inside the
> customer's Snowflake account. It is never exported, never copied to a third party, and never used to train
> a model. Cortex runs inside Snowflake's security boundary; private messages are never indexed, and are only
> sent to extraction when every participant has opted in.

## Feature map

| Keepline capability | Snowflake feature | File |
|---|---|---|
| Land Slack / email / tickets / docs as received | Internal stage, `PUT` + `COPY INTO` with a JSON file format, VARIANT | `sql/01_schema.sql`, `deploy.py` |
| Typed receipts, area linking, participant ACL | Snowflake Scripting procedure `CORE.NORMALIZE_RAW` (MERGE) | `sql/03_extract.sql` |
| Only new messages are ever processed | Stream `CORE.DOCUMENTS_NEW` (append-only) + task graph `T_NORMALIZE -> T_EXTRACT -> T_SUPERSEDE` | `sql/03_extract.sql`, `sql/04_temporal.sql` |
| Entity pull: systems, vendor contacts, promised follow-ups, credential *locations* | `AI_EXTRACT(text =>, responseFormat =>, scores => TRUE)` | `sql/03_extract.sql` |
| Fact extraction with a verbatim quote + confidence | `AI_COMPLETE(model, prompt, model_parameters, response_format => {'type':'json','schema':...})` with an enum over fact kinds | `sql/03_extract.sql` |
| Cost-bounded extraction | `CORE.EXTRACT_NEW_DOCS(model, max_docs)` queue; `deploy.py --limit N` (default 200), `--full` to lift | `sql/03_extract.sql`, `deploy.py` |
| Never cite a dead fact as current | Supersession via `MERGE` (valid_from / valid_to / supersedes / superseded_by) | `sql/04_temporal.sql` |
| "What was true on May 1?" (valid time) | SQL table function `CORE.FACTS_AS_OF(date)` | `sql/04_temporal.sql` |
| "What did we believe yesterday?" (transaction time) | Time Travel `AT(OFFSET => ...)`, `CHANGES(INFORMATION => DEFAULT)`, 30-day retention | `sql/04_temporal.sql` |
| Answers never exceed what the asker can see | Row access policy `CORE.RAP_VISIBILITY` (public / team role / participants via mapping table, memoizable asker lookup) | `sql/02_policies.sql` |
| DMs visible to participants only | Conditional masking policy `CORE.MASK_PRIVATE_TEXT` | `sql/02_policies.sql` |
| No per-person behaviour scoring | Aggregation policy `CORE.AGG_MIN_GROUP_5` (min group size 5) on expertise + query log | `sql/02_policies.sql` |
| Employee review queue + "who asked about my knowledge" | Owner's-rights procedure `APP.MY_KNOWLEDGE_QUERY_LOG`, append-only `REVIEW_EVENTS` applied by `CORE.APPLY_REVIEWS` | `sql/02_policies.sql`, `sql/04_temporal.sql` |
| Hybrid retrieval over receipts and facts | Cortex Search services `CORE.RECEIPTS_SEARCH`, `CORE.FACTS_SEARCH` (attributes: area, source, visibility, owner team, participants, date, is_current) | `sql/05_search.sql` |
| Risk map, bus factor, countdown, what-if | Snowpark Python procedure `APP.RISK_MAP(today, exclude_person)`; nightly snapshot task | `sql/06_procs.sql` |
| Handoff pack with receipts, suggested owners, gap questions | Snowpark Python procedure `APP.HANDOFF_PACK(person, today)` -> VARIANT | `sql/06_procs.sql` |
| "Which areas have bus factor 1?", "days until departure" | Cortex Analyst semantic view `APP.KEEPLINE_SEMANTIC` (verified queries) | `analyst/keepline_semantic_model.yaml` |
| Cite-or-abstain agent that routes to a person | Cortex Agent `APP.KEEPLINE_AGENT`: Cortex Search x3 + Cortex Analyst + custom tools (risk map, handoff pack) | `agent/keepline_agent.json` |
| The product UI | Streamlit in Snowflake: the local app reused over a policy-filtered snapshot, or a native Cortex page | `streamlit/` |

Risk everywhere is `risk = importance x (1 - redundancy) x departure_likelihood`; the Snowpark procedure mirrors
`keepline/products/risk.py`.

## Roles

`KEEPLINE_ADMIN` owns objects and runs tasks; `KEEPLINE_PIPELINE` runs extraction; `KEEPLINE_APP` is the app /
agent role (reads through policies, may append query log and review events); `KEEPLINE_TEAM_<TEAM>` open team
channels; `KEEPLINE_AUDITOR` sees row metadata but never private text. Map Snowflake users to Keepline people in
`CORE.USER_PERSON_MAP`.

## Runbook

```bash
# 0. Credentials in a gitignored .env at the repo root (loaded by keepline/config.py):
#    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PRIVATE_KEY_PATH (or SNOWFLAKE_PASSWORD)
pip install "snowflake-connector-python[pandas]" pyyaml

# 1. See exactly what will run (no connection, no Snowflake packages needed)
python snowflake/deploy.py --dry-run

# 2. Full deploy. The first run creates roles/warehouse/database, so connect as ACCOUNTADMIN once.
SNOWFLAKE_ROLE=ACCOUNTADMIN python snowflake/deploy.py

# 3. Optional, costs Cortex credits: extract facts from <= 200 docs with AI_EXTRACT + AI_COMPLETE
python snowflake/deploy.py --only extract --limit 200

# 4. Optional: turn on incremental extraction + nightly risk snapshot (tasks are created SUSPENDED)
python snowflake/deploy.py --only tasks
```

Steps can be re-run individually with `--only sql|load|extract|search|analyst|agent|refresh|streamlit|tasks`.
Missing local inputs (e.g. `data/memory/signoffs.json`) are skipped with a note, not an error.

Try it in a worksheet:

```sql
CALL KEEPLINE.APP.RISK_MAP('2026-09-04'::DATE, NULL);      -- today's risk map
CALL KEEPLINE.APP.RISK_MAP('2026-09-04'::DATE, 'sarah');   -- what if Sarah leaves?
CALL KEEPLINE.APP.HANDOFF_PACK('sarah', '2026-09-04'::DATE);
CALL KEEPLINE.APP.WHAT_DID_WE_BELIEVE(24, 'reconciliation');
SELECT * FROM TABLE(KEEPLINE.CORE.FACTS_AS_OF('2026-05-01'::DATE)) WHERE area_id = 'reconciliation';
```

## Notes and limits

- **Deployed and verified live (2026-09-27, AWS us-west-2, X-Small warehouse):**
  - all seven SQL files run clean (`deploy.py --only sql`: 7/7);
  - data load, including the local graph (`--only load`: 18/18);
  - both Cortex Search services (ACTIVE, 3,475 receipts and 506 facts indexed);
  - the risk-snapshot refresh;
  - the semantic view and the Cortex Agent (created);
  - Streamlit-in-Snowflake (created).

  Verified by running queries: `RAP_VISIBILITY` returns 506 / 421 / 426 facts for admin / engineering / finance;
  `APP.RISK_MAP` puts CoreLink and reconciliation at bus factor 1, dropping to 0 in the Sarah what-if; `FACTS_AS_OF`
  and Time Travel work; `SEARCH_PREVIEW` + `AI_COMPLETE` return a cited answer. See `STAGE_DEMO.md` for the exact
  queries and their output.

  Not exercised yet:
  - Cortex extraction (`--only extract`, which spends credits);
  - the task graph (created suspended);
  - Cortex Agent calls from SQL/REST;
  - the Streamlit-in-Snowflake page in a browser.
- Cortex Search reads change-tracked snapshot tables (`CORE.*_SEARCH_SRC`). The masking and row access policies on
  the base tables use correlated subqueries, and Snowflake does not allow those with change tracking. DMs are
  excluded from the snapshots. To refresh, re-run `05_search.sql`.
- `tests/test_products_snowflake.py` checks offline that every file parses, splits and plans.
- Cortex Search services index only public and team sources; the per-asker filter
  (`visibility = public OR owner_team = <team> OR participants contains <person>`) mirrors the row access policy.
- The folder is deliberately *not* a Python package (no `__init__.py`): the name `snowflake` must stay a
  namespace so `snowflake.connector` still imports from the repo root.

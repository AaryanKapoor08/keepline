# Progress

## Status: M0 done — M1 in progress (4 parallel agents)
Clock: started 2026-09-26 20:41. Judging 2026-09-27.

| Milestone | State |
|---|---|
| M0 contracts, plan, scaffold, isolation test | ✅ done (commit 7a68fb4+) |
| M1 data v1 + importable skeletons | 🔄 A data, B memory/agent, C rl/eval, D products/app/snowflake |
| M2 end-to-end offline | ⏳ |
| M3 bandit + benchmark + polish + Snowflake assets | ⏳ |
| M4 integration, demo script, cached answers, README | ⏳ coordinator |

## Decisions
- Local-first engine (SQLite + BM25) mirrors Snowflake schema 1:1; Snowflake assets are the deploy target.
- Deterministic no-LLM path for every stage; Claude/Cortex optional, disk-cached (`data/cache/llm`).
- Truth isolation enforced by `tests/test_isolation.py`.
- Questions split by truth fact → test facts never seen in train/dev. Test split hashed + guarded.

## Credentials (all in gitignored `.env`, loaded by keepline.config)
- Snowflake: account OQPUNUP-EAB79910 (AWS_US_WEST_2, Enterprise trial), user AARYAN, key-pair auth
  (private key at ~/.snowflake/keepline_rsa_key.p8). Verified: AI_COMPLETE (claude-sonnet-4-5), AI_EXTRACT.
  CORTEX_ENABLED_CROSS_REGION='ANY_REGION'.
- Anthropic: API key verified with claude-opus-5.
- Policy: `--llm none` default; LLM/Cortex runs are deliberate, bounded, and disk-cached.

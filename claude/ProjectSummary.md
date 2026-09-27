# Keepline — Sharpened Product Summary

> Glean finds what your company knows. Keepline shows what it's about to forget — and saves it.

## One sentence
Keepline turns a team's existing Slack / email / tickets into a **versioned, receipt-backed company memory**
(every fact: who said it, when it was true, what replaced it), then uses it to (1) show where knowledge is
fragile, (2) write the **handoff pack** when someone leaves, and (3) answer questions **with citations — or
say "I don't know, ask Mike."**

## Sharpened thesis (what we changed vs. the raw vision)
1. **One hero loop, not eight features.** Demo = *Risk Map → Handoff Pack (Sarah signs off) → Alex Asks → Proof*.
   Everything built this weekend serves that loop. Decision History exists to make answers current; the
   what-if simulator is just "recompute risk with Sarah removed". Claim Verifier, voice interviews, GRPO,
   hardware = TreeHacks, not now.
2. **The moat is *temporal correctness + abstention*, not search.** Every fact is bi-temporal
   (`valid_from/valid_to` = when true in the world, `learned_at` = when we learned it) with `supersedes` links
   (pattern borrowed from Zep's Graphiti). The agent never cites a dead fact as current, and it is *trained*
   (bandit) to abstain/route instead of bluffing.
3. **Access & procedures beat "background knowledge".** The practitioner stories say the damage comes from
   lost credentials locations, vendor contacts, recurring jobs, landmines. Our fact `kind`s are built around
   exactly those: `access`, `vendor_contact`, `recurring_task`, `landmine`, `decision`, `procedure`, `owner`.
4. **Proof is the product.** Truth-first synthetic company → rendered data → Keepline → grader against truth.
   Frozen test split (hashed), a plain-search baseline, hallucination rate, abstain precision,
   current-fact accuracy, calibration. We show *N* on every number.
5. **Runs anywhere, deploys to Snowflake.** A local engine (SQLite + BM25 + optional Claude) mirrors the
   Snowflake schema 1:1 so the demo never depends on Wi-Fi; `snowflake/` holds the Cortex-native version
   (AI_EXTRACT, Cortex Search, Cortex Analyst semantic model, Cortex Agent, row access policies,
   Snowpark procs, Streamlit-in-Snowflake) for the Best Use of Snowflake prize.
6. **Receipts, not clones.** No persona simulation, ever. The employee reviews what's captured about them
   (review queue, query log) — that's why they participate.

## Demo company: Harbourline Credit Union (Halifax, NS)
~10 people, 6 months (2026-03-01 → 2026-08-31). **Sarah Chen** (senior backend engineer) gives notice
2026-08-28, last day 2026-09-11. **Alex Rivera** joins 2026-09-14. Five planted landmines, incl.
the reconciliation job that must skip the 1st (later: 1st *and* 15th — a superseded fact), and the
vendor API key that must never be rotated on a Friday.

## Scope for Hack Atlantic (Sep 26–27, 2026)
| Must (demo breaks without it) | Should | Won't (this weekend) |
|---|---|---|
| Truth file + renderer + frozen question splits | Onboarding brief (Alex) | Voice interviewer |
| Extraction → bi-temporal graph | My Knowledge (review queue + query log) | Claim verifier / sensors |
| Risk map (bus factor, countdown) | Gap-interview question list | GRPO / LLM fine-tuning |
| Handoff pack + sign-off | Enron / PEP real-data eval | Real Slack OAuth connectors |
| Ask: said / inferred / no-evidence + route | What-if (remove person) | Multi-tenant auth |
| Bandit over answer/abstain/route + reward curve | Snowflake live deploy | |
| Benchmark vs plain search + charts | | |
| Streamlit app + Snowflake SQL/Cortex assets | | |

## Reward table (memorize for judges)
| Outcome | Reward |
|---|---|
| Correct answer with valid citation | **+1.0** |
| Correct abstain, or correct route | **+0.5** |
| Unnecessary abstain (answer was available) | **−0.3** |
| Confident wrong answer (hallucination) | **−2.0** |
| Calibration bonus | `+0.2 × (1 − |confidence − correct|)` |

Risk: `risk = importance × (1 − redundancy) × departure_likelihood`.

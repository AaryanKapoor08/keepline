# Keepline web demo

The flagship demo app (Next.js 16, Tailwind 4, motion, react-force-graph-2d, Recharts) on top of a thin FastAPI layer (`api/server.py`).

## Run it (two commands, from the repo root)

```bash
python -m uvicorn api.server:app --port 8000      # live API over the keepline package
cd web && npm run dev                              # http://localhost:3000
```

If the API is down, every screen falls back to the static snapshot in `web/public/data/` (a dot in the corner says LIVE or SNAPSHOT), so the demo still works.
Refresh the snapshot after the data or results change: `python scripts/export_web_data.py`.

Keys: `→` / `Space` next beat · `←` back · `1`–`9` jump to a beat · `P` presenter focus (collapses the sidebar).
Demo clock: Friday 2026-09-04. Sarah Chen's last day is Fri 2026-09-11.

## Presenter script: 2 minutes (one page per beat; → / Space moves to the next page)

Each page opens with one headline and one black button. Press the button, then say the line.

| Page | Click | Say |
|---|---|---|
| Home | none | "Sarah Chen is Harbourline's senior backend engineer. She leaves Friday. 46 things leave with her, and 3 systems have no one else who knows them." |
| Knowledge | **Replay history**, then click a red node | "This is her knowledge as a workflow: Sarah → her systems → what only she knows → who should take it over. Every fact keeps its history: the recon rule 'skip the 1st' was replaced by 'skip the 1st and 15th'. Click any node for the receipts." |
| Risk | **Simulate her leaving** | "Flip the switch. Three systems go to zero people. 4 systems only she can access, 12 never-do-this rules, 26 recurring tasks with no owner." |
| Handoff | **Generate handoff pack**, open **Landmines**, then **Sarah signs off** | "The handoff pack writes itself from her own messages, each line with a quote, a date and a link. She confirms it and signs." |
| Ask | (first answer is pre-loaded), then the NAS question, then **Ask Mike** | "Alex starts Monday. He gets the current rule with its source. When there's no evidence, Keepline says 'I don't know, ask Mike' instead of guessing." |
| Simulator | (conflict is pre-loaded), then **Why** | "Before you act, check the plan. Rotating the CoreLink key this Friday conflicts with a rule Sarah wrote on June 10." |
| Proof | **Train**, then **Add noise** | "On 216 held-out questions: 43% right with a source vs 36% for plain search, confidently wrong 44% vs 72%, routed to the right person 100% vs 57%. The bandit learns when to answer, abstain or route. Honestly, its thresholds haven't beaten the calibrated default yet." |
| Snowflake | **Execute workflow** | "All of it runs inside Snowflake, so the data never leaves. Glean finds what your company knows. Keepline shows what it's about to forget." |

## 4-minute version (additions)

- Knowledge: click Reconciliation, then the landmines node, and read one receipt aloud.
- Risk: click **View all** to open the full lists.
- Ask: open **Ask your own question** and type a live question (needs the API running).
- Simulator: try "Run the reconciliation job manually on the 15th".
- Proof: drag the noise slider from Clean to Brutal. Plain search gets worse; Keepline holds or abstains.
- Snowflake: open **Market** on the pricing card.

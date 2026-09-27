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

## Presenter script: 2 minutes

| Time | Screen | Click | Say |
|---|---|---|---|
| 0:00 | Overview | — | "Sarah Chen is Harbourline Credit Union's senior backend engineer. Her last day is next Friday. When she leaves, what breaks on Monday? Keepline read 3,914 messages, left out the private DMs, and found 45 things only Sarah knows." |
| 0:15 | Constellation | Click **Open Sarah Chen**, then press ▶ | "This is the company's knowledge: people, areas, facts, receipts. The red areas are one person deep. This is Sarah's memory replayed from March. Watch May: 'skip the 1st' gets superseded by 'skip the 1st and the 15th'. Every fact records who said it, when, and what replaced it." |
| 0:35 | Knowledge profile | — | "This is what we captured from Sarah, not a clone of her. She reviews every item, DMs are off by default, and none of it goes into a performance review." |
| 0:45 | Risk map | Toggle **Simulate Sarah's departure** | "Risk is importance × lack of redundancy × departure. Flip the switch: three areas are orphaned, with 12 landmines and 4 vendor contacts nobody else holds." |
| 0:55 | Handoff pack | Wait for the loader, expand one landmine, click **Sarah signs off** | "The handoff pack writes itself from her own receipts. Every line has a verbatim quote. Sarah confirms it and signs." |
| 1:10 | Ask | Click chip 1 (reconciliation), then chip 4 (NAS RTO) | "Alex starts Monday. He gets the current rule, and the old one shown as replaced. When there's no evidence, Keepline says so: 'I don't know, ask Mike.'" |
| 1:25 | Simulator | **Check** on "Rotate the CoreLink API key this Friday" | "Before you act, check the plan against memory. Conflict: Sarah wrote on June 10, 'don't rotate the CoreLink key on a Friday.'" |
| 1:40 | RL lab & proof | Let the replay run; point at the test table | "A contextual bandit is rewarded +1 for a cited answer and −2 for a confident wrong one, graded against a truth file the product never sees. On the frozen test split (N=216), cited accuracy is 43% vs 36% for plain search. Confident-wrong answers drop from 72% to 44%, and calibration error falls from 0.27 to 0.05." |
| 1:55 | Snowflake & market | — | "It all runs inside Snowflake, so the data never leaves. Glean finds what your company knows. Keepline shows what it's about to forget, and saves it." |

## Presenter script: 4 minutes (additions)

- **Overview (+15s):** read the countdown. Point out the sole-access systems, vendor contacts and recurring tasks listed in the footer.
- **Constellation (+30s):** hover a red diamond (landmine) and an area to show its risk and bus factor. Scrub the slider by hand to May, then to August (CoreLink rep Dan Holt → Maria Santos; 90-day → 60-day key rotation).
- **Profile (+15s):** walk through the gap questions ("Landmine with no recorded reason"). These are what Keepline asks Sarah before she leaves.
- **Handoff (+20s):** open an access item and show the receipt: monospace doc id, date and deep link.
- **Ask (+20s):** "Is it safe to rotate the CoreLink API key on a Friday?" Keepline knows today is a Friday. Then show the confidence meter and the policy arm.
- **Simulator (+30s):** run the departure what-if for Sarah, Mike and Tom by 2026-12-31. Then plan staffing on the pasted brief: bus factor before → after, with a learner and reviewer pairing.
- **RL lab (+40s):** step through the loop cards: question → features → arm → action → grader → reward. Drag the **chaos ladder** from L0 to L4 (typos, slang, bot spam, 3× chatter). Plain search hallucinates more as the data gets messier, while Keepline holds or abstains. Be honest: the bandit thresholds tuned on dev over-abstain on test. The calibrated default is the headline, and more real usage data is the roadmap.
- **Close (+10s):** go through the pricing and the Glean comparison table.

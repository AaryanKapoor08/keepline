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

## Hook
"Sarah leaves Friday. Alex starts Monday — zero days of overlap. Tuesday is the 15th: Alex runs the reconciliation job, and it breaks. The only warning was one email Sarah sent in May."

## Proof line
"On 216 questions it had never seen, plain search gave a confident wrong answer to 3 in 4. Keepline: 1 in 5 — when it doesn't know it says so, and when it routes, it picked the right person 21 out of 21 times."

## The 5-second pitch
"Keepline is GitHub for company knowledge: every fact is a commit with an author and a receipt, changes are diffs, the leaver reviews her knowledge like a pull request, and you can check out what the company believed on any date."

## Presenter script: 2 minutes (the owner's click order; → / Space moves between pages)

1. **Home** → click **Open Sarah's knowledge**.
2. **Knowledge** opens with Sarah's sheet: scroll to **Don'ts** (CoreLink Friday rule near the top) and expand one receipt.
3. **Review** (next page): Sarah's queue. Click **Approve** on the first card ("Merged into company memory · commit …"). Optional: **Correct** the next one.
   *Optional, 10 s:* back on Sarah's sheet, scroll to **Credit**: "and Sarah gets credit — privately first." Her knowledge answered questions for colleagues; she chooses whether to share it.
4. Press **⌘K** (or the "Ask Keepline" pill), asking as Alex: click "What should I know before touching reconciliation?", then type or click "What's the Bedford branch wifi password?" (an honest "I don't know"). Open **How I found this ›** once.
5. Back on **Knowledge**: **Simulate a change** → the field says "Retire CoreLink v2 before the Oct 31 sunset" → **Run** → point at the black card: "Without pairing, CoreLink is uncovered in 100% of futures; pair Aisha this week and it drops to 40%." Click a red "rules" badge if there's time.
6. **Proof**: point at the three rows (test split, N shown).

Resetting between rehearsals: press **R** on the Review page (or reload). Nothing in the demo path writes to the database.

## 4-minute version (additions)

- Home: read the three at-risk areas and the latest changes (each with a short commit hash).
- Knowledge: click Mike and Tom as well. Point out that lines show hands-on knowledge only, not job titles.
- History: switch areas (CoreLink API: key rotation 90 → 60 days; vendor rep Dan Holt → Maria Santos). Approve one fact and correct another.
- Simulate: try the mobile-app and FINTRAC templates. Read "Where we lack / strong / lose" and the timeline markers. Run the decision check "Rotate the CoreLink API key this Friday" → Conflict → Why.
- Proof: drag the noise slider from Clean to Brutal.

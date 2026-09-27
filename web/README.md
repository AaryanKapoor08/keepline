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

## The 5-second pitch
"Keepline is GitHub for company knowledge: every fact is a commit with an author and a receipt, changes are diffs, the leaver reviews her knowledge like a pull request, and you can check out what the company believed on any date."

## Presenter script: 2 minutes (→ / Space moves to the next page)

| Page | Click | Say |
|---|---|---|
| Home | Sarah in **Upcoming departures** | "This is Harbourline's COO dashboard. Five of ten critical areas are known by one person, and Sarah Chen leaves in 7 days." |
| Knowledge (Sarah's sheet) | open **Don'ts**, expand one; then ask pill 1 and pill 3 | "Here's what she knows, her don'ts, what she's handling, what only she can access, and who else knows it: for three systems, nobody. Ask about her areas: you get the current rule with a receipt, or 'I don't know, ask Mike'." |
| Knowledge (Alex) | close the sheet, click **View as Alex** | "Alex joins her team Monday. Keepline shows him who to ask about what, and the don'ts to learn first." |
| History | **Open reviews**, then **May 31** vs **Today** | "Every fact has a history. The recon rule was a diff: skip the 1st, then the 1st and 15th. Sarah reviews what was captured like a pull request; nothing is shared until she merges it. Check out any date, which is Snowflake Time Travel." |
| Simulate | **Run simulation**, switch Fastest ↔ Balanced, then tap **Aisha** in What-if | "Before staffing the CoreLink v3 upgrade, play out 2,000 futures. Fastest leaves an area uncovered 100% of the time. Balanced pairs Aisha as a learner and cuts that to 64%. If Aisha also leaves mid-project, you see what stalls. It's a recommendation for a manager to approve, never a performance score." |
| Proof | **Train** | "On 216 held-out questions: 43% right with a source vs 36%; confidently wrong 44% vs 72%. The bandit learns when to answer, abstain or route; honestly, it hasn't beaten the calibrated default yet." |
| Snowflake | **Execute workflow** | "It all runs inside Snowflake. Glean finds what your company knows. Keepline shows what it's about to forget." |

## 4-minute version (additions)

- Home: read the three at-risk areas and the latest changes (each with a short commit hash).
- Knowledge: click Mike and Tom as well. Point out that lines show hands-on knowledge only, not job titles.
- History: switch areas (CoreLink API: key rotation 90 → 60 days; vendor rep Dan Holt → Maria Santos). Approve one fact and correct another.
- Simulate: try the mobile-app and FINTRAC templates. Read "Where we lack / strong / lose" and the timeline markers. Run the decision check "Rotate the CoreLink API key this Friday" → Conflict → Why.
- Proof: drag the noise slider from Clean to Brutal.

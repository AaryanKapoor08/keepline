# Keepline UI plan

**What I studied:** apple.com/iphone and /privacy, attio.com, stripe.com, mercury.com, linear.app/method and press.stripe.com, plus the owner's four dashboard references (Workhubs, a PM dashboard, Shakuro and Halo Lab).
The elegant ones share four habits:
- They use almost no colour. Ink sits on white or a light-grey canvas, and one dark or blue pill carries the action.
- Headlines are very large and set tight. The body copy is small, grey and short.
- They leave a lot of whitespace, with at most 2–4 objects on a screen.
- Detail is revealed only when you ask for it, through pills, chevron links or expanding cards.

The dashboard references add white cards on a grey canvas, a large radius, soft shadows, huge numbers with tiny captions, and people shown as monogram pills.

## Typeface
**Jost** (self-hosted with next/font). It's a geometric grotesk in the Futura tradition, like the Workhubs reference. It feels friendly and calm, and it isn't one of the default "vibe-coded" fonts.
- Weights: 400 for body text, 500 for headlines.
- There is no serif anywhere.

## Palette (5 tokens + 1 accent + 1 risk)
| token | value | use |
|---|---|---|
| canvas | `#f4f5f7` | page background |
| surface | `#ffffff` | cards |
| ink | `#1d1d1f` | text, chart lines, the black highlight card |
| muted | `#6e6e73` | captions, secondary text |
| hairline | `#e5e5ea` | dividers |
| accent | `#0071e3` | **only** the one primary pill per screen |
| risk | `#d93025` | **only** a landmine or at-risk number or word |

There are no other colours: no coloured badges, icons, rings or multi-colour charts. Charts are drawn with ink and grey lines only, plus the accent line for Keepline.

## Scale
- **Type:** display 56 / headline 40 / title 24 / body 17 / caption 14.
- **Spacing:** 8-pt grid. Cards use 56px padding.
- **Radius:** 28 for cards, 999 for pills.
- **Shadow:** `0 1px 2px rgba(0,0,0,.04), 0 8px 24px rgba(0,0,0,.04)`.
- **Motion:** 600–900 ms ease-out fade plus 16px rise, and nothing else. No counters, pulses, glows, timers or status dots.

## Wireframe (each first view has a headline, ≤1 line, ≤3 numbers and one primary pill)
1. **Hero:** Sarah's profile card (monogram) with "Knowledge that stays." Clicking **See what leaves with her** scrolls to scene 2.
2. **Graph:** "46 things only Sarah knows." **Show me** reveals her graph. **Replay history ›** shows the recon rule being replaced.
3. **Risk:** "3 systems. No one else knows them." Three white tiles. **Simulate her leaving** turns the tiles red and shows three one-line losses.
4. **Handoff:** "Her handoff pack, written for her." **Generate** shows 6 cards (title + count; Landmines is the black card). Clicking a card opens its items with receipts. **Sarah signs off** leads to "Signed".
5. **Ask:** "Alex starts Monday." Three question chips. Each gives a one-line answer and a quote. **Show source ›** reveals the receipt. The unknown question gives "Ask Mike" with an **Ask Mike** pill.
6. **Decision:** One pill, **Rotate the CoreLink key this Friday**. It returns "Conflicts with a rule Sarah set." **Why ›** shows her quote. **Try another ›** reveals 2 more chips.
7. **Proof:** "Tested on 216 questions it had never seen." **Compare** shows 3 big rows with n. **Add noise ›** reveals the chaos slider. **How it learns ›** reveals the RL loop and the honest note.
8. **Close:** A black highlight card: "Built on Snowflake. Private by design." It has 5 labels, the tagline and **Explore the app ›**.

Secondary routes open with the same scene first, then an "All details ›" link that reveals the dense view.

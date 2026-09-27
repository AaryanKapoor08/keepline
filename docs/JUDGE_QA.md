# Keepline — Judge Q&A card

Rule: answer in ≤15 seconds, then stop. Lead with the claim, back it with one number or one thing on screen.

---

## TECH judge

**1. "How does it actually capture knowledge?"**
It reads the work people already do — Slack, email, tickets, docs — splits it into statements, and keeps each one as a fact with a receipt: who said it, when, and a link to the source. Duplicates merge into extra receipts; when a value changes, the old fact is closed and linked to the new one, like a commit.

**2. "Is the extraction just rules?"**
By default, yes — it runs offline and free, and it's what we benchmarked, so the numbers are honest. Claude and Snowflake Cortex AI_EXTRACT are wired in as drop-in extractors; the chat assistant already runs on Claude with tool use.

**3. "How do you know it's accurate? Didn't an LLM grade its own homework?"**
Truth first: we wrote 168 true facts, then generated the company's Slack and email from them. Keepline only sees the messages; a grader compares answers to the truth file. The test set — 216 questions on facts it never saw — was frozen by hash and run once. Keepline is confidently wrong 44% of the time vs 72% for plain search, and routes to the right person 100% of the time.

**4. "Where's the RL?"**
Two learned parts. A confidence calibrator trained on 388 questions cut calibration error from 0.27 to 0.05 on unseen questions — that generalized. A contextual bandit learning when to answer, abstain or route beat the default on dev but not on the held-out test — with 388 questions it overfit, and we show that openly. More real usage fixes it.

**5. "What stops it hallucinating?"**
Every answer must cite a source the tools actually returned — anything else is stripped before it reaches the user. If there's no evidence it says "I don't know" and routes to who does. Confident wrong answers cost −2 in training, a correct "I don't know" earns +0.5.

**6. "What happens when data is messy?"**
We tested it: the chaos ladder corrupts the data at five levels — typos, bot spam, split messages, wrong claims from non-experts. Plain search collapses to 16% accuracy and hallucinates 83% of the time; Keepline degrades slowly and passes it from level 3.

**7. "Is this really on Snowflake?"**
Yes — the schema, row access policies, Cortex Search, a Cortex Analyst semantic model and a Cortex Agent are deployed in our account. [Have Snowsight open on KEEPLINE.CORE.FACTS as backup.] The local engine mirrors the Snowflake tables 1:1 so the demo also runs offline.

---

## BUSINESS judge

**1. "Who pays?"**
The owner or COO of a 20–250-person company — the person who gets the call when something breaks after someone leaves. We reach them through accountants and IT service providers who already advise them on succession.

**2. "What does it cost and why would they pay?"**
$8–20 per user per month, plus a paid handoff pack per departure. Replacing an employee costs 0.5–2× their salary (Gallup). A 60-person firm pays ~$11K a year — less than one week of a senior engineer's disruption.

**3. "Have you talked to customers?"**
[Say only what's true.] "We've started: <N> owners so far, and the pattern is <quote>. Before we charge anyone we validate pricing with 5+ Atlantic Canadian owners." — if none yet: "Not yet — that's this month's work, starting with accountants who see every succession."

**4. "How do you get in the door?"**
A free knowledge risk scan: connect Slack and tickets, and in a day the owner sees which systems only one person knows. That map sells the product.

**5. "Isn't this surveillance? Won't employees hate it?"**
It's built so employees want it: DMs are never included, everything starts private in their own review queue, nothing is shared until they approve it, and it's never used in performance reviews. They get credit for knowledge they share — and fewer "quick question" pings.

**6. "What's the ROI story in one line?"**
"The call you get after someone leaves — which job not to run, which vendor only knew them — Keepline answers it before they walk out."

---

## MARKET judge

**1. "Viven raised $35M. Sensay exists. Why you?"**
Viven clones employees for enterprises; Sensay interviews you on the way out. We keep receipts, not clones — a continuous, versioned memory that knows which answer is current and shows risk months before anyone resigns — for companies too small for them.

**2. "Why won't Glean or Microsoft just do this?"**
Glean has a ~100-seat minimum and $50K+ contracts, and searches what's written. Nobody is building for the 20–250-person firm, and nobody tracks which answer is current or who is about to leave with it.

**3. "Small companies don't run Snowflake."**
They don't need to. We run Keepline for them on Snowflake, each customer isolated. Companies already on Snowflake install it from the Marketplace and their data never leaves their account.

**4. "How big is this?"**
Canada alone has ~1.07M small and ~17,000 medium employer businesses (ISED 2024). Organizations expect 51% of their workforce to retire or leave within five years, and only 8% consistently capture what leavers know (APQC 2025). New Brunswick loses ~20% of its workforce to retirement within a decade.

**5. "Why now?"**
The retirement wave is here, AI can finally read unstructured work, and data platforms like Snowflake let us process it without it leaving the company.

**6. "What's the biggest risk?"**
No single buyer owns this problem today — so we lead with the owner/COO and the moment of a resignation, when the pain is obvious. And Slack's 2025 API terms limit third-party indexing, so we're designed around them: we run inside the customer's own Snowflake.

---

## Traps to avoid
- Never say "clone", "digital twin", "trained on Sarah", or "as Sarah would say".
- Don't claim "tested on real Slack" — it's a synthetic company modelled on real Slack mess.
- Don't claim the RL bandit beats the default on test — it doesn't; the calibrator is the learned part that generalized.
- Don't quote "92% (Deloitte)" — the real source is APQC 2025: only 8% capture knowledge consistently.
- Say numbers with their N when asked: 216 test questions, 137 answerable, 21 routing.

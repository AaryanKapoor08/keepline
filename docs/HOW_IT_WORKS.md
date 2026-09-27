# How Keepline works — in plain English

## The one-line version
Keepline reads the work people already do (chat messages, emails, tickets), turns it into a list of facts with proof attached, and uses that to answer questions, spot risk, and plan for people leaving.

## 1. Where the information comes from
A company's IT person connects Slack, email, and the ticket system once. After that, new messages flow in by themselves. Private direct messages are never included. Nothing is installed on anyone's laptop.
*(In our demo, the company "Harbourline" is made up, and so are its messages.)*

## 2. Turning messages into facts
Keepline reads each message and pulls out useful statements, like *"Never rotate the CoreLink key on a Friday."* Each one becomes a **fact**, and every fact keeps its **receipt**: who said it, when, and a link back to the original message.

## 3. The graph
A graph is just a map of dots and lines.
- **Dots** are people, topics (like "Payroll" or "Reconciliation"), and facts.
- **Lines** say how they connect: *Sarah knows Reconciliation*, *this fact is about Payroll*.

We draw a line from a person to a topic only when they've **actually done the work** — closed tickets, answered questions — not because of their job title. So when a topic has only **one** line going to it, only one person really knows it. That's the red "only one person knows it" warning.

## 4. "GitHub for company knowledge"
Facts change. In March the rule was "skip the 1st"; in May it became "skip the 1st and the 15th." Keepline keeps **both**, marks the old one as replaced, and remembers who changed it and when — like GitHub keeps every version of code. So it always gives the **current** answer, and you can still see the history.

## 5. Asking questions
When someone asks something, Keepline looks for the facts that match and answers with the receipts attached. If it can't find proof, it says **"I don't know — ask Mike"** instead of guessing. The chat assistant uses Claude (an AI model) but is only allowed to repeat what the receipts say.

## 6. The simulation
You type a planned change, like *"Upgrade the CoreLink system next month."* Keepline looks at the graph and shows:
- which topics it touches,
- who knows them — and whether they're leaving,
- which "never do this" rules could be broken,
- who should learn it now.

It imagines the project playing out 2,000 times, with random sick days and the known departures, and counts how often a topic ends up with nobody who knows it. That's the "100% without pairing, 40% if Aisha learns now" number.

## 7. The "RL" (reinforcement learning) part
RL just means **learning from rewards**, like training a dog with treats. Our assistant gets points after each practice question:
- +1 for a right answer with proof
- +0.5 for honestly saying "I don't know" when it really doesn't
- −2 for a confident wrong answer

Over hundreds of practice questions it learns **when to answer and when to hold back**. We don't retrain the AI model itself — we tune its decisions.

## 8. How we prove it works
We wrote the company's "answer key" first (168 true facts), then generated the messages from it. Keepline only sees the messages. Then we asked it 216 questions it had never seen and checked its answers against the key.
- Plain search: confidently wrong **72%** of the time.
- Keepline: confidently wrong **44%**, and it sent people to the right colleague **every time**.

## 9. Where Snowflake fits
Snowflake is the company's secure data warehouse. Keepline runs **inside** it: the messages, facts and graph live there, Snowflake's AI tools (Cortex) search and read them, and permission rules make sure people only see what they're allowed to. The data never leaves the company's account.

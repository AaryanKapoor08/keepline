"""Seed ~2 weeks of simulated product usage (Aug 20 - Sep 3, 2026) into the query log for the demo.

Questions are hand-written for the demo (never taken from the benchmark or its answer key) and answered by the real
product agent, so every logged answer and credit is genuine output. The UI labels this "Demo usage: simulated
questions." Re-running replaces the previous seed.

Usage:  python scripts/seed_demo_usage.py
"""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from keepline.agent.answer import load_default_agent  # noqa: E402

QUESTIONS: list[tuple[str, str]] = [
    ("alex", "Which days does the nightly reconciliation job skip?"),
    ("alex", "Is it safe to rotate the CoreLink API key on a Friday?"),
    ("alex", "Who is our account manager at CoreLink?"),
    ("alex", "Where is the SFTP key for Bluenose kept?"),
    ("alex", "How does the portal SSL cert get renewed?"),
    ("alex", "What time does the nightly recon job run?"),
    ("alex", "Who can create CoreLink API keys?"),
    ("alex", "How often do we rotate the CoreLink API key?"),
    ("alex", "What is the CoreLink API rate limit?"),
    ("alex", "Where do the CoreLink credentials live?"),
    ("aisha", "What should I check before re-running recon by hand?"),
    ("aisha", "Who signs off on reconciliation corrections?"),
    ("aisha", "When is the Payments Canada exchange cutoff?"),
    ("aisha", "Can I restart the ACH server before the Payments Canada cutoff?"),
    ("aisha", "Who is our DNS host?"),
    ("aisha", "Where are the member portal certificates stored?"),
    ("aisha", "What breaks if the recon job runs on the 15th?"),
    ("aisha", "Which vault holds the Paylane admin login?"),
    ("aisha", "How do I upload a new cert to the portal?"),
    ("jen", "Who handles debit card disputes with the processor?"),
    ("jen", "When does the member portal certificate expire?"),
    ("jen", "Who do I call when online banking is down?"),
    ("jen", "Who fixes the member portal password reset flow?"),
    ("jen", "Where is the card processing runbook?"),
    ("jen", "Who is the contact at the card processor?"),
    ("dave", "Who owns nightly reconciliation?"),
    ("dave", "Who has admin on the CoreLink partner portal?"),
    ("dave", "Which vendor contacts only go through Sarah?"),
    ("dave", "Who renews the SSL certificate?"),
    ("dave", "Who runs the monthly backup restore test?"),
    ("dave", "Who files the FINTRAC large cash transaction reports?"),
    ("dave", "What happens to the registrar account when Sarah leaves?"),
    ("priya", "When do T4s need to be issued?"),
    ("priya", "Who approves reconciliation mismatches?"),
    ("priya", "When is the payroll cutoff?"),
    ("priya", "Where is the ACH settlement file saved?"),
    ("priya", "Who do I ask about the recon report?"),
    ("priya", "What time is the final EFT exchange?"),
    ("colin", "How do I reset a member's online banking password?"),
    ("colin", "Who handles locked member accounts?"),
    ("colin", "What do I do when the portal shows a certificate warning?"),
    ("colin", "Who do I escalate card fraud to?"),
    ("nadia", "Can I restore a backup onto the replication primary?"),
    ("nadia", "How often do we run the backup restore test?"),
    ("nadia", "Where is the restore box?"),
    ("nadia", "What should I do when the Okta AD sync stalls?"),
    ("nadia", "Who renews the SSL cert for the member portal?"),
    ("nadia", "Where are the DNS records managed?"),
    ("nadia", "What is our recovery time objective if the NAS dies?"),
    ("nadia", "Who has the Veeam admin password location?"),
    ("alex", "What should I never do with the recon job?"),
    ("alex", "Why does recon skip the 15th?"),
    ("aisha", "Who is the new CoreLink rep?"),
    ("aisha", "What is the CoreLink EOD extract?"),
    ("dave", "Who knows the ACH batch server?"),
    ("jen", "Who can change the portal FAQ?"),
    ("priya", "Who reconciles the GL after month end?"),
    ("colin", "Who do I ask about member portal outages?"),
    ("nadia", "Who else can rotate the CoreLink key?"),
    ("alex", "Where is the CoreLink API cheat sheet?"),
]

START = datetime(2026, 8, 20, 8, 30)
END = datetime(2026, 9, 3, 17, 30)


def main() -> None:
    agent = load_default_agent(use_llm=False)
    store = agent.store
    rng = random.Random(7)
    with store.conn:
        store.conn.executemany("DELETE FROM query_about WHERE query_id IN (SELECT id FROM query_log WHERE question = ?)",
                               [(q,) for _, q in QUESTIONS])
        store.conn.executemany("DELETE FROM query_log WHERE question = ?", [(q,) for _, q in QUESTIONS])
    span = (END - START).total_seconds()
    n = 0
    for asker, q in QUESTIONS:
        when = START + timedelta(seconds=rng.random() * span)
        when = when.replace(hour=8 + int(rng.random() * 9), minute=rng.randrange(60))  # working hours
        if when.weekday() >= 5:  # nobody asks on weekends
            when -= timedelta(days=2)
        ans = agent.answer(q, asker, as_of=date(when.year, when.month, when.day))
        qid = store.log_query(asker, q, ans)
        with store.conn:
            store.conn.execute("UPDATE query_log SET asked_at = ? WHERE id = ?", (when.replace(microsecond=0).isoformat(), qid))
        n += 1
    print(f"seeded {n} simulated questions ({START:%b %d} - {END:%b %d})")


if __name__ == "__main__":
    main()

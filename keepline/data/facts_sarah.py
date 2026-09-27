"""Ground truth for Sarah Chen's areas: reconciliation, CoreLink API, SSL/DNS.

Almost everything here is sole-owned by Sarah -- that is the point: these are the areas Harbourline is about to
lose when she leaves on 2026-09-11.
"""

from __future__ import annotations

from keepline.data.spec import K, FactSpec

_RECON_WHERE = ["#eng-core", "#finance", "email", "ticket", "doc"]
_CL_WHERE = ["#eng-core", "#ops", "email", "ticket", "doc"]
_SSL_WHERE = ["#eng-core", "#ops", "email", "ticket", "doc"]

FACTS: list[FactSpec] = [
    # ------------------------------------------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------------------------------------------
    FactSpec(
        key="recon.skip_days.v1", kind=K.LANDMINE, area="reconciliation", importance=3, landmine=True,
        statement="The nightly reconciliation job must skip the 1st of the month (CoreLink's month-start rollover "
                  "makes the numbers never line up).",
        kw=[["1st", "first"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2024-11-04", valid_to="2026-05-19",
        say=[
            "Heads up: the recon job skips the 1st of every month. CoreLink does its month-start rollover overnight "
            "and the balances never line up, so don't 'fix' that skip.",
            "yep that's on purpose, recon doesn't run on the first of the month. rollover on the CoreLink side "
            "makes it throw hundreds of fake mismatches",
            "If you ever touch the Jenkins schedule for recon: it has to skip the 1st. Learned that one the hard way "
            "back in 2024.",
            "Rule of thumb for the nightly reconciliation: every day except the 1st. The first is month-start "
            "rollover at CoreLink and it's garbage data until the 2nd.",
        ],
        prompts=["Why didn't the recon report come through this morning? Is it broken?",
                 "Noticed the recon cron has a weird exclusion in it - is that intentional?"],
        where=["#eng-core", "#finance", "doc", "email"],
        askers=["aisha", "priya"],
        notes="Superseded on 2026-05-19 after the May 15 incident.",
    ),
    FactSpec(
        key="recon.skip_days.v2", kind=K.LANDMINE, area="reconciliation", importance=3, landmine=True,
        statement="The nightly reconciliation job must skip both the 1st and the 15th of the month; CoreLink's "
                  "mid-month interest posting batch on the 15th double-posts into the suspense account.",
        kw=[["1st", "first"], ["15th", "fifteenth"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2026-05-19", supersedes="recon.skip_days.v1",
        say=[
            "Update after Friday's mess: the recon job now skips the 1st AND the 15th. CoreLink posts mid-month "
            "interest on the 15th and our job double-posted everything into suspense.",
            "New rule for the nightly reconciliation, effective today: no run on the 1st, no run on the 15th. "
            "I've changed the Jenkins schedule, please don't revert it.",
            "short version: skip the first and the fifteenth. the 15th is CoreLink's interest batch and it wrecks "
            "the suspense account if recon runs against it",
            "It's not just the 1st anymore - since the May 15 incident recon also sits out the 15th of every month. "
            "Interest posting on the CoreLink side lands mid-run.",
            "Reminder for anyone covering recon: the job is scheduled every night except the 1st and the 15th. "
            "Both exclusions are load-bearing.",
        ],
        prompts=["Recon didn't run last night, it was the 15th - bug or feature?",
                 "Can someone confirm which days the nightly recon is supposed to skip?"],
        where=["#incidents", "#eng-core", "ticket", "doc", "email", "#finance"],
        askers=["aisha", "priya", "dave"],
        renders=5,
        qs=[
            "Which days of the month does the nightly reconciliation job skip?",
            "Is there any day the recon job shouldn't run?",
            "I'm taking over the reconciliation schedule in Jenkins. Anything I shouldn't change?",
            "Does the recon job run on the 15th?",
            "What dates are excluded from the nightly CoreLink reconciliation, and why?",
            "Before I clean up the cron expression for recon, are the skipped days intentional?",
            "Is it safe to let reconciliation run every night of the month?",
        ],
        notes="Supersedes the 1st-only rule. Triggered by the 2026-05-15 reconciliation incident.",
    ),
    FactSpec(
        key="recon.run_time.v1", kind=K.FACT, area="reconciliation", importance=2,
        statement="The nightly reconciliation job starts at 01:30 Atlantic.",
        kw=[["1:30", "01:30", "1.30"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2023-02-01", valid_to="2026-06-08",
        say=[
            "recon kicks off at 1:30am Atlantic, usually done by 2",
            "The reconciliation job is scheduled for 01:30 every night in Jenkins.",
            "It starts at 1:30 in the morning, so if you see nothing in the recon report by 3 something's off.",
        ],
        prompts=["What time does the nightly recon actually start?"],
        where=_RECON_WHERE, askers=["aisha", "priya"],
    ),
    FactSpec(
        key="recon.run_time.v2", kind=K.DECISION, area="reconciliation", importance=2,
        statement="Since 2026-06-08 the nightly reconciliation job starts at 02:15 Atlantic, after CoreLink's "
                  "end-of-day extract lands (~02:05).",
        kw=[["2:15", "02:15", "2.15"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2026-06-08", supersedes="recon.run_time.v1", forbid=[["1:30", "01:30"]],
        contra=[("dave", "Pretty sure recon still kicks off at 1:30 in the morning, that's what's on the ops "
                         "calendar anyway.")],
        say=[
            "No, I moved it - recon starts at 2:15 now. CoreLink's EOD extract wasn't reliably there before 2.",
            "Heads up, I've shifted the nightly recon to 02:15 starting tonight so it runs after the extract lands.",
            "The ops calendar is stale, sorry. Reconciliation runs at 2:15am Atlantic as of June.",
            "Schedule change: recon job now at 02:15 instead of the old slot. Fewer false mismatches from half-"
            "written extract files.",
        ],
        prompts=["What time does recon run these days?"],
        where=_RECON_WHERE, askers=["dave", "priya", "aisha"],
        qs=[
            "What time does the nightly reconciliation job start?",
            "When does recon kick off each night?",
            "If I want to watch the recon job run, what time should I be looking at Jenkins?",
            "Is the reconciliation still scheduled at the old time or did that change?",
            "What's the current start time for the CoreLink reconciliation?",
            "Roughly when should the recon job begin overnight?",
        ],
        notes="Conflict: Dave repeats the old 01:30 time from a stale ops calendar; Sarah (owner) corrects him. "
              "Sarah's 02:15 is authoritative.",
    ),
    FactSpec(
        key="recon.report_recipients.v1", kind=K.FACT, area="reconciliation", importance=2,
        statement="The daily reconciliation report is emailed only to Priya.",
        kw=[["Priya", "priya.nair"]], known_by=["sarah", "priya"], stated_by="sarah",
        valid_from="2023-02-01", valid_to="2026-07-06",
        say=[
            "The recon report just goes to Priya's inbox each morning, nobody else gets it.",
            "Right now the daily reconciliation summary is emailed to priya.nair@ only.",
            "Only Priya gets the recon email. If she's away nobody's looking at it, which is a bit scary.",
        ],
        where=["#finance", "#eng-core", "email"], askers=["dave", "aisha"],
    ),
    FactSpec(
        key="recon.report_recipients.v2", kind=K.DECISION, area="reconciliation", importance=2,
        statement="Since 2026-07-06 the daily reconciliation report goes to the finance@harbourlinecu.ca "
                  "distribution list (Priya and Dave) instead of Priya alone.",
        kw=[["finance@"]], known_by=["sarah", "priya", "dave"], stated_by="sarah",
        valid_from="2026-07-06", supersedes="recon.report_recipients.v1",
        say=[
            "Done - recon report now goes to finance@harbourlinecu.ca, so Priya and Dave both get it.",
            "Switched the recon email target to the finance@ list today so it's not a single inbox anymore.",
            "FYI the reconciliation summary is sent to finance@harbourlinecu.ca from now on. Add yourself to that "
            "list if you want it.",
        ],
        prompts=["Can we get the recon report to more than just Priya? Holiday coverage is a pain."],
        where=["#finance", "email", "#eng-core"], askers=["dave", "priya"],
        qs=[
            "Who receives the daily reconciliation report?",
            "Where does the recon summary email get sent?",
            "I want to get the recon report every morning - which list do I join?",
            "If Priya is on vacation, does anyone else see the reconciliation report?",
            "What address is the nightly recon output mailed to now?",
        ],
    ),
    FactSpec(
        key="recon.owner", kind=K.OWNER, area="reconciliation", importance=3,
        statement="Sarah Chen owns the nightly CoreLink reconciliation job.",
        kw=[["Sarah", "Chen"]], known_by=["sarah", "dave"], stated_by="dave",
        valid_from="2021-03-01",
        say=[
            "Recon is Sarah's baby, ask her first.",
            "For anything reconciliation-related go to Sarah Chen, she built the job and runs it.",
            "Sarah owns the nightly recon. I just read the report.",
        ],
        prompts=["Who should I ping about a recon mismatch?"],
        where=["#eng-core", "#finance", "#ops"], askers=["priya", "jen", "aisha"],
        qs=[
            "Who looks after the nightly reconciliation job?",
            "Who should I talk to if the recon report looks wrong?",
            "Who owns reconciliation at Harbourline?",
            "Who's the go-to person for the CoreLink recon job?",
            "If the reconciliation breaks overnight, who do I contact?",
        ],
    ),
    FactSpec(
        key="recon.jenkins_host", kind=K.FACT, area="reconciliation", importance=2,
        statement="The reconciliation job is the 'recon-nightly' Jenkins job on the on-prem host jenkins01.",
        kw=[["jenkins01", "jenkins 01"]], known_by=["sarah", "aisha"], stated_by="sarah",
        valid_from="2022-05-01",
        say=[
            "It's the recon-nightly job on jenkins01 - the old box in the server room, not the cloud runner.",
            "recon lives on jenkins01. logs are in the job's console output",
            "If you need to look at recon, log into jenkins01 and find recon-nightly.",
        ],
        prompts=["Where does the recon job actually run? I can't find it in the new CI."],
        where=_RECON_WHERE, askers=["aisha", "nadia"],
        qs=[
            "Which server runs the reconciliation job?",
            "Where can I find the recon job in Jenkins?",
            "What host is the nightly recon on?",
            "I can't find reconciliation in our CI - where does it live?",
        ],
    ),
    FactSpec(
        key="recon.suspense_account", kind=K.FACT, area="reconciliation", importance=2,
        statement="Unreconciled differences are posted to suspense GL account 1995.",
        kw=[["1995"]], known_by=["sarah", "priya"], stated_by="sarah",
        valid_from="2021-03-01",
        say=[
            "Anything that doesn't match gets parked in GL 1995, the suspense account.",
            "the suspense account is 1995, that's where recon dumps the differences",
            "Mismatches post to suspense (GL 1995) and Priya clears them out once we know what happened.",
        ],
        prompts=["Where do the recon mismatches end up on the ledger?"],
        where=["#finance", "#eng-core", "doc"], askers=["priya", "aisha"],
        qs=[
            "Which GL account do reconciliation differences get posted to?",
            "What's the suspense account number for recon?",
            "Where do unmatched amounts from the nightly recon land in the ledger?",
            "When recon can't match something, which account does it go into?",
        ],
    ),
    FactSpec(
        key="recon.manual_rerun", kind=K.LANDMINE, area="reconciliation", importance=2, landmine=True,
        statement="Never re-run the reconciliation manually before CoreLink's end-of-day extract has landed; it "
                  "reconciles against a partial file and auto-posts wrong adjustments.",
        kw=[["extract", "EOD", "end of day", "end-of-day"], ["rerun", "re-run", "re run", "manually", "by hand"]],
        known_by=["sarah"], stated_by="sarah", valid_from="2023-09-12",
        say=[
            "Please don't re-run recon by hand until the CoreLink EOD extract is actually there. It'll happily "
            "reconcile a half file and post junk adjustments.",
            "Before any manual rerun, check the end-of-day extract has landed in the drop folder. Otherwise you get "
            "phantom adjustments and Priya has to reverse them.",
            "golden rule: no re-run until the extract file is complete. learned that in 2023",
        ],
        prompts=["Recon failed overnight, can I just kick it again from Jenkins?"],
        where=["#eng-core", "#incidents", "doc", "ticket"], askers=["aisha", "nadia"],
        qs=[
            "The recon job failed overnight. Anything I should check before re-running it?",
            "Is it safe to trigger the reconciliation manually in the morning?",
            "What can go wrong if I rerun recon by hand?",
            "Any gotchas with re-running the nightly reconciliation?",
            "Can I just hit build on the recon job again if it errors out?",
            "What do I need to wait for before manually running recon?",
        ],
    ),
    FactSpec(
        key="recon.tolerance", kind=K.DECISION, area="reconciliation", importance=2,
        statement="Reconciliation tolerance is $0.50 per account; anything above auto-opens a ticket.",
        kw=[["0.50", "50 cents", "fifty cents", ".50"]], known_by=["sarah", "priya"], stated_by="sarah",
        valid_from="2025-02-10",
        say=[
            "Tolerance is $0.50 per account - anything bigger opens a ticket automatically.",
            "we agreed with Priya on 50 cents per account as the recon tolerance. below that it's rounding noise",
            "Differences under $0.50 are ignored; over that, the job raises a ticket in the HCU queue.",
        ],
        prompts=["How big does a recon difference have to be before someone looks at it?"],
        where=["#finance", "#eng-core", "doc"], askers=["priya", "aisha", "dave"],
        qs=[
            "What's the tolerance threshold on the reconciliation?",
            "How much of a difference does recon ignore before flagging it?",
            "At what amount does a recon mismatch open a ticket?",
            "Is there a rounding tolerance in the nightly reconciliation?",
        ],
    ),
    FactSpec(
        key="recon.mismatch_procedure", kind=K.PROCEDURE, area="reconciliation", importance=2,
        statement="To clear a reconciliation mismatch: pull the CoreLink GL extract, compare it with the Jenkins log, "
                  "then post the correcting entry only with Priya's approval.",
        kw=[["Priya"], ["approv", "sign off", "sign-off", "signs off", "okay", "ok from"]],
        known_by=["sarah", "priya"], stated_by="sarah", valid_from="2023-02-01",
        say=[
            "Process is: pull the GL extract from CoreLink, diff it against the Jenkins log, and only post the "
            "correcting entry once Priya approves it.",
            "For mismatches - find the cause first (extract vs job log), then get Priya's sign-off before you touch "
            "the ledger. Never post corrections without her.",
            "you can investigate all you want but the correcting journal needs Priya's approval, full stop",
        ],
        prompts=["There's a mismatch on the recon report - what's the process to fix it?"],
        where=["#eng-core", "#finance", "doc", "ticket"], askers=["aisha"],
        qs=[
            "How do I resolve a mismatch flagged by the recon job?",
            "What's the process for posting a correction after reconciliation?",
            "Who has to approve a recon correcting entry?",
            "Can I post a fix to the ledger myself when recon finds a difference?",
            "Steps for clearing a reconciliation exception?",
        ],
    ),
    FactSpec(
        key="recon.monthly_signoff", kind=K.RECURRING_TASK, area="reconciliation", importance=2,
        statement="Every month Sarah sends Priya the reconciliation sign-off package by the 3rd business day.",
        kw=[["3rd business day", "third business day", "3 business days", "three business days"]],
        known_by=["sarah", "priya"], stated_by="sarah", valid_from="2022-01-01",
        say=[
            "Monthly recon package goes to Priya by the 3rd business day, she needs it for month-end close.",
            "Reminder to self and anyone watching: recon sign-off pack due to finance on the third business day.",
            "Priya expects the monthly reconciliation sign-off within three business days of month end.",
        ],
        prompts=["When does finance need the monthly recon stuff?"],
        where=["#finance", "email", "#eng-core"], askers=["aisha", "dave"],
        qs=[
            "When is the monthly reconciliation sign-off due to finance?",
            "Is there a recurring month-end task for recon?",
            "What's the deadline for the monthly recon package?",
            "How soon after month end does Priya need the reconciliation sign-off?",
        ],
    ),
    FactSpec(
        key="recon.no_hosted_module", kind=K.DECISION, area="reconciliation", importance=2,
        statement="In April 2026 Harbourline decided not to buy CoreLink's hosted reconciliation add-on and to "
                  "keep the in-house job.",
        kw=[["add-on", "addon", "module"], ["in-house", "in house", "ourselves", "our own", "keep"]],
        known_by=["sarah", "dave"], stated_by="dave", valid_from="2026-04-22",
        say=[
            "Decision from today: we're passing on CoreLink's hosted recon add-on. $18k a year for less than what "
            "Sarah's job does - we keep our own.",
            "We looked at the CoreLink reconciliation module and said no; the in-house job stays.",
            "Not buying the recon add-on. Keep running it in-house, revisit next budget cycle.",
        ],
        prompts=["Did we ever decide on the CoreLink recon module pitch?"],
        where=["#leadership", "#eng-core", "email"], askers=["marc", "sarah"],
        qs=[
            "Are we using CoreLink's hosted reconciliation product?",
            "Did Harbourline decide to buy the CoreLink recon module?",
            "Why do we still run our own reconciliation instead of the vendor's?",
            "What happened with the CoreLink reconciliation add-on proposal?",
        ],
    ),
    FactSpec(
        key="recon.secondary_oncall", kind=K.FACT, area="reconciliation", importance=2,
        statement="Since July 2026 Aisha is secondary on-call for reconciliation failures (Sarah primary).",
        kw=[["Aisha"], ["secondary", "backup", "second"]], known_by=["sarah", "aisha"], stated_by="sarah",
        valid_from="2026-07-13",
        say=[
            "Aisha is now secondary on the recon alerts, I'm still primary.",
            "Added Aisha as backup on-call for reconciliation failures starting this week.",
            "If the recon page goes off and I don't ack in 15 min, it rolls to Aisha as second.",
        ],
        prompts=["Who gets paged if recon fails and you're asleep?"],
        where=["#eng-core", "#ops"], askers=["dave", "nadia"],
        qs=[
            "Who's the backup on-call for reconciliation failures?",
            "If Sarah doesn't answer a recon alert, who gets it next?",
            "Is anyone besides Sarah on-call for recon?",
            "Who is secondary for the nightly reconciliation pager?",
        ],
    ),
    FactSpec(
        key="recon.svc_account_vault", kind=K.ACCESS, area="reconciliation", importance=3, private=True,
        statement="The reconciliation service-account credentials live in Sarah's personal 1Password vault, not "
                  "the shared Engineering vault.",
        kw=[["personal"], ["1Password", "1pw", "one password"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2023-02-01", where=["dm"], askers=["aisha"],
        say=[
            "between us - the recon service account login is in my personal 1Password vault, never got moved to "
            "the shared Engineering one",
            "ugh, the svc-recon creds are in my personal 1Password. I keep meaning to move them",
            "It's not in the shared vault, it's in my personal 1Password. I'll share it with you before I go.",
        ],
        prompts=["hey, where do I find the recon service account creds? not in the eng vault"],
        qs=[
            "Where are the reconciliation service account credentials stored?",
            "I can't find the recon service account in the Engineering vault - where is it?",
            "Which password vault holds the credentials the recon job runs under?",
            "How do I get the login for the reconciliation service account?",
        ],
        notes="Only in a Sarah<->Aisha DM; product excludes DMs by default -> route to Sarah.",
    ),
    FactSpec(
        key="recon.why_skip_first", kind=K.FACT, area="reconciliation", importance=2, in_corpus=False,
        statement="The 1st is skipped because CoreLink's month-start fee sweep posts after the EOD extract is cut, "
                  "so the extract is always missing that batch.",
        kw=[["fee sweep", "fee batch", "fees"]], known_by=["sarah"], stated_by="sarah", valid_from="2024-11-04",
        qs=[
            "What exactly posts on the 1st that breaks reconciliation?",
            "Which CoreLink batch runs at month start after the extract is cut?",
            "Technically, why is the 1st-of-month extract incomplete?",
        ],
        notes="Never written down; gap-interview material.",
    ),
    FactSpec(
        key="recon.fallback_script", kind=K.PROCEDURE, area="reconciliation", importance=3, in_corpus=False,
        statement="If Jenkins is down, recon can be run from a fallback Python script on the VM hcu-util02.",
        kw=[["hcu-util02", "util02"]], known_by=["sarah"], stated_by="sarah", valid_from="2023-05-01",
        qs=[
            "If jenkins01 is down, is there another way to run reconciliation?",
            "Is there a manual fallback for the recon job outside Jenkins?",
            "Where's the backup copy of the recon script kept?",
        ],
    ),
    FactSpec(
        key="recon.product77_variance", kind=K.FACT, area="reconciliation", importance=1, in_corpus=False,
        statement="CoreLink product code 77 maps to two GL accounts, which is why it always shows a small variance.",
        kw=[["77"]], known_by=["sarah"], stated_by="sarah", valid_from="2022-08-01",
        qs=[
            "Why does one product code always show a tiny variance on the recon report?",
            "Which CoreLink product code maps to two GL accounts?",
            "Is the recurring small difference on the reconciliation a known issue?",
        ],
    ),
    # ------------------------------------------------------------------------------------------------------
    # CoreLink API
    # ------------------------------------------------------------------------------------------------------
    FactSpec(
        key="corelink.key_friday", kind=K.LANDMINE, area="corelink_api", importance=3, landmine=True,
        statement="Never rotate the CoreLink API key on a Friday: the vendor's weekend batch sync locks the account "
                  "until Monday.",
        kw=[["Friday", "Fridays"]], known_by=["sarah"], stated_by="sarah", valid_from="2023-10-16",
        say=[
            "Whatever you do, don't rotate the CoreLink key on a Friday. Their weekend batch sync sees the old key, "
            "locks the account, and nobody at CoreLink can unlock it until Monday.",
            "never on a Friday!! the weekend sync locks us out and we're dead in the water till Monday",
            "Key rotation is Monday-to-Thursday only. Friday rotations lock the CoreLink account for the whole weekend.",
            "Ask me how I know: rotating the CoreLink API key on a Friday = locked out all weekend. Please pick "
            "another day.",
        ],
        prompts=["Planning to rotate the CoreLink key this Friday after the release - any objections?",
                 "Is there a good or bad day to rotate the CoreLink API key?"],
        where=["#eng-core", "#ops", "doc", "ticket", "email"], askers=["aisha", "nadia", "dave"],
        renders=4,
        qs=[
            "Is there a day I shouldn't rotate the CoreLink API key?",
            "I'm scheduling the CoreLink key rotation - any day to avoid?",
            "What happens if the CoreLink API key is rotated right before the weekend?",
            "Anything dangerous about rotating the CoreLink credentials?",
            "Can I rotate the CoreLink key Friday afternoon after the release?",
            "What's the landmine with CoreLink key rotation?",
            "Any restrictions on when we can change the core banking API key?",
        ],
        notes="Origin: October 2023 weekend lockout.",
    ),
    FactSpec(
        key="corelink.rep.v1", kind=K.VENDOR_CONTACT, area="corelink_api", importance=2,
        statement="Harbourline's account rep at CoreLink is Dan Holt.",
        kw=[["Dan Holt", "Holt"]], known_by=["sarah", "dave"], stated_by="sarah",
        valid_from="2022-03-01", valid_to="2026-06-15",
        say=[
            "Our CoreLink rep is Dan Holt, dan.holt@corelink-banking.com. He's decent, answers within a day.",
            "Email Dan Holt for anything contract-ish with CoreLink.",
            "Dan Holt is the account manager on our CoreLink contract.",
        ],
        where=["#eng-core", "email", "#ops"], askers=["dave", "aisha"],
    ),
    FactSpec(
        key="corelink.rep.v2", kind=K.VENDOR_CONTACT, area="corelink_api", importance=3,
        statement="Since 2026-06-15 Harbourline's CoreLink account rep is Maria Santos (maria.santos@corelink-"
                  "banking.com), replacing Dan Holt.",
        kw=[["Maria Santos", "Santos"]], known_by=["sarah", "dave"], stated_by="sarah",
        valid_from="2026-06-15", supersedes="corelink.rep.v1", forbid=[["Dan Holt", "Holt"]],
        say=[
            "FYI Dan's moved on at CoreLink - our new rep is Maria Santos, maria.santos@corelink-banking.com.",
            "New CoreLink account rep as of this week: Maria Santos. Update your contacts.",
            "For contract or escalation stuff with CoreLink, it's Maria Santos now.",
            "Had the intro call with Maria Santos today, she's taking over our CoreLink account.",
        ],
        prompts=["Who's our contact at CoreLink these days? Dan's email bounced."],
        where=["#eng-core", "email", "#ops"], askers=["dave", "aisha", "priya"],
        qs=[
            "Who is our account rep at CoreLink?",
            "Who do I email at CoreLink about the contract?",
            "What's the name of our CoreLink account manager now?",
            "Is Dan still our contact at CoreLink?",
            "Who's the current vendor rep for our core banking system?",
            "I need to escalate with CoreLink - who's our account person?",
        ],
    ),
    FactSpec(
        key="corelink.api_version.v1", kind=K.FACT, area="corelink_api", importance=2,
        statement="All Harbourline integrations call CoreLink API v2.",
        kw=[["v2", "version 2"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2021-09-01", valid_to="2026-07-20",
        say=[
            "Everything we have talks to CoreLink API v2 right now.",
            "We're on v2 of the CoreLink API across the board.",
            "portal, ACH, recon - all v2 endpoints at the moment",
        ],
        where=["#eng-core", "doc"], askers=["aisha"],
    ),
    FactSpec(
        key="corelink.api_version.v2", kind=K.DECISION, area="corelink_api", importance=3,
        statement="On 2026-07-20 portal and ACH traffic moved to CoreLink API v3; v2 is sunset on 2026-10-31.",
        kw=[["v3", "version 3"]], known_by=["sarah", "aisha"], stated_by="sarah",
        valid_from="2026-07-20", supersedes="corelink.api_version.v1",
        say=[
            "Cutover done: portal and ACH now hit CoreLink API v3. v2 gets switched off Oct 31.",
            "We're on v3 for the portal + ACH as of tonight. Only stragglers left on v2 before the Oct 31 sunset.",
            "The v3 migration is live. If you're writing anything new against CoreLink, use v3.",
            "API version 3 is what we're on now. Don't build anything new on the old endpoints.",
        ],
        prompts=["Which CoreLink API version should new code target?"],
        where=["#eng-core", "ticket", "email", "doc"], askers=["aisha", "dave"],
        qs=[
            "Which version of the CoreLink API are we on?",
            "What CoreLink API version should I code against?",
            "Did we finish moving to the new CoreLink API?",
            "When does the old CoreLink API get switched off?",
            "Are the portal and ACH still on the old CoreLink endpoints?",
            "What's the current CoreLink API version in production?",
        ],
    ),
    FactSpec(
        key="corelink.rotation.v1", kind=K.RECURRING_TASK, area="corelink_api", importance=2,
        statement="The CoreLink API key is rotated every 90 days.",
        kw=[["90 days", "90-day", "ninety"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2024-01-15", valid_to="2026-04-27",
        say=[
            "CoreLink key gets rotated every 90 days, calendar reminder is on my calendar.",
            "It's a 90-day rotation on the CoreLink API key.",
            "We rotate quarterly-ish - every ninety days - per their security policy.",
        ],
        where=["#eng-core", "doc"], askers=["aisha", "nadia"],
    ),
    FactSpec(
        key="corelink.rotation.v2", kind=K.RECURRING_TASK, area="corelink_api", importance=3,
        statement="Since 2026-04-27 the CoreLink API key must be rotated every 60 days (new CoreLink security "
                  "policy).",
        kw=[["60 days", "60-day", "sixty"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2026-04-27", supersedes="corelink.rotation.v1", forbid=[["90 days", "90-day", "ninety"]],
        say=[
            "CoreLink tightened their policy - key rotation is every 60 days now, not quarterly.",
            "New cadence: rotate the CoreLink API key every sixty days. Calendar updated.",
            "Heads up, CoreLink will reject keys older than 60 days from now on.",
            "Rotation is on a 60-day cycle as of this week. Still never on a Friday.",
        ],
        prompts=["How often do we have to rotate the CoreLink key?"],
        where=["#eng-core", "email", "doc", "ticket"], askers=["aisha", "nadia", "dave"],
        qs=[
            "How often does the CoreLink API key need rotating?",
            "What's the rotation cadence for the core banking API key?",
            "Is the CoreLink key still on a quarterly rotation?",
            "How many days can a CoreLink API key live before it has to be replaced?",
            "When I inherit the CoreLink integration, how frequently do I rotate the key?",
            "What's the current policy on CoreLink key rotation frequency?",
        ],
    ),
    FactSpec(
        key="corelink.key_location", kind=K.ACCESS, area="corelink_api", importance=3,
        statement="CoreLink API keys are stored in the 1Password 'Core Integrations' vault; only Sarah and Dave "
                  "have access.",
        kw=[["Core Integrations"]], known_by=["sarah", "dave"], stated_by="sarah", valid_from="2023-03-01",
        say=[
            "Keys are in 1Password under the Core Integrations vault. Just me and Dave can see it right now.",
            "The CoreLink API key lives in the Core Integrations vault - ask Dave to grant you access.",
            "Don't put the key anywhere else - Core Integrations vault in 1Password only.",
        ],
        prompts=["Where's the CoreLink API key stored? I don't want to paste it from Slack history lol"],
        where=["#eng-core", "doc", "email"], askers=["aisha", "nadia"],
        qs=[
            "Where is the CoreLink API key kept?",
            "Which 1Password vault has the core banking API credentials?",
            "Who has access to the CoreLink keys?",
            "I need the CoreLink credentials - where do they live?",
        ],
    ),
    FactSpec(
        key="corelink.portal_admin", kind=K.ACCESS, area="corelink_api", importance=3,
        statement="Sarah is the only admin on the CoreLink partner portal; Dave has read-only access.",
        kw=[["Sarah"], ["admin"]], known_by=["sarah", "dave"], stated_by="sarah", valid_from="2021-09-01",
        say=[
            "I'm the only admin on partner.corelink-banking.com, Sarah is the only one who can create keys. Dave is read-only.",
            "Only Sarah (me) has admin on the CoreLink partner portal. We should fix that before I leave.",
            "admin on the CoreLink portal = Sarah, that's it. Dave can look but not touch.",
        ],
        prompts=["Can anyone else issue CoreLink keys besides you?"],
        where=["#eng-core", "email", "#ops"], askers=["dave", "aisha"],
        qs=[
            "Who has admin rights on the CoreLink partner portal?",
            "Who can create new API keys in CoreLink?",
            "Does anyone other than Sarah have admin on the CoreLink portal?",
            "What access does Dave have on the CoreLink portal?",
        ],
    ),
    FactSpec(
        key="corelink.support", kind=K.VENDOR_CONTACT, area="corelink_api", importance=2,
        statement="CoreLink support: 1-877-555-0142 or support@corelink-banking.com; quote client ID HCU-4471.",
        kw=[["1-877-555-0142", "877-555-0142", "support@corelink-banking.com"]], known_by=["sarah", "aisha"],
        stated_by="sarah", valid_from="2021-09-01",
        say=[
            "CoreLink support is 1-877-555-0142, have our client ID HCU-4471 ready or they won't talk to you.",
            "For outages open a P1 with support@corelink-banking.com and quote HCU-4471.",
            "Their support line: 877-555-0142. Client ID is HCU-4471.",
        ],
        prompts=["What's the number for CoreLink support? API is timing out."],
        where=["#eng-core", "#incidents", "doc"], askers=["aisha", "nadia", "jen"],
        qs=[
            "How do I contact CoreLink support?",
            "What's the CoreLink support phone number?",
            "CoreLink is down - who do I call?",
            "What client ID do I give CoreLink when opening a ticket?",
        ],
    ),
    FactSpec(
        key="corelink.rate_limit", kind=K.LANDMINE, area="corelink_api", importance=2, landmine=True,
        statement="The CoreLink API allows 600 requests per minute per key; exceeding it locks the key for 15 "
                  "minutes, so bulk scripts must be throttled.",
        kw=[["600"]], known_by=["sarah"], stated_by="sarah", valid_from="2024-06-01",
        say=[
            "Throttle anything bulk - CoreLink caps us at 600 requests a minute and locks the key for 15 min if you "
            "go over. That takes the portal down with it.",
            "600 req/min per key. go over and the key is locked for 15 minutes, which means members can't log in",
            "Careful with the backfill script: CoreLink's limit is 600/minute and the lockout hits prod too.",
        ],
        prompts=["I'm going to run a backfill of member records against CoreLink tonight, anything to know?"],
        where=["#eng-core", "#incidents", "doc"], askers=["aisha"],
        qs=[
            "Is there a rate limit on the CoreLink API?",
            "Anything to watch out for when running a bulk job against CoreLink?",
            "What happens if a script hammers the CoreLink API?",
            "How many requests per minute can we send to CoreLink?",
            "Why did the portal go down when I ran my backfill?",
            "Any gotchas before I run a big data migration through the CoreLink API?",
        ],
    ),
    FactSpec(
        key="corelink.owner", kind=K.OWNER, area="corelink_api", importance=3,
        statement="Sarah Chen owns the CoreLink API integration.",
        kw=[["Sarah", "Chen"]], known_by=["sarah", "dave"], stated_by="dave", valid_from="2021-09-01",
        say=[
            "CoreLink integration is all Sarah. Loop her in on anything touching it.",
            "Sarah Chen owns everything CoreLink API on our side.",
            "Talk to Sarah - she's the one who knows the CoreLink API.",
        ],
        prompts=["Who do I ask about the CoreLink webhooks?"],
        where=["#eng-core", "#ops"], askers=["jen", "aisha", "nadia"],
        qs=[
            "Who handles the CoreLink API integration?",
            "Who should I ask about CoreLink API problems?",
            "Who owns our core banking integration?",
            "Who is the point person for anything CoreLink on the engineering side?",
            "Who do I go to about the CoreLink webhooks?",
        ],
    ),
    FactSpec(
        key="corelink.rotation_procedure", kind=K.PROCEDURE, area="corelink_api", importance=2,
        statement="CoreLink key rotation: create the new key in the partner portal, update 1Password, deploy it to "
                  "the app servers, restart the portal API, and revoke the old key after a 24-hour overlap.",
        kw=[["24 hours", "24h", "24-hour", "24 hr"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2023-10-20",
        say=[
            "Rotation steps: new key in the portal -> 1Password -> push to app servers -> restart portal API -> "
            "revoke the old key after 24 hours of overlap.",
            "keep both keys live for 24h before revoking the old one, some batch clients cache it",
            "Don't revoke the old key right away. Give it a 24-hour overlap, then kill it in the portal.",
        ],
        prompts=["What are the actual steps to rotate the CoreLink key?"],
        where=["doc", "#eng-core", "ticket"], askers=["aisha"],
        qs=[
            "What are the steps to rotate the CoreLink API key?",
            "How long should the old CoreLink key stay valid after rotation?",
            "When do I revoke the previous CoreLink key?",
            "Is there a runbook for CoreLink key rotation?",
        ],
    ),
    FactSpec(
        key="corelink.webhook", kind=K.FACT, area="corelink_api", importance=1,
        statement="CoreLink webhooks post to https://api.harbourlinecu.ca/hooks/corelink.",
        kw=[["/hooks/corelink"]], known_by=["sarah", "aisha"], stated_by="sarah", valid_from="2022-02-01",
        say=[
            "Webhooks land on https://api.harbourlinecu.ca/hooks/corelink - signing secret is in the same vault.",
            "the endpoint is /hooks/corelink on the api host",
            "CoreLink calls us back at api.harbourlinecu.ca/hooks/corelink.",
        ],
        prompts=["What URL does CoreLink send webhooks to?"],
        where=["#eng-core", "doc"], askers=["aisha"],
        qs=[
            "Where do CoreLink webhooks get delivered?",
            "What's our webhook endpoint for CoreLink events?",
            "Which URL does CoreLink call back on?",
        ],
    ),
    FactSpec(
        key="corelink.ip_allowlist", kind=K.PROCEDURE, area="corelink_api", importance=2,
        statement="CoreLink only accepts traffic from allowlisted egress IPs; adding a new server takes a CoreLink "
                  "ticket and about 5 business days.",
        kw=[["5 business days", "five business days"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2022-02-01",
        say=[
            "New servers can't talk to CoreLink until they're allowlisted - open a ticket with them, takes 5 business "
            "days.",
            "Plan ahead, the CoreLink IP allowlist change takes five business days on their side.",
            "They only allow our egress IPs. Any new box = allowlist ticket, 5 business days turnaround.",
        ],
        prompts=["My new VM can't reach CoreLink at all - firewall?"],
        where=["#eng-core", "#it-help", "ticket"], askers=["nadia", "aisha"],
        qs=[
            "Why can't a new server connect to CoreLink?",
            "How long does it take CoreLink to allowlist a new IP?",
            "What do I need to do before a new host can call the CoreLink API?",
            "Is there lead time for adding servers to the CoreLink allowlist?",
        ],
    ),
    FactSpec(
        key="corelink.contract_notice", kind=K.DECISION, area="corelink_api", importance=3, private=True,
        statement="The CoreLink contract auto-renews on Jan 31 unless 90 days' notice is given, so any change must "
                  "be communicated by Nov 2.",
        kw=[["Nov 2", "November 2", "Nov. 2"]], known_by=["sarah", "dave"], stated_by="sarah",
        valid_from="2026-02-01", where=["dm"], askers=["dave"],
        say=[
            "fyi before I forget - CoreLink auto-renews Jan 31, notice deadline is Nov 2 if we ever want to "
            "renegotiate",
            "The renewal notice window closes November 2. After that we're locked in another year.",
            "Just so it's written somewhere: CoreLink needs 90 days notice, so Nov 2 is the date.",
        ],
        prompts=["when's the CoreLink renewal again?"],
        qs=[
            "When is the deadline to give CoreLink notice before the contract renews?",
            "When does the CoreLink contract auto-renew?",
            "If we want to renegotiate CoreLink, by when do we have to tell them?",
        ],
        notes="Only in a Sarah<->Dave DM.",
    ),
    FactSpec(
        key="corelink.sandbox_refresh", kind=K.RECURRING_TASK, area="corelink_api", importance=1, in_corpus=False,
        statement="The CoreLink sandbox tenant's test data is refreshed on the first Sunday of every month.",
        kw=[["first Sunday", "1st Sunday"]], known_by=["sarah"], stated_by="sarah", valid_from="2024-01-01",
        qs=[
            "How often does the CoreLink sandbox data get reset?",
            "Why did my test accounts disappear from the CoreLink sandbox?",
            "When is the CoreLink test environment refreshed?",
        ],
    ),
    FactSpec(
        key="corelink.exec_escalation", kind=K.VENDOR_CONTACT, area="corelink_api", importance=2, in_corpus=False,
        statement="Beyond the account rep, CoreLink's escalation contact is Raj Patel, VP Client Services, whom only "
                  "Sarah has met.",
        kw=[["Raj Patel", "Patel"]], known_by=["sarah"], stated_by="sarah", valid_from="2025-05-01",
        qs=[
            "Who do we escalate to at CoreLink above the account rep?",
            "Do we have an executive contact at CoreLink?",
            "If the CoreLink rep isn't responding, who's next up the chain?",
        ],
    ),
    FactSpec(
        key="corelink.client_fork", kind=K.FACT, area="corelink_api", importance=2, in_corpus=False,
        statement="Harbourline uses a patched fork of the CoreLink Python client that fixes a v3 pagination bug.",
        kw=[["fork", "patched"]], known_by=["sarah"], stated_by="sarah", valid_from="2026-07-10",
        qs=[
            "Are we using the stock CoreLink Python client or a modified one?",
            "Why does our CoreLink client library differ from the vendor's release?",
            "Is it safe to upgrade the CoreLink SDK to the latest version?",
        ],
    ),
    # ------------------------------------------------------------------------------------------------------
    # SSL / DNS
    # ------------------------------------------------------------------------------------------------------
    FactSpec(
        key="ssl.registrar_email", kind=K.LANDMINE, area="ssl_dns", importance=3, landmine=True,
        statement="The member-portal SSL certificate renews through the Bluenose Domains registrar account, which is "
                  "tied to sarah.chen@harbourlinecu.ca; if her mailbox is closed, renewal notices and 2FA codes go "
                  "nowhere.",
        kw=[["Bluenose"], ["sarah.chen", "Sarah's"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2020-09-01",
        say=[
            "The Bluenose registrar account is on sarah.chen@harbourlinecu.ca - renewals and 2FA codes for the portal "
            "cert all come to my inbox. Do NOT close my mailbox until that's moved.",
            "Portal cert renews through Bluenose, and that account is registered to sarah.chen@harbourlinecu.ca. "
            "If that email dies, so does the renewal.",
            "heads up for offboarding: Bluenose login + 2FA = sarah.chen@harbourlinecu.ca. we need to swap it to a "
            "shared mailbox",
            "The wildcard for portal.harbourlinecu.ca gets bought through Bluenose, which is tied to Sarah's email "
            "(sarah.chen@harbourlinecu.ca). Single point of failure, I know.",
        ],
        prompts=["What do we need to transfer before your mailbox gets shut off?",
                 "How does the portal SSL cert get renewed?"],
        where=["#eng-core", "email", "#ops", "ticket"], askers=["dave", "nadia"],
        renders=4,
        qs=[
            "How does the member portal SSL certificate get renewed?",
            "Is there anything we should do before closing Sarah's email account?",
            "Which account is the domain registrar tied to?",
            "Where do the portal certificate renewal notices go?",
            "What breaks if Sarah's mailbox is deactivated?",
            "Any risks around the SSL cert renewal when Sarah leaves?",
            "Who gets the 2FA codes for the registrar login?",
        ],
    ),
    FactSpec(
        key="ssl.owner", kind=K.OWNER, area="ssl_dns", importance=3,
        statement="Sarah Chen owns SSL certificates and DNS for harbourlinecu.ca.",
        kw=[["Sarah", "Chen"]], known_by=["sarah", "dave"], stated_by="dave", valid_from="2020-09-01",
        say=[
            "Certs and DNS are Sarah's, always have been.",
            "Sarah Chen handles SSL and DNS for us - she's who you want.",
            "For anything DNS or certificate-related, Sarah.",
        ],
        prompts=["Who manages our DNS records?"],
        where=["#ops", "#it-help", "#eng-core"], askers=["nadia", "jen"],
        qs=[
            "Who manages SSL certificates at Harbourline?",
            "Who do I ask to add a DNS record?",
            "Who is responsible for our domain and certs?",
            "Who should I talk to about the TLS cert on the portal?",
            "Who handles DNS changes?",
        ],
    ),
    FactSpec(
        key="ssl.wildcard_expiry", kind=K.RECURRING_TASK, area="ssl_dns", importance=3,
        statement="The *.harbourlinecu.ca wildcard certificate expires on October 2 each year; Sarah renews it in "
                  "mid-September.",
        kw=[["Oct 2", "October 2", "Oct. 2", "2026-10-02", "October 2nd", "Oct 2nd"]], known_by=["sarah"],
        stated_by="sarah", valid_from="2020-10-02",
        say=[
            "The wildcard expires Oct 2 every year, I usually renew it around the 15th of September.",
            "Calendar note: *.harbourlinecu.ca cert dies October 2. Renew mid-September.",
            "wildcard cert is good until October 2nd, so this year's renewal lands right after I'm gone. eek",
        ],
        prompts=["When does the wildcard cert expire?"],
        where=["#eng-core", "#ops", "ticket", "email"], askers=["nadia", "dave"],
        qs=[
            "When does the harbourlinecu.ca wildcard certificate expire?",
            "When is the SSL cert due for renewal this year?",
            "What date do we need the wildcard cert renewed by?",
            "Is there an upcoming certificate expiry I should know about?",
        ],
    ),
    FactSpec(
        key="ssl.renewal_procedure", kind=K.PROCEDURE, area="ssl_dns", importance=2,
        statement="Cert renewal: generate the CSR on lb01, buy through Bluenose, upload the bundle to the load "
                  "balancer and the Okta custom domain, and include the intermediate chain.",
        kw=[["intermediate"]], known_by=["sarah"], stated_by="sarah", valid_from="2021-09-15",
        say=[
            "Renewal steps: CSR on lb01, buy it on Bluenose, upload to the LB and to the Okta custom domain. And "
            "include the intermediate chain or Android phones will choke.",
            "don't forget the intermediate cert when you upload, last time members on older Androids couldn't log in",
            "The bundle has to include the intermediate. Upload it in two places: lb01 and Okta.",
        ],
        prompts=["Walk me through renewing the wildcard cert?"],
        where=["doc", "#eng-core", "ticket"], askers=["aisha", "nadia"],
        qs=[
            "What are the steps to renew the wildcard SSL certificate?",
            "Where does the renewed certificate need to be uploaded?",
            "Anything easy to forget when installing the new cert?",
            "Why did some members' phones fail after the last cert renewal?",
        ],
    ),
    FactSpec(
        key="ssl.dns_host.v1", kind=K.FACT, area="ssl_dns", importance=2,
        statement="The harbourlinecu.ca DNS zone is hosted on Bluenose Domains' DNS.",
        kw=[["Bluenose"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2020-09-01", valid_to="2026-08-10",
        say=[
            "DNS is hosted at Bluenose, same place as the registration.",
            "Our zone file lives in the Bluenose DNS panel.",
            "Records are edited in Bluenose's DNS manager, it's clunky but it works.",
        ],
        where=["#ops", "#eng-core", "doc"], askers=["nadia"],
    ),
    FactSpec(
        key="ssl.dns_host.v2", kind=K.DECISION, area="ssl_dns", importance=3,
        statement="On 2026-08-10 DNS hosting for harbourlinecu.ca moved to Cloudflare; Bluenose remains the "
                  "registrar.",
        kw=[["Cloudflare"]], known_by=["sarah", "nadia"], stated_by="sarah",
        valid_from="2026-08-10", supersedes="ssl.dns_host.v1",
        say=[
            "DNS is on Cloudflare as of today. Registration stays at Bluenose, only the nameservers changed.",
            "Moved our DNS to Cloudflare this morning - make record changes there now, not in the old panel.",
            "Cloudflare is our DNS host now. Nadia's got admin too.",
            "Nameserver cutover to Cloudflare done, propagation looks clean.",
        ],
        prompts=["Where do I edit DNS records now?"],
        where=["#ops", "#eng-core", "ticket", "email", "doc"], askers=["nadia", "dave"],
        qs=[
            "Where is our DNS hosted?",
            "Where do I go to change a DNS record for harbourlinecu.ca?",
            "Is DNS still managed in the Bluenose panel?",
            "Which provider hosts our DNS zone now?",
            "Did we move our DNS somewhere recently?",
            "What's the current DNS provider for the member portal domain?",
        ],
    ),
    FactSpec(
        key="ssl.dns_admins", kind=K.ACCESS, area="ssl_dns", importance=2,
        statement="Sarah and Nadia are the admins on the Cloudflare DNS account.",
        kw=[["Nadia"]], known_by=["sarah", "nadia"], stated_by="sarah", valid_from="2026-08-10",
        say=[
            "Added Nadia as the second Cloudflare admin, so it's me and her.",
            "Cloudflare admins: Sarah + Nadia. Nobody else has login yet.",
            "Nadia has full admin on Cloudflare now too, so DNS isn't just me anymore.",
        ],
        prompts=["Who else can log into Cloudflare?"],
        where=["#ops", "#it-help"], askers=["dave"],
        qs=[
            "Who has admin access to our Cloudflare account?",
            "Besides Sarah, who can change DNS in Cloudflare?",
            "Who can log into the DNS provider?",
            "If Sarah's gone, who can edit our DNS?",
        ],
    ),
    FactSpec(
        key="ssl.api_cert.v1", kind=K.FACT, area="ssl_dns", importance=2,
        statement="The api.harbourlinecu.ca certificate is a paid one-year cert renewed manually through Bluenose.",
        kw=[["api.harbourlinecu.ca", "api cert", "API cert"], ["manual", "by hand", "once a year", "yearly"]],
        known_by=["sarah"], stated_by="sarah", valid_from="2022-06-29", valid_to="2026-06-29",
        say=[
            "The api.harbourlinecu.ca cert is a one-year paid cert, I renew it manually every June.",
            "api cert gets renewed by hand once a year through Bluenose",
            "The API cert is the yearly manual one, separate from the wildcard.",
        ],
        where=["#eng-core", "doc"], askers=["aisha"],
    ),
    FactSpec(
        key="ssl.api_cert.v2", kind=K.DECISION, area="ssl_dns", importance=2,
        statement="Since 2026-06-29 the api.harbourlinecu.ca certificate is a Let's Encrypt cert auto-renewed by "
                  "certbot on lb01.",
        kw=[["Let's Encrypt", "LetsEncrypt", "certbot"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2026-06-29", supersedes="ssl.api_cert.v1",
        say=[
            "Switched api.harbourlinecu.ca to Let's Encrypt, certbot on lb01 renews it automatically. One less "
            "thing on the calendar.",
            "api cert is now certbot-managed, auto-renews every 60 days-ish.",
            "No more manual renewal for the API host - it's Let's Encrypt now. The wildcard is still manual though.",
        ],
        prompts=["Do we still have to buy the api cert every June?"],
        where=["#eng-core", "ticket", "doc"], askers=["aisha", "nadia"],
        qs=[
            "How is the api.harbourlinecu.ca certificate renewed now?",
            "Do we still renew the API host cert manually?",
            "Which CA issues the certificate for our API endpoint?",
            "Is the API certificate auto-renewing?",
            "Who or what renews the cert on api.harbourlinecu.ca?",
        ],
    ),
    FactSpec(
        key="ssl.dmarc", kind=K.DECISION, area="ssl_dns", importance=1,
        statement="In April 2026 the DMARC policy for harbourlinecu.ca was moved to quarantine.",
        kw=[["quarantine"]], known_by=["sarah", "nadia"], stated_by="sarah", valid_from="2026-04-14",
        say=[
            "DMARC is at p=quarantine now. If a vendor's mail starts landing in spam, that's probably why.",
            "Flipped DMARC to quarantine today after two weeks of clean reports.",
            "we're on quarantine for DMARC - reject is the next step once the e-statement vendor is sorted",
        ],
        prompts=["Some vendor emails are going to junk suddenly, did something change?"],
        where=["#it-help", "#ops"], askers=["nadia", "jen"],
        qs=[
            "What's our DMARC policy set to?",
            "Why are some external emails being quarantined?",
            "Did we change our email authentication settings recently?",
            "Are we on DMARC reject yet?",
        ],
    ),
    FactSpec(
        key="ssl.domain_expiry", kind=K.FACT, area="ssl_dns", importance=2,
        statement="The harbourlinecu.ca domain registration runs to March 14, 2027 with auto-renew on.",
        kw=[["2027"], ["March", "Mar"]], known_by=["sarah"], stated_by="sarah", valid_from="2026-03-10",
        say=[
            "Renewed the domain - harbourlinecu.ca is paid up to March 14, 2027, auto-renew stays on.",
            "Domain registration's good until Mar 14 2027.",
            "harbourlinecu.ca expires March 2027, auto-renew is enabled at Bluenose.",
        ],
        prompts=["When does our domain name expire?"],
        where=["#ops", "email"], askers=["dave", "nadia"],
        qs=[
            "When does the harbourlinecu.ca domain registration expire?",
            "Is our domain name set to auto-renew?",
            "How long is the domain paid up for?",
            "When's the next domain renewal?",
        ],
    ),
    FactSpec(
        key="ssl.registrar_backup_codes", kind=K.ACCESS, area="ssl_dns", importance=3, private=True,
        statement="The Bluenose 2FA backup codes are in a sealed envelope in Sarah's desk drawer.",
        kw=[["backup codes", "recovery codes"], ["drawer", "desk"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2021-01-10", where=["dm"], askers=["dave"],
        say=[
            "fyi the Bluenose 2FA backup codes are in an envelope in my desk drawer, top left",
            "If my phone dies, the registrar recovery codes are sealed in my desk drawer.",
            "remind me to hand you the backup codes from my desk before my last day",
        ],
        prompts=["if your phone got lost, how would we get into the registrar?"],
        qs=[
            "Where are the registrar 2FA backup codes kept?",
            "If Sarah's phone is unavailable, how do we get past 2FA on the domain registrar?",
            "Is there a recovery method for the Bluenose login?",
        ],
        notes="Only in a Sarah<->Dave DM.",
    ),
    FactSpec(
        key="ssl.why_bluenose", kind=K.DECISION, area="ssl_dns", importance=1, in_corpus=False,
        statement="The Bluenose account was opened in 2020 under Sarah's email because the previous IT contractor's "
                  "registrar login was lost.",
        kw=[["contractor"]], known_by=["sarah", "mike"], stated_by="sarah", valid_from="2020-09-01",
        qs=[
            "Why is the registrar account in Sarah's name instead of a shared mailbox?",
            "How did we end up with Bluenose as the registrar?",
            "What happened to the old registrar account before 2020?",
        ],
    ),
    FactSpec(
        key="ssl.legacy_rates_cert", kind=K.FACT, area="ssl_dns", importance=2, in_corpus=False,
        statement="A forgotten legacy cert on the old rates.harbourlinecu.ca rate-sheet server expires in "
                  "January 2027.",
        kw=[["rates.harbourlinecu.ca", "rates server", "rate-sheet", "rate sheet"]], known_by=["sarah"],
        stated_by="sarah", valid_from="2025-01-20",
        qs=[
            "Are there any other certificates besides the wildcard and the API cert?",
            "Is there a legacy server with its own SSL cert we might forget about?",
            "What certs expire early next year?",
        ],
    ),
    FactSpec(
        key="ssl.expiry_alerts", kind=K.FACT, area="ssl_dns", importance=2,
        statement="Certificate-expiry alerts from UptimeRobot are sent only to Sarah's email.",
        kw=[["UptimeRobot", "Uptime Robot"]], known_by=["sarah"], stated_by="sarah", valid_from="2022-03-01",
        say=[
            "UptimeRobot watches the cert expiry but the alerts only go to me. Should probably add ops@.",
            "cert expiry warnings come from UptimeRobot, to my inbox only",
            "We get 30/14/7-day expiry warnings from UptimeRobot - currently only I receive them.",
        ],
        prompts=["Would we even know if a cert was about to expire?"],
        where=["#ops", "#eng-core"], askers=["dave", "nadia"],
        qs=[
            "How do we get warned before an SSL certificate expires?",
            "Who receives certificate-expiry alerts?",
            "What monitors our cert expiry dates?",
            "Would anyone notice if the portal cert was about to lapse?",
        ],
    ),
]

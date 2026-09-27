"""Phrase banks: everyday chatter, thread wrappers, email/ticket scaffolding.

Nothing in here may state a truth fact. Noise may *mention* systems ("recon ran long last night") so that keyword
search alone cannot find answers, but it never states a rule, owner, contact, credential location, or number that
the truth file tracks.
"""

from __future__ import annotations

# --------------------------------------------------------------------------------------------------
# Thread scaffolding around a fact statement (the statement itself is always embedded verbatim)
# --------------------------------------------------------------------------------------------------

ANSWER_WRAP = [
    "{say}",
    "{say}",
    "@{asker} {say}",
    "Good q. {say}",
    "{say} Learned that one the hard way.",
    "Yep — {say}",
    "{say} Holler if anything looks off.",
    "Short version: {say}",
    "{say} I should really write that down somewhere.",
    "Ah, so — {say}",
]
ANNOUNCE_WRAP = [
    "Heads up all: {say}",
    "PSA: {say}",
    "{say}",
    "FYI for anyone touching this — {say}",
    "Quick note so it's written down somewhere: {say}",
    "{say} (posting here so it's searchable)",
]
CORRECT_WRAP = [
    "Not quite — {say}",
    "Actually no, that changed. {say}",
    "Close, but {say}",
    "Careful, that's the old info. {say}",
    "Hmm, I don't think that's right. {say}",
]
GENERIC_PROMPTS = [
    "@{knower} got a sec? question about {topic}",
    "Does anyone know how {topic} works these days?",
    "Dumb question maybe, but what's the deal with {topic}?",
    "@{knower} before I poke at {topic} — anything I should know?",
    "Who knows about {topic}? Trying to sort something out",
    "Sorry to bug you @{knower} — {topic} question",
]
THANKS = [
    "ty!", "perfect, thanks", "good to know 🙏", "noted", "oh wow ok, glad I asked", "thanks, that helps",
    "👍", "makes sense, cheers", "ah ok. thank you!", "saving this", "legend, thanks",
]
TOPIC: dict[str, list[str]] = {
    "reconciliation": ["the nightly recon job", "reconciliation", "the recon report"],
    "corelink_api": ["the CoreLink integration", "CoreLink", "the CoreLink API"],
    "ach_payments": ["the ACH batches", "EFT files", "the Payments Canada stuff"],
    "payroll": ["payroll", "the pay run", "the Paylane setup"],
    "member_portal": ["the member portal", "online banking", "portal logins"],
    "backups_dr": ["backups", "the DR setup", "restores"],
    "fintrac_reporting": ["FINTRAC reporting", "LCTRs", "the AML reports"],
    "identity_access": ["Okta", "admin access", "account access"],
    "card_processing": ["the debit card side", "card disputes", "Tidewater"],
    "ssl_dns": ["the certs", "DNS", "the domain setup"],
}

EMAIL_SUBJECTS: dict[str, list[str]] = {
    "reconciliation": ["Recon job notes", "Re: reconciliation question", "Nightly recon — FYI", "Recon report"],
    "corelink_api": ["CoreLink API", "Re: CoreLink vendor contact", "CoreLink integration notes",
                     "Re: CoreLink key rotation"],
    "ach_payments": ["ACH batch notes", "Re: EFT cutoff", "Payments Canada file", "Re: direct deposit question"],
    "payroll": ["Payroll this cycle", "Re: pay run", "Payroll notes", "Re: remittance"],
    "member_portal": ["Portal update", "Re: member login issue", "Online banking notes"],
    "backups_dr": ["Backup notes", "Re: DR test", "Backups — FYI", "Re: restore request"],
    "fintrac_reporting": ["FINTRAC reporting", "Re: LCTR question", "Compliance notes", "Re: STR process"],
    "identity_access": ["Access request process", "Re: admin rights", "Okta changes", "Re: offboarding checklist"],
    "card_processing": ["Card processing notes", "Re: Tidewater", "Re: card dispute", "Debit card orders"],
    "ssl_dns": ["Cert renewal", "Re: DNS change", "Domain notes", "Re: SSL warning"],
}
EMAIL_GREET = ["Hi all,", "Hi team,", "Hey folks,", "Hi {to},", "Morning all,", "Hi everyone,"]
EMAIL_CLOSE = ["Thanks,", "Cheers,", "Thx,", "Best,", "Talk soon,", "- "]
EMAIL_ASK = [
    "Quick one — {prompt}",
    "{prompt} Want to make sure I have it right before I write it up.",
    "Hi {knower}, {prompt}",
    "{prompt} No rush.",
]

TICKET_FACT_TITLES: dict[str, list[str]] = {
    "reconciliation": ["Recon job follow-up", "Document recon job behaviour", "Recon mismatch investigation",
                       "Recon report cleanup"],
    "corelink_api": ["CoreLink integration follow-up", "CoreLink API key housekeeping", "CoreLink support case",
                     "Update CoreLink runbook"],
    "ach_payments": ["ACH batch follow-up", "EFT file investigation", "ACH returns handling",
                     "Payments Canada file question"],
    "payroll": ["Payroll process question", "Pay run follow-up", "Payroll setup change"],
    "member_portal": ["Portal follow-up", "Member login issue", "Portal config change"],
    "backups_dr": ["Backup job follow-up", "Restore request", "DR plan update"],
    "fintrac_reporting": ["FINTRAC report follow-up", "LCTR process question", "AML review item"],
    "identity_access": ["Access review item", "Admin rights change", "Okta policy change"],
    "card_processing": ["Card dispute follow-up", "Card vendor question", "Card order issue"],
    "ssl_dns": ["Cert renewal follow-up", "DNS change request", "Domain housekeeping"],
}

# --------------------------------------------------------------------------------------------------
# Background tickets ("doing" evidence). Titles only; comments are generic.
# --------------------------------------------------------------------------------------------------

BG_TICKETS: dict[str, list[str]] = {
    "reconciliation": [
        "Recon report shows 3 unmatched items for {d}", "Nightly recon ran long ({n} min)",
        "Add branch code to recon report", "Recon job failed — Jenkins agent offline",
        "Investigate suspense account balance drift", "Recon: handle closed accounts gracefully",
        "Recon email went to spam for finance", "Refactor recon matcher for joint accounts",
    ],
    "corelink_api": [
        "CoreLink 429s during morning peak", "Update CoreLink client library", "CoreLink webhook retries piling up",
        "Map new CoreLink transaction codes", "CoreLink sandbox refresh", "Log CoreLink request ids",
        "CoreLink timeout on member lookup", "Pull CoreLink statements for audit sample",
    ],
    "ach_payments": [
        "ACH return R{n} not auto-posting", "Direct deposit for new employer group", "EFT file rejected — header",
        "Add trace numbers to ACH log", "Duplicate PAD for member {n}", "ACH batch monitor alert noisy",
        "Payroll group missing from Friday batch", "Update AFT originator id docs",
    ],
    "payroll": [
        "New hire payroll setup — {who}", "Update vacation accrual for {who}", "Pay stub shows wrong dept",
        "Year-to-date correction", "Benefits deduction change", "Timesheet approval reminder",
    ],
    "member_portal": [
        "Portal login loop on Safari", "Member can't see e-statements", "2FA SMS delayed for Bell customers",
        "Update portal footer hours", "Password reset email wording", "Mobile app crash on Android 15",
        "Add French labels to transfers page", "Portal slow after 9am",
    ],
    "backups_dr": [
        "Backup job warning on FS02", "Offsite copy verification", "Restore folder for {who}",
        "Veeam license renewal", "Replace failed NAS disk", "Quarterly restore test",
    ],
    "fintrac_reporting": [
        "LCTR follow-up for Dartmouth branch", "Update AML training records", "STR draft review",
        "Ministerial directive review", "Annual compliance report prep", "Client ID record gaps",
    ],
    "identity_access": [
        "New laptop + accounts for {who}", "Remove access for summer student", "Okta app tile for Paylane",
        "Reset MFA for {who}", "Shared mailbox access for member services", "Quarterly access review",
        "VPN profile update", "Printer access on 2nd floor",
    ],
    "card_processing": [
        "Card order batch for new members", "Chargeback dispute #{n}", "Card reissue after compromise",
        "Tidewater invoice question", "Interac limit change request", "Card PIN mailer delay",
    ],
    "ssl_dns": [
        "Add SPF record for new mail vendor", "Cert warning on staging", "DNS TTL cleanup",
        "Redirect old www domain", "Add DMARC reporting", "Staging subdomain for portal",
    ],
}
TICKET_COMMENTS = [
    "Looking into it.", "Reproduced. Working on a fix.", "Fixed and deployed, monitoring.",
    "Closing — confirmed with the requester.", "Waiting on vendor.", "Done.", "Couldn't reproduce, closing for now.",
    "Patched, will watch tonight's run.", "Merged. Thanks for the report.", "Resolved after a restart of the agent.",
]

# Sarah's (and others') unresolved work at the end of the window -> handoff "unresolved_work".
OPEN_TICKETS: list[tuple[str, str, str, str, str]] = [
    # (assignee, area, title, description, created)
    ("sarah", "corelink_api", "Migrate CoreLink integration to API v3",
     "CoreLink is moving everyone off the old API version. Client changes about half done on branch "
     "feature/corelink-v3; auth flow and statements endpoint still to do.", "2026-07-14"),
    ("sarah", "reconciliation", "Move recon job off the old Jenkins box",
     "jenkins-01 is out of support. New pipeline drafted but not cut over; needs a parallel run for a week.",
     "2026-06-22"),
    ("sarah", "ssl_dns", "Move registrar + cert renewal notices to a shared mailbox",
     "Renewal notices and registrar 2FA currently go to one person's inbox. Need to switch the account contact "
     "to a shared mailbox.", "2026-08-19"),
    ("sarah", "ach_payments", "ACH return codes R14/R15 not auto-posting",
     "Deceased-member return codes land in the exception queue and need manual posting. Parser change started.",
     "2026-08-06"),
    ("sarah", "reconciliation", "Recon: alert when suspense account > $5k",
     "Finance wants a Slack alert when the suspense balance crosses a threshold after the nightly run.",
     "2026-07-29"),
    ("sarah", "member_portal", "Rate-limit password reset endpoint",
     "Seeing bursts of reset requests from a few IPs. Add per-IP throttling.", "2026-08-12"),
    ("aisha", "member_portal", "French translations for new transfers page", "Waiting on copy from Jen.",
     "2026-08-17"),
    ("nadia", "identity_access", "Quarterly access review Q3", "Export from Okta pulled; reviews pending.",
     "2026-08-24"),
    ("tom", "fintrac_reporting", "Update compliance program documentation for 2026 review",
     "Policies and procedures manual needs its annual refresh.", "2026-07-02"),
    ("mike", "backups_dr", "Document DR failover steps", "Rough notes exist, not written up yet.", "2026-04-21"),
]

# --------------------------------------------------------------------------------------------------
# Everyday chatter
# --------------------------------------------------------------------------------------------------

RANDOM = [
    "Anyone want anything from Tims? Doing a run", "Fog is so thick on the bridge this morning I couldn't see the car "
    "in front of me", "Who left the donair sauce in the fridge from last week 😬", "Mooseheads game Saturday, anyone "
    "going?", "It's 12 degrees and sunny, I'm eating lunch on the waterfront", "Lunch at the Split Crow? 12:15?",
    "Does anyone have a phone charger I can borrow (USB-C)", "Happy Friday everyone!", "The coffee machine is making "
    "that noise again", "Rain rain rain. Classic Halifax", "Anyone seen the good stapler", "Leftover cake in the "
    "kitchen, help yourselves", "Traffic on the MacKay is backed up to Dartmouth Crossing, heads up",
    "Who's in for the potluck next week?", "The parking lot is a skating rink, be careful", "Farmers market haul 🥕",
    "Oxford Theatre has a double feature Sunday", "Dog pics in the thread pls", "Lobster rolls at lunch? 🦞",
    "Can someone turn the AC down, it's arctic in here", "Just saw a seal off the ferry terminal", "Anyone doing "
    "the Bluenose marathon?", "Pizza for the late folks is in the boardroom", "Reminder the kitchen gets cleaned "
    "out Friday at 3", "Does the vending machine take tap now?", "Is it just me or is the wifi slow on the 3rd floor",
    "Sobeys run at lunch, need anything?", "Beautiful sunset over the harbour last night",
    "What's everyone doing for the long weekend?", "Who wants to split a Pizza Corner order",
    "Went to Peggy's Cove on the weekend, absolutely packed", "The ferry was cancelled again lol",
]
GENERAL = [
    "Reminder: fire drill Thursday at 10am. Please use the stairwell by the vault.",
    "Welcome back from vacation {who}!", "Staff BBQ at Point Pleasant Park next Friday — RSVP in the thread",
    "The Dartmouth branch will close at 3pm today for a staff meeting.", "Happy birthday {who}! 🎂",
    "Town hall is moved to Wednesday 2pm in the boardroom.", "Please remember to lock your screens when you step away.",
    "Parking passes for the Spring Garden lot are at the front desk.", "Reminder: expense reports due by the 25th.",
    "Great job on the member survey everyone — 4.6/5 this quarter!", "Branch closed Monday for Natal Day.",
    "Board meeting next Tuesday, leadership please have decks to Marc by Friday.",
    "Shred bins get picked up Wednesday — please empty your desk trays.",
    "United Way campaign kicks off next week.", "New coffee supplier starting Monday ☕",
]
EXTRA_GENERAL: list[tuple[str, str, str]] = [
    # (date, author, text) — org announcements (HR roster data, not truth facts)
    ("2026-03-04", "dave", "Heads up: Mike is moving to a part-time contract through the end of October. He'll be "
                           "in Tuesdays and Thursdays."),
    ("2026-06-10", "marc", "Some bittersweet news: Tom will be retiring in December after 22 years with us. We'll "
                           "celebrate properly closer to the date!"),
    ("2026-08-20", "dave", "Please welcome Alex Rivera, who joins the backend team on Sept 14. Alex comes to us from "
                           "a fintech in Moncton."),
    ("2026-08-28", "dave", "Team — Sarah has let me know she'll be leaving us; her last day is Sept 11. We're sad to "
                           "see her go and grateful for six great years. Handoff planning starts this week."),
]
EXTRA_GENERAL_REPLIES = ["🎉", "Congrats!", "Welcome Alex!", "Noooo 😢 we'll miss you", "Enjoy it, you've earned it!",
                         "Big shoes to fill", "❤️"]

ENG = [
    "PR up for the {thing}, would love a review when someone has a sec", "CI is red again, looking",
    "Jenkins agent out of disk, cleaning up old workspaces", "Deploying portal hotfix at 12:30",
    "Anyone else getting flaky tests in the transfers module?", "Bumped the Python version on the build box",
    "Merged. Thanks for the review!", "Rebasing on main, give me 10", "Is staging down for anyone else?",
    "Rolled back the {thing} change, something funky with the logs", "Pairing on the {thing} after lunch if anyone "
    "wants to join", "Opened a ticket for the {thing} thing", "Dependency bot opened like 14 PRs overnight lol",
    "Code freeze for month-end starts tomorrow", "Staging DB refreshed from last night's snapshot",
    "The {thing} tests pass locally but not in CI, classic", "Writing up the {thing} design doc, draft by Friday",
]
ENG_THINGS = ["transfers page", "recon matcher", "CoreLink client", "ACH parser", "portal login", "statement export",
              "rate limiter", "audit log", "member search", "e-statement job", "notifications service"]
STANDUP = "Standup — yesterday: {y}. today: {t}. blockers: {b}"
STANDUP_BLOCKERS = ["none", "none", "none", "waiting on vendor", "waiting on review", "none", "meetings all afternoon"]
STANDUP_TASKS: dict[str, list[str]] = {
    "sarah": ["looked into a recon mismatch", "CoreLink v3 client work", "cert renewal prep", "recon job tuning",
              "ACH returns parser", "reviewed Aisha's PR", "CoreLink support call", "DNS cleanup",
              "recon report tweaks for finance", "ACH batch monitoring", "jenkins migration for recon",
              "CoreLink webhook retries"],
    "aisha": ["transfers page", "portal login bug", "French labels", "password reset flow", "reading the recon code",
              "shadowing Sarah on ACH", "portal accessibility fixes", "unit tests for member search",
              "e-statement export"],
}

OPS = [
    "Scheduled maintenance on the phone system Saturday 7-9am", "Generator test at the main branch Friday morning",
    "Branch network switch replaced at Dartmouth, all good now", "Monitoring shows the file server at 85% — "
    "cleanup this week", "UPS battery replacement scheduled for next week", "Alarm system tech on site at 2pm",
    "Vendor on site for the ATM service, back door propped open for 10 min", "All systems green this morning ✅",
    "Heads up: ISP doing work on the line tonight after 11", "Server room AC making noises, facilities notified",
]
ITHELP_Q = [
    "My laptop won't connect to VPN from home", "Printer on 2 is jammed again", "Outlook keeps asking for my password",
    "Can someone help me get into the shared drive for member services?", "Teams audio is choppy on my headset",
    "My second monitor isn't waking up", "Is the scanner at the front desk working?", "Need Adobe installed on my "
    "machine please", "I think I clicked a sketchy link in an email, what do I do", "Keyboard missing the E key lol",
    "Can't print to PDF anymore", "Getting a certificate warning on the intranet page",
]
ITHELP_A = ["On it", "Try now?", "Fixed — restart when you can", "Coming by your desk in 5", "Ticket opened, will "
            "follow up", "Forward it to me and don't click anything else", "Should be sorted now",
            "Known issue, working on it"]
MEMBER = [
    "Member at the Dartmouth branch says the portal logged her out twice", "Had a member ask about raising their "
    "Interac limit for a car deposit", "Long lineup this morning, pension day", "Member asking why their direct "
    "deposit hasn't landed yet", "Got a call about a card declined at Costco, sorted it", "Member wants paper "
    "statements again, where's the form?", "Busy Saturday, two new accounts opened", "Anyone know if we're doing "
    "the student promo again this fall?", "Member complaining the app won't load on an old iPhone",
    "Phones are ringing off the hook today", "Had a lovely older gentleman bring in timbits for the tellers",
    "Member confused by the new login screen, walked them through it", "Couple of calls about the portal being slow",
    "Reminder: cash count at close today", "New brochures arrived for the RRSP campaign",
]
FINANCE = [
    "Month-end close starts Thursday", "Budget variance report is in the shared folder", "Who approved the invoice "
    "from the print shop?", "Audit fieldwork is scheduled for the week of the 18th", "Please code expenses to the "
    "right cost centre 🙏", "Board pack financials drafted", "Quarterly GST filing done", "Bank rec for the operating "
    "account is balanced", "Vendor payments run tomorrow morning",
]
COMPLIANCE = [
    "Annual AML training is due for everyone by end of month", "Reminder to complete the privacy refresher",
    "Policy manual review meeting moved to Thursday", "Good catch on the ID check at the branch today",
    "Board risk committee next week — I'll circulate the update", "Please don't email member SINs, use the portal",
]
LEADERSHIP = [
    "Can we move Thursday's sync to 3?", "Draft strategic plan in the shared drive", "Insurance renewal came in a bit "
    "higher than expected", "Let's discuss the branch hours proposal next week", "Hiring plan for Q4 attached",
    "Board wants a cyber update at the next meeting",
]
DM = [
    "got a sec?", "lunch?", "can you look at my PR when you have a min", "thanks for covering this morning",
    "running 5 min late to the meeting", "did you see the email from Dave?", "coffee?", "call me when you're free",
    "haha yes", "all good, no worries", "sent you the doc", "let's sync tomorrow",
]
EMAIL_NOISE: list[tuple[str, str]] = [
    ("Staff meeting agenda", "Agenda for Thursday attached. Add items by Wednesday noon."),
    ("Expense policy reminder", "Quick reminder that receipts over $50 need to be itemized."),
    ("Member survey results", "Results are in — overall satisfaction up again. Details attached."),
    ("Building maintenance", "The elevator will be serviced Saturday morning."),
    ("Holiday schedule", "Please submit summer vacation requests by the end of the month."),
    ("Wellness challenge", "Step challenge starts Monday! Teams of four."),
    ("Board meeting logistics", "Board meeting is in the boardroom at 5:30; dinner provided."),
    ("Printer lease", "New printers arrive next week; old ones will be picked up."),
    ("Newsletter draft", "Draft of the member newsletter attached for comments."),
    ("Audit request list", "The auditors sent their PBC list, I'll forward pieces to owners."),
]

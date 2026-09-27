"""Harbourline truth table: ACH/EFT payments, member portal, identity & access.

Hand-written ground truth (see ``keepline.data.spec`` for the authoring format). Every ``say`` variant satisfies
its fact's ``kw`` CNF; the build validator enforces it.
"""

from __future__ import annotations

from keepline.data.spec import K, FactSpec

_CUTOFF_OLD = ["4:30", "16:30", "four-thirty", "four thirty"]
_PICKUP_OLD = ["7:00", "07:00", "7am", "7 am"]
_TIMEOUT_OLD = ["15 min", "fifteen min"]

ACH: list[FactSpec] = [
    FactSpec(
        key="ach.no_restart_near_cutoff", kind=K.LANDMINE, area="ach_payments", importance=3, landmine=True,
        statement="Never restart the ACH batch server (or its batch service) within 30 minutes of a Payments "
                  "Canada exchange cutoff: a restart mid-transmission leaves a partial AFT file that gets resent "
                  "as a duplicate.",
        kw=[["restart", "reboot", "bounce"], ["30 min", "thirty min", "half an hour", "half hour"]],
        known_by=["sarah", "priya"], stated_by="sarah", valid_from="2024-03-18",
        notes="Planted landmine #3. Explained by the April near-miss where a Windows update rebooted hcu-ach01.",
        say=[
            "Please, please don't restart hcu-ach01 within 30 minutes of an exchange cutoff. If it goes down "
            "mid-transmission you get a half-sent AFT file and the resend shows up as a duplicate at Payments Canada.",
            "Rule of thumb for the ACH box: no reboots in the half hour before any cutoff. Patching can wait till after.",
            "if you need to bounce the batch service, check the clock first -- anything inside thirty minutes of a "
            "cutoff and we risk a partial file going out twice",
            "Reminder for whoever schedules Windows updates: the ACH batch server must not restart within 30 min of a "
            "Payments Canada window. Last time it did we nearly double-debited a few hundred members.",
        ],
        prompts=["Nadia wants to patch the ACH server this afternoon, any reason not to?",
                 "is it safe to restart the ACH batch service right now? it's acting up"],
        qs=[
            "Is there a bad time to reboot the ACH batch server?",
            "Anything I should watch out for before restarting the ACH service?",
            "Can I patch hcu-ach01 whenever I want or are there restrictions?",
            "What happens if the ACH server goes down during a transmission, and how do we avoid it?",
            "Any landmines around maintenance on the EFT batch machine?",
            "When is it unsafe to bounce the payments batch service?",
            "I need to restart the ACH box for an update -- what's the rule on timing?",
        ],
        where=["#eng-core", "#ops", "#incidents", "doc"], askers=["nadia", "aisha", "mike"],
    ),
    FactSpec(
        key="ach.last_cutoff.v1", kind=K.FACT, area="ach_payments", importance=3,
        statement="The last ACH exchange window of the day closes at 4:30 pm Atlantic; files must be transmitted "
                  "before then.",
        kw=[_CUTOFF_OLD], known_by=["priya", "sarah"], stated_by="priya",
        valid_from="2025-02-03", valid_to="2026-06-01",
        say=[
            "Last ACH window closes at 4:30 our time, so anything after that rolls to tomorrow.",
            "Heads up, the final EFT exchange is 16:30 Atlantic. Get corrections in before then.",
            "For the late window the cutoff is four-thirty. After that Bluenose won't take the file.",
        ],
        prompts=["what time is the last ACH cutoff again?"],
        where=["#finance", "#eng-core"], askers=["jen", "aisha", "dave"],
    ),
    FactSpec(
        key="ach.last_cutoff.v2", kind=K.FACT, area="ach_payments", importance=3, supersedes="ach.last_cutoff.v1",
        statement="Since June 1, 2026 the last ACH exchange window closes at 3:45 pm Atlantic (moved earlier by our "
                  "clearing sponsor).",
        kw=[["3:45", "15:45", "quarter to four"]], known_by=["priya", "sarah"], stated_by="priya",
        valid_from="2026-06-01", forbid=[_CUTOFF_OLD],
        notes="Conflict: Jen restates the old 4:30 cutoff in July; Priya corrects her. 3:45 is authoritative.",
        say=[
            "Starting June 1 the last ACH window closes at 3:45, not later. Bluenose moved their schedule up.",
            "New cutoff for the final EFT exchange is 15:45 Atlantic -- please update any reminders you have.",
            "No, it changed in June -- last window is quarter to four now. Anything after that goes tomorrow.",
            "Just a reminder the late exchange is 3:45 pm now. Payroll files for business members need to be in well "
            "before that.",
        ],
        prompts=["Member at the Dartmouth branch wants a same-day EFT, how late can we send it?"],
        contra=[("jen", "Pretty sure the last ACH window still closes at 4:30, right? Telling the member we have "
                        "till then.")],
        qs=[
            "What time is the last ACH exchange cutoff now?",
            "How late in the day can we still send an EFT file and have it go out today?",
            "If a member needs a same-day EFT, what's the latest we can transmit?",
            "When does the final Payments Canada window close these days?",
            "What's the current cutoff for the late ACH window?",
            "Did the end-of-day EFT cutoff change? What is it currently?",
        ],
        where=["#finance", "#member-services", "email"], askers=["jen", "colin", "aisha"],
    ),
    FactSpec(
        key="ach.returns_pickup.v1", kind=K.RECURRING_TASK, area="ach_payments", importance=2,
        statement="The ACH returns file is pulled from the clearing SFTP by a scheduled job at 7:00 am each "
                  "business day.",
        kw=[_PICKUP_OLD], known_by=["sarah"], stated_by="sarah",
        valid_from="2024-09-09", valid_to="2026-05-11",
        say=[
            "The returns file gets picked up off the SFTP at 7:00 every business morning by the scheduled task.",
            "Returns pull runs at 7am, so if Priya's report looks empty before then that's why.",
            "The job that grabs the R-file from Bluenose kicks off at 07:00 weekdays.",
        ],
        where=["#eng-core", "#finance"], askers=["priya", "aisha"],
    ),
    FactSpec(
        key="ach.returns_pickup.v2", kind=K.RECURRING_TASK, area="ach_payments", importance=2,
        supersedes="ach.returns_pickup.v1",
        statement="Since May 11, 2026 the ACH returns file pickup job runs at 6:15 am each business day so Priya "
                  "has the returns before the branch opens.",
        kw=[["6:15", "06:15", "quarter past six"]], known_by=["sarah", "priya"], stated_by="sarah",
        valid_from="2026-05-11", forbid=[_PICKUP_OLD],
        say=[
            "Moved the returns pickup to 6:15 starting today, so Priya has the file before the branches open.",
            "FYI returns file job now runs at 06:15 on business days.",
            "The R-file pull is at quarter past six now -- if it's not there by 6:30 something's wrong with the SFTP.",
            "Returns come down at 6:15 am weekdays. If the report is empty after that, ping me.",
        ],
        prompts=["can we get the returns file earlier? I'm always waiting on it"],
        qs=[
            "What time does the ACH returns file get picked up each day?",
            "When does the returns file land in the morning?",
            "If the returns report is empty at 6:45, is that normal?",
            "What's the schedule for the job that downloads EFT returns?",
            "How early in the morning do we get the ACH returns now?",
            "When should I expect the R-file to be available?",
        ],
        where=["#eng-core", "#finance"], askers=["priya", "aisha"],
    ),
    FactSpec(
        key="ach.owner", kind=K.OWNER, area="ach_payments", importance=3,
        statement="Sarah owns the ACH batch server and EFT file generation; Priya owns the settlement and returns "
                  "side on the finance end.",
        kw=[["Sarah"]], known_by=["sarah", "priya", "dave", "aisha"], stated_by="dave", valid_from="2021-03-01",
        say=[
            "For anything on the ACH batch side, file generation, the server, transmissions, that's Sarah. "
            "Settlement questions go to Priya.",
            "Sarah owns the EFT pipeline end to end on the tech side.",
            "If the ACH file didn't go out, Sarah's your person. If it went out and the money's wrong, Priya.",
        ],
        qs=[
            "Who handles the ACH batch files?",
            "Who should I talk to if an EFT file fails to transmit?",
            "Who owns the payments batch server?",
            "Who's the go-to person for ACH problems on the tech side?",
            "Who do I ask about how EFT files are generated?",
        ],
        where=["#eng-core", "#ops", "#general"], askers=["jen", "nadia", "colin"],
    ),
    FactSpec(
        key="ach.returns_daily", kind=K.RECURRING_TASK, area="ach_payments", importance=2,
        statement="Every business morning Priya works the ACH returns report and posts returned items back to "
                  "member accounts by 10:00 am.",
        kw=[["return"], ["10:00", "10am", "10 am", "ten o'clock"]], known_by=["priya"], stated_by="priya",
        valid_from="2023-06-01",
        say=[
            "I work the returns report every morning and get everything posted back to members by 10am.",
            "Returned EFTs are posted back to accounts by 10:00 each business day -- that's on me.",
            "My morning routine: coffee, returns report, all returned items posted by ten o'clock.",
        ],
        prompts=["Member says their direct deposit bounced, when would that show?"],
        qs=[
            "When do returned EFTs get posted back to member accounts?",
            "Who processes the ACH returns each day and by when?",
            "If a member's payment was returned, how soon would we post it back?",
            "What's the daily deadline for handling returned payments?",
        ],
        where=["#finance", "#member-services"], askers=["jen", "colin"],
    ),
    FactSpec(
        key="ach.sftp_key_vault", kind=K.ACCESS, area="ach_payments", importance=3,
        statement="The SFTP key used to transmit ACH files to the clearing sponsor is stored in the 1Password "
                  "vault 'Payments-Prod'; only Sarah and Priya have access.",
        kw=[["Payments-Prod", "payments prod"]], known_by=["sarah", "priya"], stated_by="sarah",
        valid_from="2024-02-12",
        say=[
            "The SFTP key for Bluenose lives in the Payments-Prod vault in 1Password. Only Priya and I are on it.",
            "It's in 1Password under Payments-Prod -- I'll ask Dave about adding you.",
            "Transmission key is in the Payments-Prod vault. Don't copy it anywhere else please.",
        ],
        prompts=["where do we keep the key for the ACH SFTP?"],
        qs=[
            "Where is the key for sending ACH files to the clearing SFTP stored?",
            "Which 1Password vault has the EFT transmission credentials?",
            "Who has access to the ACH SFTP key, and where is it?",
            "I need the payments SFTP credentials for a test -- where do they live?",
        ],
        where=["#eng-core", "email"], askers=["aisha", "nadia"],
    ),
    FactSpec(
        key="ach.sponsor_contact", kind=K.VENDOR_CONTACT, area="ach_payments", importance=2,
        statement="Our ACH clearing sponsor is Bluenose Central; our contact there is Rachel Oakes in payment "
                  "operations.",
        kw=[["Rachel"], ["Bluenose"]], known_by=["priya", "sarah"], stated_by="priya", valid_from="2025-04-01",
        say=[
            "Our contact at Bluenose Central is Rachel Oakes in payment ops -- she's great, answers same day.",
            "For anything the clearing side needs, email Rachel Oakes at Bluenose.",
            "Rachel at Bluenose Central confirmed the file came through, all good.",
        ],
        prompts=["who do we call at the clearing sponsor when a file gets rejected?"],
        qs=[
            "Who's our contact at the ACH clearing sponsor?",
            "Which person at Bluenose do we deal with for payment files?",
            "If the clearing sponsor rejects a file, who do I reach out to over there?",
            "Who is our rep for EFT clearing?",
        ],
        where=["#finance", "email"], askers=["dave", "aisha"],
    ),
    FactSpec(
        key="ach.cpa005_records", kind=K.FACT, area="ach_payments", importance=1,
        statement="Outbound ACH files are CPA 005 format with fixed 1464-character records.",
        kw=[["1464"]], known_by=["sarah"], stated_by="sarah", valid_from="2020-06-15",
        say=[
            "CPA 005 records are fixed width, 1464 chars each, so if the line length is off the file's toast.",
            "The outbound files are CPA 005 -- 1464-byte records. The validator checks that first.",
            "Every record in the EFT file has to be exactly 1464 characters. Trailing spaces matter!",
        ],
        prompts=["why did the file validator reject this? looks fine to me"],
        qs=[
            "What's the record length in our outbound EFT files?",
            "What format are the ACH files we send, and how long is each record?",
            "The EFT validator says record length is wrong -- what should it be?",
            "How many characters per line in a CPA 005 file?",
        ],
        where=["#eng-core", "doc"], askers=["aisha"],
    ),
    FactSpec(
        key="ach.server_host", kind=K.FACT, area="ach_payments", importance=2,
        statement="The ACH batch server is hcu-ach01, a Windows VM in the Burnside data centre rack.",
        kw=[["hcu-ach01", "ach01"]], known_by=["sarah", "mike", "nadia"], stated_by="sarah",
        valid_from="2022-10-03",
        say=[
            "The batch stuff all runs on hcu-ach01, the Windows VM down in the Burnside rack.",
            "ach01 is the box -- RDP in with your admin account, logs are under D:\\ACH\\logs.",
            "It's hcu-ach01. Mike built it back in 2022.",
        ],
        prompts=["which server actually builds the EFT files?"],
        qs=[
            "Which server builds and sends our ACH files?",
            "What's the hostname of the EFT batch machine?",
            "Where does the ACH batch job actually run?",
            "I need to look at the ACH logs -- what box are they on?",
        ],
        where=["#eng-core", "#it-help"], askers=["aisha", "nadia"],
    ),
    FactSpec(
        key="ach.hash_check_decision", kind=K.DECISION, area="ach_payments", importance=2,
        statement="After the April 2026 near-miss, Sarah added a hash check that blocks transmitting an ACH file "
                  "identical to one already sent (duplicate-file guard).",
        kw=[["hash", "checksum"], ["duplicate", "dupe", "same file"]], known_by=["sarah", "dave"],
        stated_by="sarah", valid_from="2026-04-14",
        say=[
            "Shipped the duplicate guard today: before transmitting we hash the file and refuse if it matches one "
            "already sent.",
            "We now checksum every outbound file and block dupes. Should stop a repeat of last week.",
            "Decision from the post-incident call: hash check before send, so the same file can't go twice.",
        ],
        qs=[
            "What did we change after the ACH duplicate near-miss in April?",
            "Is there anything stopping the same EFT file from being sent twice?",
            "How do we protect against resending an ACH file by accident?",
            "Why did my resend get blocked with a hash error?",
        ],
        where=["#eng-core", "#incidents", "ticket"], askers=["dave", "aisha"],
    ),
    FactSpec(
        key="ach.business_dd_deadline", kind=K.FACT, area="ach_payments", importance=2,
        statement="Business members' payroll direct-deposit files must reach us at least two business days "
                  "before the pay date.",
        kw=[["two business days", "2 business days", "two banking days", "2 banking days"]],
        known_by=["priya", "sarah", "jen"], stated_by="priya", valid_from="2023-01-16",
        say=[
            "Business payroll files have to be with us two business days before pay day, no exceptions.",
            "Tell the member we need their direct deposit file 2 business days ahead of pay date.",
            "Standard is two banking days' notice for employer payroll files. Anything later is best effort.",
        ],
        prompts=["business member asking how late they can send us their payroll file"],
        qs=[
            "How far ahead do business members need to send us their payroll direct deposit file?",
            "What's the lead time for employer payroll files?",
            "A business member wants to send their pay file the day before payday -- is that okay?",
            "What notice do we need for business direct deposits?",
        ],
        where=["#member-services", "#finance"], askers=["jen", "colin"],
    ),
    FactSpec(
        key="ach.fcn_procedure", kind=K.PROCEDURE, area="ach_payments", importance=2,
        statement="If an ACH file is rejected, increment the file creation number (FCN) before resending; never "
                  "reuse an FCN.",
        kw=[["file creation number", "FCN"]], known_by=["sarah"], stated_by="sarah", valid_from="2021-05-10",
        say=[
            "When a file bounces, bump the file creation number by one before you resend. Never reuse an FCN.",
            "Resend steps: fix the file, increment the FCN, re-run validation, transmit.",
            "Rejected files need a new file creation number or Bluenose treats it as a duplicate.",
        ],
        prompts=["file got rejected this morning, can I just resend it?"],
        qs=[
            "What do I need to change before resending a rejected ACH file?",
            "How do I resend an EFT file that bounced?",
            "Can I resend a rejected payments file as-is?",
            "What's the procedure when Bluenose rejects our file?",
        ],
        where=["#eng-core", "doc", "ticket"], askers=["aisha"],
    ),
    FactSpec(
        key="ach.daily_limit", kind=K.FACT, area="ach_payments", importance=2,
        statement="The daily outbound ACH limit is $2 million; anything above needs Dave's sign-off.",
        kw=[["2 million", "$2M", "2M", "two million"]], known_by=["priya", "dave", "sarah"], stated_by="priya",
        valid_from="2025-11-01",
        say=[
            "Daily outbound limit is $2M. Over that, Dave has to sign off.",
            "We cap outbound EFT at two million a day, anything bigger goes to Dave.",
            "Just so everyone knows, the 2 million daily ACH limit is hard -- the file won't go without Dave's okay.",
        ],
        qs=[
            "What's our daily outbound ACH limit?",
            "How much can we send in EFTs in one day before we need approval?",
            "Who approves ACH totals over the daily cap, and what is the cap?",
            "Is there a max dollar amount for outbound payments per day?",
        ],
        where=["#finance", "email"], askers=["sarah", "dave", "jen"],
    ),
    FactSpec(
        key="ach.payee_truncation", kind=K.LANDMINE, area="ach_payments", importance=2, in_corpus=False,
        statement="The ACH batch builder silently truncates payee names longer than 30 characters, which causes "
                  "some returns for name mismatch.",
        kw=[["30", "thirty"], ["truncat", "cut off", "chop"]], known_by=["sarah"], stated_by="sarah",
        valid_from="2023-08-01",
        qs=[
            "Why do some EFTs with long payee names get returned?",
            "Does the ACH builder do anything weird with long names?",
            "Is there a payee name length limit in our EFT files?",
        ],
    ),
    FactSpec(
        key="ach.resend_norenumber", kind=K.PROCEDURE, area="ach_payments", importance=2, in_corpus=False,
        statement="The ACH resend script (resend.ps1) must be run with the -NoRenumber flag for partial resends, "
                  "otherwise it renumbers every record.",
        kw=[["NoRenumber"]], known_by=["sarah"], stated_by="sarah", valid_from="2022-04-04",
        qs=[
            "What flags should I use with the ACH resend script?",
            "How do I do a partial resend of an EFT file without messing up the record numbers?",
            "Is there a gotcha with resend.ps1?",
        ],
    ),
    FactSpec(
        key="ach.signing_cert_expiry", kind=K.RECURRING_TASK, area="ach_payments", importance=3, private=True,
        statement="The ACH transmission signing certificate on hcu-ach01 expires in November 2026; renewal needs "
                  "Priya's approval in the clearing sponsor's portal.",
        kw=[["November", "Nov"]], known_by=["sarah"], stated_by="sarah", valid_from="2026-08-20",
        say=[
            "btw the signing cert on ach01 expires in November and I haven't flagged it to anyone yet. Renewal needs "
            "Priya to approve it in the Bluenose portal.",
            "one more thing for your list -- ACH signing cert, expires Nov. Priya approves the renewal.",
            "don't let me forget, the ACH signing cert dies in November. it's a Priya approval + me generating the CSR",
        ],
        qs=[
            "When does the ACH signing certificate expire?",
            "Is anything on the ACH server expiring soon?",
            "Who needs to approve the ACH cert renewal and when is it due?",
        ],
        where=["dm"], askers=["aisha"],
    ),
]

PORTAL: list[FactSpec] = [
    FactSpec(
        key="portal.owner", kind=K.OWNER, area="member_portal", importance=2,
        statement="Aisha is the day-to-day owner of the member portal (took it over from Sarah in spring 2026); "
                  "Sarah still knows the backend.",
        kw=[["Aisha"]], known_by=["dave", "aisha", "sarah", "jen"], stated_by="dave", valid_from="2026-04-06",
        say=[
            "Portal questions go to Aisha now. Sarah handed it over this spring.",
            "Aisha owns the member portal day to day -- loop Sarah in only for the deep backend stuff.",
            "Reminder: for portal bugs, tag Aisha, not Sarah.",
        ],
        qs=[
            "Who handles the member portal?",
            "Who do I talk to about a bug in online banking?",
            "Who owns the portal these days?",
            "Who should member services escalate portal issues to?",
            "Who's responsible for the online banking site?",
        ],
        where=["#member-services", "#eng-core"], askers=["jen", "colin"],
    ),
    FactSpec(
        key="portal.session_timeout.v1", kind=K.FACT, area="member_portal", importance=2,
        statement="Member portal sessions time out after 15 minutes of inactivity.",
        kw=[_TIMEOUT_OLD], known_by=["aisha", "sarah", "jen"], stated_by="aisha",
        valid_from="2024-11-01", valid_to="2026-07-06",
        say=[
            "Portal logs members out after 15 minutes idle, that's by design.",
            "Session timeout is fifteen minutes of inactivity.",
            "Yep, 15 min idle and they're kicked back to login.",
        ],
        where=["#member-services"], askers=["jen", "colin"],
    ),
    FactSpec(
        key="portal.session_timeout.v2", kind=K.DECISION, area="member_portal", importance=2,
        supersedes="portal.session_timeout.v1",
        statement="Since July 6, 2026 member portal sessions time out after 10 minutes of inactivity (audit "
                  "recommendation).",
        kw=[["10 min", "ten min"]], known_by=["aisha", "sarah", "jen", "dave"], stated_by="aisha",
        valid_from="2026-07-06", forbid=[_TIMEOUT_OLD],
        say=[
            "Heads up member services: as of today the portal times out after 10 minutes idle. Audit asked for it.",
            "Timeout is ten minutes now, down from before -- expect some grumbling from members.",
            "It's 10 min of inactivity now since the July change. That's the auditor's recommendation, not a bug.",
            "Yes the shorter logout is intentional, 10 minutes idle.",
        ],
        prompts=["members complaining they get logged out quicker than before, is that a bug?"],
        qs=[
            "How long before an idle member gets logged out of the portal?",
            "What's the portal's session timeout right now?",
            "A member says online banking kicks them out quickly -- how long is the idle timeout?",
            "After how many minutes of inactivity does the portal end a session?",
            "Did the portal timeout change? What is it now?",
            "Is the quick logout in online banking intentional?",
        ],
        where=["#member-services", "#eng-core"], askers=["jen", "colin"],
    ),
    FactSpec(
        key="portal.pwreset.v1", kind=K.PROCEDURE, area="member_portal", importance=2,
        statement="Member services resets portal passwords from the admin console after the member answers two "
                  "security questions.",
        kw=[["security question"]], known_by=["jen", "colin", "aisha"], stated_by="jen",
        valid_from="2023-03-01", valid_to="2026-05-19",
        say=[
            "For password resets: ask the two security questions, then reset from the admin console.",
            "Two security questions, both right, then you can reset it in the console.",
            "If they pass the security questions you're fine to reset it for them.",
        ],
        where=["#member-services"], askers=["colin"],
    ),
    FactSpec(
        key="portal.pwreset.v2", kind=K.PROCEDURE, area="member_portal", importance=2,
        supersedes="portal.pwreset.v1",
        statement="Since May 19, 2026 members must reset their own portal password via 'Forgot password' with an "
                  "SMS code; staff may only unlock accounts, not reset passwords.",
        kw=[["self-serve", "self serve", "Forgot password", "forgot password"]],
        known_by=["jen", "colin", "aisha"], stated_by="jen", valid_from="2026-05-19",
        forbid=[["security question"]],
        say=[
            "New as of today: we don't reset portal passwords anymore. Walk the member through Forgot password -- "
            "they get an SMS code. We can only unlock.",
            "Members self-serve password resets now. Point them to the Forgot password link.",
            "Reminder team, password resets are self-serve only since May. Unlock yes, reset no.",
            "Just send them to Forgot password on the login page, the text code does the rest.",
        ],
        prompts=["member on the phone wants me to reset their password, what's the process now?"],
        qs=[
            "How do we reset a member's online banking password?",
            "A member forgot their portal password -- what do I tell them?",
            "Can member services still reset portal passwords for members?",
            "What's the current password reset process for the portal?",
            "What should I do when a member calls because they can't remember their password?",
            "Are staff allowed to reset member passwords in the admin console?",
        ],
        where=["#member-services", "doc"], askers=["colin"],
    ),
    FactSpec(
        key="portal.mfa_callback", kind=K.LANDMINE, area="member_portal", importance=3, landmine=True,
        statement="Never reset a member's 2FA over the phone without calling them back on the number on file in "
                  "CoreLink (a social-engineering attempt in March 2026 nearly succeeded).",
        kw=[["call back", "callback", "call them back", "call-back"], ["on file"]],
        known_by=["jen", "colin", "aisha"], stated_by="jen", valid_from="2026-03-24",
        say=[
            "Nobody resets 2FA over the phone without a call back to the number on file in CoreLink. Nobody. "
            "We almost got burned last week.",
            "2FA reset requests: hang up and do a callback to the number on file. If the member argues, that's a red "
            "flag.",
            "Rule for everyone: call them back on the number on file before touching 2FA. The number they give you "
            "doesn't count.",
        ],
        prompts=["caller says they got a new phone and needs 2FA reset asap, they sound legit"],
        qs=[
            "What do I need to do before resetting a member's 2FA?",
            "A caller says they lost their phone and needs their two-factor reset -- anything to watch for?",
            "Is it okay to reset 2FA if the member verifies their identity on the call?",
            "What's the rule for two-factor resets over the phone?",
            "Any gotchas with MFA reset requests from members?",
            "Can I reset 2FA to the new number the member gives me?",
        ],
        where=["#member-services", "#incidents"], askers=["colin"],
    ),
    FactSpec(
        key="portal.banner_48h", kind=K.PROCEDURE, area="member_portal", importance=2,
        statement="Planned portal maintenance needs the maintenance banner posted at least 48 hours ahead.",
        kw=[["48 hours", "48h", "48 hrs", "two days", "2 days"]], known_by=["jen", "aisha"], stated_by="jen",
        valid_from="2024-05-01",
        say=[
            "Any planned downtime needs the banner up 48 hours ahead -- it's in the member agreement.",
            "Aisha, can you get the maintenance banner posted? We need two days' notice for members.",
            "48h notice banner or it doesn't happen, sorry!",
        ],
        qs=[
            "How much notice do we give members before portal maintenance?",
            "When does the maintenance banner need to go up?",
            "Can we do unplanned portal maintenance tonight without warning members?",
            "What's the lead time for a downtime notice in online banking?",
        ],
        where=["#member-services", "#eng-core"], askers=["aisha"],
    ),
    FactSpec(
        key="portal.deploy_window", kind=K.RECURRING_TASK, area="member_portal", importance=2,
        statement="Portal deploys only go out on Tuesday nights between 10 pm and midnight.",
        kw=[["Tuesday", "Tues"]], known_by=["aisha", "sarah"], stated_by="aisha", valid_from="2025-01-14",
        say=[
            "Portal deploys are Tuesday night, 10 to midnight. Anything else needs Dave.",
            "We ship the portal Tuesdays after 10pm, lowest traffic.",
            "It'll go out in the Tues night window.",
        ],
        prompts=["when's the next chance to push the portal fix?"],
        qs=[
            "When are we allowed to deploy portal changes?",
            "What's the release window for online banking?",
            "Can I push a portal fix on a Thursday afternoon?",
            "Which night do portal releases go out?",
        ],
        where=["#eng-core"], askers=["sarah", "dave"],
    ),
    FactSpec(
        key="portal.vendor_contact", kind=K.VENDOR_CONTACT, area="member_portal", importance=2,
        statement="The portal front end is hosted by Seabright Digital; our account manager there is Kyle Maddox.",
        kw=[["Kyle"]], known_by=["sarah", "aisha"], stated_by="sarah", valid_from="2024-06-01",
        say=[
            "Seabright hosts the front end. Kyle Maddox is our account manager -- email him, not the support queue.",
            "Kyle at Seabright can bump the ticket if it's urgent.",
            "Our guy at Seabright Digital is Kyle Maddox.",
        ],
        qs=[
            "Who's our contact at the portal hosting vendor?",
            "Who do I escalate to at Seabright?",
            "Who is the account manager for our online banking host?",
            "Which person at the hosting company can speed up a support ticket?",
        ],
        where=["#eng-core", "email"], askers=["aisha", "dave"],
    ),
    FactSpec(
        key="portal.twilio_access", kind=K.ACCESS, area="member_portal", importance=2,
        statement="The Twilio (SMS codes) console is owned by the shared eng-alerts@harbourlinecu.ca mailbox; the "
                  "login is in the 1Password Engineering vault.",
        kw=[["eng-alerts"]], known_by=["sarah", "aisha"], stated_by="sarah", valid_from="2024-02-20",
        say=[
            "Twilio's owner account is the eng-alerts@ mailbox, login's in the Engineering vault.",
            "It's under eng-alerts, not anyone's personal email, thank god.",
            "For the SMS provider console, sign in as eng-alerts -- creds are in 1Password.",
        ],
        qs=[
            "Which account owns our Twilio console?",
            "How do I log in to the SMS provider for 2FA codes?",
            "Whose email is the Twilio account under?",
            "Where are the credentials for the portal's SMS service?",
        ],
        where=["#eng-core"], askers=["aisha"],
    ),
    FactSpec(
        key="portal.estatements_job", kind=K.RECURRING_TASK, area="member_portal", importance=2,
        statement="The monthly e-statement generation job runs only on hcu-web02, on the 3rd of each month.",
        kw=[["web02"], ["3rd", "third"]], known_by=["sarah", "aisha"], stated_by="sarah", valid_from="2023-09-03",
        say=[
            "e-statements run on the 3rd, and only from hcu-web02 -- web01 doesn't have the job.",
            "The statement job is scheduled on web02 for the third of every month.",
            "If statements didn't generate, check web02, the job fires on the 3rd.",
        ],
        qs=[
            "When do e-statements get generated, and on which server?",
            "Members say their monthly statement isn't there -- where does that job run?",
            "Which portal server runs the statement job?",
            "What day of the month does the e-statement job fire?",
        ],
        where=["#eng-core", "#member-services"], askers=["aisha", "jen"],
    ),
    FactSpec(
        key="portal.lockout", kind=K.FACT, area="member_portal", importance=1,
        statement="Portal accounts lock after 5 failed login attempts; staff can unlock them from the admin "
                  "console.",
        kw=[["5 failed", "five failed", "5 wrong", "five wrong", "5 bad", "five bad"]],
        known_by=["jen", "colin", "aisha"], stated_by="jen", valid_from="2022-02-01",
        say=[
            "Five failed logins and it locks. You can unlock it in the console.",
            "They're locked out after 5 bad attempts -- unlock, then send them to Forgot password if needed.",
            "Lockout kicks in at 5 wrong passwords.",
        ],
        qs=[
            "How many failed logins before a portal account locks?",
            "Why is a member locked out of online banking after a few tries?",
            "What's the lockout threshold on the portal?",
            "Member typed their password wrong a bunch of times -- when does it lock?",
        ],
        where=["#member-services"], askers=["colin"],
    ),
    FactSpec(
        key="portal.app_freeze", kind=K.DECISION, area="member_portal", importance=2,
        statement="Mobile app releases are frozen until October 2026 to cover the engineering handover.",
        kw=[["October", "Oct"]], known_by=["dave", "aisha", "sarah"], stated_by="dave", valid_from="2026-08-10",
        say=[
            "We're freezing mobile app releases until October. Too much going on with the handover.",
            "No app releases till Oct, please. Bug fixes on the web portal are fine.",
            "Decision: app release freeze through the end of September, back in October.",
        ],
        qs=[
            "Can we ship a mobile app update this month?",
            "Is there a freeze on mobile app releases?",
            "When can we release the next version of the app?",
            "Why hasn't the app been updated lately?",
        ],
        where=["#eng-core", "#general"], askers=["aisha", "jen"],
    ),
    FactSpec(
        key="portal.outage_ivr", kind=K.PROCEDURE, area="member_portal", importance=2,
        statement="During a portal outage Jen posts the outage script to member services and updates the phone "
                  "IVR message.",
        kw=[["IVR", "phone message", "phone greeting"]], known_by=["jen"], stated_by="jen", valid_from="2024-01-10",
        say=[
            "When the portal's down I post the outage script here and update the IVR so callers hear it first.",
            "Outage playbook on our side: script in channel, then change the IVR message.",
            "I've updated the IVR and the script is pinned. Stick to it with callers please.",
        ],
        qs=[
            "What does member services do when online banking goes down?",
            "Who updates the phone message during a portal outage?",
            "Is there an outage procedure for the member-facing side?",
            "What's the playbook for callers during a portal outage?",
        ],
        where=["#member-services", "#incidents"], askers=["colin"],
    ),
    FactSpec(
        key="portal.impersonate_mode", kind=K.FACT, area="member_portal", importance=2, in_corpus=False,
        statement="The portal admin console has an 'impersonate member' mode whose audit log goes only to a local "
                  "file on the web server, not to the SIEM.",
        kw=[["impersonat"]], known_by=["sarah"], stated_by="sarah", valid_from="2022-07-01",
        qs=[
            "Can staff see the portal exactly as a member sees it?",
            "Is there a way to log in as a member in the admin console, and is it audited?",
            "Where are admin console impersonation actions logged?",
        ],
    ),
    FactSpec(
        key="portal.estatements_disk", kind=K.LANDMINE, area="member_portal", importance=2, in_corpus=False,
        statement="The e-statement job fails silently if the PDF share is more than 90% full.",
        kw=[["90", "ninety"]], known_by=["sarah"], stated_by="sarah", valid_from="2024-03-01",
        qs=[
            "Why would the e-statement job finish without producing statements?",
            "Is there a known silent failure mode for the statement job?",
            "What should I check if statements don't generate but there's no error?",
        ],
    ),
]

IAM: list[FactSpec] = [
    FactSpec(
        key="iam.owner", kind=K.OWNER, area="identity_access", importance=2,
        statement="Nadia owns Okta and access requests; Mike handles the legacy Active Directory.",
        kw=[["Nadia"]], known_by=["dave", "nadia", "mike"], stated_by="dave", valid_from="2023-06-01",
        say=[
            "Access requests go to Nadia. For the old AD stuff, Mike.",
            "Nadia owns Okta and all the joiner/leaver access. Mike still looks after legacy AD.",
            "Please file access requests with Nadia, not me.",
        ],
        qs=[
            "Who handles access requests?",
            "Who do I ask to get added to a system?",
            "Who owns Okta?",
            "Who manages user accounts and permissions here?",
            "Who should I go to when a new hire needs logins?",
        ],
        where=["#it-help", "#general"], askers=["jen", "colin", "priya"],
    ),
    FactSpec(
        key="iam.okta_superadmins", kind=K.ACCESS, area="identity_access", importance=3,
        statement="Only Nadia and Sarah are Okta super-admins.",
        kw=[["Nadia"], ["Sarah"]], known_by=["nadia", "sarah", "dave"], stated_by="nadia", valid_from="2024-08-01",
        say=[
            "Only Sarah and I (Nadia) have Okta super-admin. We should really add a third before she goes.",
            "Super-admin in Okta is just me (Nadia) and Sarah.",
            "Sarah and Nadia are the two Okta super admins -- anyone else is a helpdesk admin at most.",
        ],
        qs=[
            "Who are the Okta super-admins?",
            "Who can change Okta policies?",
            "Who has full admin rights in Okta?",
            "If Nadia is off, who else can do super-admin work in Okta?",
        ],
        where=["#it-help", "#ops"], askers=["dave", "aisha"],
    ),
    FactSpec(
        key="iam.github_owner", kind=K.ACCESS, area="identity_access", importance=3,
        statement="Sarah is the only owner of the Harbourline GitHub organization.",
        kw=[["Sarah"], ["GitHub", "github"]], known_by=["sarah", "nadia", "aisha"], stated_by="nadia",
        valid_from="2021-01-11",
        say=[
            "Only Sarah is an owner on the GitHub org, so she has to approve that.",
            "The GitHub org has exactly one owner and it's Sarah.",
            "You'll need Sarah for that, she's the sole GitHub org owner.",
        ],
        prompts=["can someone add me as a GitHub org owner so I can manage the repos?"],
        qs=[
            "Who owns our GitHub organization?",
            "Who can add people to the GitHub org?",
            "Who has owner rights on GitHub?",
            "I need a new repo created in the org -- who can do that?",
        ],
        where=["#eng-core", "#it-help"], askers=["aisha"],
    ),
    FactSpec(
        key="iam.mfa_policy.v1", kind=K.FACT, area="identity_access", importance=2,
        statement="Staff Okta MFA allows SMS codes or Okta Verify.",
        kw=[["SMS", "text message"]], known_by=["nadia"], stated_by="nadia",
        valid_from="2023-02-01", valid_to="2026-06-15",
        say=[
            "You can use SMS or Okta Verify for staff MFA, whichever.",
            "SMS works fine for Okta MFA if you don't want the app.",
            "Text message codes are allowed for MFA, yes.",
        ],
        where=["#it-help"], askers=["colin", "jen"],
    ),
    FactSpec(
        key="iam.mfa_policy.v2", kind=K.DECISION, area="identity_access", importance=2,
        supersedes="iam.mfa_policy.v1",
        statement="Since June 15, 2026 staff Okta MFA is Okta Verify push only; SMS was removed.",
        kw=[["Okta Verify"], ["push"]], known_by=["nadia", "dave"], stated_by="nadia", valid_from="2026-06-15",
        say=[
            "As of today staff MFA is Okta Verify push only -- SMS is gone. Come see me if you need help enrolling.",
            "Okta Verify with push is the only MFA factor for staff now.",
            "No more texts for MFA, sorry! Push through Okta Verify only.",
            "The policy flipped mid-June: Okta Verify push, nothing else.",
        ],
        prompts=["my Okta isn't sending me a text code anymore?"],
        qs=[
            "What MFA options do staff have for Okta?",
            "Can I still use text message codes to log in to Okta?",
            "What's the current MFA policy for employees?",
            "I didn't get an SMS code from Okta -- is that expected?",
            "Which factor do I need to set up for staff login?",
            "Did the staff MFA rules change?",
        ],
        where=["#it-help", "#general"], askers=["colin", "jen", "priya"],
    ),
    FactSpec(
        key="iam.admin_approval.v1", kind=K.PROCEDURE, area="identity_access", importance=2,
        statement="Admin-rights requests are approved by Dave.",
        kw=[["Dave"]], known_by=["nadia", "dave"], stated_by="nadia",
        valid_from="2022-01-01", valid_to="2026-04-20",
        say=[
            "Admin rights need Dave's approval, then I set it up.",
            "Get Dave to approve and I'll grant the admin access.",
            "Dave signs off on admin requests.",
        ],
        where=["#it-help"], askers=["aisha"],
    ),
    FactSpec(
        key="iam.admin_approval.v2", kind=K.PROCEDURE, area="identity_access", importance=2,
        supersedes="iam.admin_approval.v1",
        statement="Since April 20, 2026 admin-rights requests need two approvals: Nadia and Dave.",
        kw=[["Nadia"], ["Dave"]], known_by=["nadia", "dave"], stated_by="dave", valid_from="2026-04-20",
        say=[
            "New rule: admin rights need two approvals, Nadia and me (Dave). No single-person grants anymore.",
            "Both Nadia and Dave have to approve admin access now, per the audit.",
            "Admin request? Ticket to Nadia, she approves, then Dave approves. Two-person rule.",
        ],
        qs=[
            "Who approves admin rights requests?",
            "What approvals do I need to get local admin?",
            "Can Dave alone approve my admin access?",
            "What's the process for getting elevated permissions now?",
            "How many people have to sign off on admin rights?",
            "Who do I need to get approval from for domain admin?",
        ],
        where=["#it-help", "email"], askers=["aisha", "priya"],
    ),
    FactSpec(
        key="iam.onepassword_before_okta", kind=K.LANDMINE, area="identity_access", importance=3, landmine=True,
        statement="Do not disable a leaver's Okta account until ownership of their 1Password shared vaults has "
                  "been transferred; 1Password is SSO'd through Okta and the vaults become unrecoverable.",
        kw=[["1Password"], ["transfer", "hand over", "handed over", "reassign"]],
        known_by=["nadia", "mike"], stated_by="nadia", valid_from="2025-02-10",
        say=[
            "Before you disable anyone in Okta, transfer their 1Password vaults first. 1Password logs in through "
            "Okta and if the owner's gone the shared vaults are locked forever.",
            "Order matters for leavers: 1Password vault ownership gets transferred, THEN Okta gets disabled.",
            "Learned this the hard way in 2025 -- reassign the 1Password vaults before killing the Okta account.",
        ],
        prompts=["can I disable the account for the leaver today?"],
        qs=[
            "Anything I need to do before disabling a leaver's Okta account?",
            "What's the gotcha with offboarding someone who owns 1Password vaults?",
            "In what order should we shut off accounts when someone leaves?",
            "Can I just deactivate Sarah's Okta account on her last day?",
            "What goes wrong if you disable Okta before handling 1Password?",
            "Any landmines in the leaver process?",
        ],
        where=["#it-help", "doc", "#ops"], askers=["dave", "mike"],
    ),
    FactSpec(
        key="iam.quarterly_review", kind=K.RECURRING_TASK, area="identity_access", importance=2,
        statement="Nadia runs a quarterly access review (first week of January, April, July and October) and Dave "
                  "signs it off.",
        kw=[["quarter", "every three months"]], known_by=["nadia", "dave"], stated_by="nadia",
        valid_from="2024-01-02",
        say=[
            "Quarterly access review kicks off this week -- managers, you'll get a list to confirm. Dave signs it off.",
            "It's that time again, the quarterly review of who has access to what.",
            "Every three months I pull all the access lists and Dave signs off. First week of the quarter.",
        ],
        qs=[
            "How often do we review who has access to what?",
            "When is the next access review?",
            "Who runs the access reviews and who signs off?",
            "What's the schedule for access recertification?",
        ],
        where=["#it-help", "email"], askers=["dave"],
    ),
    FactSpec(
        key="iam.leaver_notice", kind=K.PROCEDURE, area="identity_access", importance=2,
        statement="For a leaver, the manager files an access-removal ticket at least 5 business days before the "
                  "last day, using the Leaver checklist in the IT wiki.",
        kw=[["5 business days", "five business days", "5 days", "five days"]], known_by=["nadia", "dave"],
        stated_by="nadia", valid_from="2024-03-01",
        say=[
            "For leavers, I need the ticket 5 business days before the last day. Leaver checklist is in the IT wiki.",
            "Managers: five business days' notice for access removals please.",
            "Give me at least 5 days' notice on a leaver so I can do the checklist properly.",
        ],
        qs=[
            "How much notice does IT need when someone is leaving?",
            "When should the access removal ticket be filed for a departing employee?",
            "Where's the leaver checklist and when do I start it?",
            "What's the offboarding lead time for accounts?",
        ],
        where=["#it-help", "doc"], askers=["dave", "jen"],
    ),
    FactSpec(
        key="iam.service_vault", kind=K.ACCESS, area="identity_access", importance=3,
        statement="Service-account credentials are stored in the 1Password vault 'Infra-Service'; Nadia and Mike "
                  "have access.",
        kw=[["Infra-Service", "infra service"]], known_by=["nadia", "mike"], stated_by="mike",
        valid_from="2024-05-06",
        say=[
            "Service account passwords are in the Infra-Service vault. Nadia and I are on it.",
            "Check Infra-Service in 1Password, that's where all the svc accounts live.",
            "It'll be in the Infra-Service vault, if it's not, it's in my head and I'll add it.",
        ],
        qs=[
            "Where are service account passwords kept?",
            "Which 1Password vault has the infrastructure service accounts?",
            "Who can get at the service account credentials?",
            "I need the svc account for the backup job -- where would it be?",
        ],
        where=["#it-help", "#ops"], askers=["nadia", "aisha"],
    ),
    FactSpec(
        key="iam.okta_ad_agent_host", kind=K.FACT, area="identity_access", importance=2,
        statement="Okta syncs users from the legacy HCU.LOCAL Active Directory via the Okta AD agent on hcu-dc02.",
        kw=[["dc02"]], known_by=["mike", "nadia"], stated_by="mike", valid_from="2023-02-01",
        say=[
            "The Okta AD agent runs on hcu-dc02. That's what syncs HCU.LOCAL users up to Okta.",
            "Okta pulls from AD through the agent on dc02.",
            "dc02 has the Okta agent, dc01 doesn't, don't mix them up.",
        ],
        qs=[
            "Which server runs the Okta AD sync agent?",
            "How do AD accounts get into Okta?",
            "Where does the Okta Active Directory agent live?",
            "What machine do I check if Okta stops syncing from AD?",
        ],
        where=["#it-help", "#ops"], askers=["nadia"],
    ),
    FactSpec(
        key="iam.okta_agent_restart", kind=K.PROCEDURE, area="identity_access", importance=2,
        statement="If Okta stops syncing from AD, restart the 'Okta AD Agent' Windows service on the domain "
                  "controller rather than rebooting the whole server.",
        kw=[["AD Agent", "AD agent"], ["service"]], known_by=["mike", "nadia"], stated_by="mike",
        valid_from="2023-02-01",
        say=[
            "When the sync stalls just restart the Okta AD Agent service. Don't reboot the DC for that.",
            "Services.msc, Okta AD Agent, restart. Nine times out of ten that's it.",
            "Don't bounce the whole box, only the Okta AD agent service.",
        ],
        prompts=["new hire isn't showing up in Okta, AD looks fine"],
        qs=[
            "How do I fix Okta not syncing from Active Directory?",
            "New AD user isn't showing up in Okta -- what should I try?",
            "Should I reboot the domain controller if the Okta sync is stuck?",
            "What's the fix when the AD-to-Okta sync stops?",
        ],
        where=["#it-help"], askers=["nadia"],
    ),
    FactSpec(
        key="iam.okta_reseller", kind=K.VENDOR_CONTACT, area="identity_access", importance=1,
        statement="Okta licences are renewed through the reseller Lighthouse IT; our contact is Brenda Clarke.",
        kw=[["Brenda"]], known_by=["nadia", "dave"], stated_by="nadia", valid_from="2025-03-01",
        say=[
            "Okta renewal goes through Lighthouse IT, Brenda Clarke is our contact.",
            "I'll ask Brenda at Lighthouse for a quote on more Okta seats.",
            "Brenda Clarke (Lighthouse) handles our Okta licensing.",
        ],
        qs=[
            "Who do we buy Okta licences from?",
            "Who's the contact for Okta renewals?",
            "We need more Okta seats -- who do I talk to at the reseller?",
            "Which vendor handles Okta licensing for us?",
        ],
        where=["#it-help", "email"], askers=["dave"],
    ),
    FactSpec(
        key="iam.dc01_badge_sync", kind=K.LANDMINE, area="identity_access", importance=3, in_corpus=False,
        statement="The old domain controller HCU-DC01 still runs the badge-door sync scheduled task; "
                  "decommissioning it breaks door badges.",
        kw=[["DC01"], ["badge"]], known_by=["mike"], stated_by="mike", valid_from="2019-05-01",
        qs=[
            "Is it safe to decommission the old domain controller?",
            "What still depends on HCU-DC01?",
            "What system syncs the door badges?",
            "Can we turn off DC01 now that Okta is in place?",
        ],
    ),
    FactSpec(
        key="iam.krbtgt_rotation", kind=K.FACT, area="identity_access", importance=2, in_corpus=False,
        statement="The AD krbtgt account password has not been rotated since 2019.",
        kw=[["2019"]], known_by=["mike"], stated_by="mike", valid_from="2019-03-01",
        qs=[
            "When was the krbtgt password last rotated?",
            "Is our AD Kerberos hygiene up to date?",
            "Has anyone reset the krbtgt account recently?",
        ],
    ),
    FactSpec(
        key="iam.breakglass_key", kind=K.ACCESS, area="identity_access", importance=3, in_corpus=False,
        statement="The YubiKey for the break-glass Okta admin account is kept in the safe at the Spring Garden "
                  "branch.",
        kw=[["Spring Garden"]], known_by=["nadia", "mike"], stated_by="nadia", valid_from="2024-09-01",
        qs=[
            "Where is the hardware key for the emergency Okta admin account?",
            "If both Okta super-admins are unavailable, how do we get in?",
            "Where's the break-glass account's YubiKey kept?",
        ],
    ),
    FactSpec(
        key="iam.hcu_admin_backdoor", kind=K.ACCESS, area="identity_access", importance=3, private=True,
        statement="The old 'hcu-admin' domain admin account is still enabled because the phone-system vendor uses "
                  "it; Mike meant to disable it after the PBX swap.",
        kw=[["hcu-admin"]], known_by=["mike"], stated_by="mike", valid_from="2026-04-02",
        say=[
            "fyi hcu-admin is still enabled. the phone system vendor uses it for remote support. I was going to kill "
            "it after the PBX swap, don't let me forget",
            "don't panic if you see hcu-admin logging in, that's the PBX vendor. yes I know. it's on my list",
            "that hcu-admin account -- leave it for now, the phone vendor still needs it. we disable it after the "
            "PBX replacement",
        ],
        qs=[
            "Are there any old domain admin accounts still enabled?",
            "Why is the hcu-admin account still active?",
            "Who uses the hcu-admin login?",
        ],
        where=["dm"], askers=["nadia"],
    ),
]

FACTS: list[FactSpec] = [*ACH, *PORTAL, *IAM]

"""Harbourline ground truth: payroll, backups & DR, FINTRAC reporting, debit card processing.

Knowledge shape (drives the risk map): payroll is Priya alone; backups/DR is Mike (part-time, older knowledge) with
Nadia partially covering; FINTRAC is Tom alone (retiring 2026-12-18); card processing is shared by Jen and Priya.
"""

from __future__ import annotations

from keepline.data.spec import FactSpec, K

PAYROLL: list[FactSpec] = [
    FactSpec(
        key="payroll.owner", kind=K.OWNER, area="payroll", importance=3,
        statement="Priya Nair runs payroll end to end; Dave only approves the pay run in Paylane.",
        kw=[["Priya"]], known_by=["priya", "dave"], stated_by="dave", valid_from="2019-01-07",
        say=[
            "Payroll is all Priya. I just click approve in Paylane when she tells me it's ready.",
            "Anything pay related goes to Priya, she runs the whole thing start to finish.",
            "Priya owns payroll here. I'm only the approver, I couldn't run a pay cycle if you paid me (ha).",
            "for payroll questions ping Priya directly, she's the only one who actually knows how it works",
        ],
        prompts=["who do I talk to about a pay stub question?", "is payroll you or finance, Dave?"],
        qs=["Who handles payroll at Harbourline?", "Who should I ask if my pay stub looks wrong?",
            "Who runs the pay cycle every two weeks?", "Which person owns the payroll process?",
            "If there's a problem with a pay run, who do I go to?"],
        where=["#general", "#finance", "email"], askers=["jen", "colin", "nadia"],
    ),
    FactSpec(
        key="payroll.pay_schedule", kind=K.FACT, area="payroll", importance=1,
        statement="Staff are paid bi-weekly, every second Friday, by direct deposit.",
        kw=[["every second Friday", "every other Friday", "bi-weekly", "biweekly", "every two weeks"]],
        known_by=["priya", "dave"], stated_by="priya", valid_from="2017-03-06",
        say=[
            "We pay every second Friday, so the next one's the 24th.",
            "Pay is bi-weekly on Fridays, it shows up first thing in the morning usually.",
            "Reminder for the new folks: payday is every other Friday.",
            "it's biweekly, Fridays. if Friday's a stat holiday it lands the Thursday before",
        ],
        prompts=["when's payday again?"],
        qs=["How often do we get paid?", "What day of the week does pay land?",
            "Is pay weekly, bi-weekly, or monthly here?", "When do paycheques come in?"],
        where=["#general", "#finance"], askers=["colin", "nadia", "aisha"],
    ),
    FactSpec(
        key="payroll.bankfile_cutoff", kind=K.LANDMINE, area="payroll", importance=3, landmine=True,
        statement="Never upload the payroll bank file after 3pm Wednesday; the bank rolls it to the next "
                  "processing day and Friday pay lands late (Monday).",
        kw=[["3pm", "3 pm", "3:00", "15:00", "three"], ["Wednesday", "Wed"]],
        known_by=["priya"], stated_by="priya", valid_from="2021-09-01",
        notes="Learned the hard way in 2021 when pay landed on a Monday.",
        say=[
            "The bank file has to be up before 3pm Wednesday. If it goes in after that it rolls to the next "
            "day and everyone's pay lands Monday instead of Friday. Ask me how I know.",
            "Hard rule: never send the payroll bank file after 3 pm on Wed. Late file = late pay, no exceptions "
            "from the bank.",
            "Wednesday 3pm is the wall for the payroll file. Miss it and the whole staff gets paid late.",
            "just so it's written down somewhere: if the bank file isn't uploaded by three o'clock Wednesday, "
            "pay slips to Monday. Happened once in 2021 and I'm still hearing about it",
        ],
        prompts=["is there a deadline for the bank file or can it go whenever?",
                 "if I ever had to cover payroll, what's the one thing I can't mess up?"],
        qs=["Is there a deadline for uploading the payroll bank file?",
            "What happens if the payroll file goes to the bank late on Wednesday?",
            "Anything I should never do when covering payroll?",
            "What's the latest I can send the payroll deposit file and still have people paid Friday?",
            "Is there a gotcha with the timing of the payroll bank upload?",
            "Why would staff get paid on a Monday instead of Friday?"],
        where=["#finance", "email", "doc"], askers=["dave"],
    ),
    FactSpec(
        key="payroll.timesheets.v1", kind=K.RECURRING_TASK, area="payroll", importance=2,
        statement="Timesheets must be approved in Paylane by Monday 10am of pay week.",
        kw=[["Monday"], ["10am", "10 am", "10:00", "ten"]],
        known_by=["priya"], stated_by="priya", valid_from="2022-01-10", valid_to="2026-05-04",
        say=[
            "Managers: timesheets need to be approved in Paylane by Monday 10am of pay week please!",
            "Friendly reminder, Monday at 10:00 is the timesheet cutoff for this pay.",
            "Timesheet approvals close Monday 10 am, anything after that goes on the next run.",
        ],
        where=["#general", "email"],
    ),
    FactSpec(
        key="payroll.timesheets.v2", kind=K.RECURRING_TASK, area="payroll", importance=2,
        supersedes="payroll.timesheets.v1",
        statement="Since May 2026, timesheets must be approved in Paylane by 4pm on the Friday before pay week "
                  "(Paylane moved its processing earlier).",
        kw=[["Friday"], ["4pm", "4 pm", "4:00", "16:00", "four"]],
        known_by=["priya"], stated_by="priya", valid_from="2026-05-04",
        forbid=[["Monday 10", "Monday at 10", "Monday morning"]],
        say=[
            "Heads up all: Paylane moved their processing up, so timesheet approvals are now due Friday by 4pm "
            "the week before pay week.",
            "New cutoff for timesheets is Friday 4 pm (the Friday before pay week). Paylane changed on us.",
            "Timesheets have to be approved by four o'clock Friday now, not the old cutoff. Please don't leave "
            "it to the last minute.",
            "reminder: approvals close Friday at 4:00 before pay week. anything later waits for the next cycle",
        ],
        prompts=["did the timesheet deadline change? I got a weird email from Paylane"],
        qs=["When are timesheets due for approval?", "What's the current timesheet cutoff for payroll?",
            "By when do managers have to approve timesheets in Paylane?",
            "If I approve my team's hours on the Monday of pay week, is that too late?",
            "What's the deadline for getting hours into the pay run these days?",
            "Did the timesheet approval deadline move? What is it now?"],
        where=["#general", "email", "#finance"], askers=["jen", "dave"],
    ),
    FactSpec(
        key="payroll.cra_remittance", kind=K.RECURRING_TASK, area="payroll", importance=3,
        statement="CRA payroll source deductions are remitted by the 15th of the following month.",
        kw=[["15th", "fifteenth"]], known_by=["priya"], stated_by="priya", valid_from="2017-03-06",
        say=[
            "CRA remittance for source deductions goes by the 15th of the next month. I set a reminder for the "
            "12th so there's slack.",
            "Source deductions have to be remitted to CRA by the fifteenth of the following month or we eat a "
            "penalty.",
            "Just did the CRA remittance for last month, due the 15th as always.",
            "the deductions remittance is monthly, due the 15th. late = 10% penalty, not fun",
        ],
        prompts=["what's the monthly CRA thing you're always doing mid-month?"],
        qs=["When is the CRA payroll remittance due?", "How often do we remit source deductions and by when?",
            "What's the monthly deadline for sending payroll deductions to CRA?",
            "Is there a recurring CRA payment I need to know about for payroll?"],
        where=["#finance", "email"], askers=["dave", "marc"],
    ),
    FactSpec(
        key="payroll.t4", kind=K.RECURRING_TASK, area="payroll", importance=2,
        statement="T4 slips must be filed with CRA and given to staff by the end of February each year.",
        kw=[["end of February", "end of Feb", "February 28", "Feb 28", "last day of February"]],
        known_by=["priya"], stated_by="priya", valid_from="2017-03-06",
        say=[
            "T4s have to be filed and out to everyone by the end of February. I'll start the year-end in January.",
            "Reminder that T4 slips are due to CRA and staff by Feb 28, so get address changes to me early.",
            "Year-end is the big one: T4s filed and distributed by end of Feb, every year.",
        ],
        qs=["When do T4s need to be issued?", "What's the deadline for T4 slips each year?",
            "When does year-end payroll filing have to be done?", "By when do staff get their T4?"],
        where=["#finance", "#general", "email"], askers=["dave", "colin"],
    ),
    FactSpec(
        key="payroll.paylane_contact", kind=K.VENDOR_CONTACT, area="payroll", importance=2,
        statement="Our Paylane account manager is Gail Fitzgerald (gail.fitzgerald@paylane.ca, 902-555-0148).",
        kw=[["Gail"]], known_by=["priya"], stated_by="priya", valid_from="2022-02-01",
        say=[
            "Our Paylane rep is Gail Fitzgerald, gail.fitzgerald@paylane.ca, 902-555-0148. She's great, "
            "usually answers same day.",
            "If Paylane is acting up, call Gail at 902-555-0148. Don't bother with their general support line.",
            "Gail Fitzgerald is our account manager at Paylane, cc me if you email her.",
        ],
        prompts=["who's our contact at Paylane if the system goes down?"],
        qs=["Who is our contact at Paylane?", "If the payroll system is down, who do we call at the vendor?",
            "Who's the account manager for our payroll provider?",
            "Do we have a named rep at Paylane? How do I reach them?"],
        where=["#finance", "email"], askers=["dave"],
    ),
    FactSpec(
        key="payroll.paylane_access", kind=K.ACCESS, area="payroll", importance=3,
        statement="The Paylane admin credentials are kept in the Finance vault in 1Password; Priya is the only "
                  "admin, Dave has approver access only.",
        kw=[["Finance"], ["1Password"]], known_by=["priya"], stated_by="priya", valid_from="2022-02-01",
        say=[
            "The Paylane admin login lives in the Finance vault in 1Password. Only me and Dave can see that vault.",
            "Admin creds for Paylane are in 1Password under Finance. Dave's account is approver-only though.",
            "If I get hit by a bus: Paylane admin is in 1Password, Finance vault. Please don't actually need it.",
        ],
        prompts=["where are the Paylane admin creds kept in case you're off sick?"],
        qs=["Where are the Paylane admin credentials stored?", "How would someone log into Paylane as admin if "
            "Priya is away?", "Which password vault has the payroll system login?",
            "Who has admin access to Paylane?"],
        where=["#finance", "email"], askers=["dave"],
    ),
    FactSpec(
        key="payroll.private_token", kind=K.ACCESS, area="payroll", importance=3, private=True,
        statement="The backup payroll approver hardware token is kept in the safe in Marc's office.",
        kw=[["safe"], ["Marc"]], known_by=["priya", "dave"], stated_by="priya", valid_from="2024-01-15",
        say=[
            "btw the backup approver token for Paylane is in the safe in Marc's office, in case I'm ever out "
            "on a pay week",
            "Just so you know, the spare approval token is locked in Marc's safe. Envelope says Paylane.",
            "if you ever need to approve pay without me, the backup token is in the safe in Marc's office",
        ],
        qs=["Where is the backup payroll approval token kept?",
            "If Priya is away on pay week, how does someone approve the run without her token?",
            "Is there a spare Paylane approver token somewhere?"],
        where=["dm"], askers=["dave"],
    ),
    FactSpec(
        key="payroll.direct_deposit_only", kind=K.DECISION, area="payroll", importance=1,
        statement="As of May 2026 paper pay cheques were discontinued; all staff are paid by direct deposit.",
        kw=[["direct deposit"]], known_by=["priya", "dave"], stated_by="priya", valid_from="2026-05-01",
        say=[
            "Starting May 1 we're direct deposit only, no more paper cheques. Get me your banking form if you "
            "haven't already!",
            "Dave and I signed off on it: paper pay cheques are done, everyone's on direct deposit from May.",
            "We've officially gone direct deposit only for pay. If you were still getting a cheque, come see me.",
        ],
        prompts=["do we still do paper pay cheques for anyone?"],
        qs=["Can I still get my pay as a paper cheque?", "Does Harbourline issue paper pay cheques?",
            "How is staff pay delivered now?", "When did we stop printing pay cheques?"],
        where=["#general", "email"], askers=["colin", "jen"],
    ),
    FactSpec(
        key="payroll.new_hire_forms", kind=K.PROCEDURE, area="payroll", importance=2,
        statement="To add a new hire to payroll, Priya needs signed federal and Nova Scotia TD1 forms and a "
                  "direct deposit form at least 5 business days before their first pay.",
        kw=[["TD1"]], known_by=["priya"], stated_by="priya", valid_from="2020-01-01",
        say=[
            "For new hires I need the TD1 (federal and NS) plus a direct deposit form, at least five business "
            "days before their first pay.",
            "Dave, for Alex's onboarding: send me his signed TD1 forms and banking info a week before his first "
            "payday or he'll miss a cycle.",
            "New starter checklist from my side: TD1 federal, TD1NS provincial, void cheque or deposit form.",
        ],
        prompts=["what does finance need from a new hire to get them paid?"],
        qs=["What paperwork does payroll need for a new hire?", "How do I get set up to be paid as a new "
            "employee?", "Which tax forms does Priya need before someone's first pay?",
            "What's the process to add someone to payroll?"],
        where=["email", "#finance", "doc"], askers=["dave", "jen"],
    ),
    FactSpec(
        key="payroll.nic_retro", kind=K.PROCEDURE, area="payroll", importance=2, in_corpus=False,
        statement="Retroactive pay adjustments must be entered as a separate off-cycle run in Paylane; entering "
                  "them in a regular run double-counts vacation accrual.",
        kw=[["off-cycle", "off cycle", "separate run"]], known_by=["priya"], stated_by="priya",
        valid_from="2023-04-01", notes="Priya's tribal knowledge; never written down.",
        qs=["How do I process a retroactive pay adjustment in Paylane?",
            "Can retro pay go in a regular pay run?", "Is there a trick to doing back pay in the payroll system?"],
    ),
    FactSpec(
        key="payroll.nic_clearing_gl", kind=K.FACT, area="payroll", importance=2, in_corpus=False,
        statement="The payroll clearing GL account is 2150 and Priya reconciles it by hand after every pay run.",
        kw=[["2150"]], known_by=["priya"], stated_by="priya", valid_from="2019-01-01",
        qs=["Which GL account does payroll clear through?", "Who reconciles the payroll clearing account and how?",
            "What's the general ledger account number for payroll clearing?"],
    ),
]

BACKUPS: list[FactSpec] = [
    FactSpec(
        key="backup.owner", kind=K.OWNER, area="backups_dr", importance=3,
        statement="Mike O'Brien owns backups and disaster recovery; Nadia covers day-to-day alerts.",
        kw=[["Mike"]], known_by=["mike", "nadia", "dave"], stated_by="dave", valid_from="2009-02-02",
        say=[
            "Backups and DR are Mike's. Nadia can look at alerts but anything deeper goes to him.",
            "For restores, ask Mike. He built the whole backup setup years ago.",
            "Mike owns backups & DR. He's part-time now so be patient, Nadia's the first stop for alerts.",
        ],
        prompts=["who do I ask about getting a file restored from backup?"],
        qs=["Who is responsible for backups?", "Who should I ask about disaster recovery?",
            "Who handles restores from backup here?", "Who owns the DR plan?",
            "If a backup job fails, who deals with it?"],
        where=["#it-help", "#ops"], askers=["jen", "sarah", "aisha"],
    ),
    FactSpec(
        key="backup.restore_primary", kind=K.LANDMINE, area="backups_dr", importance=3, landmine=True,
        statement="Never restore a backup onto the replication primary (the NAS/SQL primary): replication copies "
                  "the restore over the DR copy. Always restore to the isolated restore host (HCU-RESTORE01) first.",
        kw=[["primary"], ["restore host", "HCU-RESTORE01", "restore box", "isolated"]],
        known_by=["mike", "nadia"], stated_by="mike", valid_from="2022-11-01",
        notes="Landmine #4. Mike learned this in a 2022 near-miss; restored straight to primary and the DR copy "
              "was overwritten within minutes.",
        say=[
            "Never, ever restore onto the primary. Replication will happily copy your restore straight over the "
            "DR side and then you've got no good copy anywhere. Restore to HCU-RESTORE01 first, check it, then "
            "move what you need.",
            "Rule #1 for restores: target the isolated restore host, not the replication primary. I nearly lost "
            "the DR copy doing exactly that in 2022.",
            "If you restore to the primary the replication job overwrites the DR copy with whatever you just "
            "restored. Always use the restore box (HCU-RESTORE01).",
            "Nadia, one thing before you do restores on your own: restore host only. The primary replicates "
            "everything to DR within minutes, so a bad restore there is a bad restore everywhere.",
        ],
        prompts=["can I just restore the file share straight back to where it was?",
                 "anything I should know before doing a restore myself?"],
        qs=["Is there anything dangerous about restoring backups I should know?",
            "Can I restore a backup directly onto the primary server?",
            "Where should restores be done?",
            "What's the one mistake to avoid when restoring from Veeam?",
            "Why shouldn't you restore straight to the NAS primary?",
            "Any landmines with the backup and replication setup?",
            "What happens to the DR copy if you restore onto the replicating server?"],
        where=["#it-help", "#ops", "ticket", "doc"], askers=["nadia", "sarah"],
    ),
    FactSpec(
        key="backup.retention.v1", kind=K.FACT, area="backups_dr", importance=2,
        statement="Nightly backups are retained for 30 days.",
        kw=[["30 days", "30-day", "thirty days", "30 day"]], known_by=["mike", "nadia"], stated_by="mike",
        valid_from="2023-03-01", valid_to="2026-05-11",
        say=[
            "We keep nightly backups 30 days, so anything deleted in the last month we can get back.",
            "Retention's 30 days on the nightly jobs. Older than that and it's gone unless it's on an offsite copy.",
            "The Veeam jobs are set to a 30-day retention.",
        ],
        where=["#it-help", "#ops"],
    ),
    FactSpec(
        key="backup.retention.v2", kind=K.DECISION, area="backups_dr", importance=3,
        supersedes="backup.retention.v1",
        statement="Since 2026-05-11 nightly backups are retained for 14 days (cut to save NAS storage).",
        kw=[["14 days", "14-day", "fourteen", "two weeks", "14 day"]], known_by=["mike", "nadia", "dave"],
        stated_by="mike", valid_from="2026-05-11",
        forbid=[["30 days", "30-day", "thirty"]],
        contra=[("nadia", "pretty sure we still keep the nightlies for a full month?")],
        notes="Conflict: in a later thread Nadia states the old month-long retention; Mike corrects her.",
        say=[
            "Dropped retention on the nightly jobs to 14 days as of today. NAS was at 91% and Dave didn't want "
            "to buy another shelf.",
            "Nope, it's two weeks now. We cut it back in May to save space.",
            "FYI retention is 14 days now, down from a month. If someone wants something older than that it "
            "has to come from the offsite copy.",
            "Nightly backups only go back fourteen days these days. Tell people to shout early if they delete "
            "something.",
        ],
        prompts=["how far back can we restore a deleted file?", "someone deleted a folder 3 weeks ago, can we get "
                                                                  "it back?"],
        qs=["How long are nightly backups kept?", "What's our backup retention period?",
            "How far back can I get a deleted file restored?",
            "Someone deleted a spreadsheet three weeks ago - can we still restore it from the nightly backups?",
            "Did backup retention change this year? What is it now?",
            "How many days of nightly backups do we keep on the NAS?"],
        where=["#it-help", "#ops", "email"], askers=["nadia", "jen", "dave"],
    ),
    FactSpec(
        key="backup.offsite_day.v1", kind=K.RECURRING_TASK, area="backups_dr", importance=2,
        statement="The offsite backup copy is rotated out with the courier every Friday.",
        kw=[["Friday"]], known_by=["mike"], stated_by="mike", valid_from="2021-06-01", valid_to="2026-04-20",
        say=[
            "Offsite drive goes out with the courier Friday mornings, swap the one in the bay before 10.",
            "Friday is offsite rotation day, the courier comes around 10.",
            "Don't forget the offsite swap Friday, I won't be in till noon.",
        ],
        where=["#ops", "#it-help"],
    ),
    FactSpec(
        key="backup.offsite_day.v2", kind=K.RECURRING_TASK, area="backups_dr", importance=2,
        supersedes="backup.offsite_day.v1",
        statement="Since 2026-04-20 the offsite backup copy is rotated with the courier every Thursday.",
        kw=[["Thursday"]], known_by=["mike", "nadia"], stated_by="mike", valid_from="2026-04-20",
        forbid=[["Friday"]],
        say=[
            "Courier changed their route, so offsite rotation moves to Thursdays starting this week.",
            "Offsite swap is Thursdays now. Nadia can you do it when I'm not in?",
            "Reminder the offsite drive goes out Thursday morning now, not the old day.",
        ],
        prompts=["what day does the offsite backup drive go out now?"],
        qs=["What day is the offsite backup rotated?", "When does the courier pick up the offsite backup drive?",
            "Which day of the week do we swap the offsite copy?",
            "Did the offsite backup rotation day change? What is it now?",
            "If Mike isn't in, what day do I need to do the offsite drive swap?"],
        where=["#ops", "#it-help"], askers=["nadia"],
    ),
    FactSpec(
        key="backup.weekend_oncall.v1", kind=K.RECURRING_TASK, area="backups_dr", importance=2,
        statement="Mike takes all weekend backup failure alerts.",
        kw=[["Mike"], ["weekend"]], known_by=["mike", "nadia"], stated_by="mike",
        valid_from="2019-01-01", valid_to="2026-06-01",
        say=[
            "Weekend backup alerts come to me (Mike), always have. Don't worry about them Nadia.",
            "Mike here, I get paged for any weekend backup failures, so nobody else needs to watch the inbox on Saturday.",
            "Weekend alerts for the backup jobs go to my phone (Mike). Fine for now.",
        ],
        where=["#ops", "#it-help"],
    ),
    FactSpec(
        key="backup.weekend_oncall.v2", kind=K.RECURRING_TASK, area="backups_dr", importance=2,
        supersedes="backup.weekend_oncall.v1",
        statement="Since June 2026, Nadia and Mike alternate weekends for backup failure alerts.",
        kw=[["alternate", "every other", "alternating", "turns"], ["Nadia"]],
        known_by=["nadia", "mike"], stated_by="nadia", valid_from="2026-06-01",
        say=[
            "New weekend setup for backup alerts: Nadia and Mike alternate weekends starting June. Schedule is "
            "pinned in #ops.",
            "Mike's cutting back hours so we're taking turns on weekend backup alerts, Nadia (me) has every other "
            "weekend.",
            "Weekend pages for backups now alternate between Nadia and Mike. If it's my weekend, text me.",
        ],
        prompts=["who's getting the weekend backup pages now that Mike's part-time?"],
        qs=["Who responds to backup failure alerts on weekends?",
            "Who is on call for backups on the weekend now?",
            "If a backup fails on a Saturday, who gets paged?",
            "Did the weekend backup on-call change? How does it work now?",
            "Is Mike still the only one taking weekend backup alerts?"],
        where=["#ops", "#it-help"], askers=["dave", "sarah"],
    ),
    FactSpec(
        key="backup.restore_test", kind=K.RECURRING_TASK, area="backups_dr", importance=2,
        statement="A test restore is done on the first Tuesday of every month and logged in a ticket.",
        kw=[["first Tuesday", "1st Tuesday"]], known_by=["mike", "nadia"], stated_by="mike",
        valid_from="2020-01-01",
        say=[
            "Monthly restore test is the first Tuesday, I log it in a ticket so the auditors are happy.",
            "First Tuesday of the month = restore test. Pick a random file, restore it to the restore host, "
            "screenshot, close the ticket.",
            "Did the restore test today since it's the first Tuesday. All good.",
        ],
        prompts=["do we ever actually test the backups?"],
        qs=["How often do we test restoring from backup?", "When is the monthly restore test done?",
            "Is there a recurring backup test I need to do?", "What day of the month do we test backups?"],
        where=["#ops", "ticket"], askers=["nadia", "dave"],
    ),
    FactSpec(
        key="backup.veeam_access", kind=K.ACCESS, area="backups_dr", importance=3,
        statement="Veeam console admins are Mike and Nadia; the credentials are in the Infrastructure vault in "
                  "1Password.",
        kw=[["Infrastructure"], ["1Password"]], known_by=["mike", "nadia"], stated_by="mike",
        valid_from="2023-01-09",
        say=[
            "Veeam admin login is in 1Password, Infrastructure vault. Nadia's got access now too.",
            "Creds for the backup console live in the Infrastructure vault in 1Password.",
            "Nadia I added you to the 1Password Infrastructure vault, the Veeam login is in there.",
        ],
        prompts=["where's the login for the Veeam console?"],
        qs=["Where are the Veeam admin credentials kept?", "Who has admin access to the backup console?",
            "How do I log in to Veeam?", "Which vault has the backup system password?"],
        where=["#it-help", "#ops"], askers=["nadia"],
    ),
    FactSpec(
        key="backup.window", kind=K.FACT, area="backups_dr", importance=1,
        statement="The nightly backup job starts at 11pm and usually finishes around 3am.",
        kw=[["11pm", "11 pm", "11:00 pm", "23:00", "eleven"]], known_by=["mike", "nadia"], stated_by="mike",
        valid_from="2018-01-01",
        say=[
            "Nightly backup kicks off at 11pm, done by 3 usually.",
            "Backups run from 23:00, so don't schedule patching before 3am.",
            "The job starts at eleven at night. If the file server's slow late evening, that's why.",
        ],
        prompts=["what time do the backups run? file server was crawling last night"],
        qs=["What time does the nightly backup run?", "When is the backup window?",
            "Why is the file server slow late at night?", "When can I schedule maintenance without clashing with "
            "backups?"],
        where=["#it-help", "#ops"], askers=["sarah", "jen"],
    ),
    FactSpec(
        key="backup.dr_site", kind=K.FACT, area="backups_dr", importance=2,
        statement="The DR replica is at the colocation site in Moncton, replicated nightly.",
        kw=[["Moncton"]], known_by=["mike", "nadia", "dave"], stated_by="mike", valid_from="2019-05-01",
        say=[
            "DR copy replicates nightly to the colo in Moncton.",
            "Our disaster recovery site is the Moncton colocation, that's where the replica lives.",
            "If Halifax goes dark we fail over to Moncton. That's the whole DR story in one line.",
        ],
        prompts=["where's our DR site actually?"],
        qs=["Where is our disaster recovery site?", "Where do backups replicate to?",
            "If the Halifax office goes down, where do we fail over?", "Where is the DR replica hosted?"],
        where=["#ops", "doc"], askers=["dave", "sarah"],
    ),
    FactSpec(
        key="backup.immutable", kind=K.DECISION, area="backups_dr", importance=2,
        statement="In April 2026 Mike and Dave decided to move backups to an immutable (hardened) Veeam "
                  "repository after a phishing/ransomware scare.",
        kw=[["immutable", "hardened"]], known_by=["mike", "dave"], stated_by="mike", valid_from="2026-04-14",
        say=[
            "After last week's phishing scare Dave approved moving to a hardened repository, backups will be "
            "immutable for the retention period.",
            "We're switching the Veeam target to immutable storage. Ransomware can't encrypt what it can't "
            "modify.",
            "Decision from today's chat with Dave: immutable backups, hardened Linux repo. I'll do it over the "
            "next two weeks.",
        ],
        prompts=["are our backups safe from ransomware?"],
        qs=["Are our backups protected against ransomware?", "What did we decide about backup immutability?",
            "Why did we change the backup repository in April?", "Can an attacker delete our backups?"],
        where=["#ops", "email"], askers=["dave", "marc"],
    ),
    FactSpec(
        key="backup.private_envelope", kind=K.ACCESS, area="backups_dr", importance=3, private=True,
        statement="The Veeam break-glass local admin password is in a sealed envelope in the server room safe.",
        kw=[["envelope"], ["safe"]], known_by=["mike", "nadia"], stated_by="mike", valid_from="2021-03-01",
        say=[
            "one more thing, if 1Password is ever down, the Veeam break-glass admin is in a sealed envelope in "
            "the server room safe",
            "keep this between us: break-glass creds for Veeam are in the envelope in the server room safe",
            "if everything's on fire and you can't get into the vault: sealed envelope, server room safe",
        ],
        qs=["What's the break-glass access for Veeam if 1Password is unavailable?",
            "Is there an emergency way into the backup console?",
            "Where are the emergency backup admin credentials kept?"],
        where=["dm"], askers=["nadia"],
    ),
    FactSpec(
        key="backup.nic_tapes", kind=K.FACT, area="backups_dr", importance=2, in_corpus=False,
        statement="The offsite backup drives are stored at Bedford Secure Storage, unit 14.",
        kw=[["Bedford"]], known_by=["mike"], stated_by="mike", valid_from="2016-01-01",
        notes="Only Mike knows the storage location.",
        qs=["Where are the offsite backup drives actually stored?",
            "Which storage company holds our offsite backups?",
            "If I need an offsite drive back, where do I go?"],
    ),
    FactSpec(
        key="backup.nic_window_reason", kind=K.DECISION, area="backups_dr", importance=1, in_corpus=False,
        statement="The backup window starts at 11pm because the branch cash recycler sync to the file server "
                  "finishes around 10:30pm.",
        kw=[["recycler"]], known_by=["mike"], stated_by="mike", valid_from="2018-01-01",
        qs=["Why do backups start at 11pm and not earlier?",
            "Could we move the backup window to 9pm?",
            "What would break if the nightly backup started earlier?"],
    ),
    FactSpec(
        key="backup.nic_dr_contact", kind=K.VENDOR_CONTACT, area="backups_dr", importance=2, in_corpus=False,
        statement="Our contact at the Moncton colocation site is Rick Gallant.",
        kw=[["Rick", "Gallant"]], known_by=["mike"], stated_by="mike", valid_from="2019-05-01",
        qs=["Who is our contact at the DR colocation site?",
            "If we need hands-on help at the Moncton colo, who do we call?",
            "Who's the vendor contact for our disaster recovery site?"],
    ),
    FactSpec(
        key="backup.nic_dr_test", kind=K.FACT, area="backups_dr", importance=3, in_corpus=False,
        statement="The last full DR failover test was in November 2024, and the DNS cutover step is manual.",
        kw=[["November 2024", "Nov 2024"]], known_by=["mike"], stated_by="mike", valid_from="2024-11-16",
        qs=["When did we last do a full disaster recovery failover test?",
            "Has the DR plan ever been tested end to end?",
            "Is the DR failover fully automated?"],
    ),
]

FINTRAC: list[FactSpec] = [
    FactSpec(
        key="fintrac.owner", kind=K.OWNER, area="fintrac_reporting", importance=3,
        statement="Tom Bouchard handles all FINTRAC reporting (LCTR, STR, EFTR) and the AML program.",
        kw=[["Tom"]], known_by=["tom", "dave", "jen"], stated_by="dave", valid_from="2004-05-17",
        say=[
            "All FINTRAC reporting goes through Tom. Don't file anything yourself.",
            "Tom's our compliance officer, LCTRs, STRs, the whole AML program, it's all him.",
            "If it smells like AML or FINTRAC, send it to Tom.",
        ],
        prompts=["who handles the FINTRAC reports?"],
        qs=["Who handles FINTRAC reporting?", "Who do I send a large cash transaction report to?",
            "Who's the compliance officer?", "Who owns AML reporting at Harbourline?",
            "Who should I talk to about a suspicious transaction?"],
        where=["#compliance", "#member-services", "#general"], askers=["jen", "colin"],
    ),
    FactSpec(
        key="fintrac.lctr_deadline", kind=K.RECURRING_TASK, area="fintrac_reporting", importance=3,
        statement="Large cash transaction reports (LCTRs) must be filed within 15 calendar days of the transaction.",
        kw=[["15", "fifteen"]], known_by=["tom"], stated_by="tom", valid_from="2020-06-01",
        contra=[("colin", "I thought we had 30 days to file those large cash reports?")],
        notes="Conflict: Colin states a 30-day window; Tom corrects to 15 calendar days.",
        say=[
            "No, LCTRs are due within 15 calendar days of the transaction. Calendar, not business.",
            "We have fifteen calendar days from the transaction to get the LCTR in. I aim for a week.",
            "Reminder: 15 days from the date of the cash transaction for LCTRs. Get me the slips same day please.",
        ],
        prompts=["how long do we have to file an LCTR?"],
        qs=["How long do we have to file a large cash transaction report?",
            "What's the LCTR filing deadline?", "Is the LCTR deadline business days or calendar days?",
            "How many days after a big cash deposit does FINTRAC need the report?"],
        where=["#compliance", "#member-services", "email"], askers=["jen", "colin"],
    ),
    FactSpec(
        key="fintrac.lctr_threshold", kind=K.FACT, area="fintrac_reporting", importance=2,
        statement="Cash transactions of $10,000 or more, in one transaction or several within 24 hours for the "
                  "same member, require an LCTR.",
        kw=[["10,000", "10000", "10k", "ten thousand"], ["24"]], known_by=["tom", "jen"], stated_by="jen",
        valid_from="2020-06-01",
        say=[
            "Team: anything $10,000 or more in cash, or a few deposits adding up to that within 24 hours, gets "
            "an LCTR slip to Tom.",
            "Remember the 24-hour rule, two $6k cash deposits the same day still counts as over 10k.",
            "Cash of ten thousand or more (single or combined over 24 hours) = large cash report. When in doubt "
            "fill the slip.",
        ],
        prompts=["member just deposited $7k cash and came back after lunch with $4k more, do I need to do "
                 "anything?"],
        qs=["What's the threshold for a large cash transaction report?",
            "Do two cash deposits on the same day count together for FINTRAC?",
            "At what amount do we have to report cash to FINTRAC?",
            "A member deposited $6,000 cash twice in one day - is that reportable?"],
        where=["#member-services", "#compliance"], askers=["colin"],
    ),
    FactSpec(
        key="fintrac.duplicate_lctr", kind=K.LANDMINE, area="fintrac_reporting", importance=2, landmine=True,
        statement="Never submit the LCTR batch twice: FINTRAC can't delete duplicates, each one has to be "
                  "corrected individually.",
        kw=[["twice", "duplicate", "double", "again"],
            ["delete", "deleted", "one by one", "one at a time", "individually"]],
        known_by=["tom"], stated_by="tom", valid_from="2019-02-01",
        say=[
            "Please never resubmit an LCTR batch 'just in case'. FINTRAC can't delete duplicates, I have to "
            "correct each one individually. Took me two days last time.",
            "If a submission looks like it failed, check with me before sending it again. Duplicates can't be "
            "deleted, only fixed one by one.",
            "Golden rule with the reporting system: don't double submit. There is no delete button.",
        ],
        prompts=["the LCTR upload timed out, should I just hit submit again?"],
        qs=["What should I do if an LCTR submission seems to have failed?",
            "Can duplicate FINTRAC reports be deleted?",
            "Anything to watch out for when submitting LCTRs?",
            "Is it safe to resubmit a FINTRAC batch if I'm not sure it went through?",
            "What's the worst mistake you can make with FINTRAC submissions?",
            "Are there any landmines in the large cash reporting process?"],
        where=["#compliance", "email", "doc"], askers=["jen", "dave"],
    ),
    FactSpec(
        key="fintrac.filing.v1", kind=K.PROCEDURE, area="fintrac_reporting", importance=2,
        statement="LCTRs are keyed in manually through FINTRAC's Web Reporting System (FWR).",
        kw=[["Web Reporting", "FWR", "web form"]], known_by=["tom"], stated_by="tom",
        valid_from="2019-06-01", valid_to="2026-07-06",
        say=[
            "I key the LCTRs into FINTRAC's Web Reporting System by hand every Thursday.",
            "It's all FWR, manual entry. Tedious but it works.",
            "Filed this week's cash reports through the FINTRAC web form.",
        ],
        where=["#compliance", "email"],
    ),
    FactSpec(
        key="fintrac.filing.v2", kind=K.DECISION, area="fintrac_reporting", importance=3,
        supersedes="fintrac.filing.v1",
        statement="Since 2026-07-06 LCTRs are submitted through FINTRAC's API report submission from the AML "
                  "monitor instead of manual entry.",
        kw=[["API"]], known_by=["tom"], stated_by="tom", valid_from="2026-07-06",
        forbid=[["Web Reporting", "FWR"]],
        say=[
            "As of this week LCTRs go through the FINTRAC API straight out of the AML monitor. No more retyping.",
            "We're live on API report submission. I review the batch in the AML monitor and it submits.",
            "Big one for me: the reporting is API-based now, the monitor builds the report and pushes it.",
        ],
        prompts=["how are you filing the LCTRs now, still typing them in?"],
        qs=["How are LCTRs submitted to FINTRAC now?", "Do we still key large cash reports in by hand?",
            "What system do we use to file FINTRAC reports these days?",
            "Did the FINTRAC filing process change this summer?",
            "If Tom is away, how does a large cash report actually get sent to FINTRAC?",
            "What's the current method for LCTR submission?"],
        where=["#compliance", "email"], askers=["dave", "jen"],
    ),
    FactSpec(
        key="fintrac.utr", kind=K.PROCEDURE, area="fintrac_reporting", importance=3,
        statement="Branch staff who see something suspicious fill out an internal Unusual Transaction Report (UTR) "
                  "for Tom and never tell the member.",
        kw=[["UTR", "unusual transaction report"]], known_by=["tom", "jen"], stated_by="tom",
        valid_from="2018-01-01",
        say=[
            "If something feels off, fill out a UTR and walk it over to me. And never mention it to the member, "
            "that's tipping off and it's an offence.",
            "Suspicious activity = internal UTR form to me, same day. Don't investigate yourselves.",
            "The UTR form is on the shared drive under Compliance. Fill it, give it to me, say nothing to the "
            "member.",
        ],
        prompts=["what do I do if a member's deposit seems off but it's under 10k?"],
        qs=["What should I do if a transaction seems suspicious?", "How do front-line staff escalate suspicious "
            "activity?", "Is there a form for reporting unusual transactions internally?",
            "Should I tell a member I'm reporting their transaction?"],
        where=["#compliance", "#member-services", "doc"], askers=["colin", "jen"],
    ),
    FactSpec(
        key="fintrac.str_deadline", kind=K.RECURRING_TASK, area="fintrac_reporting", importance=2,
        statement="Tom's rule: STRs are filed with FINTRAC within 3 business days of deciding a transaction is "
                  "suspicious.",
        kw=[["3 business days", "three business days", "3 working days", "three working days"]],
        known_by=["tom"], stated_by="tom", valid_from="2021-06-01",
        say=[
            "FINTRAC says 'as soon as practicable'. My rule is 3 business days from when I decide it's suspicious.",
            "I file STRs within three business days of the decision, the examiners were happy with that.",
            "Internal standard for STRs: three working days max.",
        ],
        qs=["How quickly do suspicious transaction reports have to be filed?",
            "What's our internal deadline for STRs?", "How long does Tom take to file an STR after deciding?",
            "Is there a deadline on suspicious transaction reports?"],
        where=["#compliance", "email"], askers=["dave", "jen"],
    ),
    FactSpec(
        key="fintrac.eftr", kind=K.RECURRING_TASK, area="fintrac_reporting", importance=2,
        statement="Electronic funds transfer reports (international wires of $10,000+) are due within five working "
                  "days.",
        kw=[["five working days", "5 working days", "five business days", "5 business days"]],
        known_by=["tom"], stated_by="tom", valid_from="2020-06-01",
        say=[
            "International wires of 10k or more need an EFTR within five working days. Send me the wire "
            "confirmation.",
            "EFTRs are 5 working days, tighter than LCTRs, so don't sit on wire paperwork.",
            "Reminder: EFTR deadline is five business days after the wire.",
        ],
        qs=["What's the deadline for EFTRs?", "How long do we have to report an international wire over $10k?",
            "When does an electronic funds transfer report need to be filed?",
            "Do outgoing international wires need a FINTRAC report, and by when?"],
        where=["#compliance", "#finance"], askers=["priya", "jen"],
    ),
    FactSpec(
        key="fintrac.admin", kind=K.ACCESS, area="fintrac_reporting", importance=3,
        statement="Tom is the only administrator on Harbourline's FINTRAC reporting account; Marc is named senior "
                  "officer but has no login.",
        kw=[["Tom"], ["admin"]], known_by=["tom", "marc"], stated_by="tom",
        valid_from="2019-06-01",
        say=[
            "Tom here, I'm the only admin on our FINTRAC account. Marc is the senior officer on paper but he doesn't "
            "have a login.",
            "FINTRAC reporting account: sole admin is me, Tom. We need to fix that before December.",
            "Only one admin on the FINTRAC side and it's Tom. Yes, I know.",
        ],
        prompts=["who else can log into the FINTRAC reporting system?"],
        qs=["Who has admin access to the FINTRAC reporting system?", "Can anyone besides Tom log in to FINTRAC?",
            "If Tom retires, who can submit to FINTRAC?", "Who administers our FINTRAC account?"],
        where=["#compliance", "#leadership", "email"], askers=["marc", "dave"],
    ),
    FactSpec(
        key="fintrac.record_keeping", kind=K.FACT, area="fintrac_reporting", importance=1,
        statement="LCTR records and supporting slips are kept for five years.",
        kw=[["five years", "5 years"]], known_by=["tom"], stated_by="tom", valid_from="2015-01-01",
        say=[
            "Keep the LCTR slips, we hold those records five years.",
            "Record keeping is 5 years for large cash stuff, don't shred anything in the Compliance boxes.",
            "The retention for FINTRAC records is five years from the transaction.",
        ],
        qs=["How long do we keep large cash transaction records?", "Can I shred old LCTR slips?",
            "What's the retention period for FINTRAC records?", "How many years do compliance records stay?"],
        where=["#compliance", "#member-services"], askers=["colin", "jen"],
    ),
    FactSpec(
        key="fintrac.second_review", kind=K.DECISION, area="fintrac_reporting", importance=2,
        statement="From July 2026, every LCTR batch gets a second review by Jen before Tom submits it.",
        kw=[["Jen"], ["review", "second look", "double-check", "check"]], known_by=["tom", "jen", "dave"],
        stated_by="tom", valid_from="2026-07-13",
        say=[
            "Starting this month Jen will review each LCTR batch before I submit. Four eyes, and she learns it.",
            "Decision with Dave: Jen does a second look on every batch before it goes. Part of my retirement "
            "prep.",
            "From now on nothing goes to FINTRAC without Jen's check first.",
        ],
        qs=["Does anyone review LCTRs before they're submitted?", "Who does the second review on FINTRAC batches?",
            "What changed in the LCTR process in July?", "Is there a four-eyes check on large cash reports?"],
        where=["#compliance", "email"], askers=["dave"],
    ),
    FactSpec(
        key="fintrac.private_exam", kind=K.DECISION, area="fintrac_reporting", importance=3, private=True,
        statement="FINTRAC's 2025 examination flagged late LCTRs; the remediation plan is due by November 30, 2026.",
        kw=[["November 30", "Nov 30", "2026-11-30", "end of November"]], known_by=["tom", "marc"],
        stated_by="tom", valid_from="2026-03-20",
        say=[
            "Marc, the exam letter came in. They flagged the late LCTRs from last year, remediation plan due "
            "November 30.",
            "just between us for now: remediation plan to FINTRAC by Nov 30, I'd like it done before I leave",
            "We have until the end of November for the remediation plan. I'll draft it, need your signature.",
        ],
        qs=["Did the last FINTRAC examination find anything?", "Is there a FINTRAC remediation deadline coming up?",
            "What's outstanding from the FINTRAC exam?"],
        where=["dm"], askers=["marc"],
    ),
    FactSpec(
        key="fintrac.nic_review", kind=K.RECURRING_TASK, area="fintrac_reporting", importance=3, in_corpus=False,
        statement="The AML compliance program's two-year effectiveness review is due by March 2027; last done "
                  "March 2025.",
        kw=[["2027"]], known_by=["tom"], stated_by="tom", valid_from="2025-03-31",
        qs=["When is the next AML effectiveness review due?", "When did we last do the two-year compliance "
            "program review?", "Is there a FINTRAC program review coming up next year?"],
    ),
    FactSpec(
        key="fintrac.nic_examiner", kind=K.VENDOR_CONTACT, area="fintrac_reporting", importance=2,
        in_corpus=False,
        statement="Our FINTRAC examiner contact is Linda Pereira at the Montreal regional office.",
        kw=[["Linda", "Pereira"]], known_by=["tom"], stated_by="tom", valid_from="2025-01-01",
        qs=["Who is our contact at FINTRAC?", "Which FINTRAC examiner handles Harbourline?",
            "If FINTRAC calls, who's the person we usually deal with?"],
    ),
    FactSpec(
        key="fintrac.nic_risk_assessment", kind=K.ACCESS, area="fintrac_reporting", importance=2,
        in_corpus=False,
        statement="The AML risk assessment spreadsheet lives only on Tom's personal H: drive, not on the shared "
                  "Compliance folder.",
        kw=[["H: drive", "H drive", "H:"]], known_by=["tom"], stated_by="tom", valid_from="2022-01-01",
        qs=["Where is the AML risk assessment kept?", "Where can I find the compliance risk assessment file?",
            "Is the AML risk assessment on the shared drive?"],
    ),
]

CARDS: list[FactSpec] = [
    FactSpec(
        key="card.owner", kind=K.OWNER, area="card_processing", importance=2,
        statement="Jen handles day-to-day debit card operations and disputes; Priya handles Tidewater settlement "
                  "and billing.",
        kw=[["Jen"]], known_by=["jen", "priya", "dave"], stated_by="dave", valid_from="2016-01-01",
        say=[
            "Card stuff: Jen for anything member-facing (orders, disputes), Priya for the Tidewater invoices.",
            "Jen runs debit card ops. Settlement questions go to Priya.",
            "For card disputes talk to Jen, she's the Tidewater expert on our side.",
        ],
        prompts=["who deals with debit card disputes?"],
        qs=["Who handles debit card issues?", "Who should I ask about a card dispute?",
            "Who's our internal point person for Tidewater?", "Who owns card processing?",
            "Who do I go to if a member's debit card order is stuck?"],
        where=["#member-services", "#ops"], askers=["colin", "aisha"],
    ),
    FactSpec(
        key="card.rep.v1", kind=K.VENDOR_CONTACT, area="card_processing", importance=2,
        statement="Our Tidewater Card Services account rep is Kevin Arsenault.",
        kw=[["Kevin"]], known_by=["jen", "priya"], stated_by="jen", valid_from="2023-09-01",
        valid_to="2026-06-08",
        say=[
            "Our rep at Tidewater is Kevin Arsenault, email him for anything that isn't urgent.",
            "Kevin at Tidewater sorted the card order issue, he's pretty responsive.",
            "Tidewater account rep = Kevin Arsenault. I'll add him to the contacts sheet.",
        ],
        where=["#member-services", "email"],
    ),
    FactSpec(
        key="card.rep.v2", kind=K.VENDOR_CONTACT, area="card_processing", importance=2,
        supersedes="card.rep.v1",
        statement="Since June 2026 our Tidewater account rep is Shauna Doyle (shauna.doyle@tidewatercard.ca, "
                  "1-866-555-0192).",
        kw=[["Shauna"]], known_by=["jen", "priya"], stated_by="jen", valid_from="2026-06-08",
        forbid=[["Kevin", "Arsenault"]],
        contra=[("colin", "I just emailed our Tidewater rep from the old contacts sheet, haven't heard back")],
        notes="Conflict: Colin uses the outdated contact; Jen corrects with the new rep.",
        say=[
            "Tidewater reassigned us, our new rep is Shauna Doyle, shauna.doyle@tidewatercard.ca, 1-866-555-0192.",
            "That address is dead, Kevin moved on. Email Shauna Doyle instead.",
            "Updated the contacts sheet: Shauna Doyle is our Tidewater account rep now.",
            "For Tidewater escalations go to Shauna, 1-866-555-0192.",
        ],
        prompts=["who's our contact at Tidewater these days?"],
        qs=["Who is our account rep at Tidewater Card Services?",
            "Who do I contact at the card processor?",
            "Is Kevin still our Tidewater rep?",
            "What's the current contact for Tidewater escalations?",
            "Who should I email at Tidewater about a stuck card order?",
            "Did our card vendor contact change?"],
        where=["#member-services", "email"], askers=["colin", "priya"],
    ),
    FactSpec(
        key="card.dispute_window.v1", kind=K.PROCEDURE, area="card_processing", importance=2,
        statement="Members have 90 days from the transaction date to dispute a debit card transaction.",
        kw=[["90", "ninety"]], known_by=["jen"], stated_by="jen", valid_from="2020-01-01",
        valid_to="2026-07-01",
        say=[
            "Members get 90 days from the transaction date to file a dispute.",
            "Dispute window is ninety days, so that one from April is still fine.",
            "Anything within 90 days we can dispute through Tidewater.",
        ],
        where=["#member-services"],
    ),
    FactSpec(
        key="card.dispute_window.v2", kind=K.PROCEDURE, area="card_processing", importance=3,
        supersedes="card.dispute_window.v1",
        statement="Since 2026-07-01 Tidewater only accepts debit card disputes within 60 days of the transaction.",
        kw=[["60", "sixty"]], known_by=["jen", "priya"], stated_by="jen", valid_from="2026-07-01",
        forbid=[["90", "ninety"]],
        say=[
            "Important: Tidewater shortened the dispute window to 60 days as of July 1. Please tell members.",
            "It's sixty days now for disputes, Tidewater changed their rules.",
            "New rule from the processor: disputes must be filed within 60 days of the transaction date.",
        ],
        prompts=["member wants to dispute a charge from 75 days ago, are we ok?"],
        qs=["How long do members have to dispute a debit card transaction?",
            "What's the current card dispute window?",
            "A member wants to dispute a charge from 70 days ago - can we still do it?",
            "Did the Tidewater dispute deadline change?",
            "How many days after a transaction can a member file a card dispute?",
            "What's the cutoff for debit card chargebacks now?"],
        where=["#member-services", "email"], askers=["colin"],
    ),
    FactSpec(
        key="card.reissue_month_end", kind=K.LANDMINE, area="card_processing", importance=2, landmine=True,
        statement="Don't place card reissue orders on the last business day of the month: Tidewater's month-end "
                  "cutoff silently drops them.",
        kw=[["last business day", "month-end", "month end", "end of the month", "last day of the month"]],
        known_by=["jen", "priya"], stated_by="jen", valid_from="2024-03-01",
        say=[
            "Never submit card reissues on the last business day of the month. Tidewater's month-end cutoff "
            "eats them and nobody tells you.",
            "Hold reissue orders until the 1st if it's month end, they just vanish otherwise.",
            "Lesson learned: orders placed at the end of the month don't make it through Tidewater's batch.",
        ],
        prompts=["can I push this batch of card reissues through today? it's the 31st"],
        qs=["Is there a bad time to order replacement debit cards?",
            "Why would a card reissue order just disappear?",
            "Anything I should avoid when submitting card orders to Tidewater?",
            "Can I submit card reissues on the last day of the month?",
            "Any gotchas with Tidewater card orders?",
            "What's the landmine with debit card reissues?"],
        where=["#member-services", "#ops"], askers=["colin"],
    ),
    FactSpec(
        key="card.lost_stolen", kind=K.PROCEDURE, area="card_processing", importance=2,
        statement="For a lost or stolen card, hotcard it in the Tidewater portal immediately, then order the "
                  "replacement.",
        kw=[["hotcard", "hot card", "hot-card"]], known_by=["jen", "colin"], stated_by="jen",
        valid_from="2019-01-01",
        say=[
            "Lost or stolen: hotcard it in the Tidewater portal first, then order the new card. Order matters.",
            "Step one is always hot card. Replacement second.",
            "Colin, remember to hotcard before you reissue, otherwise the old card stays live.",
        ],
        qs=["What do I do when a member reports a stolen debit card?", "How do we block a lost card?",
            "What's the procedure for a lost card?", "Do I order the replacement first or block the card first?"],
        where=["#member-services", "doc"], askers=["colin"],
    ),
    FactSpec(
        key="card.after_hours_line", kind=K.VENDOR_CONTACT, area="card_processing", importance=2,
        statement="After hours, members report lost/stolen cards to Tidewater's 24/7 line at 1-800-555-0177.",
        kw=[["555-0177"]], known_by=["jen", "colin"], stated_by="jen", valid_from="2019-01-01",
        say=[
            "After hours members should call Tidewater's 24/7 line, 1-800-555-0177.",
            "The lost/stolen number on the back of the card is 1-800-555-0177, it's open all night.",
            "Put 1-800-555-0177 in the voicemail message for after-hours card emergencies.",
        ],
        qs=["What number do members call for a lost card after hours?", "Is there a 24/7 line for stolen cards?",
            "What's Tidewater's after-hours phone number?", "What do members do if they lose a card on a weekend?"],
        where=["#member-services"], askers=["colin"],
    ),
    FactSpec(
        key="card.portal_access", kind=K.ACCESS, area="card_processing", importance=2,
        statement="Tidewater portal admins are Jen and Priya; the credentials are in the Member Services vault in "
                  "1Password.",
        kw=[["Member Services"], ["1Password"]], known_by=["jen", "priya"], stated_by="jen",
        valid_from="2022-06-01",
        say=[
            "Tidewater portal admin logins are in 1Password, Member Services vault. Me and Priya are admins.",
            "Portal creds are in the Member Services vault in 1Password, Colin you've got read access.",
            "If you need the Tidewater portal, it's in 1Password under Member Services.",
        ],
        qs=["Where are the Tidewater portal credentials?", "Who are the admins on the card processor portal?",
            "How do I log into the Tidewater portal?", "Which 1Password vault has the card portal login?"],
        where=["#member-services"], askers=["colin", "priya"],
    ),
    FactSpec(
        key="card.settlement", kind=K.RECURRING_TASK, area="card_processing", importance=2,
        statement="Priya reconciles the Tidewater daily settlement report against the GL every morning by 10am.",
        kw=[["settlement"], ["morning", "10am", "10 am", "10:00"]], known_by=["priya"], stated_by="priya",
        valid_from="2018-01-01",
        say=[
            "I reconcile the Tidewater settlement report against the GL every morning, done by 10am.",
            "The daily settlement file from Tidewater lands overnight, I tie it out first thing in the morning.",
            "Card settlement rec is a 10 am thing for me every business day.",
        ],
        qs=["Who reconciles the card settlement report and when?", "How often is Tidewater settlement reconciled?",
            "What's the daily card settlement task?", "When does the card settlement get checked each day?"],
        where=["#finance"], askers=["dave"],
    ),
    FactSpec(
        key="card.limits", kind=K.FACT, area="card_processing", importance=1,
        statement="Default debit card daily limits are $3,000 for point-of-sale and $1,000 for ATM withdrawals.",
        kw=[["3,000", "3000", "3k"], ["1,000", "1000", "1k"]], known_by=["jen", "colin"], stated_by="jen",
        valid_from="2021-01-01",
        say=[
            "Default limits are $3,000 a day at POS and $1,000 at the ATM. We can raise them temporarily.",
            "POS is 3k, ATM is 1k per day by default.",
            "Standard card limits: $3000 POS, $1000 ATM. Anything higher needs my OK.",
        ],
        qs=["What are the default daily debit card limits?", "How much can a member withdraw from an ATM per day?",
            "What's the standard point-of-sale limit on our debit cards?", "Can members spend more than $3k a day "
            "on their card?"],
        where=["#member-services"], askers=["colin"],
    ),
    FactSpec(
        key="card.contactless_decision", kind=K.DECISION, area="card_processing", importance=1,
        statement="From June 2026 all card reissues are chip and contactless; magstripe-only cards are no longer "
                  "issued.",
        kw=[["contactless"]], known_by=["jen", "priya", "dave"], stated_by="jen", valid_from="2026-05-19",
        say=[
            "Decided with Dave today: every reissue from June is chip + contactless. No more magstripe-only.",
            "All new and replacement cards will be contactless starting in June.",
            "Heads up, we're done issuing magstripe-only cards, it's contactless for everyone.",
        ],
        qs=["Do our new debit cards support tap?", "Are we still issuing magstripe-only cards?",
            "What did we decide about contactless cards?", "Will a member's replacement card be tap-enabled?"],
        where=["#member-services", "#general"], askers=["colin"],
    ),
    FactSpec(
        key="card.pin_reset", kind=K.PROCEDURE, area="card_processing", importance=1,
        statement="Members reset their PIN themselves at a branch PIN pad; staff never ask for or see the PIN.",
        kw=[["PIN pad", "PIN-pad", "pinpad"]], known_by=["jen", "colin"], stated_by="jen",
        valid_from="2019-01-01",
        say=[
            "PIN resets happen on the branch PIN pad, the member keys it in. We never ask for the PIN.",
            "Just bring them to the PIN pad at the counter, it walks them through a reset.",
            "Reminder: never write down or ask for a PIN. Member uses the PIN pad, done.",
        ],
        qs=["How does a member reset their debit card PIN?", "Can I set a member's PIN for them?",
            "What's the PIN reset procedure?", "Where do members change their card PIN?"],
        where=["#member-services"], askers=["colin"],
    ),
    FactSpec(
        key="card.nic_emergency_fee", kind=K.FACT, area="card_processing", importance=1, in_corpus=False,
        statement="Tidewater charges $4.50 per emergency card reissue; Priya negotiated a waiver for fraud "
                  "reissues in 2024.",
        kw=[["4.50"]], known_by=["priya"], stated_by="priya", valid_from="2024-02-01",
        qs=["How much does Tidewater charge for an emergency card reissue?",
            "Do we pay a fee when replacing a card for fraud?", "What does a rush card replacement cost us?"],
    ),
    FactSpec(
        key="card.nic_contract_renewal", kind=K.DECISION, area="card_processing", importance=2, in_corpus=False,
        statement="The Tidewater contract renews in June 2027 and needs 120 days' notice to change terms.",
        kw=[["June 2027"]], known_by=["priya"], stated_by="priya", valid_from="2024-06-01",
        qs=["When does the Tidewater contract come up for renewal?",
            "How much notice do we need to give Tidewater to renegotiate?",
            "When could we switch card processors?"],
    ),
]

FACTS: list[FactSpec] = [*PAYROLL, *BACKUPS, *FINTRAC, *CARDS]

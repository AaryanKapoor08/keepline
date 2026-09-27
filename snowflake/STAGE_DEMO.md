# Keepline on Snowflake: live stage demo (Snowsight)

Every query below was run against the live `KEEPLINE` database on 2026-09-27 (demo clock 2026-09-04). The results
pasted under each query are that real output. Open a Snowsight worksheet and paste the queries in order.

One-time setup, already done on the demo account. It lets the presenter switch into team roles:

```sql
USE ROLE ACCOUNTADMIN;
GRANT ROLE KEEPLINE_TEAM_ENGINEERING TO USER AARYAN;
GRANT ROLE KEEPLINE_TEAM_FINANCE     TO USER AARYAN;
```

## 1. Row access policy: the same query returns different rows for different people

```sql
USE SECONDARY ROLES NONE;            -- only the active role counts
USE WAREHOUSE KEEPLINE_WH;

USE ROLE ACCOUNTADMIN;               -- pipeline admin
SELECT CURRENT_ROLE(), COUNT(*) AS facts_visible, COUNT_IF(visibility = 'team') AS team_facts FROM KEEPLINE.CORE.FACTS;

USE ROLE KEEPLINE_TEAM_ENGINEERING;  -- Alex, new backend engineer
USE WAREHOUSE KEEPLINE_WH;
SELECT CURRENT_ROLE(), COUNT(*) AS facts_visible, COUNT_IF(visibility = 'team') AS team_facts FROM KEEPLINE.CORE.FACTS;

USE ROLE KEEPLINE_TEAM_FINANCE;      -- Priya's team
USE WAREHOUSE KEEPLINE_WH;
SELECT CURRENT_ROLE(), COUNT(*) AS facts_visible, COUNT_IF(visibility = 'team') AS team_facts FROM KEEPLINE.CORE.FACTS;
USE ROLE ACCOUNTADMIN;
```

| role | facts_visible | team_facts |
|---|---|---|
| ACCOUNTADMIN | 506 | 117 |
| KEEPLINE_TEAM_ENGINEERING | 421 | 32 |
| KEEPLINE_TEAM_FINANCE | 426 | 37 |

What to say: this is `CORE.RAP_VISIBILITY`. Each team sees the public facts plus its own team's facts. Answers
can never show more than the asker could already see. DMs are never indexed, and their text is masked.

## 2. Risk map, computed by a Snowpark Python stored procedure

```sql
USE WAREHOUSE KEEPLINE_WH;
CALL KEEPLINE.APP.RISK_MAP('2026-09-04'::DATE, '');
SELECT area_id, ROUND(risk, 2) AS risk, bus_factor, at_risk_person_id, countdown_days
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())) ORDER BY risk DESC LIMIT 5;
```

| area_id | risk | bus_factor | at_risk_person_id | countdown_days |
|---|---|---|---|---|
| corelink_api | 0.67 | 1 | sarah | 7 |
| reconciliation | 0.66 | 1 | sarah | 7 |
| fintrac_reporting | 0.50 | 1 | tom | 105 |
| ssl_dns | 0.32 | 1 | sarah | 7 |
| backups_dr | 0.29 | 2 | mike | 56 |

The what-if runs the same procedure with Sarah removed: `CALL KEEPLINE.APP.RISK_MAP('2026-09-04'::DATE, 'sarah');`
CoreLink, reconciliation and SSL/DNS then drop to **bus factor 0**, with the explanation "Nobody left with strong
evidence…".

The same question can also go through the **Cortex Analyst semantic view**:

```sql
SELECT area_name, bus_factor, ROUND(risk, 2) AS risk
FROM SEMANTIC_VIEW(KEEPLINE.APP.KEEPLINE_SEMANTIC
       DIMENSIONS area_risk.area_name, area_risk.excluded_person_id, area_risk.snapshot_date
       FACTS area_risk.bus_factor, area_risk.risk)
WHERE bus_factor = 1 AND COALESCE(excluded_person_id, '') = '' AND snapshot_date = '2026-09-04'
ORDER BY risk DESC;
```

Result: CoreLink core-banking API 1 / 0.67, Nightly core-banking reconciliation 1 / 0.66, FINTRAC reporting & AML
1 / 0.50, SSL certificates & DNS 1 / 0.32, Payroll 1 / 0.03.

## 3. What did we believe in May? (bi-temporal facts plus Snowflake Time Travel)

```sql
-- Valid time: the world as the company believed it on May 1
SELECT id, LEFT(text, 90) AS what_we_believed, valid_from, valid_to
FROM TABLE(KEEPLINE.CORE.FACTS_AS_OF('2026-05-01'::DATE))
WHERE area_id = 'reconciliation' AND (text ILIKE '%skip%' OR text ILIKE '%except%');

-- ... and today
SELECT id, LEFT(text, 90) AS what_we_believe_now, valid_from
FROM TABLE(KEEPLINE.CORE.FACTS_AS_OF('2026-09-04'::DATE))
WHERE area_id = 'reconciliation' AND (text ILIKE '%skip%' OR text ILIKE '%no run on%' OR text ILIKE '%except%');
```

On May 1: "The recon job skips the 1st of every month." (valid 2026-03-13 to **2026-05-19**), and "Rule of thumb
for the nightly reconciliation: every day except the 1st." (valid to 2026-05-19).
Today: "New rule for the nightly reconciliation, effective today: no run on the 1st, no run on the 15th." (from
2026-05-19), plus two later confirmations from Sarah (Jun 23, Jul 24).

System time (Snowflake Time Travel) answers a different question: what Keepline itself held in the table at an
earlier moment.

```sql
SELECT COUNT(*) FROM KEEPLINE.CORE.FACTS AT(OFFSET => -60);   -- 506 one minute ago
CALL KEEPLINE.APP.WHAT_DID_WE_BELIEVE(1, 'reconciliation');  -- same idea, N hours back
```

The offset must fall after the table was loaded; the demo load was on 2026-09-27. Use `-60*60` or larger only if
the table has existed that long.

## 4. Ask: Cortex Search retrieves the receipt, AI_COMPLETE answers only from it

```sql
WITH hits AS (
  SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('KEEPLINE.CORE.FACTS_SEARCH',
    '{"query": "which days does the reconciliation job skip",
      "columns": ["fact_id","fact_text","valid_from","primary_doc_id"],
      "filter": {"@eq": {"is_current": 1}}, "limit": 3}'))['results'] AS r
)
SELECT AI_COMPLETE('claude-sonnet-4-5',
  'Answer in one sentence using ONLY these receipts and cite the fact_id and date in brackets. If they do not answer it, say "I don''t know". Receipts: '
  || r::STRING || ' Question: Which days does the nightly reconciliation job skip?') AS answer
FROM hits;
```

Answer: *"The nightly reconciliation job skips the 1st and the 15th of each month [F597df3e045e, 2026-05-19]."*
The filter `is_current = 1` keeps the replaced "1st only" rule out of the answer.

The raw receipts, including who said it and when:

```sql
SELECT r.value:doc_id::STRING AS doc_id, r.value:author_name::STRING AS author, r.value:ts::STRING AS ts,
       LEFT(r.value:snippet::STRING, 140) AS receipt
FROM TABLE(FLATTEN(PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('KEEPLINE.CORE.RECEIPTS_SEARCH',
  '{"query": "reconciliation skip the 15th", "columns": ["doc_id","snippet","author_name","ts","url"],
    "filter": {"@eq": {"visibility": "public"}}, "limit": 3}'))['results'])) r;
```

Top hit: `slack-002167`, Sarah Chen, 2026-06-23: "@aisha short version: skip the first and the fifteenth. the
15th is CoreLink's interest batch and it wrecks the suspense account if recon ru…"

Also deployed: the Cortex Agent `KEEPLINE.APP.KEEPLINE_AGENT` (Search + Analyst + procedure tools). Open it in
Snowsight under AI & ML > Agents. It was created, but it has not been exercised from SQL here.

Closing line: *"Everything you just saw ran inside Snowflake: the data never left the account."*

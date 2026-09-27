-- =================================================================================================
-- Keepline on Snowflake · 01_schema.sql
-- Raw landing tables + the bi-temporal memory graph. Mirrors keepline/memory/schema.sql (the local SQLite
-- engine, data/memory/keepline.db) table-for-table and column-for-column, so the same product code and the
-- same loader work on either backend. Differences are additive only:
--   * *_json columns are native ARRAY / VARIANT here (TEXT holding JSON in SQLite)
--   * documents.area_id / owner_team and facts.owner_team are derived columns used by access policies
--
-- Docs:
--   https://docs.snowflake.com/en/sql-reference/sql/create-table
--   https://docs.snowflake.com/en/sql-reference/sql/create-file-format   (TYPE = JSON, STRIP_OUTER_ARRAY)
--   https://docs.snowflake.com/en/user-guide/data-time-travel             (DATA_RETENTION_TIME_IN_DAYS)
--   https://docs.snowflake.com/en/sql-reference/data-types-semistructured (VARIANT / ARRAY / OBJECT)
--
-- Bi-temporal model (pattern from Zep/Graphiti):
--   valid_from / valid_to  = when the fact was true *in the world*   (valid time)
--   learned_at             = when Keepline learned it                (transaction time)
--   supersedes / superseded_by = explicit replacement chain, never a silent overwrite
--   + Snowflake Time Travel gives a third axis for free: what the *table* said at any past moment.
-- =================================================================================================

USE ROLE KEEPLINE_ADMIN;
USE WAREHOUSE KEEPLINE_WH;
USE DATABASE KEEPLINE;

-- -------------------------------------------------------------------------------------------------
-- RAW: exports exactly as received. One VARIANT per record; typed columns are derived in CORE.
-- -------------------------------------------------------------------------------------------------
USE SCHEMA RAW;

CREATE FILE FORMAT IF NOT EXISTS RAW.JSONL_FMT
  TYPE = JSON
  STRIP_OUTER_ARRAY = TRUE      -- org/*.json are arrays; corpus/*.jsonl are newline-delimited: both parse
  COMMENT = 'Keepline exports: NDJSON corpus and JSON-array org files';

CREATE STAGE IF NOT EXISTS RAW.LANDING
  FILE_FORMAT = RAW.JSONL_FMT
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'PUT target for work-tool exports (deploy.py). Internal stage: data never leaves the account.';

CREATE TABLE IF NOT EXISTS RAW.SLACK_MESSAGES (record VARIANT, source_file STRING, loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());
CREATE TABLE IF NOT EXISTS RAW.EMAILS         (record VARIANT, source_file STRING, loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());
CREATE TABLE IF NOT EXISTS RAW.TICKETS        (record VARIANT, source_file STRING, loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());
CREATE TABLE IF NOT EXISTS RAW.DOCS           (record VARIANT, source_file STRING, loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());
CREATE TABLE IF NOT EXISTS RAW.INTERVIEWS     (record VARIANT, source_file STRING, loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());
CREATE TABLE IF NOT EXISTS RAW.ORG_PEOPLE     (record VARIANT, source_file STRING, loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());
CREATE TABLE IF NOT EXISTS RAW.ORG_AREAS      (record VARIANT, source_file STRING, loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());

-- One logical stream of "messages" regardless of tool; this is what extraction reads.
CREATE OR REPLACE VIEW RAW.MESSAGES AS
  SELECT record, source_file, loaded_at FROM RAW.SLACK_MESSAGES
  UNION ALL SELECT record, source_file, loaded_at FROM RAW.EMAILS
  UNION ALL SELECT record, source_file, loaded_at FROM RAW.TICKETS
  UNION ALL SELECT record, source_file, loaded_at FROM RAW.DOCS
  UNION ALL SELECT record, source_file, loaded_at FROM RAW.INTERVIEWS;

-- -------------------------------------------------------------------------------------------------
-- CORE: org config (HR roster + areas). Mirrors contracts.Person / contracts.Area.
-- -------------------------------------------------------------------------------------------------
USE SCHEMA CORE;

CREATE TABLE IF NOT EXISTS CORE.PEOPLE (
  id              STRING    NOT NULL PRIMARY KEY,   -- slug, e.g. 'sarah'
  name            STRING    NOT NULL,
  role            STRING,
  team            STRING,                          -- engineering | finance | operations | member_services | leadership | it
  email           STRING,
  start_date      DATE,
  departure_date  DATE,                            -- known future/past departure (HR)
  departure_type  STRING,                          -- resignation | retirement | leave | contract_end
  manager_id      STRING
) COMMENT = 'HR roster (contracts.Person).';

CREATE TABLE IF NOT EXISTS CORE.AREAS (
  id           STRING NOT NULL PRIMARY KEY,
  name         STRING NOT NULL,
  description  STRING,
  keywords_json  ARRAY,
  systems_json   ARRAY,
  criticality  NUMBER(1,0) DEFAULT 2              -- 1 nice-to-have .. 3 business-critical (customer prior)
) COMMENT = 'Topics / systems / responsibilities (contracts.Area).';

-- -------------------------------------------------------------------------------------------------
-- CORE: source documents = receipts. Mirrors contracts.SourceDoc / SQLite documents.
-- owner_team is derived at normalization (author's team) and drives team-visibility access.
-- -------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS CORE.DOCUMENTS (
  id                 STRING NOT NULL PRIMARY KEY,  -- 'slack-000123', 'ticket-HCU-212'
  source_type        STRING NOT NULL,              -- slack | email | ticket | interview | doc
  author_id          STRING,
  ts                 TIMESTAMP_NTZ,
  text               STRING,
  container          STRING,                       -- channel / thread / ticket key / doc path
  thread_id          STRING,
  title              STRING,
  participants_json  ARRAY,                        -- person ids who can see it (team/private)
  visibility         STRING DEFAULT 'public',      -- public | team | private
  url                STRING,
  meta_json          VARIANT,                      -- ticket status/assignee/closed_at, email to/cc ...
  ticket_status      STRING,                       -- denormalised from meta for cheap open-ticket queries
  ticket_assignee    STRING,
  ticket_closed_at   STRING,
  area_id            STRING,                       -- primary area (highest DOC_AREAS score)
  owner_team         STRING,
  ingested_at        TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
) CHANGE_TRACKING = TRUE                           -- required by streams + Cortex Search incremental refresh
  COMMENT = 'Receipts (contracts.SourceDoc). Private docs are excluded from extraction unless all participants opt in.';

-- Which areas a document is about (a doc can touch several).
CREATE TABLE IF NOT EXISTS CORE.DOC_AREAS (
  doc_id   STRING NOT NULL,
  area_id  STRING NOT NULL,
  score    FLOAT
);

-- Access control list: which person may see which private/team object. Referenced by row access
-- policies as a mapping table; readable only by KEEPLINE_ADMIN.
CREATE TABLE IF NOT EXISTS CORE.ACL (
  object_id  STRING NOT NULL,                      -- DOCUMENTS.id or FACTS.id
  person_id  STRING NOT NULL                       -- PEOPLE.id, or '__pipeline__' for opted-in private sources
) COMMENT = 'Participants mapping for row access policies.';

-- Team -> Snowflake role mapping used by the team-visibility branch of the row access policy.
CREATE TABLE IF NOT EXISTS CORE.TEAM_ROLES (
  team       STRING NOT NULL PRIMARY KEY,
  role_name  STRING NOT NULL
);
MERGE INTO CORE.TEAM_ROLES t
USING (SELECT column1 AS team, column2 AS role_name FROM VALUES
         ('engineering', 'KEEPLINE_TEAM_ENGINEERING'), ('finance', 'KEEPLINE_TEAM_FINANCE'),
         ('operations', 'KEEPLINE_TEAM_OPERATIONS'), ('member_services', 'KEEPLINE_TEAM_MEMBER_SERVICES'),
         ('leadership', 'KEEPLINE_TEAM_LEADERSHIP'), ('it', 'KEEPLINE_TEAM_IT')) s
ON t.team = s.team
WHEN MATCHED THEN UPDATE SET role_name = s.role_name
WHEN NOT MATCHED THEN INSERT (team, role_name) VALUES (s.team, s.role_name);

-- Snowflake user -> Keepline person. The asker's identity for every policy decision.
CREATE TABLE IF NOT EXISTS CORE.USER_PERSON_MAP (
  snowflake_user  STRING NOT NULL PRIMARY KEY,     -- CURRENT_USER()
  person_id       STRING NOT NULL
);

-- Employee source controls (My Knowledge page). DMs are OFF by default: absence of a row = excluded.
CREATE TABLE IF NOT EXISTS CORE.SOURCE_CONTROLS (
  person_id        STRING NOT NULL,
  source_type      STRING NOT NULL,                -- slack | email | ticket | doc | interview
  include_private  BOOLEAN DEFAULT FALSE,
  updated_at       TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- -------------------------------------------------------------------------------------------------
-- CORE: extracted knowledge. Mirrors contracts.Fact (bi-temporal + receipts + review state).
-- -------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS CORE.FACTS (
  id              STRING NOT NULL PRIMARY KEY,
  text            STRING NOT NULL,                 -- normalized statement
  kind            STRING NOT NULL,                 -- access | vendor_contact | recurring_task | landmine | procedure | decision | owner | fact
  area_id         STRING,
  stated_by       STRING,                          -- person id (NULL if inferred)
  source_doc_ids_json ARRAY,                       -- receipts
  quote           STRING,                          -- verbatim span from the primary source
  valid_from      DATE,
  valid_to        DATE,                            -- NULL = still true
  learned_at      TIMESTAMP_NTZ,
  supersedes      STRING,
  superseded_by   STRING,
  epistemic       STRING DEFAULT 'said',           -- said | inferred
  verification    STRING DEFAULT 'unverified',     -- unverified | verified | contradicted
  visibility      STRING DEFAULT 'public',
  participants_json ARRAY,                         -- who may see a team/private fact (from its receipts)
  confidence      FLOAT  DEFAULT 0.5,              -- extraction confidence [0,1]
  review_status   STRING DEFAULT 'pending',        -- pending | approved | rejected | corrected
  corrected_text  STRING,                          -- the owner's correction, if any
  subject         STRING,                          -- entity the fact is about ('CoreLink API key')
  extractor       STRING DEFAULT 'heuristic',      -- heuristic | claude | cortex
  owner_team      STRING
) CHANGE_TRACKING = TRUE
  DATA_RETENTION_TIME_IN_DAYS = 30
  COMMENT = 'Versioned facts with receipts (contracts.Fact). Never overwritten: superseded via 04_temporal.sql.';

-- Staging for extraction output before supersession is applied (03_extract -> 04_temporal).
CREATE TABLE IF NOT EXISTS CORE.FACT_CANDIDATES (
  candidate_id    STRING DEFAULT UUID_STRING(),
  doc_id          STRING NOT NULL,
  text            STRING,
  kind            STRING,
  area_id         STRING,
  subject         STRING,
  stated_by       STRING,
  quote           STRING,
  valid_from      DATE,
  confidence      FLOAT,
  visibility      STRING,
  owner_team      STRING,
  extractor       STRING DEFAULT 'cortex',
  extracted_at    TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
  applied         BOOLEAN DEFAULT FALSE
);

-- Entities pulled by AI_EXTRACT (systems, vendors, dates, promised follow-ups) for linking + handoff.
CREATE TABLE IF NOT EXISTS CORE.DOC_ENTITIES (
  doc_id       STRING NOT NULL,
  entities     VARIANT,                             -- AI_EXTRACT response object
  scores       VARIANT,                             -- per-field extraction confidence
  extracted_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS CORE.EDGES (
  src               STRING NOT NULL,
  dst               STRING NOT NULL,
  rel               STRING NOT NULL,               -- knows | owns | decided | has_access | about | supported_by | supersedes | asked
  weight            FLOAT DEFAULT 1.0,
  valid_from        DATE,
  valid_to          DATE,
  evidence_doc_ids_json  ARRAY
) COMMENT = 'Graph edges (contracts.Edge).';

-- Two facts that disagree with no clear "update" signal: both kept, the weaker one marked contradicted.
CREATE TABLE IF NOT EXISTS CORE.CONFLICTS (
  fact_id_a  STRING NOT NULL,
  fact_id_b  STRING NOT NULL,
  area_id    STRING,
  subject    STRING,
  note       STRING
);

CREATE TABLE IF NOT EXISTS CORE.EXPERTISE (
  person_id            STRING NOT NULL,
  area_id              STRING NOT NULL,
  score                FLOAT,                      -- [0,1]; doing > talking (closed tickets weigh more)
  n_docs               NUMBER,
  n_tickets_closed     NUMBER,
  n_facts_stated       NUMBER,
  n_answers            NUMBER,                     -- answers that relied on this person's facts
  last_active          DATE,
  confirmed_by_person  BOOLEAN DEFAULT FALSE,
  enough_data          BOOLEAN DEFAULT TRUE        -- FALSE => "unknown", never treated as zero
) COMMENT = 'Evidence that a person knows an area (contracts.Expertise). Topic-level use only.';

CREATE TABLE IF NOT EXISTS CORE.QUERY_LOG (
  id             STRING DEFAULT UUID_STRING(),
  asked_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()::TIMESTAMP_NTZ,
  asker_id       STRING,
  question       STRING,
  action         STRING,                           -- answer | abstain | route
  area_id        STRING,
  confidence     FLOAT,
  answer_text    STRING,
  route_to_json  ARRAY,
  fact_ids_json  ARRAY
) COMMENT = 'Who asked what. Feeds ask-frequency importance; never used to score individuals.';

-- "Who asked what about my knowledge": one row per person whose facts/expertise an answer relied on.
CREATE TABLE IF NOT EXISTS CORE.QUERY_ABOUT (
  query_id   STRING NOT NULL,
  person_id  STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS CORE.REVIEW_EVENTS (
  id              STRING DEFAULT UUID_STRING(),
  fact_id         STRING NOT NULL,
  status          STRING NOT NULL,                 -- approved | rejected | corrected
  corrected_text  STRING,
  "AT"            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()::TIMESTAMP_NTZ,  -- quoted: AT is an SQL keyword
  reviewer_id     STRING
) COMMENT = 'Append-only audit of employee review decisions (the employee owns what is captured about them).';

-- -------------------------------------------------------------------------------------------------
-- APP: product outputs.
-- -------------------------------------------------------------------------------------------------
USE SCHEMA APP;

CREATE TABLE IF NOT EXISTS APP.AREA_RISK_SNAPSHOT (
  snapshot_date          DATE NOT NULL,
  area_id                STRING NOT NULL,
  area_name              STRING,
  importance             FLOAT,
  redundancy             FLOAT,
  departure_likelihood   FLOAT,
  risk                   FLOAT,                    -- importance x (1 - redundancy) x departure_likelihood
  bus_factor             NUMBER,
  at_risk_person_id      STRING,
  countdown_days         NUMBER,
  n_facts                NUMBER,
  n_landmines            NUMBER,
  explanation            STRING,
  excluded_person_id     STRING                    -- non-NULL for what-if scenarios ("remove Sarah")
) COMMENT = 'Risk map snapshots written by APP.REFRESH_RISK_SNAPSHOT (06_procs.sql); read by Cortex Analyst.';

CREATE TABLE IF NOT EXISTS APP.HANDOFF_SIGNOFFS (
  person_id       STRING NOT NULL,
  signed_off      BOOLEAN DEFAULT FALSE,
  signed_off_at   TIMESTAMP_NTZ,
  item_statuses   VARIANT,                         -- {item_key: confirmed | corrected | removed}
  pack            VARIANT                          -- the handoff pack as reviewed (receipts included)
) COMMENT = 'Handoff pack sign-off state (mirrors data/memory/signoffs.json).';

CREATE STAGE IF NOT EXISTS APP.SEMANTIC_MODELS
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Cortex Analyst semantic model YAML files.';

CREATE STAGE IF NOT EXISTS APP.STREAMLIT_SRC
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Streamlit-in-Snowflake source: snowflake/streamlit + keepline/ package.';

-- Demo clock. In production leave demo_today NULL and "today" is CURRENT_DATE().
CREATE TABLE IF NOT EXISTS APP.SETTINGS (key STRING NOT NULL PRIMARY KEY, value STRING);
MERGE INTO APP.SETTINGS t USING (SELECT 'demo_today' AS key, '2026-09-04' AS value) s ON t.key = s.key
WHEN NOT MATCHED THEN INSERT (key, value) VALUES (s.key, s.value);

CREATE OR REPLACE FUNCTION APP.KEEPLINE_TODAY()
  RETURNS DATE
  COMMENT = 'The Keepline clock: APP.SETTINGS.demo_today if set, else CURRENT_DATE().'
AS $$
  SELECT COALESCE((SELECT TRY_TO_DATE(value) FROM APP.SETTINGS WHERE key = 'demo_today'), CURRENT_DATE())
$$;

-- Convenience view for Analyst + the app: departures with a countdown.
CREATE OR REPLACE VIEW APP.PEOPLE_DEPARTURES AS
  SELECT p.id AS person_id, p.name, p.role, p.team, p.departure_date, p.departure_type,
         DATEDIFF('day', APP.KEEPLINE_TODAY(), p.departure_date) AS days_until_departure
  FROM CORE.PEOPLE p
  WHERE p.departure_date IS NOT NULL;

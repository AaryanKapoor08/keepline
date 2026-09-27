-- =================================================================================================
-- Keepline on Snowflake · 05_search.sql
-- Cortex Search: hybrid (vector + keyword) retrieval over receipts and facts, refreshed incrementally.
--
--   CORE.RECEIPTS_SEARCH  source snippets (Slack / email / tickets / docs / interviews) -> citation cards
--   CORE.FACTS_SEARCH     extracted facts, current AND superseded, with is_current as a filter attribute,
--                         so "replaced by ..." badges come from the same call.
--
-- Access: private sources are never indexed. Team sources are indexed with owner_team + participants
-- attributes and every query from the app / agent carries a filter built from the asker's identity:
--   {"@or": [ {"@eq": {"visibility": "public"}},
--             {"@eq": {"owner_team": "<asker team>"}},
--             {"@contains": {"participants": "<asker person id>"}} ]}
-- This mirrors CORE.RAP_VISIBILITY (02_policies.sql) so search results never exceed what the asker sees.
--
-- Docs:
--   https://docs.snowflake.com/en/sql-reference/sql/create-cortex-search      (ON, ATTRIBUTES, WAREHOUSE, TARGET_LAG, EMBEDDING_MODEL)
--   https://docs.snowflake.com/en/sql-reference/functions/search_preview-snowflake-cortex (@eq/@contains/@gte/@lte/@and/@or/@not)
-- =================================================================================================

USE ROLE KEEPLINE_ADMIN;
USE WAREHOUSE KEEPLINE_WH;
USE DATABASE KEEPLINE;
USE SCHEMA CORE;

-- Materialized source: Cortex Search needs change tracking, which the masking / row access policies on
-- the base tables (correlated subqueries) do not allow. DMs are excluded here, so nothing masked is copied.
CREATE OR REPLACE TABLE CORE.RECEIPTS_SEARCH_SRC CHANGE_TRACKING = TRUE AS
  SELECT
    d.id                                                  AS doc_id,
    COALESCE(d.title || ' - ', '') || d.text              AS snippet,
    d.area_id,
    d.source_type,
    d.visibility,
    d.owner_team,
    d.author_id,
    p.name                                                AS author_name,
    d.participants_json                                   AS participants,
    d.ts::DATE                                            AS doc_date,
    TO_VARCHAR(d.ts, 'YYYY-MM-DD"T"HH24:MI:SS')           AS ts,
    d.url,
    d.container
  FROM CORE.DOCUMENTS d
  LEFT JOIN CORE.PEOPLE p ON p.id = d.author_id
  WHERE d.visibility IN ('public', 'team')                -- DMs are never indexed
    AND d.text IS NOT NULL;

CREATE OR REPLACE CORTEX SEARCH SERVICE CORE.RECEIPTS_SEARCH
  ON snippet
  ATTRIBUTES area_id, source_type, visibility, owner_team, author_id, participants, doc_date
  WAREHOUSE = KEEPLINE_WH
  TARGET_LAG = '15 minutes'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
  COMMENT = 'Keepline receipts: every answer cites one of these rows.'
AS (
  SELECT * FROM CORE.RECEIPTS_SEARCH_SRC
);

-- Materialized source: Cortex Search needs change tracking, which the masking / row access policies on
-- the base tables (correlated subqueries) do not allow. DMs are excluded here, so nothing masked is copied.
CREATE OR REPLACE TABLE CORE.FACTS_SEARCH_SRC CHANGE_TRACKING = TRUE AS
  SELECT
    f.id                                                  AS fact_id,
    f.text || COALESCE(' (quote: "' || f.quote || '")', '') AS fact_text,
    f.area_id,
    f.kind,
    IFF(f.valid_to IS NULL AND f.superseded_by IS NULL, 1, 0) AS is_current,   -- NUMBER: @eq supports text/numeric
    f.visibility,
    f.owner_team,
    f.stated_by,
    f.valid_from,
    f.valid_to,
    f.superseded_by,
    f.supersedes,
    f.epistemic,
    f.confidence,
    f.source_doc_ids_json[0]::STRING                      AS primary_doc_id
  FROM CORE.FACTS f
  WHERE f.visibility IN ('public', 'team')
    AND f.review_status <> 'rejected';

CREATE OR REPLACE CORTEX SEARCH SERVICE CORE.FACTS_SEARCH
  ON fact_text
  ATTRIBUTES area_id, kind, is_current, visibility, owner_team, stated_by, valid_from
  WAREHOUSE = KEEPLINE_WH
  TARGET_LAG = '15 minutes'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
  COMMENT = 'Keepline facts with supersession state; filter is_current = 1 for answers, 0 for history.'
AS (
  SELECT * FROM CORE.FACTS_SEARCH_SRC
);

GRANT USAGE ON CORTEX SEARCH SERVICE CORE.RECEIPTS_SEARCH TO ROLE KEEPLINE_APP;
GRANT USAGE ON CORTEX SEARCH SERVICE CORE.FACTS_SEARCH    TO ROLE KEEPLINE_APP;

-- Examples (run by hand; the first refresh completes shortly after creation):
--
-- Alex (engineering) asks about the reconciliation job, as of the demo date:
--   SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('KEEPLINE.CORE.RECEIPTS_SEARCH', '{
--     "query": "when must the nightly reconciliation job not run",
--     "columns": ["doc_id", "snippet", "author_name", "ts", "url", "source_type"],
--     "filter": {"@and": [
--        {"@lte": {"doc_date": "2026-09-04"}},
--        {"@or": [{"@eq": {"visibility": "public"}},
--                 {"@eq": {"owner_team": "engineering"}},
--                 {"@contains": {"participants": "alex"}}]}]},
--     "limit": 8}'))['results'];
--
-- Current facts only (never cite a dead fact as current):
--   SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('KEEPLINE.CORE.FACTS_SEARCH', '{
--     "query": "reconciliation skip dates",
--     "columns": ["fact_id", "fact_text", "valid_from", "supersedes", "primary_doc_id"],
--     "filter": {"@eq": {"is_current": 1}},
--     "limit": 5}'))['results'];

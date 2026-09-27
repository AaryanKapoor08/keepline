-- =================================================================================================
-- Keepline on Snowflake · 04_temporal.sql
-- Temporal correctness is the moat: the agent must never cite a dead fact as current.
--
--   * Supersession: new candidates are MERGEd into FACTS; when a candidate restates the same
--     (area, kind, subject) with different content and a later valid_from, the old fact is closed
--     (valid_to, superseded_by) and the new one links back (supersedes). Nothing is ever overwritten.
--   * Valid time "as of": CORE.FACTS_AS_OF(date) returns what was true in the world on a date.
--   * Transaction time for free: Snowflake Time Travel answers "what did *we believe* yesterday?"
--     (AT(OFFSET => ...)) and CHANGES shows exactly which beliefs moved since then.
--
-- Docs:
--   https://docs.snowflake.com/en/sql-reference/sql/merge
--   https://docs.snowflake.com/en/sql-reference/constructs/at-before      (AT(OFFSET => -seconds), BEFORE(STATEMENT => ...))
--   https://docs.snowflake.com/en/sql-reference/constructs/changes        (CHANGES(INFORMATION => DEFAULT))
--   https://docs.snowflake.com/en/developer-guide/udf/sql/udf-sql-tabular-functions
--   https://docs.snowflake.com/en/sql-reference/sql/execute-immediate
-- =================================================================================================

USE ROLE KEEPLINE_ADMIN;
USE WAREHOUSE KEEPLINE_WH;
USE DATABASE KEEPLINE;
USE SCHEMA CORE;

-- -------------------------------------------------------------------------------------------------
-- Supersession
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE CORE.APPLY_SUPERSESSION()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS
$$
DECLARE
  n_new NUMBER DEFAULT 0;
  n_closed NUMBER DEFAULT 0;
BEGIN
  BEGIN TRANSACTION;

  -- 1) Insert candidates as facts (stable id = hash of receipt + statement, so re-runs are no-ops),
  --    linking each to the current fact it replaces, if any.
  MERGE INTO CORE.FACTS t
  USING (
    WITH c AS (
      SELECT 'cx-' || SUBSTR(SHA2(fc.doc_id || '|' || LOWER(TRIM(fc.text)), 256), 1, 16) AS id, fc.*
      FROM CORE.FACT_CANDIDATES fc
      WHERE NOT fc.applied AND fc.text IS NOT NULL
      QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY fc.confidence DESC) = 1
    ),
    prev AS (
      -- the current fact this candidate replaces: same area + kind + subject, older, different content
      SELECT c.id AS new_id, f.id AS old_id
      FROM c JOIN CORE.FACTS f
        ON f.area_id = c.area_id AND f.kind = c.kind
       AND LOWER(COALESCE(f.subject, '')) = LOWER(COALESCE(c.subject, ''))
       AND f.superseded_by IS NULL AND f.valid_to IS NULL
       AND f.valid_from < c.valid_from
       AND LOWER(TRIM(f.text)) <> LOWER(TRIM(c.text))
      QUALIFY ROW_NUMBER() OVER (PARTITION BY c.id ORDER BY f.valid_from DESC) = 1
    )
    SELECT c.*, prev.old_id,
           -- a claim is "said" only if its quote is literally in the receipt; otherwise it is labelled inferred
           IFF(c.quote IS NOT NULL AND CONTAINS(LOWER(d.text), LOWER(c.quote)), 'said', 'inferred') AS epistemic
    FROM c
    LEFT JOIN prev ON prev.new_id = c.id
    LEFT JOIN CORE.SOURCE_DOCS d ON d.id = c.doc_id
  ) s
  ON t.id = s.id
  WHEN NOT MATCHED THEN INSERT
    (id, text, kind, area_id, stated_by, source_doc_ids, quote, valid_from, valid_to, learned_at,
     supersedes, superseded_by, epistemic, verification, visibility, confidence, review_status,
     subject, extractor, owner_team)
  VALUES
    (s.id, s.text, s.kind, s.area_id, s.stated_by, ARRAY_CONSTRUCT(s.doc_id), s.quote, s.valid_from, NULL,
     CURRENT_TIMESTAMP()::TIMESTAMP_NTZ, s.old_id, NULL, s.epistemic, 'unverified', s.visibility,
     s.confidence, 'pending', s.subject, s.extractor, s.owner_team);
  n_new := SQLROWCOUNT;

  -- 2) Close the replaced facts (valid time ends where the new one begins).
  UPDATE CORE.FACTS f_old
     SET valid_to = f_new.valid_from,
         superseded_by = f_new.id
    FROM CORE.FACTS f_new
   WHERE f_new.supersedes = f_old.id
     AND f_old.superseded_by IS NULL;
  n_closed := SQLROWCOUNT;

  UPDATE CORE.FACT_CANDIDATES SET applied = TRUE WHERE NOT applied;
  COMMIT;
  RETURN 'facts inserted: ' || n_new || ', superseded: ' || n_closed;
END;
$$;

CREATE OR REPLACE TASK CORE.T_SUPERSEDE
  WAREHOUSE = KEEPLINE_WH
  COMMENT = 'Keepline: apply supersession after each extraction run.'
  AFTER CORE.T_EXTRACT
AS
  CALL CORE.APPLY_SUPERSESSION();

-- -------------------------------------------------------------------------------------------------
-- Valid time: what was true in the world on a given date (the agent answers "as of" a question date).
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION CORE.FACTS_AS_OF(as_of DATE)
  RETURNS TABLE (id STRING, text STRING, kind STRING, area_id STRING, stated_by STRING,
                 valid_from DATE, valid_to DATE, supersedes STRING, confidence FLOAT)
  COMMENT = 'Facts true in the world on as_of (bi-temporal valid time). Row access policy still applies.'
AS
$$
  SELECT id, text, kind, area_id, stated_by, valid_from, valid_to, supersedes, confidence
  FROM CORE.FACTS
  WHERE valid_from <= as_of
    AND (valid_to IS NULL OR valid_to > as_of)
    AND review_status <> 'rejected'
$$;

-- Supersession chain for a fact, oldest -> newest (Decision History page).
CREATE OR REPLACE VIEW CORE.SUPERSESSION_EDGES AS
  SELECT f.id AS fact_id, f.supersedes AS replaces_id, f.superseded_by AS replaced_by_id,
         f.valid_from, f.valid_to, f.text, f.area_id, f.kind,
         (f.valid_to IS NULL AND f.superseded_by IS NULL) AS is_current
  FROM CORE.FACTS f;

-- -------------------------------------------------------------------------------------------------
-- Transaction time via Time Travel: "what did we believe <hours> ago?" and "what changed since then?"
-- Dynamic SQL because AT(OFFSET => ...) needs a constant; the argument is a NUMBER so it is injection-safe.
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE APP.WHAT_DID_WE_BELIEVE(hours_ago NUMBER, area STRING)
  RETURNS TABLE (id STRING, text STRING, kind STRING, valid_from DATE, valid_to DATE, superseded_by STRING)
  LANGUAGE SQL
  EXECUTE AS CALLER      -- caller's rights: the row access policy still decides what the asker sees
AS
$$
DECLARE
  secs NUMBER DEFAULT -1 * ROUND(hours_ago * 3600);
  res RESULTSET;
BEGIN
  res := (EXECUTE IMMEDIATE
    'SELECT id, text, kind, valid_from, valid_to, superseded_by FROM KEEPLINE.CORE.FACTS AT(OFFSET => ' || secs || ')'
    || ' WHERE area_id = ? ORDER BY valid_from' USING (area));
  RETURN TABLE(res);
END;
$$;

CREATE OR REPLACE PROCEDURE APP.BELIEF_CHANGES_SINCE(hours_ago NUMBER)
  RETURNS TABLE (id STRING, text STRING, action STRING, is_update BOOLEAN, superseded_by STRING)
  LANGUAGE SQL
  EXECUTE AS CALLER
AS
$$
DECLARE
  secs NUMBER DEFAULT -1 * ROUND(hours_ago * 3600);
  res RESULTSET;
BEGIN
  res := (EXECUTE IMMEDIATE
    'SELECT id, text, METADATA$ACTION, METADATA$ISUPDATE, superseded_by '
    || 'FROM KEEPLINE.CORE.FACTS CHANGES(INFORMATION => DEFAULT) AT(OFFSET => ' || secs || ')');
  RETURN TABLE(res);
END;
$$;

GRANT USAGE ON FUNCTION  CORE.FACTS_AS_OF(DATE)                  TO ROLE KEEPLINE_APP;
GRANT USAGE ON PROCEDURE APP.WHAT_DID_WE_BELIEVE(NUMBER, STRING)  TO ROLE KEEPLINE_APP;
GRANT USAGE ON PROCEDURE APP.BELIEF_CHANGES_SINCE(NUMBER)         TO ROLE KEEPLINE_APP;

-- Examples (run by hand once the tables are older than the offset):
--   CALL APP.WHAT_DID_WE_BELIEVE(24, 'reconciliation');   -- what we believed yesterday
--   CALL APP.BELIEF_CHANGES_SINCE(24);                     -- which beliefs changed since yesterday
--   SELECT * FROM TABLE(CORE.FACTS_AS_OF('2026-05-01'::DATE)) WHERE area_id = 'reconciliation';
--   SELECT text, valid_from, valid_to FROM KEEPLINE.CORE.FACTS AT(OFFSET => -60*60*24) WHERE kind = 'landmine';

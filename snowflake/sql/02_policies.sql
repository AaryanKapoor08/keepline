-- =================================================================================================
-- Keepline on Snowflake · 02_policies.sql
-- Governance that makes the product trustworthy: answers never exceed what the asker could already see.
--
--   1. Row access policy  CORE.RAP_VISIBILITY  on SOURCE_DOCS and FACTS
--        public  -> everyone with the app role
--        team    -> members of the owning team (role) or listed participants
--        private -> listed participants only (DMs / 1:1 email); the pipeline sees a private source only
--                   after every participant opted in (CORE.SOURCE_CONTROLS -> ACL '__pipeline__')
--   2. Masking policy     CORE.MASK_PRIVATE_TEXT  hides private message text from anyone who is not a
--        participant, even roles that can see the row (e.g. KEEPLINE_ADMIN for ops, KEEPLINE_AUDITOR).
--   3. Aggregation policy CORE.AGG_MIN_GROUP_5 on EXPERTISE and QUERY_LOG: ad-hoc analysis must aggregate
--        over >= 5 rows, so nobody can build per-person behaviour scores. Risk scoring runs inside
--        owner's-rights procedures (06_procs.sql) that only ever emit topic-level results.
--
-- Docs:
--   https://docs.snowflake.com/en/sql-reference/sql/create-row-access-policy
--   https://docs.snowflake.com/en/user-guide/security-row-intro           (mapping tables, IS_ROLE_IN_SESSION)
--   https://docs.snowflake.com/en/sql-reference/sql/create-masking-policy (conditional masking: USING (...))
--   https://docs.snowflake.com/en/sql-reference/sql/create-aggregation-policy
--   https://docs.snowflake.com/en/developer-guide/udf/sql/udf-sql-scalar-functions (MEMOIZABLE)
-- =================================================================================================

USE ROLE KEEPLINE_ADMIN;
USE WAREHOUSE KEEPLINE_WH;
USE DATABASE KEEPLINE;
USE SCHEMA CORE;

-- The asker. Memoizable so the lookup runs once per query, not once per row.
CREATE OR REPLACE FUNCTION CORE.CURRENT_PERSON_ID()
  RETURNS STRING
  MEMOIZABLE
  COMMENT = 'Keepline person id of CURRENT_USER() (CORE.USER_PERSON_MAP).'
AS $$
  SELECT MAX(person_id) FROM CORE.USER_PERSON_MAP WHERE snowflake_user = CURRENT_USER()
$$;

-- Policies must be detached before they can be replaced; this makes the file re-runnable.
ALTER TABLE IF EXISTS CORE.SOURCE_DOCS DROP ALL ROW ACCESS POLICIES;
ALTER TABLE IF EXISTS CORE.FACTS       DROP ALL ROW ACCESS POLICIES;
ALTER TABLE IF EXISTS CORE.SOURCE_DOCS MODIFY COLUMN text UNSET MASKING POLICY;
ALTER TABLE IF EXISTS CORE.FACTS       MODIFY COLUMN quote UNSET MASKING POLICY;
ALTER TABLE IF EXISTS CORE.EXPERTISE   UNSET AGGREGATION POLICY;
ALTER TABLE IF EXISTS CORE.QUERY_LOG   UNSET AGGREGATION POLICY;

-- -------------------------------------------------------------------------------------------------
-- 1. Row access: visibility-aware, participant-aware, team-aware.
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE ROW ACCESS POLICY CORE.RAP_VISIBILITY
  AS (p_object_id STRING, p_visibility STRING, p_owner_team STRING)
  RETURNS BOOLEAN ->
    -- Public sources: anyone who can use the app.
    COALESCE(p_visibility, 'public') = 'public'
    -- Ops/admin see team + private *rows* (to run the pipeline); private *text* stays masked below.
    OR IS_ROLE_IN_SESSION('KEEPLINE_ADMIN')
    -- Team sources: members of the owning team, via their team role.
    OR (p_visibility = 'team' AND EXISTS (
          SELECT 1 FROM CORE.TEAM_ROLES tr
          WHERE tr.team = p_owner_team AND IS_ROLE_IN_SESSION(tr.role_name)))
    -- Team or private: explicit participants.
    OR (p_visibility IN ('team', 'private') AND EXISTS (
          SELECT 1 FROM CORE.ACL a
          WHERE a.object_id = p_object_id AND a.person_id = CORE.CURRENT_PERSON_ID()))
    -- Extraction pipeline: private sources only when every participant opted in.
    OR (IS_ROLE_IN_SESSION('KEEPLINE_PIPELINE') AND (
          p_visibility = 'team' OR EXISTS (
            SELECT 1 FROM CORE.ACL a WHERE a.object_id = p_object_id AND a.person_id = '__pipeline__')))
  COMMENT = 'Keepline: answers never exceed what the asker can already see.';

ALTER TABLE CORE.SOURCE_DOCS ADD ROW ACCESS POLICY CORE.RAP_VISIBILITY ON (id, visibility, owner_team);
ALTER TABLE CORE.FACTS       ADD ROW ACCESS POLICY CORE.RAP_VISIBILITY ON (id, visibility, owner_team);

-- -------------------------------------------------------------------------------------------------
-- 2. Masking: DM text is visible to participants only. Conditional masking uses the visibility + id columns.
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE MASKING POLICY CORE.MASK_PRIVATE_TEXT
  AS (val STRING, p_visibility STRING, p_object_id STRING)
  RETURNS STRING ->
    CASE
      WHEN COALESCE(p_visibility, 'public') <> 'private' THEN val
      WHEN EXISTS (SELECT 1 FROM CORE.ACL a
                   WHERE a.object_id = p_object_id AND a.person_id = CORE.CURRENT_PERSON_ID()) THEN val
      WHEN IS_ROLE_IN_SESSION('KEEPLINE_PIPELINE') AND EXISTS (
             SELECT 1 FROM CORE.ACL a WHERE a.object_id = p_object_id AND a.person_id = '__pipeline__') THEN val
      ELSE '[private message - visible to participants only]'
    END
  COMMENT = 'Keepline: DMs masked for everyone but their participants (and the pipeline, if opted in).';

ALTER TABLE CORE.SOURCE_DOCS MODIFY COLUMN text  SET MASKING POLICY CORE.MASK_PRIVATE_TEXT USING (text, visibility, id);
ALTER TABLE CORE.FACTS       MODIFY COLUMN quote SET MASKING POLICY CORE.MASK_PRIVATE_TEXT USING (quote, visibility, id);

-- -------------------------------------------------------------------------------------------------
-- 3. Aggregation: no per-person behaviour scoring. Groups of >= 5 or nothing.
--    The admin role (which owns the risk/handoff procedures) is exempt so owner's-rights procedures can
--    compute topic-level bus factor; those procedures never return per-person activity counts.
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE AGGREGATION POLICY CORE.AGG_MIN_GROUP_5
  AS () RETURNS AGGREGATION_CONSTRAINT ->
    CASE
      WHEN IS_ROLE_IN_SESSION('KEEPLINE_ADMIN') THEN NO_AGGREGATION_CONSTRAINT()
      ELSE AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => 5)
    END
  COMMENT = 'Keepline privacy principle: aggregates over fewer than 5 people are never shown.';

ALTER TABLE CORE.EXPERTISE SET AGGREGATION POLICY CORE.AGG_MIN_GROUP_5;
ALTER TABLE CORE.QUERY_LOG SET AGGREGATION POLICY CORE.AGG_MIN_GROUP_5;

-- -------------------------------------------------------------------------------------------------
-- Opt-in plumbing: when every participant of a private source has include_private = TRUE for that
-- source type, the pipeline may read it. Recomputed by task in 03_extract.sql.
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE CORE.REFRESH_PIPELINE_OPT_INS()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS
$$
BEGIN
  DELETE FROM CORE.ACL WHERE person_id = '__pipeline__';
  INSERT INTO CORE.ACL (object_id, person_id)
    SELECT d.id, '__pipeline__'
    FROM CORE.SOURCE_DOCS d, LATERAL FLATTEN(input => d.participants) p
    LEFT JOIN CORE.SOURCE_CONTROLS sc
      ON sc.person_id = p.value::STRING AND sc.source_type = d.source_type
    WHERE d.visibility = 'private'
    GROUP BY d.id
    HAVING COUNT(*) > 0 AND COUNT_IF(COALESCE(sc.include_private, FALSE)) = COUNT(*);
  RETURN 'pipeline opt-ins refreshed';
END;
$$;

-- -------------------------------------------------------------------------------------------------
-- Employee-facing, owner's-rights accessor: "who asked about my knowledge?" returns only rows whose
-- answers relied on facts the *caller* stated. This is the only per-person view of the query log,
-- and it is about the caller themself.
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE APP.MY_KNOWLEDGE_QUERY_LOG(max_rows NUMBER)
  RETURNS TABLE (ts TIMESTAMP_LTZ, asker_id STRING, question STRING, action STRING, area_id STRING)
  LANGUAGE SQL
  EXECUTE AS OWNER
AS
$$
DECLARE
  res RESULTSET DEFAULT (
    SELECT DISTINCT q.ts, q.asker_id, q.question, q.action, q.area_id
    FROM CORE.QUERY_LOG q, LATERAL FLATTEN(input => q.fact_ids) f
    JOIN CORE.FACTS fa ON fa.id = f.value::STRING
    WHERE fa.stated_by = CORE.CURRENT_PERSON_ID()
    ORDER BY q.ts DESC
    LIMIT :max_rows);
BEGIN
  RETURN TABLE(res);
END;
$$;

GRANT USAGE ON FUNCTION  CORE.CURRENT_PERSON_ID() TO ROLE KEEPLINE_APP;
GRANT USAGE ON PROCEDURE APP.MY_KNOWLEDGE_QUERY_LOG(NUMBER) TO ROLE KEEPLINE_APP;
-- The app may log questions and record reviews, but never edit facts directly.
GRANT INSERT ON TABLE CORE.QUERY_LOG     TO ROLE KEEPLINE_APP;
GRANT INSERT ON TABLE CORE.REVIEW_EVENTS TO ROLE KEEPLINE_APP;
GRANT INSERT, UPDATE ON TABLE APP.HANDOFF_SIGNOFFS TO ROLE KEEPLINE_APP;
GRANT INSERT, UPDATE ON TABLE CORE.SOURCE_CONTROLS TO ROLE KEEPLINE_APP;
-- Mapping tables are policy internals: nobody but the admin reads them directly.
REVOKE SELECT ON TABLE CORE.ACL             FROM ROLE KEEPLINE_APP;
REVOKE SELECT ON TABLE CORE.USER_PERSON_MAP FROM ROLE KEEPLINE_APP;
REVOKE SELECT ON TABLE CORE.ACL             FROM ROLE KEEPLINE_AUDITOR;
REVOKE SELECT ON TABLE CORE.USER_PERSON_MAP FROM ROLE KEEPLINE_AUDITOR;

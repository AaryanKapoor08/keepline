-- =================================================================================================
-- Keepline on Snowflake · 00_setup.sql
-- Account-level objects: warehouse, database, schemas, roles, grants.
--
-- Run as a role that can create roles and warehouses (ACCOUNTADMIN, or SYSADMIN + SECURITYADMIN).
-- Idempotent: safe to re-run.
--
-- Docs:
--   https://docs.snowflake.com/en/sql-reference/sql/create-warehouse
--   https://docs.snowflake.com/en/user-guide/security-access-control-overview   (role hierarchy)
--   https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql#required-privileges (SNOWFLAKE.CORTEX_USER)
--
-- Layout
--   KEEPLINE.RAW   landing zone: work-tool exports exactly as received (VARIANT), never edited
--   KEEPLINE.CORE  the versioned, receipt-backed memory graph (people, areas, documents, facts, edges ...)
--   KEEPLINE.APP   what the product reads: risk snapshots, handoff sign-offs, semantic view, agent, Streamlit
--
-- Roles
--   KEEPLINE_ADMIN      owns every object; runs deploy + pipeline tasks
--   KEEPLINE_PIPELINE   runs extraction tasks (sees public/team data and opted-in private data only)
--   KEEPLINE_APP        the app / agent service role: read CORE through policies, write query log + reviews
--   KEEPLINE_TEAM_*     one per team; used by row access policies to open team-visibility channels
--   KEEPLINE_AUDITOR    compliance read-only: sees row metadata, never private message text (masked)
-- =================================================================================================

USE ROLE SYSADMIN;

CREATE WAREHOUSE IF NOT EXISTS KEEPLINE_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60                 -- seconds; the demo is bursty, don't pay for idle
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Keepline: extraction tasks, risk scoring, Cortex Search refresh, Streamlit';

CREATE DATABASE IF NOT EXISTS KEEPLINE
  DATA_RETENTION_TIME_IN_DAYS = 30  -- Time Travel window: "what did we believe last month?"
  COMMENT = 'Keepline: versioned, receipt-backed company memory. Data never leaves this account.';

CREATE SCHEMA IF NOT EXISTS KEEPLINE.RAW  COMMENT = 'Landing zone: work-tool exports as received (immutable).';
CREATE SCHEMA IF NOT EXISTS KEEPLINE.CORE COMMENT = 'Bi-temporal memory graph: facts with receipts, supersession, expertise.';
CREATE SCHEMA IF NOT EXISTS KEEPLINE.APP  COMMENT = 'Product surface: risk snapshots, sign-offs, semantic view, agent, Streamlit.';

-- -------------------------------------------------------------------------------------------------
-- Roles
-- -------------------------------------------------------------------------------------------------
USE ROLE SECURITYADMIN;

CREATE ROLE IF NOT EXISTS KEEPLINE_ADMIN    COMMENT = 'Owns Keepline objects; runs deploy.';
CREATE ROLE IF NOT EXISTS KEEPLINE_PIPELINE COMMENT = 'Runs extraction / normalization tasks.';
CREATE ROLE IF NOT EXISTS KEEPLINE_APP      COMMENT = 'Keepline app + Cortex Agent service role.';
CREATE ROLE IF NOT EXISTS KEEPLINE_AUDITOR  COMMENT = 'Compliance read-only; private text is masked.';

-- One role per team. Row access policies open team-visibility sources to members of the owning team.
CREATE ROLE IF NOT EXISTS KEEPLINE_TEAM_ENGINEERING;
CREATE ROLE IF NOT EXISTS KEEPLINE_TEAM_FINANCE;
CREATE ROLE IF NOT EXISTS KEEPLINE_TEAM_OPERATIONS;
CREATE ROLE IF NOT EXISTS KEEPLINE_TEAM_MEMBER_SERVICES;
CREATE ROLE IF NOT EXISTS KEEPLINE_TEAM_LEADERSHIP;
CREATE ROLE IF NOT EXISTS KEEPLINE_TEAM_IT;

-- Hierarchy: team roles inherit the app's read surface; admin sits under SYSADMIN (best practice).
GRANT ROLE KEEPLINE_APP TO ROLE KEEPLINE_TEAM_ENGINEERING;
GRANT ROLE KEEPLINE_APP TO ROLE KEEPLINE_TEAM_FINANCE;
GRANT ROLE KEEPLINE_APP TO ROLE KEEPLINE_TEAM_OPERATIONS;
GRANT ROLE KEEPLINE_APP TO ROLE KEEPLINE_TEAM_MEMBER_SERVICES;
GRANT ROLE KEEPLINE_APP TO ROLE KEEPLINE_TEAM_LEADERSHIP;
GRANT ROLE KEEPLINE_APP TO ROLE KEEPLINE_TEAM_IT;
GRANT ROLE KEEPLINE_PIPELINE TO ROLE KEEPLINE_ADMIN;
GRANT ROLE KEEPLINE_APP      TO ROLE KEEPLINE_ADMIN;
GRANT ROLE KEEPLINE_AUDITOR  TO ROLE KEEPLINE_ADMIN;
GRANT ROLE KEEPLINE_ADMIN    TO ROLE SYSADMIN;

-- -------------------------------------------------------------------------------------------------
-- Ownership + privileges
-- -------------------------------------------------------------------------------------------------
USE ROLE SYSADMIN;

GRANT OWNERSHIP ON DATABASE KEEPLINE       TO ROLE KEEPLINE_ADMIN COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA   KEEPLINE.RAW   TO ROLE KEEPLINE_ADMIN COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA   KEEPLINE.CORE  TO ROLE KEEPLINE_ADMIN COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA   KEEPLINE.APP   TO ROLE KEEPLINE_ADMIN COPY CURRENT GRANTS;
GRANT USAGE, OPERATE ON WAREHOUSE KEEPLINE_WH TO ROLE KEEPLINE_ADMIN;
GRANT USAGE ON WAREHOUSE KEEPLINE_WH TO ROLE KEEPLINE_PIPELINE;
GRANT USAGE ON WAREHOUSE KEEPLINE_WH TO ROLE KEEPLINE_APP;
GRANT USAGE ON WAREHOUSE KEEPLINE_WH TO ROLE KEEPLINE_AUDITOR;

USE ROLE ACCOUNTADMIN;
-- Cortex AI functions (AI_COMPLETE, AI_EXTRACT), Cortex Search, Analyst and Agents require this database role.
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE KEEPLINE_ADMIN;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE KEEPLINE_PIPELINE;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE KEEPLINE_APP;
-- Tasks run on the admin's behalf (serverless-free: they use KEEPLINE_WH).
GRANT EXECUTE TASK ON ACCOUNT TO ROLE KEEPLINE_ADMIN;
-- Policies are created by the admin and applied inside the Keepline database only.
GRANT CREATE ROW ACCESS POLICY  ON SCHEMA KEEPLINE.CORE TO ROLE KEEPLINE_ADMIN;
GRANT CREATE MASKING POLICY     ON SCHEMA KEEPLINE.CORE TO ROLE KEEPLINE_ADMIN;
GRANT CREATE AGGREGATION POLICY ON SCHEMA KEEPLINE.CORE TO ROLE KEEPLINE_ADMIN;

USE ROLE KEEPLINE_ADMIN;
USE WAREHOUSE KEEPLINE_WH;
USE DATABASE KEEPLINE;

-- Read surface for the app role. Row access / masking / aggregation policies (02_policies.sql) decide
-- *which rows* each caller actually sees; these grants only decide which objects exist for them.
GRANT USAGE ON DATABASE KEEPLINE TO ROLE KEEPLINE_APP;
GRANT USAGE ON SCHEMA KEEPLINE.CORE TO ROLE KEEPLINE_APP;
GRANT USAGE ON SCHEMA KEEPLINE.APP  TO ROLE KEEPLINE_APP;
GRANT SELECT ON FUTURE TABLES IN SCHEMA KEEPLINE.CORE TO ROLE KEEPLINE_APP;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA KEEPLINE.CORE TO ROLE KEEPLINE_APP;
GRANT SELECT ON FUTURE TABLES IN SCHEMA KEEPLINE.APP  TO ROLE KEEPLINE_APP;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA KEEPLINE.APP  TO ROLE KEEPLINE_APP;

GRANT USAGE ON DATABASE KEEPLINE TO ROLE KEEPLINE_PIPELINE;
GRANT USAGE ON SCHEMA KEEPLINE.RAW  TO ROLE KEEPLINE_PIPELINE;
GRANT USAGE ON SCHEMA KEEPLINE.CORE TO ROLE KEEPLINE_PIPELINE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA KEEPLINE.RAW TO ROLE KEEPLINE_PIPELINE;

GRANT USAGE ON DATABASE KEEPLINE TO ROLE KEEPLINE_AUDITOR;
GRANT USAGE ON SCHEMA KEEPLINE.CORE TO ROLE KEEPLINE_AUDITOR;
GRANT SELECT ON FUTURE TABLES IN SCHEMA KEEPLINE.CORE TO ROLE KEEPLINE_AUDITOR;

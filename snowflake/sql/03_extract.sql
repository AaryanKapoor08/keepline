-- =================================================================================================
-- Keepline on Snowflake · 03_extract.sql
-- RAW exports -> CORE.DOCUMENTS (normalize + area linking + ACL) -> Cortex extraction -> FACT_CANDIDATES.
-- Incremental: a stream on DOCUMENTS feeds a task graph, so new messages become facts within minutes,
-- and the LLM only ever sees each message once.
--
--   T_NORMALIZE   (every 15 min)   CALL CORE.NORMALIZE_RAW()
--     └─ T_EXTRACT  (stream has data) AI_EXTRACT entities + AI_COMPLETE(response_format => JSON schema) facts
--          └─ T_SUPERSEDE (04_temporal.sql)  MERGE candidates into FACTS with supersession
--
-- Docs:
--   https://docs.snowflake.com/en/sql-reference/functions/ai_complete-single-string   (model, prompt, model_parameters, response_format)
--   https://docs.snowflake.com/en/user-guide/snowflake-cortex/complete-structured-outputs ({'type':'json','schema':{...}}, enum, arrays)
--   https://docs.snowflake.com/en/sql-reference/functions/ai_extract                  (text => , responseFormat => , scores => TRUE)
--   https://docs.snowflake.com/en/sql-reference/sql/create-stream                     (APPEND_ONLY)
--   https://docs.snowflake.com/en/sql-reference/sql/create-task                       (SCHEDULE, AFTER, WHEN SYSTEM$STREAM_HAS_DATA)
--
-- Privacy: private sources are never sent to the model unless every participant opted in
-- (CORE.ACL '__pipeline__', maintained by CORE.REFRESH_PIPELINE_OPT_INS in 02_policies.sql).
-- Cortex runs inside Snowflake's boundary: prompts and data are not used to train models.
-- =================================================================================================

USE ROLE KEEPLINE_ADMIN;
USE WAREHOUSE KEEPLINE_WH;
USE DATABASE KEEPLINE;
USE SCHEMA CORE;

-- -------------------------------------------------------------------------------------------------
-- Normalization: RAW VARIANT -> typed CORE tables. Deterministic, idempotent (MERGE on id).
-- Area linking is keyword-based (customer-provided lexicon in AREAS.keywords_json): cheap, explainable,
-- and identical to the local engine; Cortex adds facts on top of it, it does not replace it.
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE CORE.NORMALIZE_RAW()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS
$$
BEGIN
  MERGE INTO CORE.PEOPLE t
  USING (
    SELECT record:id::STRING AS id, record:name::STRING AS name, record:role::STRING AS role,
           record:team::STRING AS team, record:email::STRING AS email,
           TRY_TO_DATE(record:start_date::STRING) AS start_date,
           TRY_TO_DATE(record:departure_date::STRING) AS departure_date,
           record:departure_type::STRING AS departure_type, record:manager_id::STRING AS manager_id
    FROM RAW.ORG_PEOPLE
    QUALIFY ROW_NUMBER() OVER (PARTITION BY record:id ORDER BY loaded_at DESC) = 1
  ) s ON t.id = s.id
  WHEN MATCHED THEN UPDATE SET name = s.name, role = s.role, team = s.team, email = s.email,
       start_date = s.start_date, departure_date = s.departure_date, departure_type = s.departure_type,
       manager_id = s.manager_id
  WHEN NOT MATCHED THEN INSERT (id, name, role, team, email, start_date, departure_date, departure_type, manager_id)
       VALUES (s.id, s.name, s.role, s.team, s.email, s.start_date, s.departure_date, s.departure_type, s.manager_id);

  MERGE INTO CORE.AREAS t
  USING (
    SELECT record:id::STRING AS id, record:name::STRING AS name, record:description::STRING AS description,
           record:keywords::ARRAY AS keywords_json, COALESCE(record:systems::ARRAY, ARRAY_CONSTRUCT()) AS systems_json,
           COALESCE(record:criticality::NUMBER, 2) AS criticality
    FROM RAW.ORG_AREAS
    QUALIFY ROW_NUMBER() OVER (PARTITION BY record:id ORDER BY loaded_at DESC) = 1
  ) s ON t.id = s.id
  WHEN MATCHED THEN UPDATE SET name = s.name, description = s.description, keywords_json = s.keywords_json,
       systems_json = s.systems_json, criticality = s.criticality
  WHEN NOT MATCHED THEN INSERT (id, name, description, keywords_json, systems_json, criticality)
       VALUES (s.id, s.name, s.description, s.keywords_json, s.systems_json, s.criticality);

  -- Source docs + keyword area linking (best area = most keyword hits; ties -> higher criticality).
  MERGE INTO CORE.DOCUMENTS t
  USING (
    WITH m AS (
      SELECT record:id::STRING AS id, record:source_type::STRING AS source_type,
             record:author_id::STRING AS author_id, TRY_TO_TIMESTAMP_NTZ(record:timestamp::STRING) AS ts,
             record:text::STRING AS text, record:container::STRING AS container,
             record:thread_id::STRING AS thread_id, record:title::STRING AS title,
             COALESCE(record:participants::ARRAY, ARRAY_CONSTRUCT()) AS participants_json,
             COALESCE(record:visibility::STRING, 'public') AS visibility,
             record:url::STRING AS url, record:meta AS meta_json,
             record:meta:status::STRING AS ticket_status, record:meta:assignee::STRING AS ticket_assignee,
             record:meta:closed_at::STRING AS ticket_closed_at
      FROM RAW.MESSAGES
      QUALIFY ROW_NUMBER() OVER (PARTITION BY record:id ORDER BY loaded_at DESC) = 1
    ),
    hits AS (
      SELECT m.id, a.id AS area_id, a.criticality,
             COUNT_IF(CONTAINS(LOWER(COALESCE(m.title, '') || ' ' || m.text), LOWER(k.value::STRING))) AS n_hits
      FROM m, CORE.AREAS a, LATERAL FLATTEN(input => a.keywords_json) k
      GROUP BY m.id, a.id, a.criticality
      HAVING n_hits > 0
      QUALIFY ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY n_hits DESC, a.criticality DESC, a.id) = 1
    )
    SELECT m.*, h.area_id, p.team AS owner_team
    FROM m LEFT JOIN hits h ON h.id = m.id LEFT JOIN CORE.PEOPLE p ON p.id = m.author_id
  ) s ON t.id = s.id
  WHEN MATCHED THEN UPDATE SET text = s.text, title = s.title, meta_json = s.meta_json,
       ticket_status = s.ticket_status, ticket_assignee = s.ticket_assignee, ticket_closed_at = s.ticket_closed_at,
       area_id = COALESCE(t.area_id, s.area_id),   -- keep a better (DOC_AREAS) link if one was loaded
       participants_json = s.participants_json, visibility = s.visibility, owner_team = s.owner_team
  WHEN NOT MATCHED THEN INSERT (id, source_type, author_id, ts, text, container, thread_id, title,
       participants_json, visibility, url, meta_json, ticket_status, ticket_assignee, ticket_closed_at,
       area_id, owner_team)
       VALUES (s.id, s.source_type, s.author_id, s.ts, s.text, s.container, s.thread_id, s.title,
       s.participants_json, s.visibility, s.url, s.meta_json, s.ticket_status, s.ticket_assignee,
       s.ticket_closed_at, s.area_id, s.owner_team);

  -- Participants of non-public sources become ACL rows (the row access policy's mapping table).
  MERGE INTO CORE.ACL t
  USING (
    SELECT DISTINCT d.id AS object_id, p.value::STRING AS person_id
    FROM CORE.DOCUMENTS d, LATERAL FLATTEN(input => d.participants_json) p
    WHERE d.visibility IN ('team', 'private')
  ) s ON t.object_id = s.object_id AND t.person_id = s.person_id
  WHEN NOT MATCHED THEN INSERT (object_id, person_id) VALUES (s.object_id, s.person_id);

  CALL CORE.REFRESH_PIPELINE_OPT_INS();
  RETURN 'normalized';
END;
$$;

-- -------------------------------------------------------------------------------------------------
-- Stream: only new receipts are ever sent to the model.
-- -------------------------------------------------------------------------------------------------
CREATE STREAM IF NOT EXISTS CORE.DOCUMENTS_NEW
  ON TABLE CORE.DOCUMENTS
  APPEND_ONLY = TRUE
  COMMENT = 'New source docs awaiting Cortex extraction.';

-- -------------------------------------------------------------------------------------------------
-- Extraction over the batch drained from the stream.
--
--  * AI_EXTRACT: typed entity pull with per-field scores (systems, vendors, promised follow-ups, deadlines).
--  * AI_COMPLETE with response_format JSON schema: the list of durable facts, each with a verbatim quote
--    and a self-reported confidence. Kinds are constrained by an enum, so the output always parses.
--  Quotes are verified against the source text (CONTAINS) before a candidate is accepted; unquotable
--  claims are downgraded to epistemic = 'inferred' in 04_temporal.sql ("receipts, not vibes").
-- -------------------------------------------------------------------------------------------------
-- Extraction queue. The stream is drained into it by a DML INSERT (which is what advances the stream
-- offset); each run then processes at most MAX_DOCS queued docs, newest first. Cost is bounded per run,
-- and nothing is dropped: unprocessed docs wait for the next run.
CREATE TABLE IF NOT EXISTS CORE.EXTRACT_QUEUE (
  id STRING, source_type STRING, author_id STRING, ts TIMESTAMP_NTZ, text STRING, title STRING,
  area_id STRING, visibility STRING, owner_team STRING,
  batch_id STRING, processed BOOLEAN DEFAULT FALSE, queued_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE PROCEDURE CORE.EXTRACT_NEW_DOCS(MODEL STRING, MAX_DOCS NUMBER)
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
  COMMENT = 'Cortex extraction over at most MAX_DOCS queued docs (NULL = no bound; use deliberately).'
AS
$$
DECLARE
  run_id STRING DEFAULT UUID_STRING();
  n_docs NUMBER DEFAULT 0;
BEGIN
  INSERT INTO CORE.EXTRACT_QUEUE (id, source_type, author_id, ts, text, title, area_id, visibility, owner_team)
    SELECT s.id, s.source_type, s.author_id, s.ts, s.text, s.title, s.area_id, s.visibility, s.owner_team
    FROM CORE.DOCUMENTS_NEW s
    WHERE s.text IS NOT NULL
      AND (s.visibility <> 'private'
           OR EXISTS (SELECT 1 FROM CORE.ACL a WHERE a.object_id = s.id AND a.person_id = '__pipeline__'));

  UPDATE CORE.EXTRACT_QUEUE SET batch_id = :run_id
   WHERE id IN (SELECT id FROM CORE.EXTRACT_QUEUE
                WHERE NOT processed AND batch_id IS NULL
                ORDER BY ts DESC
                LIMIT :MAX_DOCS);
  n_docs := SQLROWCOUNT;

  INSERT INTO CORE.DOC_ENTITIES (doc_id, entities, scores)
    SELECT b.id, r:response, r:scoring:scores
    FROM (
      SELECT b.id,
             AI_EXTRACT(
               text => b.text,
               responseFormat => {
                 'systems':          'Which software systems, services or tools are mentioned?',
                 'vendor_contact':   'Which external vendor contact person (name and company) is mentioned, if any?',
                 'promised_followup':'What follow-up did the author promise to do, and by when, if any?',
                 'credential_location':'Where are credentials or secrets said to be stored (location only, never the secret)?',
                 'deadline':         'What date or recurring schedule is mentioned, if any?'
               },
               scores => TRUE) AS r
      FROM CORE.EXTRACT_QUEUE b WHERE b.batch_id = :run_id
    ) b;

  INSERT INTO CORE.FACT_CANDIDATES
    (doc_id, text, kind, area_id, subject, stated_by, quote, valid_from, confidence, visibility, owner_team, extractor)
  SELECT b.id,
         f.value:text::STRING,
         f.value:kind::STRING,
         b.area_id,
         f.value:subject::STRING,
         b.author_id,
         f.value:quote::STRING,
         COALESCE(TRY_TO_DATE(f.value:valid_from::STRING), b.ts::DATE),
         LEAST(GREATEST(COALESCE(f.value:confidence::FLOAT, 0.5), 0), 1)
           -- a quote that is not literally in the source can never be high-confidence
           * IFF(CONTAINS(LOWER(b.text), LOWER(COALESCE(f.value:quote::STRING, '~no-quote~'))), 1.0, 0.5),
         b.visibility,
         b.owner_team,
         'cortex'
  FROM (
    SELECT b.*,
           AI_COMPLETE(
             model => :model,
             prompt => 'You extract durable operational knowledge from a workplace message for a credit union''s '
                    || 'knowledge-continuity system. Only extract statements that stay useful after the author leaves: '
                    || 'who has access to what (never secrets themselves), vendor contacts, recurring tasks, landmines '
                    || '(things that break if done wrong), procedures, decisions (with the reason if given), ownership. '
                    || 'Every fact MUST include a verbatim quote copied from the message. If nothing durable is stated, '
                    || 'return an empty list. Do not guess.\n\n'
                    || 'Message (' || b.source_type || ', ' || TO_VARCHAR(b.ts, 'YYYY-MM-DD') || ', title: '
                    || COALESCE(b.title, '-') || '):\n' || b.text,
             model_parameters => {'temperature': 0, 'max_tokens': 2048},
             response_format => {
               'type': 'json',
               'schema': {
                 'type': 'object',
                 'properties': {
                   'facts': {
                     'type': 'array',
                     'items': {
                       'type': 'object',
                       'properties': {
                         'text':       {'type': 'string', 'description': 'One normalized, self-contained statement.'},
                         'kind':       {'type': 'string', 'enum': ['access', 'vendor_contact', 'recurring_task', 'landmine',
                                                                     'procedure', 'decision', 'owner', 'fact']},
                         'subject':    {'type': 'string', 'description': 'The system or entity the fact is about.'},
                         'quote':      {'type': 'string', 'description': 'Verbatim span from the message.'},
                         'valid_from': {'type': 'string', 'description': 'YYYY-MM-DD when it became true, if stated.'},
                         'confidence': {'type': 'number', 'description': '0..1 how clearly the message states it.'}
                       },
                       'required': ['text', 'kind', 'subject', 'quote', 'valid_from', 'confidence'],
                       'additionalProperties': false
                     }
                   }
                 },
                 'required': ['facts'],
                 'additionalProperties': false
               }
             }
           ) AS out
    FROM CORE.EXTRACT_QUEUE b WHERE b.batch_id = :run_id
  ) b,
  LATERAL FLATTEN(input => b.out:facts) f
  WHERE f.value:text IS NOT NULL;

  UPDATE CORE.EXTRACT_QUEUE SET processed = TRUE WHERE batch_id = :run_id;
  RETURN 'extracted facts from ' || n_docs || ' docs (batch ' || run_id || ')';
END;
$$;

-- -------------------------------------------------------------------------------------------------
-- Task graph (created SUSPENDED; deploy.py --resume-tasks enables it). Tasks run as KEEPLINE_ADMIN.
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE TASK CORE.T_NORMALIZE
  WAREHOUSE = KEEPLINE_WH
  SCHEDULE = '15 MINUTE'
  COMMENT = 'Keepline: RAW -> CORE normalization.'
AS
  CALL CORE.NORMALIZE_RAW();

CREATE OR REPLACE TASK CORE.T_EXTRACT
  WAREHOUSE = KEEPLINE_WH
  COMMENT = 'Keepline: Cortex extraction over new source docs only.'
  AFTER CORE.T_NORMALIZE
  WHEN SYSTEM$STREAM_HAS_DATA('CORE.DOCUMENTS_NEW')
AS
  CALL CORE.EXTRACT_NEW_DOCS('claude-sonnet-4-5', 200);   -- cost bound per run

-- Ad-hoc: run extraction once without the task graph (used by deploy.py --extract).
-- CALL CORE.NORMALIZE_RAW();
-- CALL CORE.EXTRACT_NEW_DOCS('claude-sonnet-4-5', 200);

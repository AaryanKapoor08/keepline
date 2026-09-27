-- Keepline memory schema (SQLite, local engine).
--
-- PORTABILITY NOTE: this file mirrors snowflake/sql/01_schema.sql 1:1. Keep it to portable SQL:
--   * types: TEXT / REAL / INTEGER only (Snowflake: VARCHAR / FLOAT / NUMBER; JSON text -> VARIANT via PARSE_JSON)
--   * no AUTOINCREMENT, no triggers, no partial indexes, no SQLite-only functions in DDL
--   * dates as ISO-8601 TEXT ('2026-05-16'), timestamps as ISO-8601 TEXT ('2026-05-16T09:12:00')
--   * list/dict fields stored as JSON text (column names end in _json)
--   * booleans as INTEGER 0/1
-- Bi-temporal facts: valid_from/valid_to = when true in the world; learned_at = when Keepline learned it.

CREATE TABLE IF NOT EXISTS people (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    role            TEXT,
    team            TEXT,
    email           TEXT,
    start_date      TEXT,
    departure_date  TEXT,
    departure_type  TEXT,
    manager_id      TEXT
);

CREATE TABLE IF NOT EXISTS areas (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    keywords_json   TEXT,
    systems_json    TEXT,
    criticality     INTEGER
);

CREATE TABLE IF NOT EXISTS documents (
    id                  TEXT PRIMARY KEY,
    source_type         TEXT NOT NULL,
    author_id           TEXT,
    ts                  TEXT NOT NULL,
    text                TEXT,
    container           TEXT,
    thread_id           TEXT,
    title               TEXT,
    participants_json   TEXT,
    visibility          TEXT,
    url                 TEXT,
    meta_json           TEXT,
    ticket_status       TEXT,     -- denormalised from meta for cheap open-ticket queries
    ticket_assignee     TEXT,
    ticket_closed_at    TEXT
);

-- Which areas a document is about (a doc can touch several).
CREATE TABLE IF NOT EXISTS doc_areas (
    doc_id      TEXT NOT NULL,
    area_id     TEXT NOT NULL,
    score       REAL,
    PRIMARY KEY (doc_id, area_id)
);

CREATE TABLE IF NOT EXISTS facts (
    id                  TEXT PRIMARY KEY,
    text                TEXT NOT NULL,
    kind                TEXT NOT NULL,
    area_id             TEXT,
    stated_by           TEXT,
    source_doc_ids_json TEXT,
    quote               TEXT,
    valid_from          TEXT NOT NULL,
    valid_to            TEXT,
    learned_at          TEXT,
    supersedes          TEXT,
    superseded_by       TEXT,
    epistemic           TEXT,
    verification        TEXT,
    visibility          TEXT,
    participants_json   TEXT,     -- who may see a TEAM/PRIVATE fact (from its source docs)
    confidence          REAL,
    review_status       TEXT,
    corrected_text      TEXT,
    subject             TEXT,
    extractor           TEXT
);

CREATE TABLE IF NOT EXISTS edges (
    src                     TEXT NOT NULL,
    dst                     TEXT NOT NULL,
    rel                     TEXT NOT NULL,
    weight                  REAL,
    valid_from              TEXT,
    valid_to                TEXT,
    evidence_doc_ids_json   TEXT
);

CREATE TABLE IF NOT EXISTS expertise (
    person_id               TEXT NOT NULL,
    area_id                 TEXT NOT NULL,
    score                   REAL,
    n_docs                  INTEGER,
    n_tickets_closed        INTEGER,
    n_facts_stated          INTEGER,
    n_answers               INTEGER,
    last_active             TEXT,
    confirmed_by_person     INTEGER,
    enough_data             INTEGER,
    PRIMARY KEY (person_id, area_id)
);

-- Two facts that disagree with no clear "update" signal: both kept, the weaker one marked contradicted.
CREATE TABLE IF NOT EXISTS conflicts (
    fact_id_a       TEXT NOT NULL,
    fact_id_b       TEXT NOT NULL,
    area_id         TEXT,
    subject         TEXT,
    note            TEXT,
    PRIMARY KEY (fact_id_a, fact_id_b)
);

CREATE TABLE IF NOT EXISTS query_log (
    id              TEXT PRIMARY KEY,
    asked_at        TEXT NOT NULL,
    asker_id        TEXT,
    question        TEXT,
    action          TEXT,
    area_id         TEXT,
    confidence      REAL,
    answer_text     TEXT,
    route_to_json   TEXT,
    fact_ids_json   TEXT
);

-- "Who asked what about my knowledge": one row per person whose facts/expertise an answer relied on.
CREATE TABLE IF NOT EXISTS query_about (
    query_id        TEXT NOT NULL,
    person_id       TEXT NOT NULL,
    PRIMARY KEY (query_id, person_id)
);

CREATE TABLE IF NOT EXISTS review_events (
    id              TEXT PRIMARY KEY,
    fact_id         TEXT NOT NULL,
    status          TEXT NOT NULL,
    corrected_text  TEXT,
    at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS build_meta (
    key             TEXT PRIMARY KEY,
    value           TEXT
);

CREATE INDEX IF NOT EXISTS ix_facts_area ON facts (area_id);
CREATE INDEX IF NOT EXISTS ix_facts_stated_by ON facts (stated_by);
CREATE INDEX IF NOT EXISTS ix_docs_author ON documents (author_id);
CREATE INDEX IF NOT EXISTS ix_doc_areas_area ON doc_areas (area_id);
CREATE INDEX IF NOT EXISTS ix_edges_src ON edges (src);
CREATE INDEX IF NOT EXISTS ix_query_about_person ON query_about (person_id);

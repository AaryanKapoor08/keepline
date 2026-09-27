-- =================================================================================================
-- Keepline on Snowflake · 06_procs.sql
-- Snowpark Python stored procedures: the product logic, next to the data.
--
--   APP.RISK_MAP(today, exclude_person)      -> TABLE   risk = importance x (1 - redundancy) x departure_likelihood
--   APP.REFRESH_RISK_SNAPSHOT(today)         -> STRING  baseline + one what-if per known departure -> AREA_RISK_SNAPSHOT
--   APP.HANDOFF_PACK(person_id, today)       -> VARIANT access, vendors, recurring tasks, unresolved work,
--                                                        landmines (with receipts), suggested owners, gap questions
--
-- These are the custom tools the Cortex Agent calls (agent/keepline_agent.json). They run with owner's
-- rights so they can compute topic-level bus factor under the min-group-size aggregation policy, and
-- they only ever return topic-level results: no per-person behaviour scores leave these procedures.
-- The scoring mirrors keepline/products/risk.py so local and Snowflake numbers agree.
--
-- Docs:
--   https://docs.snowflake.com/en/developer-guide/stored-procedure/python/procedure-python-writing
--   https://docs.snowflake.com/en/developer-guide/stored-procedure/stored-procedures-returning-tabular-data
--   https://docs.snowflake.com/en/sql-reference/sql/create-procedure  (RUNTIME_VERSION, PACKAGES, HANDLER)
-- =================================================================================================

USE ROLE KEEPLINE_ADMIN;
USE WAREHOUSE KEEPLINE_WH;
USE DATABASE KEEPLINE;
USE SCHEMA APP;

-- -------------------------------------------------------------------------------------------------
-- Risk map
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE APP.RISK_MAP(TODAY DATE, EXCLUDE_PERSON STRING)
  RETURNS TABLE (
    area_id STRING, area_name STRING, importance FLOAT, redundancy FLOAT, departure_likelihood FLOAT,
    risk FLOAT, bus_factor NUMBER, at_risk_person_id STRING, countdown_days NUMBER,
    n_facts NUMBER, n_landmines NUMBER, explanation STRING)
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python')
  HANDLER = 'run'
  COMMENT = 'Keepline risk map (topic-level). EXCLUDE_PERSON simulates a departure ("what if Sarah leaves?").'
  EXECUTE AS OWNER
AS
$$
import math
from datetime import date

STRONG = 0.35          # expertise score that counts toward bus factor
BASELINE_HAZARD = 0.05 # nobody is guaranteed to stay
TYPE_WEIGHT = {"resignation": 1.0, "retirement": 0.95, "contract_end": 0.9, "leave": 0.6}


def departure_likelihood(dep_date, dep_type, today):
    """~1 when a departure date is known and near; decays with distance; small hazard otherwise."""
    if dep_date is None:
        return BASELINE_HAZARD
    days = (dep_date - today).days
    if days <= 30:
        time_factor = 1.0
    else:
        time_factor = math.exp(-(days - 30) / 365.0)
    return max(BASELINE_HAZARD, TYPE_WEIGHT.get(dep_type or "resignation", 0.9) * time_factor)


def redundancy(bus_factor):
    """Saturating: 1 strong expert -> 0, 2 -> 0.5, 3 -> 0.75, ..."""
    return 0.0 if bus_factor <= 1 else 1.0 - 0.5 ** (bus_factor - 1)


def _norm(values):
    top = max(values.values() or [0]) or 1
    return {k: v / top for k, v in values.items()}


def score(session, today, exclude_person):
    people = {r["ID"]: r for r in session.sql(
        "SELECT id, name, departure_date, departure_type FROM KEEPLINE.CORE.PEOPLE").collect()}
    areas = session.sql("SELECT id, name, criticality FROM KEEPLINE.CORE.AREAS").collect()
    fact_counts = {r["AREA_ID"]: r.as_dict() for r in session.sql("""
        SELECT area_id, COUNT(*) AS n_facts, COUNT_IF(kind = 'landmine') AS n_landmines,
               COUNT_IF(kind = 'decision') AS n_decisions,
               COUNT_IF(kind IN ('access', 'vendor_contact', 'recurring_task')) AS n_dependencies
        FROM KEEPLINE.CORE.FACTS WHERE valid_to IS NULL AND superseded_by IS NULL GROUP BY area_id""").collect()}
    incidents = {r["AREA_ID"]: r["N"] for r in session.sql("""
        SELECT area_id, COUNT(*) AS n FROM KEEPLINE.CORE.DOCUMENTS
        WHERE source_type = 'ticket'
          AND (LOWER(meta_json:priority::STRING) IN ('high', 'highest', 'critical')
               OR title ILIKE '%incident%' OR title ILIKE '%outage%')
        GROUP BY area_id""").collect()}
    asks = {r["AREA_ID"]: r["N"] for r in session.sql(
        "SELECT area_id, COUNT(*) AS n FROM KEEPLINE.CORE.QUERY_LOG GROUP BY area_id").collect()}
    expertise = {}
    for r in session.sql("""
        SELECT person_id, area_id, score, n_docs, n_tickets_closed, n_facts_stated FROM KEEPLINE.CORE.EXPERTISE
        WHERE enough_data ORDER BY score DESC""").collect():
        if r["PERSON_ID"] != exclude_person and r["PERSON_ID"] in people:
            expertise.setdefault(r["AREA_ID"], []).append(r.as_dict())

    signals = {
        "incidents": _norm({a["ID"]: incidents.get(a["ID"], 0) for a in areas}),
        "decisions": _norm({a["ID"]: fact_counts.get(a["ID"], {}).get("N_DECISIONS", 0) for a in areas}),
        "landmines": _norm({a["ID"]: fact_counts.get(a["ID"], {}).get("N_LANDMINES", 0) for a in areas}),
        "dependencies": _norm({a["ID"]: fact_counts.get(a["ID"], {}).get("N_DEPENDENCIES", 0) for a in areas}),
        "asks": _norm({a["ID"]: asks.get(a["ID"], 0) for a in areas}),
    }
    rows = []
    for a in areas:
        aid = a["ID"]
        crit = ((a["CRITICALITY"] or 2) - 1) / 2.0
        evidence = sum(s[aid] for s in signals.values()) / len(signals)
        importance = min(1.0, 0.4 * crit + 0.6 * evidence)
        # "Doing > talking" (same rule as keepline.products._common.is_strong): a strong holder also has
        # hands-on evidence -- closed tickets or a body of stated facts -- not just chatter about the area.
        strong = [e for e in expertise.get(aid, []) if e["SCORE"] >= STRONG
                  and ((e.get("N_TICKETS_CLOSED") or 0) >= 2 or (e.get("N_FACTS_STATED") or 0) >= 8)]
        bf = len(strong)
        red = redundancy(bf)
        at_risk, dl, countdown = None, 1.0, None
        if strong:
            # the holder whose departure hurts most: likelihood weighted by their share of the evidence
            top_score = max(e["SCORE"] for e in strong) or 1.0

            def weighted(e):
                pp = people[e["PERSON_ID"]]
                return departure_likelihood(pp["DEPARTURE_DATE"], pp["DEPARTURE_TYPE"], today) * e["SCORE"] / top_score

            top = max(strong, key=lambda e: (weighted(e), e["SCORE"]))
            p = people[top["PERSON_ID"]]
            at_risk = top["PERSON_ID"]
            dl = weighted(top)
            countdown = (p["DEPARTURE_DATE"] - today).days if p["DEPARTURE_DATE"] else None
        risk = importance * (1 - red) * dl
        n_facts = fact_counts.get(aid, {}).get("N_FACTS", 0)
        n_landmines = fact_counts.get(aid, {}).get("N_LANDMINES", 0)
        if bf == 0:
            explanation = f"Nobody left with strong evidence in {a['NAME']}. {n_facts} facts, {n_landmines} landmines on record."
        elif bf == 1:
            e = strong[0]
            explanation = (f"Only {people[e['PERSON_ID']]['NAME']} has strong evidence in {a['NAME']}: "
                           f"{e['N_DOCS']} messages, {e['N_TICKETS_CLOSED']} closed tickets.")
        else:
            explanation = f"{bf} people have strong evidence in {a['NAME']}."
        if countdown is not None and at_risk:
            explanation += f" {people[at_risk]['NAME']}'s last day is in {countdown} days."
        rows.append((aid, a["NAME"], round(importance, 4), round(red, 4), round(dl, 4), round(risk, 4), bf,
                     at_risk, countdown, n_facts, n_landmines, explanation))
    rows.sort(key=lambda r: -r[5])
    return rows


def run(session, today, exclude_person):
    from snowflake.snowpark.types import FloatType, LongType, StringType, StructField, StructType

    today = today or date.today()
    rows = score(session, today, exclude_person or None)
    # Explicit schema: columns that are NULL in every row (e.g. no countdown) must still type-check.
    schema = StructType([
        StructField("AREA_ID", StringType()), StructField("AREA_NAME", StringType()),
        StructField("IMPORTANCE", FloatType()), StructField("REDUNDANCY", FloatType()),
        StructField("DEPARTURE_LIKELIHOOD", FloatType()), StructField("RISK", FloatType()),
        StructField("BUS_FACTOR", LongType()), StructField("AT_RISK_PERSON_ID", StringType()),
        StructField("COUNTDOWN_DAYS", LongType()), StructField("N_FACTS", LongType()),
        StructField("N_LANDMINES", LongType()), StructField("EXPLANATION", StringType()),
    ])
    return session.create_dataframe(rows, schema=schema)
$$;

-- Baseline snapshot + one what-if per person with a known future departure. Cortex Analyst reads this.
CREATE OR REPLACE PROCEDURE APP.REFRESH_RISK_SNAPSHOT(TODAY DATE)
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS
$$
DECLARE
  d DATE DEFAULT COALESCE(TODAY, APP.KEEPLINE_TODAY());
  c1 CURSOR FOR SELECT id FROM KEEPLINE.CORE.PEOPLE WHERE departure_date IS NOT NULL;
BEGIN
  DELETE FROM APP.AREA_RISK_SNAPSHOT WHERE snapshot_date = :d;
  CALL APP.RISK_MAP(:d, NULL);
  INSERT INTO APP.AREA_RISK_SNAPSHOT
    SELECT :d, area_id, area_name, importance, redundancy, departure_likelihood, risk, bus_factor,
           at_risk_person_id, countdown_days, n_facts, n_landmines, explanation, NULL
    FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
  FOR p IN c1 DO
    LET pid STRING := p.id;
    CALL APP.RISK_MAP(:d, :pid);
    INSERT INTO APP.AREA_RISK_SNAPSHOT
      SELECT :d, area_id, area_name, importance, redundancy, departure_likelihood, risk, bus_factor,
             at_risk_person_id, countdown_days, n_facts, n_landmines, explanation, :pid
      FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
  END FOR;
  RETURN 'risk snapshot refreshed for ' || :d;
END;
$$;

CREATE OR REPLACE TASK APP.T_NIGHTLY_RISK
  WAREHOUSE = KEEPLINE_WH
  SCHEDULE = 'USING CRON 0 6 * * * America/Halifax'
  COMMENT = 'Keepline: nightly risk-map snapshot (feeds the month-over-month trend).'
AS
  CALL APP.REFRESH_RISK_SNAPSHOT(NULL);

-- -------------------------------------------------------------------------------------------------
-- Handoff pack
-- -------------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE APP.HANDOFF_PACK(PERSON_ID STRING, TODAY DATE)
  RETURNS VARIANT
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python')
  HANDLER = 'run'
  COMMENT = 'Keepline handoff pack for a departing person. Every item carries receipts. Never includes secrets.'
  EXECUTE AS OWNER
AS
$$
import json
import re
from datetime import date, datetime

SECTION_BY_KIND = {
    "access": "access", "owner": "access", "vendor_contact": "vendor_contacts",
    "recurring_task": "recurring_tasks", "landmine": "landmines", "procedure": "procedures", "decision": "decisions",
}
FOLLOWUP = re.compile(r"\bI(?:'ll| will)\b[^.?!]{0,80}\b(monday|tuesday|wednesday|thursday|friday|tomorrow|next week|by \w+)",
                      re.IGNORECASE)
HAS_REASON = re.compile(r"\b(because|so that|since|due to|otherwise|reason)\b", re.IGNORECASE)


def _q(session, sql, params=None):
    return [r.as_dict() for r in session.sql(sql, params=params).collect()]


def _citations(session, doc_ids):
    if not doc_ids:
        return []
    rows = _q(session, """
        SELECT id, author_id, TO_VARCHAR(ts, 'YYYY-MM-DD"T"HH24:MI:SS') AS ts, url, LEFT(text, 280) AS quote
        FROM KEEPLINE.CORE.DOCUMENTS WHERE ARRAY_CONTAINS(id::VARIANT, PARSE_JSON(?))""", [json.dumps(doc_ids)])
    return [{"doc_id": r["ID"], "author_id": r["AUTHOR_ID"], "timestamp": r["TS"], "url": r["URL"], "quote": r["QUOTE"]}
            for r in rows]


def _suggested_owner(session, area_id, person_id):
    """Next-best expert; prefer a learner (0.2-0.5) paired with the strongest remaining reviewer. Humans approve."""
    rows = _q(session, """SELECT person_id, score FROM KEEPLINE.CORE.EXPERTISE
                          WHERE area_id = ? AND person_id <> ? AND enough_data ORDER BY score DESC""", [area_id, person_id])
    if not rows:
        return None, None
    learners = [r for r in rows if 0.2 <= r["SCORE"] < 0.5]
    owner = learners[0] if learners else rows[0]
    reviewer = next((r for r in rows if r["PERSON_ID"] != owner["PERSON_ID"]), None)
    return owner["PERSON_ID"], reviewer["PERSON_ID"] if reviewer else None


def run(session, person_id, today):
    today = today or date.today()
    person = _q(session, "SELECT * FROM KEEPLINE.CORE.PEOPLE WHERE id = ?", [person_id])
    if not person:
        return {"error": f"unknown person {person_id}"}
    items, gaps = [], []
    facts = _q(session, """
        SELECT id, text, kind, area_id, source_doc_ids_json, quote, epistemic
        FROM KEEPLINE.CORE.FACTS
        WHERE stated_by = ? AND valid_to IS NULL AND superseded_by IS NULL AND review_status <> 'rejected'
        ORDER BY kind, area_id""", [person_id])
    owners = {}
    for f in facts:
        raw_ids = f["SOURCE_DOC_IDS_JSON"]
        doc_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else (raw_ids or [])
        area = f["AREA_ID"]
        if area not in owners:
            owners[area] = _suggested_owner(session, area, person_id)
        items.append({
            "section": SECTION_BY_KIND.get(f["KIND"], "key_facts"), "title": f["TEXT"][:90], "detail": f["TEXT"],
            "area_id": area, "fact_ids": [f["ID"]], "citations": _citations(session, doc_ids),
            "suggested_owner_id": owners[area][0], "reviewer_id": owners[area][1], "status": "pending_review"})
        if f["KIND"] in ("decision", "landmine") and not HAS_REASON.search(f["TEXT"] + " " + (f["QUOTE"] or "")):
            gaps.append({"person_id": person_id, "area_id": area, "fact_ids": [f["ID"]],
                         "question": f"Why? \"{f['TEXT']}\" - what breaks if this is ignored?",
                         "reason": f"{f['KIND']} with no recorded reason", "priority": 0.8})
        elif len(doc_ids) == 1:
            gaps.append({"person_id": person_id, "area_id": area, "fact_ids": [f["ID"]],
                         "question": f"Is this still true, and where is it written down? \"{f['TEXT']}\"",
                         "reason": "single-receipt fact", "priority": 0.4})

    # Unresolved work: open tickets assigned to them + promised follow-ups in their recent messages.
    for t in _q(session, """
        SELECT id, title, area_id FROM KEEPLINE.CORE.DOCUMENTS
        WHERE source_type = 'ticket' AND ticket_assignee = ?
          AND COALESCE(LOWER(ticket_status), 'open') NOT IN ('closed', 'done', 'resolved')""", [person_id]):
        items.append({"section": "unresolved_work", "title": f"Open ticket: {t['TITLE']}", "detail": t["TITLE"],
                      "area_id": t["AREA_ID"], "fact_ids": [], "citations": _citations(session, [t["ID"]]),
                      "suggested_owner_id": owners.get(t["AREA_ID"], (None,))[0], "status": "pending_review"})
    for m in _q(session, """
        SELECT id, text, area_id FROM KEEPLINE.CORE.DOCUMENTS
        WHERE author_id = ? AND ts >= DATEADD('day', -30, ?::DATE)""", [person_id, today.isoformat()]):
        hit = FOLLOWUP.search(m["TEXT"] or "")
        if hit:
            items.append({"section": "unresolved_work", "title": "Promised follow-up",
                          "detail": m["TEXT"][max(0, hit.start() - 40): hit.end() + 40], "area_id": m["AREA_ID"],
                          "fact_ids": [], "citations": _citations(session, [m["ID"]]), "status": "pending_review"})

    # Areas where the agent had to abstain or route: the questions nobody could answer from the record.
    for r in _q(session, """
        SELECT area_id, COUNT(*) AS n FROM KEEPLINE.CORE.QUERY_LOG
        WHERE action IN ('abstain', 'route') AND ARRAY_CONTAINS(?::VARIANT, route_to_json) GROUP BY area_id""", [person_id]):
        gaps.append({"person_id": person_id, "area_id": r["AREA_ID"], "fact_ids": [],
                     "question": f"Colleagues asked about {r['AREA_ID']} {r['N']} times and we had no receipt. What should they know?",
                     "reason": f"agent abstained/routed {r['N']}x", "priority": min(1.0, 0.5 + 0.1 * r["N"])})

    gaps.sort(key=lambda g: -g["priority"])
    p = person[0]
    return {
        "person_id": person_id, "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "last_day": p["DEPARTURE_DATE"].isoformat() if p.get("DEPARTURE_DATE") else None,
        "items": items, "gaps": gaps[:8], "signed_off": False,
    }
$$;

GRANT USAGE ON PROCEDURE APP.RISK_MAP(DATE, STRING)        TO ROLE KEEPLINE_APP;
GRANT USAGE ON PROCEDURE APP.HANDOFF_PACK(STRING, DATE)    TO ROLE KEEPLINE_APP;
GRANT USAGE ON PROCEDURE APP.REFRESH_RISK_SNAPSHOT(DATE)   TO ROLE KEEPLINE_ADMIN;

-- Examples:
--   CALL APP.RISK_MAP('2026-09-04'::DATE, NULL);          -- today's risk map
--   CALL APP.RISK_MAP('2026-09-04'::DATE, 'sarah');       -- what if Sarah leaves?
--   CALL APP.HANDOFF_PACK('sarah', '2026-09-04'::DATE);   -- Sarah's handoff pack (VARIANT)
--   CALL APP.REFRESH_RISK_SNAPSHOT('2026-09-04'::DATE);
